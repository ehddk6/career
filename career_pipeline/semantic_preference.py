"""Semantic revealed-preference memory for self-introduction arguments.

The user supplies the winner/loser label. A model may explain which fixed
argument dimensions differ, but it cannot reverse the user's preference.
Raw source text is never persisted.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
import argparse
import json
import subprocess
import tempfile

from .argument_search import DIMENSION_LABELS, SEMANTIC_DIMENSIONS
from .copyeditor_adapter import _resolved_codex_command
from .model_policy import resolve_model

ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]
SCHEMA_VERSION = 1

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dimensions"],
    "properties": {
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "preference", "confidence"],
                "properties": {
                    "dimension": {"type": "string", "enum": list(SEMANTIC_DIMENSIONS)},
                    "preference": {"type": "string", "enum": ["winner", "loser", "tie"]},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 4},
                },
            },
        }
    },
}

def _empty() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "comparison_count": 0,
        "updated_at": None,
        "dimensions": {
            dim: {"winner": 0.0, "loser": 0.0, "tie": 0.0}
            for dim in SEMANTIC_DIMENSIONS
        },
        "provider_winners": {},
        "provider_losers": {},
        "weights": {dim: 1.0 for dim in SEMANTIC_DIMENSIONS},
        "directives": [],
        "privacy": {"stores_source_text": False, "stores_applicant_facts": False},
    }

def load_semantic_preference(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or int(value.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("invalid semantic preference profile")
    result = _empty()
    result.update(dict(value))
    return result

def _refresh(profile: dict[str, Any]) -> None:
    weights = {}
    ranked = []
    for dim in SEMANTIC_DIMENSIONS:
        row = profile["dimensions"].get(dim, {})
        win = float(row.get("winner", 0.0))
        lose = float(row.get("loser", 0.0))
        total = win + lose
        signed = (win - lose) / (total + 2.0)
        confidence = min(1.0, total / 8.0)
        weight = max(0.75, min(1.35, 1.0 + 0.30 * signed * confidence))
        weights[dim] = round(weight, 4)
        if total:
            ranked.append((abs(weight - 1.0), dim, weight))
    profile["weights"] = weights
    profile["directives"] = [
        (
            f"사용자는 '{DIMENSION_LABELS[dim]}'을 상대적으로 더 중시한다."
            if weight > 1.0 else
            f"사용자는 '{DIMENSION_LABELS[dim]}'을 과도하게 최적화하는 것을 선호하지 않는다."
        )
        for _, dim, weight in sorted(ranked, reverse=True)[:5]
        if abs(weight - 1.0) >= 0.01
    ]

def record_semantic_preference(
    path: Path,
    verdicts: list[Mapping[str, Any]],
    *,
    winner_label: str = "",
    loser_label: str = "",
) -> dict[str, Any]:
    profile = load_semantic_preference(path) or _empty()
    seen = set()
    for verdict in verdicts:
        dim = str(verdict.get("dimension", ""))
        pref = str(verdict.get("preference", ""))
        confidence = verdict.get("confidence")
        if dim not in SEMANTIC_DIMENSIONS or dim in seen:
            raise ValueError("invalid or duplicate semantic dimension")
        if pref not in {"winner", "loser", "tie"}:
            raise ValueError("invalid semantic preference")
        if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 4:
            raise ValueError("confidence must be 0..4")
        seen.add(dim)
        profile["dimensions"][dim][pref] = float(profile["dimensions"][dim].get(pref, 0.0)) + confidence / 4.0
    if seen != set(SEMANTIC_DIMENSIONS):
        raise ValueError("every semantic dimension must be classified")
    profile["comparison_count"] = int(profile.get("comparison_count", 0)) + 1
    if winner_label:
        c = Counter({str(k): int(v) for k, v in profile.get("provider_winners", {}).items()})
        c[winner_label] += 1; profile["provider_winners"] = dict(c)
    if loser_label:
        c = Counter({str(k): int(v) for k, v in profile.get("provider_losers", {}).items()})
        c[loser_label] += 1; profile["provider_losers"] = dict(c)
    profile["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _refresh(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile

def semantic_preference_weights(profile: Mapping[str, Any] | None) -> dict[str, float]:
    if not profile:
        return {dim: 1.0 for dim in SEMANTIC_DIMENSIONS}
    values = profile.get("weights", {})
    return {dim: float(values.get(dim, 1.0)) for dim in SEMANTIC_DIMENSIONS}

def semantic_preference_directives(profile: Mapping[str, Any] | None) -> list[str]:
    if not profile:
        return []
    return [str(x) for x in profile.get("directives", []) if str(x).strip()]

def _runner(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="career-semantic-pref-") as temp:
        root = Path(temp)
        schema = root / "schema.json"
        schema.write_text(json.dumps(_SCHEMA, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            _resolved_codex_command(root, schema, resolve=True, model_id=model_id),
            input=prompt, text=True, encoding="utf-8", capture_output=True,
            timeout=max(1, timeout_ms // 1000 + 30),
        )
    if completed.returncode:
        raise ValueError("semantic preference evaluator failed")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("semantic preference evaluator returned non-object")
    return value

def compare_and_record(
    path: Path,
    *,
    winner_text: str,
    loser_text: str,
    model_id: str,
    winner_label: str = "",
    loser_label: str = "",
    timeout_ms: int = 180_000,
    runner: ModelRunner = _runner,
) -> dict[str, Any]:
    prompt = (
        "The user has already chosen WINNER over LOSER. Do not judge or reverse that choice. "
        "For each fixed semantic dimension, classify whether WINNER demonstrates more of the "
        "desired property, LOSER does, or they tie. Confidence is 0..4. Analyze argument "
        "quality rather than provider identity. JSON only.\n"
        + json.dumps({
            "rubric": DIMENSION_LABELS,
            "WINNER": winner_text,
            "LOSER": loser_text,
        }, ensure_ascii=False)
    )
    raw = runner("semantic_preference_compare", prompt, model_id, timeout_ms)
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, Mapping) or not isinstance(raw.get("dimensions"), list):
        raise ValueError("invalid semantic comparison")
    return record_semantic_preference(
        path, list(raw["dimensions"]),
        winner_label=winner_label, loser_label=loser_label,
    )

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record revealed semantic writing preferences")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--profile", type=Path, required=True)
    record.add_argument("--winner", type=Path, required=True)
    record.add_argument("--loser", type=Path, required=True)
    record.add_argument("--winner-label", default="")
    record.add_argument("--loser-label", default="")
    record.add_argument("--model-id")
    record.add_argument("--timeout-ms", type=int, default=180_000)
    show = sub.add_parser("show")
    show.add_argument("--profile", type=Path, required=True)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "show":
        print(json.dumps(load_semantic_preference(args.profile), ensure_ascii=False, indent=2))
        return 0
    model = args.model_id or resolve_model("sol").model_id
    if not model:
        raise ValueError("record requires --model-id or CAREER_MODEL_SOL")
    profile = compare_and_record(
        args.profile,
        winner_text=args.winner.read_text(encoding="utf-8"),
        loser_text=args.loser.read_text(encoding="utf-8"),
        model_id=model,
        winner_label=args.winner_label,
        loser_label=args.loser_label,
        timeout_ms=args.timeout_ms,
    )
    print(json.dumps({"comparison_count": profile["comparison_count"], "weights": profile["weights"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
