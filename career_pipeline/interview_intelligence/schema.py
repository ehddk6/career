"""Authority schema and claim-defense graph for interview intelligence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ..facts import METRIC, _normalize
from ..profile_schema import Experience, ExperienceLedger, ProfileClaim, load_ledger
from ..research_evidence import ResearchClaim, load_research_claims


SCHEMA_VERSION = 1
PLAN_JSON = "08_면접지능설계.json"
BANK_MD = "08_면접질문은행.md"
EVALUATION_JSON = "08_면접세션평가.json"
WEAKNESS_PROFILE = ".career_profile/interview_weakness_profile.json"

DIMENSIONS = (
    "directness",
    "evidence_defensibility",
    "ownership_precision",
    "causal_precision",
    "decision_visibility",
    "specificity",
    "job_understanding",
    "organization_understanding",
    "pressure_resilience",
    "reflection_quality",
    "communication_density",
)

DIMENSION_LABELS = {
    "directness": "질문에 바로 답하는 정도",
    "evidence_defensibility": "근거로 방어 가능한 정도",
    "ownership_precision": "본인 기여와 팀 기여 구분",
    "causal_precision": "성과 인과관계의 정확성",
    "decision_visibility": "판단 기준과 선택 이유의 가시성",
    "specificity": "행동·대상·순서의 구체성",
    "job_understanding": "직무 이해",
    "organization_understanding": "기관·회사 이해",
    "pressure_resilience": "압박 질문에서 논리 유지",
    "reflection_quality": "한계·실패·학습의 질",
    "communication_density": "시간 대비 정보 밀도",
}

BEHAVIOR_ANCHORS = {
    "directness": {0: "질문을 회피하거나 핵심 답이 없음", 2: "핵심 답은 있으나 배경 뒤에 묻힘", 4: "첫 부분에서 결론을 제시하고 이후 근거를 붙임"},
    "evidence_defensibility": {0: "근거 밖 사실·수치 또는 모순이 있음", 2: "대체로 근거와 맞지만 출처·범위 설명이 약함", 4: "주장·수치·범위를 승인 근거와 정확히 연결함"},
    "ownership_precision": {0: "팀 성과를 개인 성과로 확대하거나 역할이 불명확", 2: "본인 역할은 보이나 타인·팀 경계가 약함", 4: "본인 행동·팀 행동·기여 범위를 명확히 분리함"},
    "causal_precision": {0: "상관·팀 결과를 단독 인과로 단정", 2: "인과 설명은 있으나 대안 요인·검증 범위가 약함", 4: "검증 가능한 인과 범위와 다른 요인을 함께 구분함"},
    "decision_visibility": {0: "무엇을 왜 선택했는지 설명하지 못함", 2: "선택 이유는 있으나 기준·대안 비교가 약함", 4: "판단 기준·대안·trade-off가 명확함"},
    "specificity": {0: "추상적 태도·역량 표현 중심", 2: "행동은 있으나 대상·순서·도구가 일부 빠짐", 4: "행동의 대상·순서·도구·결과가 관찰 가능하게 구체적"},
    "job_understanding": {0: "직무를 일반론으로만 설명", 2: "주요 업무를 알고 있으나 판단·통제 단위가 약함", 4: "업무의 실제 행동·권한·통제·인계 기준까지 연결"},
    "organization_understanding": {0: "어느 기관에도 적용 가능한 설명", 2: "기관 사실을 알지만 개인 판단과 연결이 약함", 4: "검증된 기관 사실의 의미를 해석하고 직무·선택 기준과 연결"},
    "pressure_resilience": {0: "압박 시 과장·모순·회피가 발생", 2: "답은 유지하지만 경계·불확실성 표현이 약함", 4: "압박에도 주장 범위·근거·모르는 부분을 안정적으로 구분"},
    "reflection_quality": {0: "실패·한계가 없거나 포장함", 2: "개선점은 있으나 이후 행동 변화가 약함", 4: "통제 가능한 한계와 바뀐 판단 기준·행동을 구체화"},
    "communication_density": {0: "시간 대비 핵심 정보가 매우 부족하거나 장황", 2: "핵심은 있으나 반복·배경이 많음", 4: "시간 안에 결론·근거·행동·의미를 압축해 전달"},
}

_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("motivation", ("지원동기", "지원 동기", "지원한 이유", "지원하게 된", "선택한 이유")),
    ("job_plan", ("업무수행계획", "직무수행계획", "근무계획", "직무계획", "입사 후")),
    ("collaboration", ("협업", "협력", "갈등", "팀워크", "의견 차이", "조율")),
    ("problem_solving", ("문제해결", "문제 해결", "개선", "어려움", "해결")),
    ("growth", ("부족", "실패", "배운", "성장", "보완")),
    ("integrity", ("윤리", "원칙", "책임감", "신뢰", "정직", "규정")),
    ("competency", ("강점", "역량", "능력", "전문성", "직무역량")),
    ("issue_analysis", ("시사", "이슈", "현안", "사회문제", "경제", "논술")),
)

_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOPWORDS = {
    "그리고", "하지만", "때문", "통해", "대한", "관련", "지원", "기관", "회사", "직무",
    "업무", "경험", "결과", "문항", "답변", "본인", "제가", "저는", "하는", "했습니다",
}
_OWNERSHIP_CUES = ("제가", "저는", "직접", "담당", "맡아", "책임", "제 역할", "제가 한")
_BOUNDARY_CUES = ("팀", "함께", "공동", "동료", "제 기여", "제가 맡은", "범위", "부분")
_DECISION_CUES = ("기준", "판단", "선택", "우선", "비교", "이유", "때문", "대안")
_REFLECTION_CUES = ("아쉬", "실패", "부족", "한계", "다시", "바꾸", "배웠", "이후", "교훈")
_PRESSURE_CUES = ("정확히", "범위", "확인", "근거", "다만", "구분", "과장", "모르")
_CAUSAL_VERBS = ("달성", "개선", "증가", "감소", "절감", "향상", "높였", "낮췄", "해결")


@dataclass(frozen=True)
class DraftRef:
    question_index: int
    answer: str
    experience_refs: tuple[dict[str, Any], ...]
    research_refs: tuple[str, ...]


class InterviewIntelligenceError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InterviewIntelligenceError(f"cannot read JSON: {path}: {error}") from error


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _WORD.findall(text)
        if token.lower() not in _STOPWORDS and len(token) >= 2
    }


def _compact(text: str, limit: int = 180) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _intent(prompt: str) -> str:
    compact = re.sub(r"\s+", "", prompt)
    for name, cues in _INTENT_RULES:
        if any(re.sub(r"\s+", "", cue) in compact for cue in cues):
            return name
    return "general_experience"


def _load_state(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run.json"
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise InterviewIntelligenceError("run.json must contain an object")
    return payload


def _resolve_draft_path(run_dir: Path, explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit if explicit.is_absolute() else run_dir / explicit)
    state_path = run_dir / "run.json"
    if state_path.is_file():
        state = _read_json(state_path)
        final_artifact = state.get("final_artifact", {}) if isinstance(state, Mapping) else {}
        if isinstance(final_artifact, Mapping):
            for key in ("json", "json_path", "draft_json", "selected_json"):
                value = final_artifact.get(key)
                if isinstance(value, str) and value.endswith(".json"):
                    path = Path(value)
                    candidates.append(path if path.is_absolute() else run_dir / path)
    candidates.extend((run_dir / "draft_final.json", run_dir / "draft.json"))
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise InterviewIntelligenceError("final draft JSON not found; pass --draft or run finalize first")


def _load_draft(path: Path) -> tuple[DraftRef, ...]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise InterviewIntelligenceError(f"{path.name} must contain an array")
    rows: list[DraftRef] = []
    seen: set[int] = set()
    for position, item in enumerate(payload, 1):
        if not isinstance(item, Mapping):
            raise InterviewIntelligenceError(f"{path.name}[{position}] must be an object")
        index = item.get("question_index")
        answer = item.get("answer")
        refs = item.get("experience_refs", [])
        research_refs = item.get("research_refs", [])
        if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
            raise InterviewIntelligenceError(f"{path.name}[{position}].question_index is invalid")
        if index in seen:
            raise InterviewIntelligenceError(f"duplicate question_index in {path.name}: {index}")
        if not isinstance(answer, str) or not answer.strip():
            raise InterviewIntelligenceError(f"{path.name}[{position}].answer is empty")
        if not isinstance(refs, list) or not all(isinstance(ref, Mapping) for ref in refs):
            raise InterviewIntelligenceError(f"{path.name}[{position}].experience_refs is invalid")
        if not isinstance(research_refs, list) or not all(isinstance(ref, str) for ref in research_refs):
            raise InterviewIntelligenceError(f"{path.name}[{position}].research_refs is invalid")
        rows.append(
            DraftRef(
                question_index=index,
                answer=answer.strip(),
                experience_refs=tuple(dict(ref) for ref in refs),
                research_refs=tuple(research_refs),
            )
        )
        seen.add(index)
    return tuple(sorted(rows, key=lambda row: row.question_index))


def _question_map(state: Mapping[str, Any], draft: Sequence[DraftRef]) -> dict[int, str]:
    result: dict[int, str] = {}
    questions = state.get("questions", [])
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, Mapping):
                continue
            index = item.get("index")
            prompt = item.get("prompt")
            if isinstance(index, int) and not isinstance(index, bool) and isinstance(prompt, str):
                result[index] = prompt.strip()
    for row in draft:
        result.setdefault(row.question_index, f"자기소개서 문항 {row.question_index}")
    return result


def _research_raw(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = _read_json(path)
    if not isinstance(payload, list):
        return {}
    return {
        str(item.get("claim_id")): dict(item)
        for item in payload
        if isinstance(item, Mapping) and item.get("claim_id")
    }


def _claim_lookup(ledger: ExperienceLedger) -> tuple[dict[str, Experience], dict[tuple[str, str], ProfileClaim], dict[tuple[str, str], ProfileClaim]]:
    experiences = {
        exp.experience_id: exp
        for exp in ledger.experiences
        if exp.status == "confirmed"
    }
    by_id: dict[tuple[str, str], ProfileClaim] = {}
    by_field: dict[tuple[str, str], ProfileClaim] = {}
    for exp in experiences.values():
        for claim in exp.claims:
            if claim.status != "confirmed":
                continue
            if claim.claim_id:
                by_id[(exp.experience_id, claim.claim_id)] = claim
            by_field[(exp.experience_id, claim.field)] = claim
    return experiences, by_id, by_field


def _metric_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in METRIC.finditer(text):
        normalized, _ = _normalize(match.group("number"), match.group("unit"))
        values.append(normalized)
    return tuple(dict.fromkeys(values))


def _applicant_node(
    *,
    index: int,
    exp: Experience,
    claim: ProfileClaim,
) -> dict[str, Any]:
    verification = claim.verification
    contribution = verification.contribution if verification is not None else "unknown"
    metric_values = _metric_values(claim.normalized_value)
    risk = 1.0
    if metric_values:
        risk += 2.2
    if contribution == "caused":
        risk += 1.4
    elif contribution == "contributed":
        risk += 0.9
    elif contribution in {"observed", "unknown"}:
        risk += 1.7
    if any(verb in claim.normalized_value for verb in _CAUSAL_VERBS):
        risk += 0.8
    context = " ".join((exp.situation, *exp.actions, *exp.outcomes))
    anchors = sorted(_tokens(claim.normalized_value).union(_tokens(context)))[:24]
    return {
        "node_id": f"applicant:{exp.experience_id}:{claim.claim_id or claim.field}",
        "source_kind": "applicant",
        "question_indexes": [index],
        "experience_id": exp.experience_id,
        "claim_id": claim.claim_id,
        "claim_field": claim.field,
        "claim_value": claim.normalized_value,
        "experience_title": exp.title,
        "role": exp.role,
        "situation": _compact(exp.situation),
        "actions": [_compact(value) for value in exp.actions[:5]],
        "outcomes": [_compact(value) for value in exp.outcomes[:5]],
        "competencies": list(exp.competencies),
        "verification": {
            "method": verification.method if verification is not None else "none",
            "scope": verification.scope if verification is not None else None,
            "measurement_period": verification.measurement_period if verification is not None else None,
            "contribution": contribution,
            "formula": verification.formula if verification is not None else None,
        },
        "metric_values": list(metric_values),
        "anchors": anchors,
        "risk": round(min(risk, 5.0), 2),
        "factual_authority": True,
    }


def _research_node(index: int, claim: ResearchClaim, raw: Mapping[str, Any]) -> dict[str, Any]:
    freshness = str(raw.get("freshness_class", ""))
    risk = 1.0
    if freshness in {"volatile", "very_volatile", "high"}:
        risk += 1.8
    if claim.claim_type in {"risk_or_limit", "selection_criteria", "eligibility"}:
        risk += 0.7
    if raw.get("conflict_group"):
        risk += 0.8
    return {
        "node_id": f"research:{claim.claim_id}",
        "source_kind": "research",
        "question_indexes": [index],
        "claim_id": claim.claim_id,
        "claim": claim.claim,
        "claim_type": claim.claim_type,
        "application_use": claim.application_use,
        "source_url": claim.source_url,
        "checked_at": claim.checked_at,
        "published_at": claim.published_at,
        "basis_date": claim.basis_date,
        "source_type": claim.source_type,
        "source_tier": raw.get("source_tier"),
        "argument_role": raw.get("argument_role"),
        "support_strength": raw.get("support_strength"),
        "freshness_class": freshness,
        "conflict_group": raw.get("conflict_group"),
        "effective_from": raw.get("effective_from"),
        "effective_to": raw.get("effective_to"),
        "metric_values": list(_metric_values(claim.claim)),
        "anchors": sorted(_tokens(claim.claim))[:20],
        "risk": round(min(risk, 5.0), 2),
        "factual_authority": claim.verification_status == "confirmed",
    }


def _merge_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    key = str(node["node_id"])
    current = nodes.get(key)
    if current is None:
        nodes[key] = node
        return
    indexes = sorted(set(current.get("question_indexes", [])).union(node.get("question_indexes", [])))
    current["question_indexes"] = indexes
    current["risk"] = max(float(current.get("risk", 1.0)), float(node.get("risk", 1.0)))


def _compile_claim_graph(
    draft: Sequence[DraftRef],
    ledger: ExperienceLedger,
    research_claims: Sequence[ResearchClaim],
    research_raw: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    experiences, by_id, by_field = _claim_lookup(ledger)
    research = {
        claim.claim_id: claim
        for claim in research_claims
        if claim.verification_status == "confirmed" and claim.claim_id
    }
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    issues: list[str] = []
    for response in draft:
        qnode = f"response:q{response.question_index}"
        if not response.experience_refs and not response.research_refs:
            issues.append(f"q{response.question_index}: final answer has no authoritative claim references")
        for ref in response.experience_refs:
            experience_id = str(ref.get("experience_id", ""))
            exp = experiences.get(experience_id)
            if exp is None:
                issues.append(f"q{response.question_index}: unknown or unconfirmed experience {experience_id}")
                continue
            claim_ids = ref.get("claim_ids", [])
            claim_fields = ref.get("claim_fields", [])
            selected: list[ProfileClaim] = []
            if isinstance(claim_ids, list) and claim_ids:
                for claim_id in claim_ids:
                    claim = by_id.get((experience_id, str(claim_id)))
                    if claim is None:
                        issues.append(f"q{response.question_index}: unknown or unconfirmed claim {experience_id}/{claim_id}")
                    else:
                        selected.append(claim)
            elif isinstance(claim_fields, list) and claim_fields:
                for field in claim_fields:
                    claim = by_field.get((experience_id, str(field)))
                    if claim is None:
                        issues.append(f"q{response.question_index}: unknown or unconfirmed claim field {experience_id}/{field}")
                    else:
                        selected.append(claim)
            else:
                issues.append(f"q{response.question_index}: experience ref {experience_id} has no claim_ids/claim_fields")
            for claim in selected:
                node = _applicant_node(index=response.question_index, exp=exp, claim=claim)
                _merge_node(nodes, node)
                edges.append({"from": qnode, "to": node["node_id"], "relation": "asserts_with"})
        for claim_id in response.research_refs:
            claim = research.get(claim_id)
            if claim is None:
                issues.append(f"q{response.question_index}: unknown or unconfirmed research claim {claim_id}")
                continue
            node = _research_node(response.question_index, claim, research_raw.get(claim_id, {}))
            _merge_node(nodes, node)
            edges.append({"from": qnode, "to": node["node_id"], "relation": "supports_with"})
    if issues:
        raise InterviewIntelligenceError("claim graph blocked:\n- " + "\n- ".join(issues))
    return {
        "nodes": sorted(nodes.values(), key=lambda item: item["node_id"]),
        "edges": edges,
    }
