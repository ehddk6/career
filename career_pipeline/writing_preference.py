"""Privacy-preserving revealed writing-preference memory.

The profile learns *how* the user tends to prefer prose, not factual content.
Only aggregate structural/style metrics are persisted; winner/loser text is
never written to the profile. This lets outputs from Claude, Gemini, GPT, or a
human editor teach the GPT drafting path without importing their facts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import re
from statistics import mean, pstdev
from typing import Any, Mapping


SCHEMA_VERSION = 1
_SENTENCE = re.compile(r"[^.!?…。\n]+(?:[.!?…。]+|$)")
_ENDING = re.compile(r"([가-힣A-Za-z]+(?:했습니다|하겠습니다|합니다|됩니다|입니다|습니다|했다|한다|된다|이다))$")
_CONNECTORS = ("이를 통해", "또한", "따라서", "특히", "그리고", "하지만", "그러나", "먼저", "둘째", "셋째")
_BUREAUCRATIC = ("확인", "대조", "기록", "보고", "점검", "검토", "처리", "절차", "기준에 따라")
_ABSTRACT_PROMISES = (
    "기여하겠습니다", "노력하겠습니다", "최선을 다하겠습니다", "성장하겠습니다",
    "역량을 발휘", "할 수 있습니다", "도움이 되겠습니다",
)
_FIRST_PERSON_START = re.compile(r"^\s*(저는|제가|저의|저에게)")
FEATURES = (
    "avg_sentence_chars",
    "sentence_length_cv",
    "ending_diversity_ratio",
    "connector_density",
    "bureaucratic_density",
    "abstract_promise_density",
    "first_person_start_ratio",
    "long_sentence_ratio",
    "short_sentence_ratio",
    "paragraph_count",
)


def _sentences(text: str) -> list[str]:
    result: list[str] = []
    for match in _SENTENCE.finditer(text):
        sentence = match.group(0).strip().rstrip(".!?…。 ")
        if sentence:
            result.append(sentence)
    return result


def style_fingerprint(text: str) -> dict[str, float]:
    sentences = _sentences(text)
    lengths = [len(re.sub(r"\s+", "", sentence)) for sentence in sentences]
    count = max(1, len(sentences))
    avg_len = mean(lengths) if lengths else 0.0
    cv = (pstdev(lengths) / avg_len) if len(lengths) >= 2 and avg_len else 0.0
    endings: list[str] = []
    for sentence in sentences:
        match = _ENDING.search(sentence)
        if match:
            endings.append(match.group(1)[-6:])
        elif sentence:
            endings.append(sentence[-4:])
    ending_diversity = len(set(endings)) / max(1, len(endings))
    connector_hits = sum(text.count(item) for item in _CONNECTORS)
    bureaucratic_hits = sum(text.count(item) for item in _BUREAUCRATIC)
    abstract_hits = sum(text.count(item) for item in _ABSTRACT_PROMISES)
    first_person_starts = sum(bool(_FIRST_PERSON_START.search(item)) for item in sentences)
    paragraphs = [item for item in re.split(r"\n\s*\n|\n", text) if item.strip()]
    return {
        "avg_sentence_chars": float(round(avg_len, 4)),
        "sentence_length_cv": round(cv, 4),
        "ending_diversity_ratio": round(ending_diversity, 4),
        "connector_density": round(connector_hits / count, 4),
        "bureaucratic_density": round(bureaucratic_hits / count, 4),
        "abstract_promise_density": round(abstract_hits / count, 4),
        "first_person_start_ratio": round(first_person_starts / count, 4),
        "long_sentence_ratio": round(sum(length >= 60 for length in lengths) / count, 4),
        "short_sentence_ratio": round(sum(length <= 25 for length in lengths) / count, 4),
        "paragraph_count": float(max(1, len(paragraphs))),
    }


def _empty_profile() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "comparison_count": 0,
        "updated_at": None,
        "winner_sums": {feature: 0.0 for feature in FEATURES},
        "delta_sums": {feature: 0.0 for feature in FEATURES},
        "winner_labels": {},
        "loser_labels": {},
        "targets": {},
        "deltas": {},
        "directives": [],
        "privacy": {
            "stores_source_text": False,
            "stores_applicant_facts": False,
            "purpose": "surface-style preference only",
        },
    }


def _require_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    if int(value.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("unsupported writing preference profile schema")
    result = _empty_profile()
    result.update(dict(value))
    for key in ("winner_sums", "delta_sums"):
        current = value.get(key, {})
        if not isinstance(current, Mapping):
            raise ValueError(f"invalid preference profile {key}")
        result[key] = {feature: float(current.get(feature, 0.0)) for feature in FEATURES}
    for key in ("winner_labels", "loser_labels"):
        current = value.get(key, {})
        result[key] = dict(current) if isinstance(current, Mapping) else {}
    result["comparison_count"] = int(value.get("comparison_count", 0))
    return result


def load_preference_profile(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("writing preference profile must be a JSON object")
    return _require_profile(payload)


def _directives(targets: Mapping[str, float], deltas: Mapping[str, float]) -> list[str]:
    directives: list[tuple[float, str]] = []

    def add(feature: str, threshold: float, positive: str, negative: str) -> None:
        delta = float(deltas.get(feature, 0.0))
        if abs(delta) < threshold:
            return
        directives.append((abs(delta) / threshold, positive if delta > 0 else negative))

    add(
        "avg_sentence_chars", 3.0,
        "선호 답변은 평균 문장이 더 길다. 한 문장 안에서 생각의 인과를 충분히 이어가되 과밀하게 만들지 않는다.",
        "선호 답변은 평균 문장이 더 짧다. 한 문장에 한 판단만 남기고 군더더기를 줄인다.",
    )
    add(
        "sentence_length_cv", 0.06,
        "선호 답변은 장단문 리듬 변화가 더 크다. 핵심 문장은 짧게, 설명 문장은 필요한 만큼 길게 쓴다.",
        "선호 답변은 문장 길이가 더 안정적이다. 과도한 장단문 대비를 만들지 않는다.",
    )
    add(
        "ending_diversity_ratio", 0.08,
        "선호 답변은 종결 리듬이 더 다양하다. 같은 어미가 연속되지 않게 자연스럽게 변주한다.",
        "선호 답변은 종결 방식이 더 절제되어 있다. 억지로 어미를 다양화하지 않는다.",
    )
    add(
        "connector_density", 0.08,
        "선호 답변은 명시적 연결어를 더 자주 쓴다. 논리 전환이 필요한 곳에만 사용한다.",
        "선호 답변은 '또한/따라서/이를 통해' 같은 표지어가 적다. 문장 의미 자체로 흐름을 연결한다.",
    )
    add(
        "bureaucratic_density", 0.12,
        "선호 답변은 절차·통제 동사를 더 구체적으로 사용한다. 단, 업무 매뉴얼처럼 나열하지 않는다.",
        "선호 답변은 확인·대조·기록·보고 같은 관공서식 동사 연쇄가 적다. 장면·판단·행동의 구체성을 우선한다.",
    )
    add(
        "abstract_promise_density", 0.05,
        "선호 답변은 미래 지향 문장이 조금 더 많다. 추상적 다짐 대신 구체 행동으로 표현한다.",
        "선호 답변은 '기여하겠습니다/노력하겠습니다' 같은 추상적 다짐이 적다. 마지막도 행동이나 판단 기준으로 끝낸다.",
    )
    add(
        "first_person_start_ratio", 0.08,
        "선호 답변은 1인칭 주어를 더 명확히 쓴다. 책임 주체가 필요한 문장에만 사용한다.",
        "선호 답변은 '저는/제가'로 시작하는 문장이 적다. 주어를 반복하지 않아도 책임 주체가 드러나게 쓴다.",
    )
    add(
        "long_sentence_ratio", 0.10,
        "선호 답변은 긴 설명 문장을 일부 허용한다. 긴 문장에는 하나의 인과 축만 유지한다.",
        "선호 답변은 긴 문장 비율이 낮다. 관형절과 병렬 나열을 분리한다.",
    )
    add(
        "short_sentence_ratio", 0.10,
        "선호 답변은 짧은 강조 문장을 더 활용한다. 핵심 판단이나 전환에만 쓴다.",
        "선호 답변은 지나치게 끊어 쓰지 않는다. 짧은 문장을 연속해 메모처럼 만들지 않는다.",
    )
    paragraph_target = float(targets.get("paragraph_count", 0.0))
    if paragraph_target >= 2.5:
        directives.append((1.0, "선호 답변은 의미 단위가 바뀔 때 문단을 나눈다. 문항 형식이 허용하면 2~3개의 자연스러운 문단을 사용한다."))
    return [text for _, text in sorted(directives, key=lambda item: item[0], reverse=True)[:6]]


def _refresh_derived(profile: dict[str, Any]) -> dict[str, Any]:
    count = max(1, int(profile.get("comparison_count", 0)))
    targets = {
        feature: round(float(profile["winner_sums"].get(feature, 0.0)) / count, 4)
        for feature in FEATURES
    }
    deltas = {
        feature: round(float(profile["delta_sums"].get(feature, 0.0)) / count, 4)
        for feature in FEATURES
    }
    profile["targets"] = targets
    profile["deltas"] = deltas
    profile["directives"] = _directives(targets, deltas)
    return profile


def record_preference(
    profile_path: Path,
    *,
    winner_text: str,
    loser_text: str,
    winner_label: str = "",
    loser_label: str = "",
) -> dict[str, Any]:
    profile_path = profile_path.resolve()
    profile = load_preference_profile(profile_path) or _empty_profile()
    winner = style_fingerprint(winner_text)
    loser = style_fingerprint(loser_text)
    profile["comparison_count"] = int(profile.get("comparison_count", 0)) + 1
    for feature in FEATURES:
        profile["winner_sums"][feature] = float(profile["winner_sums"].get(feature, 0.0)) + winner[feature]
        profile["delta_sums"][feature] = float(profile["delta_sums"].get(feature, 0.0)) + winner[feature] - loser[feature]
    if winner_label:
        labels = Counter({str(key): int(value) for key, value in profile.get("winner_labels", {}).items()})
        labels[winner_label] += 1
        profile["winner_labels"] = dict(labels)
    if loser_label:
        labels = Counter({str(key): int(value) for key, value in profile.get("loser_labels", {}).items()})
        labels[loser_label] += 1
        profile["loser_labels"] = dict(labels)
    profile["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _refresh_derived(profile)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile


def preference_directives(profile: Mapping[str, Any] | None) -> list[str]:
    if not profile:
        return [
            "정확성 때문에 문장이 관공서 보고서처럼 굳지 않게 한다.",
            "장면·판단·행동이 자연스럽게 이어지는 한국어 산문을 쓴다.",
            "지원자가 실제 면접에서 말할 수 있는 어휘와 호흡을 유지한다.",
        ]
    values = profile.get("directives", [])
    return [str(item) for item in values if str(item).strip()]


def preference_distance(text: str, profile: Mapping[str, Any] | None) -> float:
    if not profile or int(profile.get("comparison_count", 0)) < 1:
        return 0.0
    targets = profile.get("targets", {})
    if not isinstance(targets, Mapping):
        return 0.0
    actual = style_fingerprint(text)
    scales = {
        "avg_sentence_chars": 20.0,
        "sentence_length_cv": 0.35,
        "ending_diversity_ratio": 0.5,
        "connector_density": 0.5,
        "bureaucratic_density": 0.7,
        "abstract_promise_density": 0.3,
        "first_person_start_ratio": 0.4,
        "long_sentence_ratio": 0.4,
        "short_sentence_ratio": 0.4,
        "paragraph_count": 2.0,
    }
    weighted = 0.0
    weight_total = 0.0
    deltas = profile.get("deltas", {}) if isinstance(profile.get("deltas"), Mapping) else {}
    for feature in FEATURES:
        if feature not in targets:
            continue
        # Features that actually separated chosen/rejected examples matter more.
        learned_weight = 1.0 + min(2.0, abs(float(deltas.get(feature, 0.0))) / max(1e-6, scales[feature]))
        weighted += learned_weight * abs(actual[feature] - float(targets[feature])) / scales[feature]
        weight_total += learned_weight
    return round(weighted / max(1e-6, weight_total), 6)


def render_profile(profile: Mapping[str, Any]) -> str:
    lines = [
        "# Writing Preference Profile",
        "",
        f"- comparisons: {profile.get('comparison_count', 0)}",
        f"- updated_at: {profile.get('updated_at') or '없음'}",
        "- raw source text stored: no",
        "",
        "## Learned directives",
        "",
    ]
    directives = preference_directives(profile)
    lines.extend(f"- {item}" for item in directives)
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Learn privacy-preserving writing preferences from pairwise choices")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--profile", required=True, type=Path)
    record.add_argument("--winner", required=True, type=Path)
    record.add_argument("--loser", required=True, type=Path)
    record.add_argument("--winner-label", default="")
    record.add_argument("--loser-label", default="")
    show = sub.add_parser("show")
    show.add_argument("--profile", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "record":
        profile = record_preference(
            args.profile,
            winner_text=args.winner.read_text(encoding="utf-8"),
            loser_text=args.loser.read_text(encoding="utf-8"),
            winner_label=args.winner_label,
            loser_label=args.loser_label,
        )
        print(render_profile(profile), end="")
        return 0
    profile = load_preference_profile(args.profile)
    if profile is None:
        raise FileNotFoundError(args.profile)
    print(render_profile(profile), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
