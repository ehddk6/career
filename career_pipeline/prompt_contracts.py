"""회사조사·면접 프롬프트를 파이프라인의 검증 가능한 계약으로 통합합니다.

기존 Markdown 산출물은 사람이 읽기 위한 결과물로 유지하고, 이 모듈은 두 JSON
사이드카의 자료 버전·근거 연결·면접 방어 깊이를 결정론적으로 검사합니다.
사이드카가 없는 기존 실행은 그대로 동작하며, 둘 중 하나만 존재하면 fail closed 합니다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Literal


CONTRACT_VERSION = "2026-07-15"
COMPANY_CONTRACT_NAME = "04_기업직무조사.json"
INTERVIEW_CONTRACT_NAME = "08_면접대비팩.json"
CONTRACT_REPORT_NAME = "13_프롬프트통합검증.json"

Severity = Literal["HARD_FAIL", "REVIEW_REQUIRED"]

_SOURCE_LEVELS = {1, 2, 3, 4, 5}
_ENTITY_STATUSES = {"CONFIRMED", "UNVERIFIED"}
_CLAIM_TYPES = {
    "FACT",
    "COMPANY_CLAIM",
    "EXTERNAL_CLAIM",
    "CALCULATION",
    "INFERENCE",
    "FORECAST",
    "VALUE_JUDGMENT",
}
_CLAIM_STATUSES = {
    "CONFIRMED_PRIMARY",
    "CONFIRMED_MULTI_SOURCE",
    "ATTRIBUTED_ONLY",
    "INFERENCE_SUPPORTED",
    "NEEDS_VERIFICATION",
    "CONFLICT",
    "OUTDATED",
    "NOT_APPLICABLE",
    "PROHIBITED",
}
_STRATEGY_STAGES = {
    "ANNOUNCED",
    "FUNDED",
    "STARTED",
    "OPERATING",
    "RESULT_OBSERVED",
    "DELAYED",
    "REDUCED",
    "CANCELLED",
    "UNKNOWN",
}
_ROLE_CERTAINTY = {
    "POSTING_CONFIRMED",
    "ORGANIZATION_SUPPORTED",
    "REASONABLE_INFERENCE",
}
_FIT_STATES = {"STRONG_FIT", "TRANSFERABLE", "PARTIAL", "GAP", "UNKNOWN"}
_DECISIONS = {
    "PRIORITY_APPLY",
    "APPLY_WITH_CONDITIONS",
    "WATCH_AND_VERIFY",
    "LOW_PRIORITY",
    "INSUFFICIENT_EVIDENCE",
}
_ANALYSIS_STATUSES = {"ANALYZED", "NOT_APPLICABLE", "INSUFFICIENT_EVIDENCE"}
_CONSISTENCY_STATUSES = {"CONSISTENT", "CONFLICT", "UNVERIFIED"}
_ARCHITECTURE_STATUSES = {
    "CONFIRMED",
    "SUPPORTED_INFERENCE",
    "WEAK_INFERENCE",
    "UNKNOWN",
}
_QUESTION_TYPES = {
    "RECRUITER",
    "HIRING_MANAGER",
    "FACT_AUDITOR",
    "SITUATIONAL_INTERVIEWER",
    "EXECUTIVE",
    "RED_TEAM",
}
_PROBABILITIES = {"HIGH", "MEDIUM", "LOW", "FORMAT_DEPENDENT", "SPECULATIVE"}
_DEFENSE_DEPTHS = {f"D{index}" for index in range(6)}
_PROBE_CATEGORIES = {
    "FACT",
    "JUDGMENT",
    "CONTRIBUTION",
    "ALTERNATIVE",
    "CONDITION_CHANGE",
    "JOB_TRANSFER",
}
_PROBE_STATUSES = {
    "DEFENSIBLE",
    "DEFENSIBLE_WITH_QUALIFICATION",
    "WEAK",
    "CONFLICT",
    "UNKNOWN",
}
_INTERVIEW_DEFENSE_STATUSES = {
    "DEFENSIBLE",
    "DEFENSIBLE_WITH_QUALIFICATION",
    "NEEDS_VERIFICATION",
    "PROHIBITED",
}
_REQUIRED_TIER1_COVERAGE = {
    "self_intro",
    "motivation",
    "company_choice",
    "job_choice",
    "representative_experience",
    "failure",
    "conflict",
    "collaboration",
    "strength",
    "weakness",
    "first_90_days",
    "core_numbers",
}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?\s*(?:%|건|명|원|시간|일|개월|회|페이지|개|대|장|점|년|월|bp|조원|억원)", re.IGNORECASE)
_CLAIM_NUMBER = re.compile(r"\d")
_PROMPT_INJECTION_CUES = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "이전 지시",
    "위 지시",
    "시스템 지시",
    "규칙을 무시",
    "명령을 무시",
    "지시를 무시",
)


@dataclass(frozen=True)
class ContractIssue:
    code: str
    severity: Severity
    artifact: str
    message: str


@dataclass(frozen=True)
class PromptContractReport:
    enabled: bool
    contract_version: str
    data_package_id: str | None
    data_package_version: str | None
    company_path: str | None
    interview_path: str | None
    issues: tuple[ContractIssue, ...]
    company_payload: dict[str, Any] | None = None
    interview_payload: dict[str, Any] | None = None

    @property
    def hard_fail(self) -> bool:
        return any(issue.severity == "HARD_FAIL" for issue in self.issues)

    @property
    def review_required(self) -> bool:
        return any(issue.severity == "REVIEW_REQUIRED" for issue in self.issues)

    def to_dict(self, *, include_payloads: bool = False) -> dict[str, Any]:
        payload = {
            "enabled": self.enabled,
            "validation_scope": "PROMPT_CONTRACT_INTEGRITY",
            "submission_readiness_assessed": False,
            "actual_mock_interview_assessed": False,
            "scope_note": "hard_fail과 review_required는 두 계약 파일의 구조·근거·상호 일치만 판정하며, 실제 음성 모의면접 완료나 최종 제출 준비 완료를 뜻하지 않습니다.",
            "contract_version": self.contract_version,
            "data_package_id": self.data_package_id,
            "data_package_version": self.data_package_version,
            "company_path": self.company_path,
            "interview_path": self.interview_path,
            "hard_fail": self.hard_fail,
            "review_required": self.review_required,
            "issues": [asdict(issue) for issue in self.issues],
        }
        if include_payloads:
            payload["company_payload"] = self.company_payload
            payload["interview_payload"] = self.interview_payload
        return payload


def validate_blind_comparison_payload(
    payload: dict[str, Any], question_indexes: Iterable[int]
) -> None:
    """최종 X/Y 비교가 모든 실제 문항을 구체적 근거와 함께 다뤘는지 검사합니다."""

    required = {
        "choice",
        "hard_fail",
        "reason",
        "comparison_ready",
        "question_choices",
        "risk_audit",
        "remaining_risks",
    }
    if not required.issubset(payload):
        raise ValueError("final comparison schema mismatch")
    if payload.get("choice") not in {"X", "Y"}:
        raise ValueError("invalid final comparison choice")
    if not isinstance(payload.get("comparison_ready"), bool):
        raise ValueError("invalid final comparison readiness")
    hard_fail = payload.get("hard_fail")
    if not isinstance(hard_fail, dict) or set(hard_fail) != {"X", "Y"}:
        raise ValueError("invalid final comparison hard-fail audit")
    if any(
        not isinstance(hard_fail[side], list)
        or any(not isinstance(item, str) for item in hard_fail[side])
        for side in ("X", "Y")
    ):
        raise ValueError("invalid final comparison hard-fail reasons")

    expected = {f"q{int(index)}" for index in question_indexes}
    choices = payload.get("question_choices")
    if not isinstance(choices, dict) or set(choices) != expected:
        raise ValueError("final comparison question set mismatch")
    for question_id, item in choices.items():
        if not isinstance(item, dict) or set(item) != {
            "choice",
            "reason",
            "decisive_difference",
        }:
            raise ValueError(f"invalid final comparison detail: {question_id}")
        if item.get("choice") not in {"X", "Y"}:
            raise ValueError(f"invalid final comparison question choice: {question_id}")
        if not str(item.get("reason", "")).strip() or not str(
            item.get("decisive_difference", "")
        ).strip():
            raise ValueError(f"missing final comparison rationale: {question_id}")

    risk_audit = payload.get("risk_audit")
    risk_categories = {
        "remaining_fact_risks",
        "interview_defense_risks",
        "spoken_answer_risks",
        "company_specificity_regression",
        "applicant_voice_regression",
        "experience_duplication",
        "style_regression",
    }
    if not isinstance(risk_audit, dict) or set(risk_audit) != risk_categories:
        raise ValueError("invalid final comparison risk audit")
    for category, by_side in risk_audit.items():
        if not isinstance(by_side, dict) or set(by_side) != {"X", "Y"}:
            raise ValueError(f"invalid final comparison risk category: {category}")
        if any(
            not isinstance(by_side[side], list)
            or any(not isinstance(item, str) for item in by_side[side])
            for side in ("X", "Y")
        ):
            raise ValueError(f"invalid final comparison risk entries: {category}")
    if not isinstance(payload.get("remaining_risks"), list) or any(
        not isinstance(item, str) for item in payload["remaining_risks"]
    ):
        raise ValueError("invalid final comparison remaining risks")


def _issue(
    issues: list[ContractIssue],
    code: str,
    artifact: str,
    message: str,
    severity: Severity = "HARD_FAIL",
) -> None:
    issues.append(ContractIssue(code, severity, artifact, message))


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _unique_ids(
    rows: list[dict[str, Any]],
    key: str,
    *,
    artifact: str,
    label: str,
    issues: list[ContractIssue],
) -> set[str]:
    values = [str(row.get(key, "")).strip() for row in rows]
    if any(not value for value in values):
        _issue(issues, f"missing_{key}", artifact, f"{label}에 빈 {key}가 있습니다.")
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        _issue(
            issues,
            f"duplicate_{key}",
            artifact,
            f"{label}의 중복 {key}: {', '.join(sorted(duplicates))}",
        )
    return seen


def _valid_date(value: Any) -> bool:
    return isinstance(value, str) and bool(_DATE.fullmatch(value))


def _https(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) > 8


def _contains_prompt_injection(value: Any) -> bool:
    if isinstance(value, str):
        normalized = " ".join(value.casefold().split())
        return any(cue in normalized for cue in _PROMPT_INJECTION_CUES)
    if isinstance(value, list):
        return any(_contains_prompt_injection(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_prompt_injection(item) for item in value.values())
    return False


def company_claim_use_decision(
    claim: dict[str, Any], *, output: str = "SELF_INTRO"
) -> Literal["ALLOW", "QUALIFY", "BLOCK"]:
    """도메인 상태를 바꾸지 않고 산출물별 사용 가능성을 계산한다."""
    status = str(claim.get("status", ""))
    if status not in {
        "CONFIRMED_PRIMARY",
        "CONFIRMED_MULTI_SOURCE",
        "ATTRIBUTED_ONLY",
        "INFERENCE_SUPPORTED",
    }:
        return "BLOCK"
    allowed = _strings(claim.get("allowed_outputs")) or _strings(
        claim.get("application_use")
    )
    if not allowed:
        return "BLOCK"
    normalized = {item.strip().casefold() for item in allowed}
    output_key = output.casefold()
    generic_application = {
        "all",
        "application",
        "self_intro",
        "cover_letter",
        "지원서",
        "자기소개서",
    }
    if not (
        output_key in normalized
        or normalized.intersection(generic_application)
        or any(item.startswith("문항") for item in normalized)
    ):
        return "BLOCK"
    if status in {"ATTRIBUTED_ONLY", "INFERENCE_SUPPORTED"}:
        return "QUALIFY"
    return "ALLOW"


def _validate_analysis_section(
    value: Any,
    *,
    artifact: str,
    section: str,
    item_key: str,
    issues: list[ContractIssue],
) -> list[dict[str, Any]]:
    payload = _object(value)
    status = payload.get("status")
    if status not in _ANALYSIS_STATUSES:
        _issue(
            issues,
            f"invalid_{section}_status",
            artifact,
            f"{section}.status는 ANALYZED, NOT_APPLICABLE, INSUFFICIENT_EVIDENCE 중 하나여야 합니다.",
        )
        return []
    rows = _rows(payload.get(item_key))
    if status == "ANALYZED" and not rows:
        _issue(
            issues,
            f"empty_{section}",
            artifact,
            f"{section}을 ANALYZED로 표시했지만 {item_key}가 비어 있습니다.",
        )
    if status != "ANALYZED" and not str(payload.get("reason", "")).strip():
        _issue(
            issues,
            f"missing_{section}_reason",
            artifact,
            f"{section}을 분석하지 않은 이유가 필요합니다.",
            "REVIEW_REQUIRED",
        )
    return rows


def _contract_meta(
    payload: dict[str, Any], artifact: str, issues: list[ContractIssue]
) -> tuple[str, str]:
    if payload.get("schema_version") not in {1, 2}:
        _issue(issues, "invalid_contract_schema", artifact, "schema_version은 1 또는 2여야 합니다.")
    if payload.get("contract_version") != CONTRACT_VERSION:
        _issue(
            issues,
            "invalid_contract_version",
            artifact,
            f"contract_version은 {CONTRACT_VERSION}이어야 합니다.",
        )
    package_id = str(payload.get("data_package_id", "")).strip()
    package_version = str(payload.get("data_package_version", "")).strip()
    if not package_id:
        _issue(issues, "missing_data_package_id", artifact, "data_package_id가 없습니다.")
    if not package_version:
        _issue(
            issues,
            "missing_data_package_version",
            artifact,
            "data_package_version이 없습니다.",
        )
    return package_id, package_version


def _known_ids_from_ledger(ledger: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    experience_ids: set[str] = set()
    claim_ids: set[str] = set()
    numeric_claim_ids: set[str] = set()
    for experience in _rows(ledger.get("experiences")):
        experience_id = str(experience.get("experience_id", "")).strip()
        if experience.get("status") == "confirmed" and experience_id:
            experience_ids.add(experience_id)
        for claim in _rows(experience.get("claims")):
            claim_id = str(claim.get("claim_id", "")).strip()
            if claim.get("status") != "confirmed" or not claim_id:
                continue
            claim_ids.add(claim_id)
            if _CLAIM_NUMBER.search(str(claim.get("normalized_value", ""))):
                numeric_claim_ids.add(claim_id)
    return experience_ids, claim_ids, numeric_claim_ids


def _response_reference_map(responses: Iterable[Any]) -> dict[int, dict[str, set[str]]]:
    result: dict[int, dict[str, set[str]]] = {}
    for raw in responses:
        if hasattr(raw, "question_index"):
            index = int(raw.question_index)
            experience_refs = getattr(raw, "experience_refs", ())
            research_refs = getattr(raw, "research_refs", ())
            experience_ids = {
                str(getattr(reference, "experience_id", ""))
                for reference in experience_refs
                if getattr(reference, "experience_id", "")
            }
            claim_ids = {
                str(claim_id)
                for reference in experience_refs
                for claim_id in getattr(reference, "claim_ids", ())
                if claim_id
            }
        elif isinstance(raw, dict):
            index = int(raw.get("question_index", 0))
            refs = _rows(raw.get("experience_refs"))
            experience_ids = {
                str(reference.get("experience_id", "")).strip()
                for reference in refs
                if str(reference.get("experience_id", "")).strip()
            }
            claim_ids = {
                str(claim_id)
                for reference in refs
                for claim_id in _strings(reference.get("claim_ids"))
            }
            research_refs = _strings(raw.get("research_refs"))
        else:
            continue
        if index <= 0:
            continue
        result[index] = {
            "experience_ids": experience_ids,
            "claim_ids": claim_ids,
            "research_ids": {str(item) for item in research_refs if item},
        }
    return result


def validate_company_contract(
    payload: dict[str, Any],
    *,
    target: str,
    known_research_ids: set[str],
    known_experience_ids: set[str],
    known_profile_claim_ids: set[str],
) -> tuple[str, str, list[ContractIssue]]:
    artifact = COMPANY_CONTRACT_NAME
    issues: list[ContractIssue] = []
    package_id, package_version = _contract_meta(payload, artifact, issues)

    if str(payload.get("target", "")).strip() != target.strip():
        _issue(issues, "company_target_mismatch", artifact, "회사조사 target이 run.json과 다릅니다.")
    if not _valid_date(payload.get("research_cutoff_date")):
        _issue(
            issues,
            "invalid_research_cutoff_date",
            artifact,
            "research_cutoff_date는 YYYY-MM-DD 형식이어야 합니다.",
        )

    entity = _object(payload.get("entity"))
    entity_status = entity.get("status")
    if entity_status not in _ENTITY_STATUSES:
        _issue(issues, "invalid_entity_status", artifact, "법인 식별 상태가 잘못되었습니다.")
    if not str(entity.get("legal_entity_name", "")).strip():
        _issue(issues, "missing_legal_entity", artifact, "정확한 채용 법인명이 없습니다.")
    if entity_status == "UNVERIFIED":
        _issue(
            issues,
            "unverified_legal_entity",
            artifact,
            "법인·브랜드·사업부 관계를 확인해야 합니다.",
            "REVIEW_REQUIRED",
        )

    sources = _rows(payload.get("source_manifest"))
    source_ids = _unique_ids(
        sources,
        "source_id",
        artifact=artifact,
        label="source_manifest",
        issues=issues,
    )
    if not sources:
        _issue(issues, "missing_source_manifest", artifact, "회사조사 출처 원장이 비어 있습니다.")
    source_levels: set[int] = set()
    for source in sources:
        source_id = str(source.get("source_id", "")).strip() or "<unknown>"
        level = source.get("source_level")
        if level not in _SOURCE_LEVELS:
            _issue(issues, "invalid_source_level", artifact, f"{source_id}의 출처 수준이 잘못되었습니다.")
        elif isinstance(level, int):
            source_levels.add(level)
        if not _https(source.get("url")):
            _issue(issues, "invalid_source_url", artifact, f"{source_id}는 HTTPS 원문 URL이 필요합니다.")
        if not _valid_date(source.get("checked_at")):
            _issue(issues, "invalid_source_checked_at", artifact, f"{source_id}의 확인일이 잘못되었습니다.")
        if not str(source.get("target_entity", "")).strip():
            _issue(issues, "missing_source_entity_scope", artifact, f"{source_id}의 대상 법인 범위가 없습니다.")
    if sources and not ({1, 2} & source_levels):
        _issue(
            issues,
            "weak_source_hierarchy",
            artifact,
            "규제·법정 공시 또는 회사 공식 자료가 없습니다.",
            "REVIEW_REQUIRED",
        )

    claims = _rows(payload.get("claim_ledger"))
    claim_ids = _unique_ids(
        claims,
        "claim_id",
        artifact=artifact,
        label="claim_ledger",
        issues=issues,
    )
    if not claims:
        _issue(issues, "missing_company_claim_ledger", artifact, "회사조사 주장 원장이 비어 있습니다.")
    for claim in claims:
        claim_id = str(claim.get("claim_id", "")).strip() or "<unknown>"
        claim_type = claim.get("claim_type")
        status = claim.get("status")
        refs = set(_strings(claim.get("research_refs")))
        source_refs = set(_strings(claim.get("source_ids")))
        if claim_type not in _CLAIM_TYPES:
            _issue(issues, "invalid_company_claim_type", artifact, f"{claim_id}의 주장 유형이 잘못되었습니다.")
        if status not in _CLAIM_STATUSES:
            _issue(issues, "invalid_company_claim_status", artifact, f"{claim_id}의 주장 상태가 잘못되었습니다.")
        unknown_sources = source_refs - source_ids
        if unknown_sources:
            _issue(issues, "unknown_company_source_ref", artifact, f"{claim_id}가 알 수 없는 source_id를 참조합니다: {', '.join(sorted(unknown_sources))}")
        unknown_research = refs - known_research_ids
        if unknown_research:
            _issue(issues, "unknown_research_ref", artifact, f"{claim_id}가 04_공식근거.json에 없는 ID를 참조합니다: {', '.join(sorted(unknown_research))}")
        if status in {"CONFIRMED_PRIMARY", "CONFIRMED_MULTI_SOURCE", "ATTRIBUTED_ONLY", "INFERENCE_SUPPORTED"} and not (refs or source_refs):
            _issue(issues, "ungrounded_company_claim", artifact, f"{claim_id}에 출처 또는 공식 근거 참조가 없습니다.")
        if claim_type == "COMPANY_CLAIM" and status not in {"ATTRIBUTED_ONLY", "NEEDS_VERIFICATION", "CONFLICT", "OUTDATED", "PROHIBITED"}:
            _issue(issues, "company_claim_objectified", artifact, f"{claim_id}는 회사 주장인데 객관적 사실 상태로 저장되었습니다.")
        if status in {"NEEDS_VERIFICATION", "CONFLICT", "OUTDATED", "PROHIBITED"} and _strings(claim.get("application_use")):
            _issue(issues, "unsafe_company_claim_in_use", artifact, f"{claim_id}는 본문 활용 금지 상태인데 application_use가 지정되었습니다.")
        if _contains_prompt_injection(claim):
            _issue(
                issues,
                "company_claim_prompt_injection",
                artifact,
                f"{claim_id}에 외부 문서 지시문으로 보이는 내용이 포함되어 있습니다.",
            )
        if payload.get("schema_version") == 2:
            allowed_outputs = _strings(claim.get("allowed_outputs"))
            prohibited_uses = _strings(claim.get("prohibited_uses"))
            confidence = claim.get("confidence")
            requires_confirmation = claim.get("requires_user_confirmation")
            defense_status = claim.get("interview_defense_status")
            if status in {
                "CONFIRMED_PRIMARY",
                "CONFIRMED_MULTI_SOURCE",
                "ATTRIBUTED_ONLY",
                "INFERENCE_SUPPORTED",
            } and not allowed_outputs:
                _issue(
                    issues,
                    "missing_claim_allowed_outputs",
                    artifact,
                    f"{claim_id}의 허용 산출물이 지정되지 않았습니다.",
                )
            if status in {"NEEDS_VERIFICATION", "CONFLICT", "OUTDATED", "PROHIBITED"} and not prohibited_uses:
                _issue(
                    issues,
                    "missing_claim_prohibited_uses",
                    artifact,
                    f"{claim_id}의 금지 용도가 지정되지 않았습니다.",
                )
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                _issue(issues, "invalid_claim_confidence", artifact, f"{claim_id}의 confidence는 0~1이어야 합니다.")
            if not isinstance(requires_confirmation, bool):
                _issue(issues, "invalid_claim_confirmation_flag", artifact, f"{claim_id}의 사용자 확인 여부가 잘못되었습니다.")
            if defense_status not in _INTERVIEW_DEFENSE_STATUSES:
                _issue(issues, "invalid_claim_interview_defense", artifact, f"{claim_id}의 면접 방어 상태가 잘못되었습니다.")

    business_model = _object(payload.get("business_model"))
    for key in (
        "core_customers",
        "customer_problem",
        "value_proposition",
        "revenue_logic",
        "major_costs",
        "critical_risks",
    ):
        value = business_model.get(key)
        if not (str(value).strip() if isinstance(value, str) else _strings(value)):
            _issue(issues, "incomplete_business_model", artifact, f"business_model.{key}가 비어 있습니다.")

    strategy_rows = _rows(payload.get("strategy_execution"))
    if not strategy_rows:
        _issue(issues, "missing_strategy_execution", artifact, "전략 발표·자원 투입·실행·성과 단계가 없습니다.")
    for row in strategy_rows:
        strategy_id = str(row.get("strategy_id", "")).strip() or "<unknown>"
        stage = row.get("stage")
        row_claims = set(_strings(row.get("claim_ids")))
        if stage not in _STRATEGY_STAGES:
            _issue(issues, "invalid_strategy_stage", artifact, f"{strategy_id}의 전략 단계가 잘못되었습니다.")
        if row_claims - claim_ids:
            _issue(issues, "unknown_strategy_claim", artifact, f"{strategy_id}가 알 수 없는 회사조사 claim을 참조합니다.")
        if stage in {"FUNDED", "STARTED", "OPERATING", "RESULT_OBSERVED"} and not row_claims:
            _issue(issues, "strategy_stage_without_evidence", artifact, f"{strategy_id}는 {stage} 단계인데 근거 claim이 없습니다.")
        if payload.get("schema_version") == 2:
            if not _strings(row.get("success_conditions")):
                _issue(issues, "missing_strategy_success_conditions", artifact, f"{strategy_id}의 성공 조건이 없습니다.")
            if not _strings(row.get("failure_signals")):
                _issue(issues, "missing_strategy_failure_signals", artifact, f"{strategy_id}의 실패 신호가 없습니다.")
            if not _strings(row.get("job_implications")):
                _issue(issues, "missing_strategy_job_implications", artifact, f"{strategy_id}의 직무 영향이 없습니다.")

    role_rows = _rows(payload.get("role_value_map"))
    if not role_rows:
        _issue(issues, "missing_role_value_map", artifact, "회사 과제와 지원 직무의 연결 지도가 없습니다.")
    for row in role_rows:
        if row.get("certainty") not in _ROLE_CERTAINTY:
            _issue(issues, "invalid_role_certainty", artifact, "role_value_map의 확실성 상태가 잘못되었습니다.")
        if not str(row.get("company_issue", "")).strip() or not _strings(row.get("role_actions")):
            _issue(issues, "incomplete_role_value_map", artifact, "회사 과제와 실제 직무 행동이 모두 필요합니다.")
        unknown = set(_strings(row.get("claim_ids"))) - claim_ids
        if unknown:
            _issue(issues, "unknown_role_claim", artifact, f"role_value_map이 알 수 없는 claim을 참조합니다: {', '.join(sorted(unknown))}")

    bridge_rows = _rows(payload.get("applicant_bridge"))
    if not bridge_rows:
        _issue(issues, "missing_applicant_bridge", artifact, "회사·직무 요구와 지원자 경험 연결이 없습니다.")
    for row in bridge_rows:
        experience_id = str(row.get("experience_id", "")).strip()
        if experience_id not in known_experience_ids:
            _issue(issues, "unknown_bridge_experience", artifact, f"확정 경험 원장에 없는 경험을 연결했습니다: {experience_id or '<empty>'}")
        if row.get("fit_state") not in _FIT_STATES:
            _issue(issues, "invalid_fit_state", artifact, "applicant_bridge의 fit_state가 잘못되었습니다.")
        bridge_claims = set(_strings(row.get("experience_claim_ids")))
        unknown_claims = bridge_claims - known_profile_claim_ids
        if unknown_claims:
            _issue(
                issues,
                "unknown_bridge_claim",
                artifact,
                f"{experience_id} 연결에 확정 원장에 없는 claim이 있습니다: {', '.join(sorted(unknown_claims))}",
            )
        if not str(row.get("requirement", "")).strip():
            _issue(issues, "incomplete_applicant_bridge", artifact, "applicant_bridge.requirement가 비어 있습니다.")
        if not bridge_claims and row.get("fit_state") in {"STRONG_FIT", "TRANSFERABLE", "PARTIAL"}:
            _issue(
                issues,
                "unsupported_applicant_fit",
                artifact,
                f"{experience_id}의 적합성 판단에 경험 claim 근거가 없습니다.",
            )

    financial_rows = _validate_analysis_section(
        payload.get("financial_analysis"),
        artifact=artifact,
        section="financial_analysis",
        item_key="metrics",
        issues=issues,
    )
    for row in financial_rows:
        metric_id = str(row.get("metric_id", "")).strip() or "<unknown>"
        if not str(row.get("period", "")).strip() or not str(row.get("unit", "")).strip():
            _issue(issues, "incomplete_financial_metric", artifact, f"{metric_id}의 기간과 단위가 필요합니다.")
        if not str(row.get("formula", "")).strip() and row.get("calculated_value") not in {None, ""}:
            _issue(issues, "financial_formula_missing", artifact, f"{metric_id}의 계산식이 없습니다.")
        unknown = set(_strings(row.get("claim_ids"))) - claim_ids
        if unknown:
            _issue(issues, "unknown_financial_claim", artifact, f"{metric_id}가 알 수 없는 claim을 참조합니다.")

    competitor_rows = _validate_analysis_section(
        payload.get("competitor_analysis"),
        artifact=artifact,
        section="competitor_analysis",
        item_key="selection",
        issues=issues,
    )
    for row in competitor_rows:
        if not str(row.get("name", "")).strip() or not str(row.get("selection_reason", "")).strip():
            _issue(issues, "incomplete_competitor_selection", artifact, "경쟁사명과 선정 이유가 모두 필요합니다.")
        unknown = set(_strings(row.get("claim_ids"))) - claim_ids
        if unknown:
            _issue(issues, "unknown_competitor_claim", artifact, "경쟁사 비교가 알 수 없는 claim을 참조합니다.")

    culture_rows = _validate_analysis_section(
        payload.get("culture_analysis"),
        artifact=artifact,
        section="culture_analysis",
        item_key="evidence",
        issues=issues,
    )
    for row in culture_rows:
        if not str(row.get("observation", "")).strip() or not str(row.get("scope", "")).strip():
            _issue(issues, "incomplete_culture_evidence", artifact, "문화 관찰의 내용과 범위를 구분해야 합니다.")
        if not str(row.get("sample_limit", "")).strip():
            _issue(
                issues,
                "culture_sample_limit_missing",
                artifact,
                "문화 근거의 표본 한계를 기록해야 합니다.",
                "REVIEW_REQUIRED",
            )

    if payload.get("schema_version") == 2:
        market_position = _object(payload.get("market_position"))
        for key in (
            "target_market",
            "customer_alternatives",
            "competitor_selection_basis",
            "differentiators",
            "uncertainties",
        ):
            value = market_position.get(key)
            if not (str(value).strip() if isinstance(value, str) else _strings(value)):
                _issue(issues, "incomplete_market_position", artifact, f"market_position.{key}가 비어 있습니다.")

        recent_performance = _rows(payload.get("recent_performance"))
        if not recent_performance:
            _issue(
                issues,
                "missing_recent_performance",
                artifact,
                "최근 실적·사업 진행 상황이 없습니다. 확인할 수 없다면 상태와 이유를 기록해야 합니다.",
            )
        for row in recent_performance:
            if row.get("status") not in _CLAIM_STATUSES:
                _issue(issues, "invalid_recent_performance_status", artifact, "최근 실적 상태가 잘못되었습니다.")
            if not str(row.get("observation", "")).strip() or not str(row.get("interpretation", "")).strip():
                _issue(issues, "incomplete_recent_performance", artifact, "최근 실적의 관찰과 해석을 분리해야 합니다.")
            if set(_strings(row.get("claim_ids"))) - claim_ids:
                _issue(issues, "unknown_recent_performance_claim", artifact, "최근 실적이 알 수 없는 claim을 참조합니다.")

        completeness = _object(payload.get("research_completeness"))
        if not _strings(completeness.get("answered_questions")):
            _issue(issues, "missing_research_answered_questions", artifact, "답변한 조사 질문 목록이 없습니다.")
        if not str(completeness.get("stopping_reason", "")).strip():
            _issue(issues, "missing_research_stopping_reason", artifact, "조사 종료 기준이 없습니다.")

        implications = _object(payload.get("interview_implications"))
        if not _strings(implications.get("expected_questions")):
            _issue(issues, "missing_company_expected_questions", artifact, "회사조사 기반 예상 면접 질문이 없습니다.")
        if not _strings(implications.get("reverse_questions")):
            _issue(issues, "missing_company_reverse_questions", artifact, "회사조사 기반 역질문이 없습니다.")
        if not _strings(implications.get("prohibited_talking_points")):
            _issue(
                issues,
                "missing_prohibited_talking_points",
                artifact,
                "면접에서 사용하면 안 되는 회사 주장이 구분되지 않았습니다.",
            )

    first_90_days = _object(payload.get("first_90_days"))
    for key in ("days_0_30", "days_31_60", "days_61_90"):
        if not _strings(first_90_days.get(key)):
            _issue(issues, "incomplete_first_90_days", artifact, f"first_90_days.{key}가 비어 있습니다.")

    red_team = _object(payload.get("red_team"))
    if not str(red_team.get("strongest_counterargument", "")).strip():
        _issue(issues, "missing_company_counterargument", artifact, "가장 강한 반대 해석이 없습니다.", "REVIEW_REQUIRED")
    if not _strings(red_team.get("critical_unknowns")):
        _issue(issues, "missing_company_unknowns", artifact, "핵심 불확실성이 기록되지 않았습니다.", "REVIEW_REQUIRED")

    decision = _object(payload.get("decision"))
    if decision.get("status") not in _DECISIONS:
        _issue(issues, "invalid_application_decision", artifact, "지원 우선순위 판정 상태가 잘못되었습니다.")
    for key in ("main_reason", "strongest_support", "strongest_counterargument"):
        if not str(decision.get(key, "")).strip():
            _issue(issues, "incomplete_application_decision", artifact, f"decision.{key}가 비어 있습니다.")

    return package_id, package_version, issues


def validate_interview_contract(
    payload: dict[str, Any],
    *,
    expected_package_id: str,
    expected_package_version: str,
    response_refs: dict[int, dict[str, set[str]]],
    known_experience_ids: set[str],
    known_profile_claim_ids: set[str],
    numeric_claim_ids: set[str],
    known_research_ids: set[str],
) -> tuple[str, str, list[ContractIssue]]:
    artifact = INTERVIEW_CONTRACT_NAME
    issues: list[ContractIssue] = []
    package_id, package_version = _contract_meta(payload, artifact, issues)
    if package_id != expected_package_id or package_version != expected_package_version:
        _issue(issues, "interview_data_package_mismatch", artifact, "회사조사와 면접 패킷의 DATA PACKAGE가 다릅니다.")

    submitted = _rows(payload.get("submitted_claims"))
    submitted_by_question: dict[int, dict[str, set[str]]] = {}
    for row in submitted:
        try:
            index = int(row.get("question_index", 0))
        except (TypeError, ValueError):
            index = 0
        if index <= 0:
            _issue(issues, "invalid_submitted_claim_question", artifact, "submitted_claims의 question_index가 잘못되었습니다.")
            continue
        bucket = submitted_by_question.setdefault(
            index,
            {"experience_ids": set(), "claim_ids": set(), "research_ids": set()},
        )
        bucket["experience_ids"].update(_strings(row.get("experience_ids")))
        bucket["claim_ids"].update(_strings(row.get("experience_claim_ids")))
        bucket["research_ids"].update(_strings(row.get("research_claim_ids")))
        if row.get("status") not in {
            "CONFIRMED",
            "PARTIALLY_CONFIRMED",
            "NEEDS_VERIFICATION",
            "CONFLICT",
            "DEFENSIBLE_WITH_QUALIFICATION",
            "PROHIBITED",
        }:
            _issue(issues, "invalid_submitted_claim_status", artifact, f"문항 {index}의 제출 주장 상태가 잘못되었습니다.")
        unknown_experiences = bucket["experience_ids"] - known_experience_ids
        unknown_claims = bucket["claim_ids"] - known_profile_claim_ids
        unknown_research = bucket["research_ids"] - known_research_ids
        if unknown_experiences or unknown_claims or unknown_research:
            _issue(
                issues,
                "unknown_submitted_claim_reference",
                artifact,
                f"문항 {index}의 제출 주장 감사가 동결 원장 밖의 근거를 참조합니다.",
            )
    for index, expected in response_refs.items():
        actual = submitted_by_question.get(index)
        if actual is None:
            _issue(issues, "missing_submitted_claim_audit", artifact, f"최종 자기소개서 문항 {index}의 제출 주장 감사가 없습니다.")
            continue
        for key, label in (
            ("experience_ids", "경험"),
            ("claim_ids", "경험 claim"),
            ("research_ids", "공식 근거"),
        ):
            missing = expected[key] - actual[key]
            if missing:
                _issue(issues, "submitted_claim_not_linked", artifact, f"문항 {index}의 {label} 참조가 면접 패킷에 누락되었습니다: {', '.join(sorted(missing))}")

    submitted_experience_ids = set().union(
        *(row["experience_ids"] for row in submitted_by_question.values()), set()
    )
    submitted_profile_claim_ids = set().union(
        *(row["claim_ids"] for row in submitted_by_question.values()), set()
    )
    submitted_research_ids = set().union(
        *(row["research_ids"] for row in submitted_by_question.values()), set()
    )

    consistency_rows = _rows(payload.get("document_consistency"))
    if not consistency_rows:
        _issue(
            issues,
            "missing_document_consistency",
            artifact,
            "이력서·자기소개서·경력기술서 간 표현 차이와 모순 감사가 없습니다.",
            "REVIEW_REQUIRED",
        )
    for row in consistency_rows:
        status = row.get("status")
        if status not in _CONSISTENCY_STATUSES:
            _issue(issues, "invalid_document_consistency_status", artifact, "document_consistency의 상태가 잘못되었습니다.")
        if status == "CONFLICT" and not str(row.get("response_strategy", "")).strip():
            _issue(issues, "unresolved_document_conflict", artifact, "문서 간 충돌에 대한 대응 전략이 없습니다.")

    architecture = _object(payload.get("interview_architecture"))
    if not architecture:
        _issue(
            issues,
            "missing_interview_architecture",
            artifact,
            "면접 단계·방식·발표·과제 여부를 구분한 구조 패킷이 없습니다.",
            "REVIEW_REQUIRED",
        )
    else:
        for key in ("stage", "format", "duration", "panel", "presentation", "case", "group_discussion"):
            item = _object(architecture.get(key))
            if item.get("status") not in _ARCHITECTURE_STATUSES:
                _issue(issues, "invalid_interview_architecture_status", artifact, f"interview_architecture.{key}.status가 잘못되었습니다.")

    competencies = _rows(payload.get("competencies"))
    competency_ids = _unique_ids(
        competencies,
        "competency_id",
        artifact=artifact,
        label="competencies",
        issues=issues,
    )
    if not 4 <= len(competencies) <= 6:
        _issue(issues, "competency_count_review", artifact, "핵심 역량은 4~6개로 압축하는 편이 좋습니다.", "REVIEW_REQUIRED")
    for row in competencies:
        if not str(row.get("definition", "")).strip() or not _strings(row.get("observable_behaviors")):
            _issue(issues, "incomplete_competency", artifact, "역량의 정확한 의미와 관찰 가능한 행동이 필요합니다.")

    defense_rows = _rows(payload.get("experience_defense"))
    defense_by_experience = {
        str(row.get("experience_id", "")).strip(): row
        for row in defense_rows
        if str(row.get("experience_id", "")).strip()
    }
    used_experiences = set().union(
        *(refs["experience_ids"] for refs in response_refs.values()),
        set(),
    )
    for experience_id in used_experiences:
        row = defense_by_experience.get(experience_id)
        if row is None:
            _issue(issues, "missing_experience_defense", artifact, f"핵심 경험 {experience_id}의 방어 원장이 없습니다.")
            continue
        depth = str(row.get("depth", ""))
        if depth not in _DEFENSE_DEPTHS:
            _issue(issues, "invalid_defense_depth", artifact, f"{experience_id}의 방어 깊이가 잘못되었습니다.")
            continue
        claim_ids = set(_strings(row.get("claim_ids")))
        if claim_ids - known_profile_claim_ids:
            _issue(issues, "unknown_defense_claim", artifact, f"{experience_id}가 확정 원장에 없는 claim을 참조합니다.")
        minimum = 4 if claim_ids & numeric_claim_ids else 3
        if int(depth[1]) < minimum:
            _issue(issues, "insufficient_defense_depth", artifact, f"{experience_id}는 D{minimum} 이상이어야 합니다.")
        if not _strings(row.get("direct_actions")) or not _strings(row.get("judgment_standards")):
            _issue(issues, "incomplete_experience_defense", artifact, f"{experience_id}의 직접 행동과 판단 기준이 필요합니다.")

    questions = _rows(payload.get("questions"))
    question_ids = _unique_ids(
        questions,
        "question_id",
        artifact=artifact,
        label="questions",
        issues=issues,
    )
    tier1_ids: set[str] = set()
    coverage: set[str] = set()
    for row in questions:
        question_id = str(row.get("question_id", "")).strip()
        tier = row.get("tier")
        if tier not in {1, 2, 3}:
            _issue(issues, "invalid_question_tier", artifact, f"{question_id or '<unknown>'}의 tier가 잘못되었습니다.")
        if row.get("question_type") not in _QUESTION_TYPES:
            _issue(issues, "invalid_interview_question_type", artifact, f"{question_id or '<unknown>'}의 질문 유형이 잘못되었습니다.")
        if row.get("probability") not in _PROBABILITIES:
            _issue(issues, "invalid_interview_probability", artifact, f"{question_id or '<unknown>'}의 출제 가능성 상태가 잘못되었습니다.")
        if tier == 1:
            tier1_ids.add(question_id)
            coverage.update(_strings(row.get("coverage_tags")))
        unknown_competencies = set(_strings(row.get("competency_ids"))) - competency_ids
        if unknown_competencies:
            _issue(issues, "unknown_question_competency", artifact, f"{question_id}가 알 수 없는 역량을 참조합니다.")
        unknown_experiences = set(_strings(row.get("experience_ids"))) - known_experience_ids
        if unknown_experiences:
            _issue(issues, "unknown_question_experience", artifact, f"{question_id}가 확정되지 않은 경험을 사용합니다.")
        if tier == 1 and row.get("evidence_scope", "SUBMITTED_DRAFT") != "CONFIRMED_LEDGER" and set(_strings(row.get("experience_ids"))) - submitted_experience_ids:
            _issue(issues, "question_experience_not_submitted", artifact, f"{question_id}가 최종 제출본에 없는 경험을 핵심 질문에 배정했습니다.")
    missing_coverage = _REQUIRED_TIER1_COVERAGE - coverage
    if missing_coverage:
        _issue(issues, "missing_tier1_coverage", artifact, "필수 면접 영역이 누락되었습니다: " + ", ".join(sorted(missing_coverage)))
    if len(tier1_ids) < 10:
        _issue(issues, "thin_tier1_question_set", artifact, "TIER 1 질문이 10개보다 적습니다.", "REVIEW_REQUIRED")
    if len(questions) < 25:
        _issue(issues, "thin_core_question_set", artifact, "핵심 질문 세트가 25개보다 적습니다.", "REVIEW_REQUIRED")

    cards = _rows(payload.get("answer_cards"))
    cards_by_question = {
        str(row.get("question_id", "")).strip(): row
        for row in cards
        if str(row.get("question_id", "")).strip()
    }
    missing_cards = tier1_ids - set(cards_by_question)
    if missing_cards:
        _issue(issues, "missing_tier1_answer_card", artifact, "TIER 1 답변 카드가 없습니다: " + ", ".join(sorted(missing_cards)))
    for question_id, row in cards_by_question.items():
        if question_id not in question_ids:
            _issue(issues, "unknown_answer_card_question", artifact, f"답변 카드가 알 수 없는 질문을 참조합니다: {question_id}")
        if not str(row.get("one_sentence_answer", "")).strip() or not str(row.get("judgment_standard", "")).strip():
            _issue(issues, "incomplete_answer_card", artifact, f"{question_id}의 첫 문장과 판단 기준이 필요합니다.")
        if not _strings(row.get("direct_actions")) or not str(row.get("job_connection", "")).strip():
            _issue(issues, "incomplete_answer_card", artifact, f"{question_id}의 직접 행동과 직무 연결이 필요합니다.")
        profile_refs = set(_strings(row.get("experience_claim_ids")))
        research_refs = set(_strings(row.get("research_claim_ids")))
        if profile_refs - known_profile_claim_ids:
            _issue(issues, "unknown_answer_card_claim", artifact, f"{question_id}가 확정 원장에 없는 claim을 참조합니다.")
        if research_refs - known_research_ids:
            _issue(issues, "unknown_answer_card_research", artifact, f"{question_id}가 공식 근거 원장에 없는 claim을 참조합니다.")
        source_indexes: list[int] = []
        for value in row.get("source_question_indexes", []) if isinstance(row.get("source_question_indexes"), list) else []:
            try:
                source_indexes.append(int(value))
            except (TypeError, ValueError):
                _issue(issues, "invalid_answer_card_source_question", artifact, f"{question_id}의 source_question_indexes가 잘못되었습니다.")
        scope = str(row.get("evidence_scope", "SUBMITTED_DRAFT"))
        if scope not in {"SUBMITTED_DRAFT", "CONFIRMED_LEDGER"}:
            _issue(issues, "invalid_answer_card_evidence_scope", artifact, f"{question_id}의 evidence_scope가 잘못되었습니다.")
        allowed_profile_refs = known_profile_claim_ids if scope == "CONFIRMED_LEDGER" else submitted_profile_claim_ids
        allowed_research_refs = submitted_research_ids
        if source_indexes and scope != "CONFIRMED_LEDGER":
            allowed_profile_refs = set().union(
                *(submitted_by_question.get(index, {}).get("claim_ids", set()) for index in source_indexes), set()
            )
            allowed_research_refs = set().union(
                *(submitted_by_question.get(index, {}).get("research_ids", set()) for index in source_indexes), set()
            )
            if any(index not in submitted_by_question for index in source_indexes):
                _issue(issues, "unknown_answer_card_source_question", artifact, f"{question_id}가 제출본에 없는 문항을 답변 근거로 지정했습니다.")
        if profile_refs - allowed_profile_refs:
            _issue(issues, "answer_card_claim_not_submitted", artifact, f"{question_id}가 연결된 최종 제출 문항 밖의 경험 claim을 사용합니다.")
        if research_refs - allowed_research_refs:
            _issue(issues, "answer_card_research_not_submitted", artifact, f"{question_id}가 연결된 최종 제출 문항 밖의 회사 claim을 사용합니다.")
        if payload.get("schema_version") == 2:
            spoken = _object(row.get("spoken_versions"))
            durations: list[int] = []
            text_lengths: list[int] = []
            spoken_texts: list[str] = []
            for version in ("brief", "standard", "detailed"):
                item = _object(spoken.get(version))
                seconds = item.get("target_seconds")
                text = str(item.get("text", "")).strip()
                if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0 or not text:
                    _issue(issues, "incomplete_spoken_version", artifact, f"{question_id}.{version} 말하기 버전이 불완전합니다.")
                    continue
                durations.append(seconds)
                text_lengths.append(len(text))
                spoken_texts.append(text)
            if len(durations) == 3 and durations != sorted(durations):
                _issue(issues, "invalid_spoken_duration_order", artifact, f"{question_id}의 말하기 시간 순서가 잘못되었습니다.")
            if len(text_lengths) == 3 and text_lengths != sorted(text_lengths):
                _issue(issues, "invalid_spoken_detail_order", artifact, f"{question_id}의 말하기 상세도 순서가 잘못되었습니다.")
            if any(_NUMBER.search(text) for text in spoken_texts) and not (
                profile_refs.intersection(numeric_claim_ids) or research_refs
            ):
                _issue(
                    issues,
                    "unapproved_spoken_metric",
                    artifact,
                    f"{question_id}의 말하기 답변에 수치 근거 참조가 없습니다.",
                )

    probes = _rows(payload.get("probes"))
    _unique_ids(probes, "probe_id", artifact=artifact, label="probes", issues=issues)
    probes_by_question: dict[str, list[dict[str, Any]]] = {}
    for row in probes:
        question_id = str(row.get("question_id", "")).strip()
        probes_by_question.setdefault(question_id, []).append(row)
        if question_id not in question_ids:
            _issue(issues, "unknown_probe_question", artifact, f"추가질문이 알 수 없는 질문을 참조합니다: {question_id}")
        if row.get("category") not in _PROBE_CATEGORIES:
            _issue(issues, "invalid_probe_category", artifact, f"{question_id}의 추가질문 범주가 잘못되었습니다.")
        if row.get("status") not in _PROBE_STATUSES:
            _issue(issues, "invalid_probe_status", artifact, f"{question_id}의 추가질문 방어 상태가 잘못되었습니다.")
        unknown_refs = set(_strings(row.get("experience_claim_ids"))) - known_profile_claim_ids
        unknown_refs |= set(_strings(row.get("research_claim_ids"))) - known_research_ids
        if unknown_refs:
            _issue(issues, "unknown_probe_evidence", artifact, f"{question_id} 추가질문이 알 수 없는 근거를 참조합니다.")
        card = cards_by_question.get(question_id, {})
        if set(_strings(row.get("experience_claim_ids"))) - set(_strings(card.get("experience_claim_ids"))):
            _issue(issues, "probe_claim_not_in_answer_card", artifact, f"{question_id} 추가질문이 답변 카드 밖의 경험 claim을 사용합니다.")
        if set(_strings(row.get("research_claim_ids"))) - set(_strings(card.get("research_claim_ids"))):
            _issue(issues, "probe_research_not_in_answer_card", artifact, f"{question_id} 추가질문이 답변 카드 밖의 회사 claim을 사용합니다.")
    for question_id in tier1_ids:
        rows = probes_by_question.get(question_id, [])
        categories = {row.get("category") for row in rows}
        if len(categories & _PROBE_CATEGORIES) < 5:
            _issue(issues, "insufficient_probe_tree", artifact, f"{question_id}의 추가질문 방향이 5개보다 적습니다.")
        unsafe = [row for row in rows if row.get("status") in {"WEAK", "CONFLICT", "UNKNOWN"}]
        if unsafe:
            _issue(issues, "unsafe_core_answer", artifact, f"{question_id}는 방어되지 않은 추가질문이 있어 핵심 답변으로 확정할 수 없습니다.")

    reverse_questions = _strings(payload.get("reverse_questions"))
    if not 2 <= len(reverse_questions) <= 3:
        _issue(issues, "reverse_question_count_review", artifact, "우선 역질문은 2~3개가 적절합니다.", "REVIEW_REQUIRED")
    if not _strings(payload.get("day_of_checklist")):
        _issue(issues, "missing_day_of_checklist", artifact, "면접 당일 체크리스트가 없습니다.")

    simulation = _object(payload.get("simulation_policy"))
    if not simulation:
        _issue(
            issues,
            "missing_simulation_policy",
            artifact,
            "질문을 한 번에 하나씩 제시하는 모의면접 운영 규칙이 없습니다.",
            "REVIEW_REQUIRED",
        )
    elif not bool(simulation.get("one_question_at_a_time")) or not bool(
        simulation.get("wait_for_user_answer")
    ):
        _issue(
            issues,
            "unsafe_simulation_policy",
            artifact,
            "모의면접은 질문 하나를 제시한 뒤 실제 답변을 기다려야 합니다.",
        )

    if payload.get("schema_version") == 2:
        delivery = _object(payload.get("delivery_evaluation"))
        if not _strings(delivery.get("content_criteria")) or not _strings(
            delivery.get("delivery_criteria")
        ):
            _issue(
                issues,
                "missing_delivery_evaluation_split",
                artifact,
                "면접 내용과 전달 방식의 평가 기준을 분리해야 합니다.",
            )
        unknown_policy = _object(payload.get("unknown_answer_policy"))
        for key in ("boundary_statement", "reasoning_bridge", "verification_commitment"):
            if not str(unknown_policy.get(key, "")).strip():
                _issue(
                    issues,
                    "incomplete_unknown_answer_policy",
                    artifact,
                    f"모르는 질문 대응의 {key}가 비어 있습니다.",
                )

    final_audit = _object(payload.get("final_audit"))
    if final_audit.get("status") not in {"PASS", "CONDITIONAL_PASS", "FAIL", "PENDING"}:
        _issue(issues, "invalid_interview_final_audit", artifact, "final_audit.status가 잘못되었습니다.")
    if final_audit.get("status") in {"PASS", "CONDITIONAL_PASS"} and not str(
        final_audit.get("largest_risk", "")
    ).strip():
        _issue(
            issues,
            "missing_interview_largest_risk",
            artifact,
            "최종 면접 감사에 가장 큰 위험이 기록되지 않았습니다.",
            "REVIEW_REQUIRED",
        )

    return package_id, package_version, issues


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: expected object")
    return value


def validate_run_prompt_contracts(
    run_dir: Path,
    *,
    target: str | None = None,
    responses: Iterable[Any] | None = None,
    write_report: bool = True,
) -> PromptContractReport:
    run_dir = run_dir.resolve()
    company_path = run_dir / COMPANY_CONTRACT_NAME
    interview_path = run_dir / INTERVIEW_CONTRACT_NAME
    present = (company_path.exists(), interview_path.exists())
    if not any(present):
        return PromptContractReport(
            False,
            CONTRACT_VERSION,
            None,
            None,
            None,
            None,
            (),
        )

    issues: list[ContractIssue] = []
    if not all(present):
        missing = INTERVIEW_CONTRACT_NAME if present[0] else COMPANY_CONTRACT_NAME
        _issue(issues, "incomplete_prompt_contract_pair", missing, f"통합 계약은 두 JSON 사이드카가 모두 필요합니다: {missing}")
        report = PromptContractReport(
            True,
            CONTRACT_VERSION,
            None,
            None,
            str(company_path) if present[0] else None,
            str(interview_path) if present[1] else None,
            tuple(issues),
        )
        if write_report:
            (run_dir / CONTRACT_REPORT_NAME).write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return report

    try:
        company = _load_object(company_path)
        interview = _load_object(interview_path)
        state = _load_object(run_dir / "run.json")
        ledger = _load_object(run_dir / "02_확정경험원장.json")
        research_value = json.loads((run_dir / "04_공식근거.json").read_text(encoding="utf-8"))
        if not isinstance(research_value, list):
            raise ValueError("04_공식근거.json: expected array")
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        _issue(issues, "invalid_prompt_contract_input", "run", str(error))
        report = PromptContractReport(
            True,
            CONTRACT_VERSION,
            None,
            None,
            str(company_path),
            str(interview_path),
            tuple(issues),
        )
        if write_report:
            (run_dir / CONTRACT_REPORT_NAME).write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return report

    target_value = target if target is not None else str(state.get("target", ""))
    experience_ids, profile_claim_ids, numeric_claim_ids = _known_ids_from_ledger(ledger)
    research_ids = {
        str(item.get("claim_id", "")).strip()
        for item in research_value
        if isinstance(item, dict) and str(item.get("claim_id", "")).strip()
    }
    if responses is None:
        draft_path = run_dir / "draft_final.json"
        if not draft_path.exists():
            draft_path = run_dir / "draft.json"
        try:
            response_value = json.loads(draft_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            _issue(issues, "invalid_contract_draft", draft_path.name, str(error))
            response_value = []
        responses = response_value if isinstance(response_value, list) else []
    response_refs = _response_reference_map(responses)

    package_id, package_version, company_issues = validate_company_contract(
        company,
        target=target_value,
        known_research_ids=research_ids,
        known_experience_ids=experience_ids,
        known_profile_claim_ids=profile_claim_ids,
    )
    issues.extend(company_issues)
    _, _, interview_issues = validate_interview_contract(
        interview,
        expected_package_id=package_id,
        expected_package_version=package_version,
        response_refs=response_refs,
        known_experience_ids=experience_ids,
        known_profile_claim_ids=profile_claim_ids,
        numeric_claim_ids=numeric_claim_ids,
        known_research_ids=research_ids,
    )
    issues.extend(interview_issues)

    report = PromptContractReport(
        True,
        CONTRACT_VERSION,
        package_id or None,
        package_version or None,
        str(company_path),
        str(interview_path),
        tuple(issues),
        company,
        interview,
    )
    if write_report:
        (run_dir / CONTRACT_REPORT_NAME).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def prompt_contract_context(run_dir: Path) -> dict[str, Any] | None:
    """rigorous 후보·심사에 전달할 검증 가능한 회사·면접 컨텍스트를 반환합니다."""
    company_path = run_dir / COMPANY_CONTRACT_NAME
    interview_path = run_dir / INTERVIEW_CONTRACT_NAME
    if not (company_path.exists() and interview_path.exists()):
        return None
    company = _load_object(company_path)
    interview = _load_object(interview_path)
    claim_rows = _rows(company.get("claim_ledger"))
    safe_company_claims = [
        {**row, "use_decision": decision}
        for row in claim_rows
        if (decision := company_claim_use_decision(row)) != "BLOCK"
    ]
    prohibited_company_claim_ids = [
        str(row.get("claim_id", ""))
        for row in claim_rows
        if company_claim_use_decision(row) == "BLOCK"
        and str(row.get("claim_id", "")).strip()
    ]
    defensible_experience_ids = [
        str(row.get("experience_id", ""))
        for row in _rows(interview.get("experience_defense"))
        if str(row.get("depth", "")) in {"D3", "D4", "D5"}
        and str(row.get("experience_id", "")).strip()
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "data_package_id": company.get("data_package_id"),
        "data_package_version": company.get("data_package_version"),
        "company_research": {
            "entity": company.get("entity"),
            "safe_claims": safe_company_claims,
            "prohibited_claim_ids": prohibited_company_claim_ids,
            "business_model": company.get("business_model"),
            "strategy_execution": company.get("strategy_execution"),
            "financial_analysis": company.get("financial_analysis"),
            "competitor_analysis": company.get("competitor_analysis"),
            "culture_analysis": company.get("culture_analysis"),
            "market_position": company.get("market_position"),
            "recent_performance": company.get("recent_performance"),
            "research_completeness": company.get("research_completeness"),
            "interview_implications": company.get("interview_implications"),
            "role_value_map": company.get("role_value_map"),
            "applicant_bridge": company.get("applicant_bridge"),
            "red_team": company.get("red_team"),
            "first_90_days": company.get("first_90_days"),
            "decision": company.get("decision"),
        },
        "interview_defense": {
            "submitted_claims": interview.get("submitted_claims"),
            "document_consistency": interview.get("document_consistency"),
            "interview_architecture": interview.get("interview_architecture"),
            "competencies": interview.get("competencies"),
            "experience_defense": interview.get("experience_defense"),
            "defensible_experience_ids": defensible_experience_ids,
            "questions": interview.get("questions"),
            "answer_cards": interview.get("answer_cards"),
            "probes": interview.get("probes"),
            "delivery_evaluation": interview.get("delivery_evaluation"),
            "unknown_answer_policy": interview.get("unknown_answer_policy"),
            "simulation_policy": interview.get("simulation_policy"),
        },
    }


def _contract_digest(run_dir: Path) -> str:
    digest = sha256()
    required = (
        "00_채용공고분석.json",
        "02_확정경험원장.json",
        "03_경험직무매칭.json",
        "04_공식근거.json",
    )
    for name in required:
        path = run_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"계약 초기화 전 필요한 파일이 없습니다: {name}")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def initialize_run_prompt_contracts(run_dir: Path) -> tuple[Path, Path]:
    """현재 동결 자료에서 두 JSON 템플릿을 만들며 기존 파일은 덮어쓰지 않습니다."""
    run_dir = run_dir.resolve()
    state = _load_object(run_dir / "run.json")
    digest = _contract_digest(run_dir)
    package_id = f"CAREER-DATA-{digest[:12].upper()}"
    package_version = "2.0"
    target = str(state.get("target", ""))
    company_path = run_dir / COMPANY_CONTRACT_NAME
    interview_path = run_dir / INTERVIEW_CONTRACT_NAME
    if company_path.exists() or interview_path.exists():
        raise FileExistsError("통합 계약 파일이 이미 있습니다. 기존 파일을 검토하거나 별도 실행 디렉터리를 사용하세요.")

    ledger = _load_object(run_dir / "02_확정경험원장.json")
    experience_ids, _, _ = _known_ids_from_ledger(ledger)
    try:
        draft = json.loads((run_dir / "draft.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        draft = []
    response_refs = _response_reference_map(draft if isinstance(draft, list) else [])
    submitted_claims = [
        {
            "question_index": index,
            "experience_ids": sorted(refs["experience_ids"]),
            "experience_claim_ids": sorted(refs["claim_ids"]),
            "research_claim_ids": sorted(refs["research_ids"]),
            "status": "CONFIRMED",
        }
        for index, refs in sorted(response_refs.items())
    ]
    used_experience_ids = sorted(
        set().union(*(refs["experience_ids"] for refs in response_refs.values()), set())
    )

    company = {
        "schema_version": 2,
        "contract_version": CONTRACT_VERSION,
        "data_package_id": package_id,
        "data_package_version": package_version,
        "target": target,
        "research_cutoff_date": "",
        "entity": {
            "legal_entity_name": "",
            "brand_name": "",
            "target_business_unit": "",
            "status": "UNVERIFIED",
        },
        "source_manifest": [],
        "claim_ledger": [],
        "business_model": {
            "core_customers": [],
            "customer_problem": "",
            "value_proposition": "",
            "revenue_logic": "",
            "major_costs": [],
            "critical_risks": [],
        },
        "strategy_execution": [],
        "financial_analysis": {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "",
            "metrics": [],
        },
        "competitor_analysis": {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "",
            "selection": [],
            "comparisons": [],
        },
        "culture_analysis": {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "",
            "evidence": [],
            "unknowns": [],
        },
        "market_position": {
            "target_market": "",
            "customer_alternatives": [],
            "competitor_selection_basis": "",
            "differentiators": [],
            "uncertainties": [],
        },
        "recent_performance": [],
        "research_completeness": {
            "answered_questions": [],
            "unresolved_questions": [],
            "stopping_reason": "",
        },
        "interview_implications": {
            "expected_questions": [],
            "reverse_questions": [],
            "prohibited_talking_points": [],
        },
        "role_value_map": [],
        "applicant_bridge": [
            {
                "requirement": "",
                "experience_id": experience_id,
                "experience_claim_ids": [],
                "fit_state": "UNKNOWN",
            }
            for experience_id in sorted(experience_ids)
        ],
        "red_team": {"strongest_counterargument": "", "critical_unknowns": []},
        "first_90_days": {
            "days_0_30": [],
            "days_31_60": [],
            "days_61_90": [],
        },
        "decision": {
            "status": "INSUFFICIENT_EVIDENCE",
            "main_reason": "",
            "strongest_support": "",
            "strongest_counterargument": "",
            "conditions_that_would_change_decision": [],
        },
    }
    interview = {
        "schema_version": 2,
        "contract_version": CONTRACT_VERSION,
        "data_package_id": package_id,
        "data_package_version": package_version,
        "submitted_claims": submitted_claims,
        "document_consistency": [],
        "interview_architecture": {
            key: {"value": "", "status": "UNKNOWN", "evidence": ""}
            for key in (
                "stage",
                "format",
                "duration",
                "panel",
                "presentation",
                "case",
                "group_discussion",
            )
        },
        "competencies": [],
        "experience_defense": [
            {
                "experience_id": experience_id,
                "depth": "D0",
                "claim_ids": sorted(
                    set().union(
                        *(refs["claim_ids"] for refs in response_refs.values() if experience_id in refs["experience_ids"]),
                        set(),
                    )
                ),
                "direct_actions": [],
                "judgment_standards": [],
                "limitations": [],
            }
            for experience_id in used_experience_ids
        ],
        "questions": [],
        "answer_cards": [],
        "probes": [],
        "reverse_questions": [],
        "day_of_checklist": [],
        "delivery_evaluation": {
            "content_criteria": [],
            "delivery_criteria": [],
        },
        "unknown_answer_policy": {
            "boundary_statement": "",
            "reasoning_bridge": "",
            "verification_commitment": "",
        },
        "simulation_policy": {
            "mode": "RANDOM_MIXED",
            "feedback_timing": "AFTER_FULL_INTERVIEW",
            "difficulty": "REALISTIC",
            "one_question_at_a_time": True,
            "wait_for_user_answer": True,
        },
        "final_audit": {
            "status": "PENDING",
            "strongest_point": "",
            "largest_risk": "",
            "priority_revisions": [],
        },
    }
    company_path.write_text(json.dumps(company, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    interview_path.write_text(json.dumps(interview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return company_path, interview_path
