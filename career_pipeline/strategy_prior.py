"""Compile strategy-only priors for Evidence-to-Argument Search.

Facts remain authoritative only in the confirmed experience ledger, posting,
and official research. YouTube guidance, legacy writing strategy, historical
application metadata and outcomes may influence structure/selection only.
Raw historical self-introduction prose is never forwarded to the writer.
"""
from __future__ import annotations

from collections import Counter
import csv
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
POLICY = "strategy_only_never_factual_authority"
TARGET_ALIASES = {
    "신용보증기금": ("신용보증기금", "KODIT", "신보"),
    "한국주택금융공사": ("한국주택금융공사", "주택금융공사", "HF"),
    "주택도시보증공사": ("주택도시보증공사", "HUG"),
}
TARGET_GROUPS = {
    "신용보증기금": ("보증/기금/HUG",),
    "한국주택금융공사": ("보증/기금/HUG",),
    "주택도시보증공사": ("보증/기금/HUG",),
}
OUTCOME_DIMENSIONS = {
    "job_competency", "motivation", "culture_fit", "organization_interest",
    "product_understanding", "document_hygiene", "question_differentiation",
    "fact_ownership", "interview_defense",
}


def _json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _target_terms(target: str) -> tuple[str, ...]:
    normalized = _norm(target)
    terms = {_norm(target)} if target.strip() else set()
    matched = False
    for anchor, aliases in TARGET_ALIASES.items():
        if _norm(anchor) in normalized or any(_norm(x) in normalized for x in aliases):
            matched = True
            terms.update(_norm(x) for x in aliases)
    if target.strip() and not matched:
        terms.update(_norm(x) for x in re.findall(r"[가-힣A-Za-z]{3,}", target))
    return tuple(sorted((x for x in terms if len(x) >= 2), key=lambda x: (-len(x), x)))


def _group_terms(target: str) -> tuple[str, ...]:
    normalized = _norm(target)
    terms: set[str] = set()
    for anchor, groups in TARGET_GROUPS.items():
        aliases = TARGET_ALIASES.get(anchor, (anchor,))
        if _norm(anchor) in normalized or any(_norm(x) in normalized for x in aliases):
            terms.update(_norm(x) for x in groups)
    return tuple(sorted(terms, key=lambda x: (-len(x), x)))


def _bullets(path: Path, limit: int = 18) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    result: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith(("- ", "* ", "• ")):
            text = _compact(line[2:])
        elif re.match(r"^\d+[.)]\s+", line):
            text = _compact(re.sub(r"^\d+[.)]\s+", "", line))
        else:
            continue
        if text and len(text) <= 320:
            result.append(text)
        if len(result) >= limit:
            break
    return list(dict.fromkeys(result))


def _guidance_dir(root: Path, state: Mapping[str, Any]) -> Path | None:
    guidance = state.get("writing_guidance")
    if isinstance(guidance, Mapping):
        source = str(guidance.get("source_dir", "")).strip()
        if source and (root / source).is_dir():
            return root / source
    base = root / "자료조사"
    if not base.is_dir():
        return None
    choices = [x for x in base.glob("자소서_유튜브_프레임분석_*") if x.is_dir()]
    return max(choices, key=lambda x: (x.stat().st_mtime, x.name)) if choices else None


def _freshness(source_dir: Path | None) -> dict[str, Any]:
    if source_dir is None:
        return {"status": "missing"}
    configured = os.environ.get("CAREER_YOUTUBE_GUIDANCE_ROOT", "").strip()
    external = Path(configured).expanduser() if configured else Path.home() / "OneDrive" / "문서" / "자소서 유튜브 정보"

    def latest(paths: Sequence[Path]) -> float | None:
        values: list[float] = []
        for path in paths:
            try:
                if path.is_file():
                    values.append(path.stat().st_mtime)
                elif path.is_dir():
                    values.extend(x.stat().st_mtime for x in path.rglob("*") if x.is_file())
            except OSError:
                pass
        return max(values) if values else None

    imported = latest([source_dir])
    ext = latest([external / "captures_manifest.csv", external / "playlist.json", external / "progress.json", external / "analyses"])
    status = "external_source_unavailable" if ext is None else "imported_snapshot_unavailable" if imported is None else "stale" if ext > imported else "fresh"
    return {"status": status, "external_root": str(external), "external_available": ext is not None}


def _target_youtube(source_dir: Path | None, target: str) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "source_unavailable" if source_dir is None else "no_match", "target": target, "use_policy": POLICY, "matches": []}
    if source_dir is None or not (source_dir / "04_프레임_근거색인.csv").is_file():
        return result
    terms, groups = _target_terms(target), _group_terms(target)
    rows: list[dict[str, Any]] = []
    try:
        with (source_dir / "04_프레임_근거색인.csv").open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            for row in csv.DictReader(stream):
                title = _norm(row.get("title", ""))
                companies = {_norm(x) for x in (row.get("companies") or "").split(";") if x.strip()}
                group_text = _norm(row.get("company_groups", ""))
                title_match = any(x in title for x in terms)
                company_match = any(x in companies for x in terms)
                group_match = any(x in group_text for x in groups)
                if not (title_match or company_match or group_match):
                    continue
                try:
                    score = int(float(row.get("score") or 0))
                except (TypeError, ValueError):
                    score = 0
                rows.append({
                    "video_id": _compact(row.get("video_id", "")),
                    "title": _compact(row.get("title", "")),
                    "match_type": "title_direct" if title_match else "company_tag" if company_match else "institution_group",
                    "question_types": [x.strip() for x in (row.get("question_types") or "").split(";") if x.strip()],
                    "strategy_excerpt": _compact(row.get("key_lines", ""))[:260],
                    "score": score,
                })
    except (OSError, csv.Error, UnicodeError):
        return result
    priority = {"title_direct": 0, "company_tag": 1, "institution_group": 2}
    rows.sort(key=lambda x: (priority[x["match_type"]], -int(x["score"]), str(x["video_id"])))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row["video_id"]), str(row["strategy_excerpt"]))
        if key not in seen:
            seen.add(key); deduped.append(row)
        if len(deduped) >= 8:
            break
    result.update(status="matched" if deduped else "no_match", matches=deduped)
    return result


def _question_strategy(run_dir: Path) -> dict[int, list[str]]:
    payload = _json(run_dir / "05_문항전략.json", {})
    result: dict[int, list[str]] = {}
    rows = payload.get("questions") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        index = row.get("question_index", row.get("index"))
        if not isinstance(index, int):
            continue
        values: list[str] = []
        for key in ("direct_answer_requirement", "answer_strategy", "writing_strategy", "focus", "avoid", "required_structure", "historical_feedback_requirements"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                values.append(_compact(value)[:320])
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        values.append(_compact(item)[:320])
                    elif isinstance(item, Mapping) and str(item.get("description", "")).strip():
                        values.append(_compact(str(item["description"]))[:320])
        if values:
            result[index] = list(dict.fromkeys(values))[:12]
    return result


def _historical_usage(run_dir: Path) -> dict[str, Any]:
    parent = run_dir.parent
    if not parent.is_dir():
        return {"status": "not_available", "experience_usage": {}, "claim_usage": {}, "raw_prose_forwarded": False}
    exp: Counter[str] = Counter(); claims: Counter[str] = Counter(); count = 0
    siblings = sorted((x for x in parent.iterdir() if x.is_dir() and x.resolve() != run_dir.resolve()), key=lambda x: x.stat().st_mtime, reverse=True)[:24]
    for sibling in siblings:
        path = sibling / "draft_final.json"
        if not path.is_file():
            path = sibling / "draft.json"
        payload = _json(path, [])
        if not isinstance(payload, list):
            continue
        count += 1
        for response in payload:
            if not isinstance(response, Mapping) or not isinstance(response.get("experience_refs"), list):
                continue
            for ref in response["experience_refs"]:
                if not isinstance(ref, Mapping):
                    continue
                eid = str(ref.get("experience_id", "")).strip()
                if eid:
                    exp[eid] += 1
                for cid in ref.get("claim_ids", []) if isinstance(ref.get("claim_ids"), list) else []:
                    if str(cid).strip():
                        claims[str(cid)] += 1
    return {"status": "available" if count else "not_available", "historical_run_count": count, "experience_usage": dict(exp.most_common(20)), "claim_usage": dict(claims.most_common(30)), "use": "portfolio_novelty_signal_only", "raw_prose_forwarded": False}


def _outcomes(root: Path, target: str) -> dict[str, Any]:
    payload = _json(root / ".career_profile" / "application_outcomes.json", {})
    if not isinstance(payload, Mapping) or not isinstance(payload.get("cases"), list):
        return {"status": "not_available", "requirements": [], "raw_prose_forwarded": False}
    target_norm = _norm(target); requirements = []
    for case in payload["cases"]:
        if not isinstance(case, Mapping):
            continue
        org = str(case.get("organization", "")); scope = str(case.get("scope", ""))
        exact = bool(org and (_norm(org) in target_norm or target_norm in _norm(org)))
        if not exact and scope != "cross_target":
            continue
        for signal in case.get("signals", []) if isinstance(case.get("signals"), list) else []:
            if not isinstance(signal, Mapping):
                continue
            dim, direction = str(signal.get("dimension", "")), str(signal.get("direction", ""))
            if dim not in OUTCOME_DIMENSIONS or direction not in {"strength", "weakness"}:
                continue
            requirements.append({"dimension": dim, "direction": direction, "decision": str(case.get("decision", "")), "exact_target": exact, "confidence": "confirmed_official" if case.get("verification_status") == "confirmed" and case.get("feedback_source") == "official" else "review_only"})
    return {"status": "applied" if requirements else "no_relevant_cases", "requirements": requirements[:24], "metric_semantics": "historical outcomes only, never hire probability", "raw_prose_forwarded": False}


def build_strategy_prior(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = _json(run_dir / "run.json", {})
    if not isinstance(state, Mapping):
        raise ValueError("run.json must be an object")
    root = Path(str(state.get("root", run_dir.parent))).expanduser().resolve()
    target = str(state.get("target", "")); source_dir = _guidance_dir(root, state)
    youtube_rules: list[str] = []
    if source_dir is not None:
        for name in ("01_자소서_작성원칙_요약.md", "02_문항유형별_전략.md", "03_기관별_적용노트.md"):
            youtube_rules.extend(_bullets(source_dir / name, 8))
    youtube_rules.extend(_bullets(run_dir / "05_작성가이드_유튜브프레임.md", 8))
    youtube_rules = list(dict.fromkeys(youtube_rules))[:18]
    ledger = _json(run_dir / "02_확정경험원장.json", {})
    matches = _json(run_dir / "03_경험직무매칭.json", [])
    research = _json(run_dir / "04_공식근거.json", [])
    exp_count = len(ledger.get("experiences", [])) if isinstance(ledger, Mapping) and isinstance(ledger.get("experiences"), list) else 0
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": POLICY,
        "target": target,
        "authority": {
            "applicant_facts": "02_확정경험원장.json only",
            "experience_assignment": "03_경험직무매칭.json + Narrative Compiler portfolio assignment",
            "organization_facts": "00_채용공고분석.json + 04_공식근거.json only",
            "strategy_only": ["05_문항전략.*", "05_작성가이드_유튜브프레임.md", "자소서 유튜브 정보 imported analysis", "historical application metadata/outcome signals", "surface/semantic preference profiles"],
            "never_authorizes": ["new applicant fact", "new metric", "new motive", "new causal claim", "company fact from YouTube", "verbatim legacy answer reuse"],
        },
        "current_pipeline": {"confirmed_experience_count": exp_count, "matching_artifact_present": isinstance(matches, list) and bool(matches), "official_research_claim_count": len(research) if isinstance(research, list) else 0, "existing_question_strategy_present": (run_dir / "05_문항전략.md").is_file() or (run_dir / "05_문항전략.json").is_file()},
        "youtube": {"status": "available" if source_dir is not None else "missing", "source_dir": str(source_dir) if source_dir else None, "freshness": _freshness(source_dir), "general_strategy_rules": youtube_rules, "target_specific": _target_youtube(source_dir, target), "factual_authority": False},
        "legacy_writing_pipeline": {"general_rules": _bullets(run_dir / "05_문항전략.md"), "per_question": {str(k): v for k, v in sorted(_question_strategy(run_dir).items())}, "factual_authority": False},
        "historical_run_usage": _historical_usage(run_dir),
        "historical_outcomes": _outcomes(root, target),
        "application_rules": [
            "Current confirmed ledger and official research always override every strategy prior.",
            "Use YouTube and legacy materials only for structure, emphasis, evaluation criteria and anti-patterns.",
            "Do not copy sentences from YouTube or historical self-introductions.",
            "Historical application outcomes are diagnostic signals, not hiring probability or causal proof.",
            "If a strategy needs a motive, judgment, number or result absent from blueprint evidence, surface an evidence gap instead of inventing it.",
        ],
    }


def strategy_prior_for_stage(packet: Mapping[str, Any], stage: str) -> dict[str, Any]:
    match = re.search(r"(?:^|_)q(\d+)(?:_|$)", stage)
    q = int(match.group(1)) if match else None
    prior = {"policy": packet.get("policy"), "authority": packet.get("authority"), "application_rules": packet.get("application_rules", []), "youtube": packet.get("youtube", {}), "historical_outcomes": packet.get("historical_outcomes", {}), "historical_run_usage": packet.get("historical_run_usage", {})}
    legacy = packet.get("legacy_writing_pipeline", {})
    if q is not None:
        per_q = legacy.get("per_question", {}) if isinstance(legacy, Mapping) else {}
        prior.update(question_index=q, legacy_question_strategy=per_q.get(str(q), []) if isinstance(per_q, Mapping) else [])
    else:
        prior["legacy_writing_pipeline"] = legacy
    return prior


def render_strategy_prior_markdown(packet: Mapping[str, Any]) -> str:
    youtube = packet.get("youtube", {}) if isinstance(packet.get("youtube"), Mapping) else {}
    lines = ["# 통합 작성전략 선행정보", "", f"- 정책: `{packet.get('policy')}`", f"- 대상: {packet.get('target') or '(없음)'}", "- 사실 권한: 확정 경험원장·공식 공고·공식 조사만 사용", "- 유튜브/과거 자기소개서/기존 작성전략: 전략 신호로만 사용", "", "## 유튜브 전략", "", f"- 상태: {youtube.get('status')} / freshness={youtube.get('freshness', {}).get('status') if isinstance(youtube.get('freshness'), Mapping) else None}"]
    lines.extend(f"- {x}" for x in youtube.get("general_strategy_rules", []) if isinstance(x, str))
    target = youtube.get("target_specific", {})
    if isinstance(target, Mapping) and target.get("status") == "matched":
        lines.extend(["", "## 기관 맞춤 유튜브 전략", ""])
        for row in target.get("matches", []):
            if isinstance(row, Mapping):
                lines.append(f"- [{row.get('match_type')}] {row.get('title')}: {row.get('strategy_excerpt')}")
    lines.extend(["", "## 경계", "", "- 과거 자기소개서 원문은 새 답변의 사실 근거로 전달하지 않음", "- 과거 run은 experience/claim 사용 빈도만 novelty 신호로 사용", "- 전형 결과는 검증된 메타데이터가 있을 때만 전략 피드백으로 사용", "- 근거가 없으면 창작하지 않고 서사 정보 공백으로 처리", ""])
    return "\n".join(lines)
