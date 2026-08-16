"""채용 결과를 최소 메타데이터로 기록하고 다음 문항전략에 연결한다."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .path_policy import confine_path, exclusive_lock
from .state import write_json


SCHEMA_VERSION = 1
DECISIONS = frozenset({"rejected", "advanced", "accepted", "withdrawn", "unknown"})
VERIFICATION_STATUSES = frozenset({"confirmed", "proposed"})
FEEDBACK_SOURCES = frozenset({"official", "user_reported", "inferred"})
SCOPES = frozenset({"target_only", "cross_target"})
DIRECTIONS = frozenset({"strength", "weakness"})
DIMENSIONS = frozenset(
    {
        "job_competency",
        "motivation",
        "culture_fit",
        "organization_interest",
        "product_understanding",
        "document_hygiene",
        "question_differentiation",
        "fact_ownership",
        "interview_defense",
    }
)

_CASE_KEYS = frozenset(
    {
        "case_id",
        "organization",
        "target_role",
        "decision",
        "verification_status",
        "feedback_source",
        "scope",
        "recorded_at",
        "evidence_refs",
        "signals",
        "metrics",
    }
)
_REQUIRED_CASE_KEYS = _CASE_KEYS - {"metrics"}
_SIGNAL_KEYS = frozenset({"dimension", "direction"})
_METRIC_KEYS = frozenset({"applicant_score", "cutoff_score", "rank", "pool_size"})
_CASE_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}\Z")

_DIMENSION_POLICY: dict[str, dict[str, Any]] = {
    "job_competency": {
        "applies_to": ("experience", "competency", "job_plan", "motivation"),
        "weakness": "본인의 판단·행동·관찰 가능한 결과를 공고상 실제 업무 행동까지 연결한다.",
        "strength": "검증된 직무 수행 증거와 구체적인 업무 연결을 유지한다.",
    },
    "motivation": {
        "applies_to": ("motivation",),
        "weakness": "첫 두 문장 안에 지원자의 관찰·문제의식·선택 이유를 두고 기관 설명은 근거로만 제한한다.",
        "strength": "개인 경험에서 출발한 기관 선택 이유를 유지한다.",
    },
    "culture_fit": {
        "applies_to": ("collaboration", "culture"),
        "weakness": "친절·성실 같은 선언 대신 다른 사람과 기준·역할·방법을 조정한 장면을 제시한다.",
        "strength": "조직 안에서 관찰 가능한 협업 행동과 변화를 유지한다.",
    },
    "organization_interest": {
        "applies_to": ("motivation", "organization"),
        "weakness": "기관 이해를 일반 설명이 아니라 지원자의 선택과 수행 행동에 연결한다.",
        "strength": "검증된 기관 이해와 관심의 구체성을 유지하되 회사 소개가 본인 행동을 앞서지 않게 한다.",
    },
    "product_understanding": {
        "applies_to": ("motivation", "organization", "job_plan"),
        "weakness": "상품·사업 설명을 줄이고 지원자가 확인·안내·기록할 행동으로 전환한다.",
        "strength": "공식 근거에 기반한 상품·사업 이해를 유지하되 지식이 직무 증거를 대신하지 않게 한다.",
    },
    "document_hygiene": {
        "applies_to": ("all",),
        "weakness": "편집 메모, Markdown 표식, 글자 수 작업 문구가 최종 제출물에 남지 않게 한다.",
        "strength": "제출 파일의 형식·표식·편집 잔여물이 없는 상태를 유지한다.",
    },
    "question_differentiation": {
        "applies_to": ("all",),
        "weakness": "문항마다 다른 중심 경험·판단·결론을 배치하고 같은 절차 표어를 반복하지 않는다.",
        "strength": "문항별 소재와 결론의 차별성을 유지한다.",
    },
    "fact_ownership": {
        "applies_to": ("experience", "competency", "collaboration"),
        "weakness": "개인 행동과 팀 결과의 주어·범위·수치를 분리해 면접에서 방어 가능하게 한다.",
        "strength": "본인 기여 범위와 결과 소유권이 명확한 표현을 유지한다.",
    },
    "interview_defense": {
        "applies_to": ("experience", "competency", "collaboration", "job_plan"),
        "weakness": "판단 기준·예외·보고 경계를 답변에 남겨 후속 질문에 근거로 답할 수 있게 한다.",
        "strength": "수치·역할·판단을 원자료로 방어할 수 있는 수준을 유지한다.",
    },
}


class OutcomeFeedbackError(ValueError):
    """결과 원장 또는 피드백 계약이 유효하지 않을 때 발생한다."""


def _plain_text(value: object, field: str, *, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise OutcomeFeedbackError(f"invalid {field}")
    return text


def _recorded_at(value: object) -> str:
    text = _plain_text(value, "recorded_at", maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise OutcomeFeedbackError("invalid recorded_at") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OutcomeFeedbackError("recorded_at must be timezone-aware")
    return text


def _evidence_ref(root: Path | None, value: object) -> str:
    text = _plain_text(value, "evidence_ref", maximum=240)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise OutcomeFeedbackError("evidence_ref must be workspace-relative")
    if root is not None:
        try:
            resolved = confine_path(root, path, must_exist=True, require_file=True)
            text = resolved.relative_to(root.resolve()).as_posix()
        except ValueError as error:
            raise OutcomeFeedbackError("invalid evidence_ref") from error
    return text.replace("\\", "/")


def _validate_metrics(value: object) -> dict[str, int | float]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not set(value).issubset(_METRIC_KEYS):
        raise OutcomeFeedbackError("invalid metrics")
    metrics: dict[str, int | float] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw < 0:
            raise OutcomeFeedbackError(f"invalid metric: {key}")
        metrics[key] = raw
    rank = metrics.get("rank")
    pool_size = metrics.get("pool_size")
    if rank is not None and pool_size is not None and rank > pool_size:
        raise OutcomeFeedbackError("rank cannot exceed pool_size")
    return metrics


def validate_outcome_case(value: object, *, root: Path | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or not _REQUIRED_CASE_KEYS.issubset(value) or not set(value).issubset(_CASE_KEYS):
        raise OutcomeFeedbackError("invalid outcome case shape")
    case_id = _plain_text(value.get("case_id"), "case_id", maximum=80)
    if not _CASE_ID.fullmatch(case_id):
        raise OutcomeFeedbackError("invalid case_id")
    decision = str(value.get("decision", ""))
    verification_status = str(value.get("verification_status", ""))
    feedback_source = str(value.get("feedback_source", ""))
    scope = str(value.get("scope", ""))
    if decision not in DECISIONS:
        raise OutcomeFeedbackError("invalid decision")
    if verification_status not in VERIFICATION_STATUSES:
        raise OutcomeFeedbackError("invalid verification_status")
    if feedback_source not in FEEDBACK_SOURCES:
        raise OutcomeFeedbackError("invalid feedback_source")
    if scope not in SCOPES:
        raise OutcomeFeedbackError("invalid scope")
    raw_evidence = value.get("evidence_refs")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise OutcomeFeedbackError("at least one evidence_ref is required")
    evidence_refs = tuple(dict.fromkeys(_evidence_ref(root, item) for item in raw_evidence))
    raw_signals = value.get("signals")
    if not isinstance(raw_signals, list) or not raw_signals:
        raise OutcomeFeedbackError("at least one feedback signal is required")
    signals: list[dict[str, str]] = []
    seen_signals: set[tuple[str, str]] = set()
    for raw_signal in raw_signals:
        if not isinstance(raw_signal, dict) or set(raw_signal) != _SIGNAL_KEYS:
            raise OutcomeFeedbackError("invalid feedback signal")
        dimension = str(raw_signal.get("dimension", ""))
        direction = str(raw_signal.get("direction", ""))
        if dimension not in DIMENSIONS or direction not in DIRECTIONS:
            raise OutcomeFeedbackError("invalid feedback signal")
        key = (dimension, direction)
        if key not in seen_signals:
            signals.append({"dimension": dimension, "direction": direction})
            seen_signals.add(key)
    result = {
        "case_id": case_id,
        "organization": _plain_text(value.get("organization"), "organization", maximum=120),
        "target_role": _plain_text(value.get("target_role"), "target_role", maximum=160),
        "decision": decision,
        "verification_status": verification_status,
        "feedback_source": feedback_source,
        "scope": scope,
        "recorded_at": _recorded_at(value.get("recorded_at")),
        "evidence_refs": list(evidence_refs),
        "signals": signals,
    }
    metrics = _validate_metrics(value.get("metrics"))
    if metrics:
        result["metrics"] = metrics
    return result


def validate_outcome_ledger(value: object, *, root: Path | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "cases"}:
        raise OutcomeFeedbackError("invalid outcome ledger shape")
    if value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("cases"), list):
        raise OutcomeFeedbackError("unsupported outcome ledger")
    cases = [validate_outcome_case(item, root=root) for item in value["cases"]]
    case_ids = [item["case_id"] for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise OutcomeFeedbackError("duplicate case_id")
    return {"schema_version": SCHEMA_VERSION, "cases": cases}


def load_outcome_ledger(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OutcomeFeedbackError("outcome ledger is unreadable") from error
    return validate_outcome_ledger(value, root=root)


def parse_feedback_signals(values: Iterable[str]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    for value in values:
        dimension, separator, direction = str(value).partition("=")
        if not separator or dimension not in DIMENSIONS or direction not in DIRECTIONS:
            raise OutcomeFeedbackError(
                "signal must be one of the supported dimension=strength|weakness values"
            )
        signals.append({"dimension": dimension, "direction": direction})
    if not signals:
        raise OutcomeFeedbackError("at least one feedback signal is required")
    return signals


def record_outcome_case(
    root: Path,
    ledger_path: Path,
    case: dict[str, Any],
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    try:
        destination = confine_path(workspace, ledger_path, must_exist=False)
    except ValueError as error:
        raise OutcomeFeedbackError("ledger must remain inside workspace") from error
    validated_case = validate_outcome_case(case, root=workspace)
    lock_path = destination.with_name(destination.name + ".lock")
    with exclusive_lock(lock_path):
        if destination.exists():
            ledger = load_outcome_ledger(destination, root=workspace)
        else:
            ledger = {"schema_version": SCHEMA_VERSION, "cases": []}
        if any(item["case_id"] == validated_case["case_id"] for item in ledger["cases"]):
            raise OutcomeFeedbackError("case_id already exists")
        ledger["cases"].append(validated_case)
        ledger["cases"].sort(key=lambda item: (item["recorded_at"], item["case_id"]))
        write_json(destination, ledger)
    return ledger


def _normalized_target(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def _target_matches(case: dict[str, Any], target: str) -> bool:
    organization = _normalized_target(str(case.get("organization", "")))
    normalized_target = _normalized_target(target)
    return bool(
        organization
        and normalized_target
        and (organization in normalized_target or normalized_target in organization)
    )


def build_outcome_feedback_context(
    ledger: dict[str, Any],
    *,
    target: str,
) -> dict[str, Any]:
    validated = validate_outcome_ledger(ledger)
    relevant: list[tuple[dict[str, Any], bool]] = []
    for case in validated["cases"]:
        exact_target = _target_matches(case, target)
        if exact_target or case["scope"] == "cross_target":
            relevant.append((case, exact_target))
    if not relevant:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "no_relevant_cases",
            "target": target,
            "active_case_count": 0,
            "requirements": [],
            "metric_semantics": "historical outcomes, not hire probability",
        }

    repeated_official_weaknesses = Counter(
        signal["dimension"]
        for case, _ in relevant
        if case["decision"] == "rejected"
        and case["verification_status"] == "confirmed"
        and case["feedback_source"] == "official"
        for signal in case["signals"]
        if signal["direction"] == "weakness"
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for case, exact_target in relevant:
        if case["decision"] not in {"rejected", "advanced", "accepted"}:
            continue
        for signal in case["signals"]:
            dimension = signal["dimension"]
            direction = signal["direction"]
            key = (dimension, direction)
            row = grouped.setdefault(
                key,
                {
                    "dimension": dimension,
                    "direction": direction,
                    "case_ids": [],
                    "exact_target": False,
                    "official_confirmed": False,
                    "proposed": False,
                },
            )
            row["case_ids"].append(case["case_id"])
            row["exact_target"] = row["exact_target"] or exact_target
            row["official_confirmed"] = row["official_confirmed"] or (
                case["verification_status"] == "confirmed"
                and case["feedback_source"] == "official"
            )
            row["proposed"] = row["proposed"] or case["verification_status"] == "proposed"

    requirements: list[dict[str, Any]] = []
    for (dimension, direction), row in sorted(grouped.items()):
        policy = _DIMENSION_POLICY[dimension]
        if direction == "strength":
            enforcement = "preserve_strength"
        elif (
            row["official_confirmed"]
            and not row["proposed"]
            and (row["exact_target"] or repeated_official_weaknesses[dimension] >= 2)
        ):
            enforcement = "hard_requirement"
        else:
            enforcement = "review_required"
        requirements.append(
            {
                "code": f"OUTCOME_{dimension.upper()}_{direction.upper()}",
                "dimension": dimension,
                "direction": direction,
                "enforcement": enforcement,
                "applies_to": list(policy["applies_to"]),
                "description": policy[direction],
                "case_count": len(set(row["case_ids"])),
                "source_case_ids": sorted(set(row["case_ids"])),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "applied" if requirements else "no_actionable_signals",
        "target": target,
        "active_case_count": len(relevant),
        "requirements": requirements,
        "hard_requirement_count": sum(
            item["enforcement"] == "hard_requirement" for item in requirements
        ),
        "review_required_count": sum(
            item["enforcement"] == "review_required" for item in requirements
        ),
        "metric_semantics": "historical outcomes, not hire probability",
    }


def _question_types(prompt: str) -> set[str]:
    types: set[str] = set()
    marker_map = {
        "motivation": ("지원동기", "지원하게 된", "지원한 이유", "선택한 이유"),
        "experience": ("경험", "사례", "상황"),
        "competency": ("역량", "강점", "직무능력", "능력"),
        "job_plan": ("업무수행계획", "근무계획", "직무계획", "입사 후", "기여"),
        "collaboration": ("협업", "협력", "갈등", "팀"),
        "culture": ("조직문화", "인재상", "가치"),
        "organization": ("기관", "회사", "공사", "상품", "사업"),
    }
    for question_type, markers in marker_map.items():
        if any(marker in prompt for marker in markers):
            types.add(question_type)
    return types or {"all"}


def merge_outcome_feedback(
    requirement_map: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    merged = json.loads(json.dumps(requirement_map, ensure_ascii=False))
    merged["historical_outcome_feedback"] = context
    requirements = context.get("requirements", []) if isinstance(context, dict) else []
    for row in merged.get("questions", []):
        if not isinstance(row, dict):
            continue
        question_types = _question_types(str(row.get("prompt", "")))
        row["historical_feedback_requirements"] = [
            item
            for item in requirements
            if isinstance(item, dict)
            and (
                "all" in item.get("applies_to", [])
                or question_types.intersection(item.get("applies_to", []))
            )
        ]
    canonical = json.dumps(
        merged.get("questions", []),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    merged["question_set_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    return merged
