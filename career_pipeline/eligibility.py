"""Phase 2 applicant, posting, and deterministic eligibility contracts.

The evaluator only makes a positive decision from structured, explicit data.
Natural-language or missing requirements are represented as ``unknown`` and
therefore lead to ``manual_review`` rather than an inferred pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from .models import (
    ApplicantExperience,
    ApplicantLocation,
    ApplicantProfile,
    CertificationRecord,
    DecisionReason,
    EducationRecord,
    EligibilityDecision,
    EligibilityRule,
    PostingRecord,
    RuleEvaluation,
)
from .posting_schema import PostingAnalysis
from .profile_schema import ExperienceLedger, ledger_to_dict, validate_ledger


ELIGIBILITY_STATUSES = {
    "eligible",
    "eligible_with_gaps",
    "manual_review",
    "ineligible",
}
RULE_STATUSES = {"met", "not_met", "unknown"}
SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LEVEL_RANK = {
    "고졸": 1,
    "고등학교": 1,
    "high_school": 1,
    "high school": 1,
    "highschool": 1,
    "associate": 2,
    "전문학사": 2,
    "전문대": 2,
    "bachelor": 3,
    "bachelor's": 3,
    "bachelors": 3,
    "학사": 3,
    "4년제": 3,
    "master": 4,
    "master's": 4,
    "masters": 4,
    "석사": 4,
    "doctorate": 5,
    "박사": 5,
}
_EXPERIENCE_STATUSES = {"confirmed", "proposed", "stale", "unknown"}
_CERTIFICATION_STATUSES = {"valid", "expired", "expected", "unknown"}
_EDUCATION_STATUSES = {"graduated", "expected", "enrolled", "unknown"}
_LOCATION_KINDS = {"work_location", "residence", "school_region", "regional_talent", "unknown"}
_RULE_KINDS = {"education", "experience", "certification", "location", "work_authorization", "custom"}
_SOURCE_STATUSES = {"verified_domain", "user_attested", "unverified"}
_POSTING_STATUSES = {"active", "expired", "closed", "manual_review"}
_CERTIFICATION_ALIASES = {
    "정보처리기사": {"정보처리기사", "engineer information processing"},
}
_LOCATION_ALIASES = {
    "서울": {"서울", "서울특별시"},
    "부산": {"부산", "부산광역시"},
    "대구": {"대구", "대구광역시"},
    "인천": {"인천", "인천광역시"},
    "광주": {"광주", "광주광역시"},
    "대전": {"대전", "대전광역시"},
    "울산": {"울산", "울산광역시"},
    "세종": {"세종", "세종특별자치시"},
    "경기": {"경기", "경기도"},
    "강원": {"강원", "강원도", "강원특별자치도"},
    "충북": {"충북", "충청북도"},
    "충남": {"충남", "충청남도"},
    "전북": {"전북", "전라북도", "전북특별자치도"},
    "전남": {"전남", "전라남도"},
    "경북": {"경북", "경상북도"},
    "경남": {"경남", "경상남도"},
    "제주": {"제주", "제주도", "제주특별자치도"},
}


class EligibilityValidationError(ValueError):
    """Raised when a Phase 2 JSON contract is malformed or unsafe to use."""

    def __init__(self, issues: list[str] | tuple[str, ...]):
        self.issues = tuple(issues)
        super().__init__("\n".join(self.issues))


@dataclass(frozen=True)
class PostingComparison:
    key: str
    event: str
    previous_body_sha256: str | None
    current_body_sha256: str


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EligibilityValidationError([f"{path}: expected object"])
    return value


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise EligibilityValidationError([f"{path}: expected non-empty string"])
    return value


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _string_tuple(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EligibilityValidationError([f"{path}: expected string array"])
    return tuple(value)


def _iso_date(value: str | None, path: str) -> None:
    if value is None:
        return
    try:
        date.fromisoformat(value.replace("Z", "+00:00")[:10])
    except ValueError as error:
        raise EligibilityValidationError([f"{path}: expected ISO date"])


def _timezone_from_timestamp(value: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    offset = parsed.utcoffset()
    if offset is None:
        return None
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def _sha256(value: str, path: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise EligibilityValidationError([f"{path}: expected lowercase SHA-256"])


def _unique_ids(values: list[str], path: str) -> list[str]:
    seen: set[str] = set()
    issues: list[str] = []
    for value in values:
        if value in seen:
            issues.append(f"{path}: duplicate ID {value}")
        seen.add(value)
    return issues


def validate_applicant_profile(profile: ApplicantProfile) -> ApplicantProfile:
    issues: list[str] = []
    if profile.schema_version != SCHEMA_VERSION:
        issues.append("schema_version: expected 1")
    if not profile.profile_id:
        issues.append("profile_id: must not be empty")
    if not profile.generated_at:
        issues.append("generated_at: must not be empty")
    issues.extend(
        _unique_ids(
            [item.experience_id for item in profile.experiences],
            "experiences",
        )
    )
    for index, item in enumerate(profile.experiences):
        if not item.experience_id or not item.title:
            issues.append(f"experiences[{index}]: experience_id and title are required")
        if item.months is not None and (isinstance(item.months, bool) or item.months < 0):
            issues.append(f"experiences[{index}].months: expected non-negative integer")
        if item.status not in _EXPERIENCE_STATUSES:
            issues.append(f"experiences[{index}].status: unknown experience status")
        _iso_date(item.start_date, f"experiences[{index}].start_date")
        _iso_date(item.end_date, f"experiences[{index}].end_date")
        if item.is_current is not None and not isinstance(item.is_current, bool):
            issues.append(f"experiences[{index}].is_current: expected boolean or null")
        if item.start_date and item.end_date and item.start_date > item.end_date:
            issues.append(f"experiences[{index}]: start_date must not be after end_date")
    for index, item in enumerate(profile.education):
        if not item.level:
            issues.append(f"education[{index}].level: must not be empty")
        _iso_date(item.graduation_date, f"education[{index}].graduation_date")
        if item.status not in _EDUCATION_STATUSES:
            issues.append(f"education[{index}].status: unknown education status")
    for index, item in enumerate(profile.certifications):
        if not item.name:
            issues.append(f"certifications[{index}].name: must not be empty")
        _iso_date(item.issued_at, f"certifications[{index}].issued_at")
        _iso_date(item.expires_at, f"certifications[{index}].expires_at")
        _iso_date(item.expected_at, f"certifications[{index}].expected_at")
        if item.status not in _CERTIFICATION_STATUSES:
            issues.append(f"certifications[{index}].status: unknown certification status")
        if item.verified is not None and not isinstance(item.verified, bool):
            issues.append(f"certifications[{index}].verified: expected boolean or null")
    seen_certifications: list[str] = []
    for item in profile.certifications:
        if any(_certification_match(item.name, previous) for previous in seen_certifications):
            issues.append(f"certifications: duplicate certification {item.name}")
        seen_certifications.append(item.name)
    for index, item in enumerate(profile.location_records):
        if not item.name:
            issues.append(f"location_records[{index}].name: must not be empty")
        if item.kind not in _LOCATION_KINDS:
            issues.append(f"location_records[{index}].kind: unknown location kind")
        _iso_date(item.valid_from, f"location_records[{index}].valid_from")
        _iso_date(item.valid_until, f"location_records[{index}].valid_until")
        if item.duration_months is not None and (
            not isinstance(item.duration_months, int)
            or isinstance(item.duration_months, bool)
            or item.duration_months < 0
        ):
            issues.append(f"location_records[{index}].duration_months: expected non-negative integer")
    if profile.experience_ledger_sha256 is not None:
        _sha256(profile.experience_ledger_sha256, "experience_ledger_sha256")
    if issues:
        raise EligibilityValidationError(issues)
    return profile


def validate_posting_record(record: PostingRecord) -> PostingRecord:
    issues: list[str] = []
    if record.schema_version != SCHEMA_VERSION:
        issues.append("schema_version: expected 1")
    for field_name in ("posting_id", "url", "title", "organization", "role", "retrieved_at"):
        if not getattr(record, field_name):
            issues.append(f"{field_name}: must not be empty")
    if not record.parser_version:
        issues.append("parser_version: must not be empty")
    if record.timezone is not None and not re.fullmatch(r"[+-][0-9]{2}:[0-9]{2}", record.timezone):
        issues.append("timezone: expected numeric UTC offset")
    _sha256(record.body_sha256, "body_sha256")
    if record.question_hash is not None:
        _sha256(record.question_hash, "question_hash")
    if record.raw_sha256 is not None:
        _sha256(record.raw_sha256, "raw_sha256")
    if record.normalized_content_sha256 is not None:
        _sha256(record.normalized_content_sha256, "normalized_content_sha256")
    if record.url:
        parsed = urlsplit(record.url)
        if parsed.scheme not in {"https", "file"}:
            issues.append("url: expected HTTPS or local file URL")
    if record.canonical_url:
        parsed_canonical = urlsplit(record.canonical_url)
        if parsed_canonical.scheme not in {"https", "file"}:
            issues.append("canonical_url: expected HTTPS or local file URL")
    if record.source_status not in _SOURCE_STATUSES:
        issues.append("source_status: unknown source status")
    _iso_date(record.published_at, "published_at")
    _iso_date(record.deadline_at, "deadline_at")
    _iso_date(record.first_seen_at, "first_seen_at")
    _iso_date(record.last_seen_at, "last_seen_at")
    if record.status not in _POSTING_STATUSES:
        issues.append("status: unknown posting status")
    if record.source_id is not None and not record.source_id.strip():
        issues.append("source_id: must not be empty when provided")
    if any(not item.strip() for item in record.alias_urls):
        issues.append("alias_urls: must not contain empty URLs")
    rule_ids = [item.rule_id for item in (*record.required_rules, *record.preferred_rules)]
    issues.extend(_unique_ids(rule_ids, "rules"))
    for index, rule in enumerate(record.required_rules):
        if rule.kind not in _RULE_KINDS:
            issues.append(f"required_rules[{index}].kind: unsupported eligibility rule kind")
        if not isinstance(rule.required, bool):
            issues.append(f"required_rules[{index}].required: expected boolean")
        if rule.parse_status not in {"parsed", "manual_review"}:
            issues.append(f"required_rules[{index}].parse_status: unknown parse status")
        if rule.parse_status == "manual_review" and not rule.source_excerpt:
            issues.append(f"required_rules[{index}].source_excerpt: required for manual parse status")
        _iso_date(rule.comparison_date, f"required_rules[{index}].comparison_date")
        if rule.confidence is not None and (not isinstance(rule.confidence, (int, float)) or not 0 <= rule.confidence <= 1):
            issues.append(f"required_rules[{index}].confidence: expected a number from 0 to 1")
        if not rule.required:
            issues.append(f"required_rules[{index}].required: must be true")
    for index, rule in enumerate(record.preferred_rules):
        if rule.kind not in _RULE_KINDS:
            issues.append(f"preferred_rules[{index}].kind: unsupported eligibility rule kind")
        if not isinstance(rule.required, bool):
            issues.append(f"preferred_rules[{index}].required: expected boolean")
        if rule.parse_status not in {"parsed", "manual_review"}:
            issues.append(f"preferred_rules[{index}].parse_status: unknown parse status")
        if rule.parse_status == "manual_review" and not rule.source_excerpt:
            issues.append(f"preferred_rules[{index}].source_excerpt: required for manual parse status")
        _iso_date(rule.comparison_date, f"preferred_rules[{index}].comparison_date")
        if rule.confidence is not None and (not isinstance(rule.confidence, (int, float)) or not 0 <= rule.confidence <= 1):
            issues.append(f"preferred_rules[{index}].confidence: expected a number from 0 to 1")
        if rule.required:
            issues.append(f"preferred_rules[{index}].required: must be false")
    if issues:
        raise EligibilityValidationError(issues)
    return record


def validate_decision(decision: EligibilityDecision) -> EligibilityDecision:
    issues: list[str] = []
    if decision.schema_version != SCHEMA_VERSION:
        issues.append("schema_version: expected 1")
    if decision.status not in ELIGIBILITY_STATUSES:
        issues.append(f"status: expected one of {sorted(ELIGIBILITY_STATUSES)}")
    if not decision.decision_id or not decision.posting_id or not decision.profile_id:
        issues.append("decision_id, posting_id, and profile_id are required")
    if decision.human_review_required != (decision.status in {"manual_review", "eligible_with_gaps"}):
        issues.append("human_review_required: inconsistent with status")
    for index, item in enumerate(decision.rule_evaluations):
        if item.status not in RULE_STATUSES:
            issues.append(f"rule_evaluations[{index}].status: unknown rule status")
        if not item.reason_code or not item.reason:
            issues.append(f"rule_evaluations[{index}]: reason_code and reason are required")
    for index, item in enumerate(decision.reasons):
        if not item.code or not item.message:
            issues.append(f"reasons[{index}]: code and message are required")
    if issues:
        raise EligibilityValidationError(issues)
    return decision


def _education_from_dict(value: Any, path: str) -> EducationRecord:
    mapping = _require_mapping(value, path)
    completed = mapping.get("completed")
    if completed is not None and not isinstance(completed, bool):
        raise EligibilityValidationError([f"{path}.completed: expected boolean or null"])
    return EducationRecord(
        level=_string(mapping.get("level"), f"{path}.level"),
        field=_string(mapping.get("field", ""), f"{path}.field", allow_empty=True),
        completed=completed,
        graduation_date=_optional_string(mapping.get("graduation_date"), f"{path}.graduation_date"),
        status=_string(mapping.get("status", "unknown"), f"{path}.status"),
    )


def _experience_from_dict(value: Any, path: str) -> ApplicantExperience:
    mapping = _require_mapping(value, path)
    months = mapping.get("months")
    if months is not None and (not isinstance(months, int) or isinstance(months, bool)):
        raise EligibilityValidationError([f"{path}.months: expected integer or null"])
    return ApplicantExperience(
        experience_id=_string(mapping.get("experience_id"), f"{path}.experience_id"),
        title=_string(mapping.get("title"), f"{path}.title"),
        months=months,
        skills=_string_tuple(mapping.get("skills", []), f"{path}.skills"),
        locations=_string_tuple(mapping.get("locations", []), f"{path}.locations"),
        status=_string(mapping.get("status", "unknown"), f"{path}.status"),
        start_date=_optional_string(mapping.get("start_date"), f"{path}.start_date"),
        end_date=_optional_string(mapping.get("end_date"), f"{path}.end_date"),
        is_current=mapping.get("is_current"),
        employment_type=_optional_string(mapping.get("employment_type"), f"{path}.employment_type"),
        claim_fields=_string_tuple(mapping.get("claim_fields", []), f"{path}.claim_fields"),
        evidence_paths=_string_tuple(mapping.get("evidence_paths", []), f"{path}.evidence_paths"),
    )


def _certification_from_dict(value: Any, path: str) -> CertificationRecord:
    mapping = _require_mapping(value, path)
    return CertificationRecord(
        name=_string(mapping.get("name"), f"{path}.name"),
        issued_at=_optional_string(mapping.get("issued_at"), f"{path}.issued_at"),
        expires_at=_optional_string(mapping.get("expires_at"), f"{path}.expires_at"),
        status=_string(mapping.get("status", "unknown"), f"{path}.status"),
        verified=mapping.get("verified"),
        level=_optional_string(mapping.get("level"), f"{path}.level"),
        expected_at=_optional_string(mapping.get("expected_at"), f"{path}.expected_at"),
    )


def _location_from_dict(value: Any, path: str) -> ApplicantLocation:
    mapping = _require_mapping(value, path)
    return ApplicantLocation(
        name=_string(mapping.get("name"), f"{path}.name"),
        kind=_string(mapping.get("kind", "unknown"), f"{path}.kind"),
        valid_from=_optional_string(mapping.get("valid_from"), f"{path}.valid_from"),
        valid_until=_optional_string(mapping.get("valid_until"), f"{path}.valid_until"),
        duration_months=mapping.get("duration_months"),
    )


def applicant_profile_from_dict(value: Any) -> ApplicantProfile:
    mapping = _require_mapping(value, "$")
    profile = ApplicantProfile(
        schema_version=mapping.get("schema_version", SCHEMA_VERSION),
        profile_id=_string(mapping.get("profile_id"), "$.profile_id"),
        generated_at=_string(mapping.get("generated_at"), "$.generated_at"),
        experience_ledger_path=_optional_string(
            mapping.get("experience_ledger_path"), "$.experience_ledger_path"
        ),
        experiences=tuple(
            _experience_from_dict(item, f"$.experiences[{index}]")
            for index, item in enumerate(mapping.get("experiences", []))
        ),
        education=tuple(
            _education_from_dict(item, f"$.education[{index}]")
            for index, item in enumerate(mapping.get("education", []))
        ),
        certifications=tuple(
            _certification_from_dict(item, f"$.certifications[{index}]")
            for index, item in enumerate(mapping.get("certifications", []))
        ),
        locations=_string_tuple(mapping.get("locations", []), "$.locations"),
        personal_info_ref=_optional_string(mapping.get("personal_info_ref"), "$.personal_info_ref"),
        experience_ledger_sha256=_optional_string(
            mapping.get("experience_ledger_sha256"), "$.experience_ledger_sha256"
        ),
        location_records=tuple(
            _location_from_dict(item, f"$.location_records[{index}]")
            for index, item in enumerate(mapping.get("location_records", []))
        ),
        projection_warnings=_string_tuple(
            mapping.get("projection_warnings", []), "$.projection_warnings"
        ),
    )
    return validate_applicant_profile(profile)


def _rule_from_dict(value: Any, path: str, *, required: bool) -> EligibilityRule:
    mapping = _require_mapping(value, path)
    criteria = mapping.get("criteria", {})
    if not isinstance(criteria, dict):
        raise EligibilityValidationError([f"{path}.criteria: expected object"])
    kind = _string(mapping.get("kind"), f"{path}.kind")
    if kind not in _RULE_KINDS:
        raise EligibilityValidationError([f"{path}.kind: unsupported eligibility rule kind"])
    return EligibilityRule(
        rule_id=_string(mapping.get("rule_id"), f"{path}.rule_id"),
        kind=kind,
        description=_string(mapping.get("description"), f"{path}.description"),
        required=required,
        criteria=dict(criteria),
        parse_status=_string(mapping.get("parse_status", "parsed"), f"{path}.parse_status"),
        source_excerpt=_optional_string(mapping.get("source_excerpt"), f"{path}.source_excerpt"),
        source_location=_optional_string(mapping.get("source_location"), f"{path}.source_location"),
        operator=_optional_string(mapping.get("operator"), f"{path}.operator"),
        expected_value=mapping.get("expected_value"),
        comparison_date=_optional_string(mapping.get("comparison_date"), f"{path}.comparison_date"),
        confidence=mapping.get("confidence"),
    )


def posting_record_from_dict(value: Any) -> PostingRecord:
    mapping = _require_mapping(value, "$")
    record = PostingRecord(
        schema_version=mapping.get("schema_version", SCHEMA_VERSION),
        posting_id=_string(mapping.get("posting_id"), "$.posting_id"),
        url=_string(mapping.get("url", ""), "$.url", allow_empty=True),
        official_domain=_optional_string(mapping.get("official_domain"), "$.official_domain"),
        published_at=_optional_string(mapping.get("published_at"), "$.published_at"),
        deadline_at=_optional_string(mapping.get("deadline_at"), "$.deadline_at"),
        title=_string(mapping.get("title"), "$.title"),
        organization=_string(mapping.get("organization"), "$.organization"),
        role=_string(mapping.get("role"), "$.role"),
        body_sha256=_string(mapping.get("body_sha256"), "$.body_sha256"),
        retrieved_at=_string(mapping.get("retrieved_at"), "$.retrieved_at"),
        source_status=_string(mapping.get("source_status"), "$.source_status"),
        locations=_string_tuple(mapping.get("locations", []), "$.locations"),
        required_rules=tuple(
            _rule_from_dict(item, f"$.required_rules[{index}]", required=True)
            for index, item in enumerate(mapping.get("required_rules", []))
        ),
        preferred_rules=tuple(
            _rule_from_dict(item, f"$.preferred_rules[{index}]", required=False)
            for index, item in enumerate(mapping.get("preferred_rules", []))
        ),
        question_hash=_optional_string(mapping.get("question_hash"), "$.question_hash"),
        canonical_url=_optional_string(mapping.get("canonical_url"), "$.canonical_url"),
        timezone=_optional_string(mapping.get("timezone"), "$.timezone"),
        parser_version=_string(mapping.get("parser_version", "1"), "$.parser_version"),
        raw_sha256=_optional_string(mapping.get("raw_sha256"), "$.raw_sha256"),
        normalized_content_sha256=_optional_string(
            mapping.get("normalized_content_sha256"), "$.normalized_content_sha256"
        ),
        source_id=_optional_string(mapping.get("source_id"), "$.source_id"),
        employment_type=_string_tuple(mapping.get("employment_type", []), "$.employment_type"),
        status=_string(mapping.get("status", "active"), "$.status"),
        first_seen_at=_optional_string(mapping.get("first_seen_at"), "$.first_seen_at"),
        last_seen_at=_optional_string(mapping.get("last_seen_at"), "$.last_seen_at"),
        source_excerpt=_optional_string(mapping.get("source_excerpt"), "$.source_excerpt"),
        unparsed_requirements=_string_tuple(
            mapping.get("unparsed_requirements", []), "$.unparsed_requirements"
        ),
        alias_urls=_string_tuple(mapping.get("alias_urls", []), "$.alias_urls"),
    )
    return validate_posting_record(record)


def _evaluation_from_dict(value: Any, path: str) -> RuleEvaluation:
    mapping = _require_mapping(value, path)
    required = mapping.get("required")
    if not isinstance(required, bool):
        raise EligibilityValidationError([f"{path}.required: expected boolean"])
    return RuleEvaluation(
        rule_id=_string(mapping.get("rule_id"), f"{path}.rule_id"),
        required=required,
        status=_string(mapping.get("status"), f"{path}.status"),
        reason=_string(mapping.get("reason"), f"{path}.reason"),
        evidence=_string_tuple(mapping.get("evidence", []), f"{path}.evidence"),
        reason_code=_string(mapping.get("reason_code", "unspecified"), f"{path}.reason_code"),
        field=_optional_string(mapping.get("field"), f"{path}.field"),
    )


def _reason_from_dict(value: Any, path: str) -> DecisionReason:
    if isinstance(value, str):
        return DecisionReason("legacy_reason", None, value)
    mapping = _require_mapping(value, path)
    return DecisionReason(
        code=_string(mapping.get("code"), f"{path}.code"),
        field=_optional_string(mapping.get("field"), f"{path}.field"),
        message=_string(mapping.get("message"), f"{path}.message"),
    )


def decision_from_dict(value: Any) -> EligibilityDecision:
    mapping = _require_mapping(value, "$")
    human_review_required = mapping.get("human_review_required")
    if not isinstance(human_review_required, bool):
        raise EligibilityValidationError(["$.human_review_required: expected boolean"])
    decision = EligibilityDecision(
        schema_version=mapping.get("schema_version", SCHEMA_VERSION),
        decision_id=_string(mapping.get("decision_id"), "$.decision_id"),
        posting_id=_string(mapping.get("posting_id"), "$.posting_id"),
        profile_id=_string(mapping.get("profile_id"), "$.profile_id"),
        status=_string(mapping.get("status"), "$.status"),
        evaluated_at=_string(mapping.get("evaluated_at"), "$.evaluated_at"),
        rule_evaluations=tuple(
            _evaluation_from_dict(item, f"$.rule_evaluations[{index}]")
            for index, item in enumerate(mapping.get("rule_evaluations", []))
        ),
        reasons=tuple(
            _reason_from_dict(item, f"$.reasons[{index}]")
            for index, item in enumerate(mapping.get("reasons", []))
        ),
        human_review_required=human_review_required,
    )
    return validate_decision(decision)


def load_applicant_profile(path: Path) -> ApplicantProfile:
    return applicant_profile_from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_posting_record(path: Path) -> PostingRecord:
    return posting_record_from_dict(json.loads(path.read_text(encoding="utf-8")))


def decision_to_dict(decision: EligibilityDecision) -> dict[str, Any]:
    return asdict(validate_decision(decision))


def posting_record_to_dict(record: PostingRecord) -> dict[str, Any]:
    return asdict(validate_posting_record(record))


def applicant_profile_to_dict(profile: ApplicantProfile) -> dict[str, Any]:
    return asdict(validate_applicant_profile(profile))


def applicant_profile_from_ledger(
    ledger: ExperienceLedger,
    *,
    profile_id: str,
    generated_at: str | None = None,
    ledger_path: str | None = None,
) -> ApplicantProfile:
    """Create a safe profile projection using confirmed experiences only."""
    validate_ledger(ledger)
    ledger_payload = json.dumps(
        ledger_to_dict(ledger), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    ledger_sha256 = (
        sha256(Path(ledger_path).read_bytes()).hexdigest()
        if ledger_path and Path(ledger_path).is_file()
        else sha256(ledger_payload).hexdigest()
    )
    experiences = tuple(
        ApplicantExperience(
            experience_id=item.experience_id,
            title=item.title,
            months=_period_months(item.period),
            skills=item.competencies,
            status="confirmed",
            start_date=_period_value(item.period, "start"),
            end_date=_period_value(item.period, "end"),
            is_current=_period_bool(item.period, "current"),
            employment_type=_period_value(item.period, "employment_type"),
            claim_fields=tuple(claim.field for claim in item.claims if claim.status == "confirmed"),
            evidence_paths=tuple(
                evidence.source_path
                for claim in item.claims
                if claim.status == "confirmed"
                for evidence in claim.evidence
            ),
        )
        for item in ledger.experiences
        if item.status == "confirmed"
    )
    profile = ApplicantProfile(
        schema_version=SCHEMA_VERSION,
        profile_id=profile_id,
        generated_at=generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        experience_ledger_path=ledger_path,
        experiences=experiences,
        education=(),
        certifications=(),
        locations=(),
        experience_ledger_sha256=ledger_sha256,
        projection_warnings=(
            "education_not_projected_from_experience_ledger",
            "certifications_not_projected_from_experience_ledger",
            "locations_not_projected_from_experience_ledger",
        ),
    )
    return validate_applicant_profile(profile)


def is_profile_stale(profile: ApplicantProfile, ledger_path: Path) -> bool:
    """Detect a profile produced from an older ledger without rewriting it."""

    if not profile.experience_ledger_sha256 or not ledger_path.is_file():
        return True
    return profile.experience_ledger_sha256 != sha256(ledger_path.read_bytes()).hexdigest()


def _period_value(period: Mapping[str, Any] | None, key: str) -> str | None:
    if not isinstance(period, dict):
        return None
    for candidate in (key, f"{key}_date"):
        value = period.get(candidate)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _period_bool(period: Mapping[str, Any] | None, key: str) -> bool | None:
    if not isinstance(period, dict):
        return None
    value = period.get(key, period.get(f"is_{key}"))
    return value if isinstance(value, bool) else None


def _period_months(period: Mapping[str, Any] | None) -> int | None:
    start = _period_value(period, "start")
    end = _period_value(period, "end")
    if not start or not end:
        return None
    try:
        return _months_between(date.fromisoformat(start[:10]), date.fromisoformat(end[:10]))
    except ValueError:
        return None


def posting_record_from_analysis(
    analysis: PostingAnalysis,
    *,
    posting_id: str | None = None,
    normalized_content_sha256: str | None = None,
) -> PostingRecord:
    """Project the existing posting analysis into the Phase 2 record."""

    source = analysis.source
    url = source.location
    if not url.startswith(("https://", "http://", "file://")):
        url = Path(url).resolve().as_uri()
    generated_id = canonical_posting_id(
        url=canonicalize_url(url),
        organization=analysis.organization,
        role=analysis.role,
    )
    required_rules = tuple(
        EligibilityRule(
            rule_id=f"required-{index}",
            kind="custom",
            description=value,
            required=True,
            criteria={"text": value},
            parse_status="manual_review",
            source_excerpt=value,
            source_location=source.location,
        )
        for index, value in enumerate(analysis.requirements, start=1)
    )
    preferred_rules = tuple(
        EligibilityRule(
            rule_id=f"preferred-{index}",
            kind="custom",
            description=value,
            required=False,
            criteria={"text": value},
            parse_status="manual_review",
            source_excerpt=value,
            source_location=source.location,
        )
        for index, value in enumerate(analysis.preferences, start=1)
    )
    question_payload = json.dumps(
        [(item.index, item.prompt, item.character_limit) for item in analysis.questions],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    question_hash = sha256(question_payload).hexdigest()
    record = PostingRecord(
        schema_version=SCHEMA_VERSION,
        posting_id=posting_id or generated_id,
        url=url,
        official_domain=(urlsplit(url).hostname if url.startswith("https://") else None),
        published_at=None,
        deadline_at=None,
        title=analysis.target,
        organization=analysis.organization,
        role=analysis.role,
        body_sha256=source.content_sha256,
        retrieved_at=source.retrieved_at,
        source_status=source.official_status,
        locations=analysis.locations,
        required_rules=required_rules,
        preferred_rules=preferred_rules,
        question_hash=question_hash,
        canonical_url=canonicalize_url(url),
        timezone=_timezone_from_timestamp(source.retrieved_at),
        parser_version="1",
        raw_sha256=source.content_sha256,
        normalized_content_sha256=normalized_content_sha256,
    )
    return validate_posting_record(record)


def normalized_posting_content_sha256(content: bytes) -> str:
    """Hash stable visible-ish content while ignoring markup and whitespace."""

    if content.startswith(b"PK") or content.startswith(b"%PDF"):
        return sha256(content).hexdigest()
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return sha256(text.encode("utf-8")).hexdigest()


def canonical_posting_id(*, url: str, organization: str, role: str) -> str:
    normalized = "|".join(
        item.strip().casefold()
        for item in (canonicalize_url(url), organization, role)
    )
    return "posting-" + sha256(normalized.encode("utf-8")).hexdigest()[:24]


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        host = parsed.hostname.casefold()
        if parsed.port and parsed.port not in {80, 443}:
            host = f"{host}:{parsed.port}"
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return f"{parsed.scheme.casefold()}://{host}{path}{('?' + parsed.query) if parsed.query else ''}"
    if parsed.scheme == "file":
        return parsed._replace(fragment="").geturl()
    return url.strip().rstrip("/")


def compare_postings(previous: PostingRecord | None, current: PostingRecord) -> PostingComparison:
    """Return a duplicate/change event without treating changed text as new."""

    key = current.posting_id or canonical_posting_id(
        url=current.url,
        organization=current.organization,
        role=current.role,
    )
    if previous is None:
        return PostingComparison(key, "new", None, current.body_sha256)
    previous_url = canonicalize_url(previous.canonical_url or previous.url)
    current_url = canonicalize_url(current.canonical_url or current.url)
    previous_comparison_hash = previous.normalized_content_sha256 or previous.body_sha256
    current_comparison_hash = current.normalized_content_sha256 or current.body_sha256
    if previous_url == current_url and previous_comparison_hash == current_comparison_hash:
        event = "exact_duplicate" if previous.body_sha256 == current.body_sha256 else "unchanged"
    elif previous_url != current_url and previous_comparison_hash == current_comparison_hash:
        event = "content_duplicate"
    elif previous.posting_id == current.posting_id or previous_url == current_url:
        event = "changed"
    else:
        event = "distinct"
    return PostingComparison(key, event, previous.body_sha256, current.body_sha256)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _level_rank(value: str) -> int:
    normalized = _normalize(value).replace("’", "'")
    return _LEVEL_RANK.get(normalized, 0)


def _months_between(start: date, end: date) -> int:
    if end < start:
        return 0
    return (end - start).days // 30


def _experience_total_months(
    experiences: list[ApplicantExperience], as_of: date
) -> int | None:
    dated: list[tuple[date, date]] = []
    undated: list[ApplicantExperience] = []
    for item in experiences:
        if item.start_date:
            try:
                start = date.fromisoformat(item.start_date[:10])
                if item.end_date:
                    end = date.fromisoformat(item.end_date[:10])
                elif item.is_current is True:
                    end = as_of
                else:
                    return None
                dated.append((start, min(end, as_of)))
            except ValueError:
                return None
        else:
            undated.append(item)
    if dated and undated:
        return None
    if not dated:
        if len(undated) == 1:
            return undated[0].months
        return None
    intervals = sorted((start, end) for start, end in dated if end >= start)
    if not intervals:
        return 0
    merged: list[list[date]] = [[intervals[0][0], intervals[0][1]]]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(_months_between(start, end) for start, end in merged)


def _alias_match(value: str, candidate: str, aliases: Mapping[str, set[str]]) -> bool:
    left = _normalize(value)
    right = _normalize(candidate)
    if left == right:
        return True
    for group in aliases.values():
        normalized = {_normalize(item) for item in group}
        if left in normalized and right in normalized:
            return True
    return False


def _certification_match(required: str, actual: str) -> bool:
    return _alias_match(required, actual, _CERTIFICATION_ALIASES)


def _location_match(required: str, actual: str) -> bool:
    return _alias_match(required, actual, _LOCATION_ALIASES)


def _criteria_values(criteria: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = criteria.get(key, ())
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


def _evaluate_education(
    rule: EligibilityRule, profile: ApplicantProfile, as_of: date
) -> RuleEvaluation:
    criteria = rule.criteria
    minimum = criteria.get("minimum_level", criteria.get("level"))
    required_field = str(criteria.get("field", "")).strip()
    if not isinstance(minimum, str) or _level_rank(minimum) == 0:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "학력 기준이 구조화되지 않았습니다.", reason_code="education_rule_unparsed", field="education")
    if not profile.education:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "학력 정보가 없습니다.", reason_code="education_info_missing", field="education")
    graduates_only = bool(criteria.get("graduates_only"))
    if graduates_only and any(item.completed is False for item in profile.education):
        return RuleEvaluation(rule.rule_id, rule.required, "not_met", "졸업자만 허용되는 조건을 충족하지 않습니다.", reason_code="graduates_only_not_met", field="education")
    allow_current_student = bool(criteria.get("allow_current_student"))
    comparable = [
        item
        for item in profile.education
        if item.completed is not False or (allow_current_student and item.status == "enrolled")
    ]
    if not comparable:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "졸업 완료 여부를 확인할 수 없습니다.", reason_code="graduation_status_unknown", field="education")
    level_matches = [item for item in comparable if _level_rank(item.level) >= _level_rank(minimum)]
    completed_level_matches = [item for item in level_matches if item.completed is True]
    pending_level_matches = [item for item in level_matches if item.completed is None]
    if (
        pending_level_matches
        and not completed_level_matches
        and not any(item.status == "expected" or item.graduation_date for item in pending_level_matches)
    ):
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "졸업 완료 여부를 확인할 수 없습니다.", reason_code="graduation_status_unknown", field="education")
    if not level_matches and any(_level_rank(item.level) == 0 for item in comparable):
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "학력 수준을 판정할 수 없습니다.", reason_code="education_level_unknown", field="education")
    level_matches = completed_level_matches or level_matches
    if not level_matches:
        return RuleEvaluation(rule.rule_id, rule.required, "not_met", "요구 학력 수준을 충족하는 학력이 없습니다.", reason_code="education_level_not_met", field="education")
    allow_expected = bool(criteria.get("allow_expected"))
    expected = [item for item in level_matches if item.status == "expected" or item.completed is None]
    if expected and not completed_level_matches:
        if not allow_expected:
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "졸업예정자 인정 여부가 확인되지 않았습니다.", reason_code="graduation_expected_not_allowed", field="education")
        if any(not item.graduation_date for item in expected):
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "졸업예정 인정 기준일을 확인할 수 없습니다.", reason_code="graduation_expected_date_unknown", field="education")
        if any(date.fromisoformat(item.graduation_date[:10]) > as_of for item in expected):
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "졸업예정일이 평가 기준일 이후입니다.", reason_code="graduation_expected_after_cutoff", field="education")
    if required_field:
        if any(not item.field for item in level_matches):
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "전공 정보가 없어 전공 요건을 확정할 수 없습니다.", reason_code="major_unknown", field="education")
        if not any(_normalize(required_field) in _normalize(item.field) for item in level_matches):
            return RuleEvaluation(rule.rule_id, rule.required, "not_met", "요구 전공과 일치하는 학력이 없습니다.", reason_code="major_not_met", field="education")
    return RuleEvaluation(rule.rule_id, rule.required, "met", "요구 학력을 충족합니다.", reason_code="education_met", field="education")


def _evaluate_experience(
    rule: EligibilityRule, profile: ApplicantProfile, as_of: date
) -> RuleEvaluation:
    confirmed = [item for item in profile.experiences if item.status == "confirmed"]
    criteria = rule.criteria
    if criteria.get("mode") in {"none", "new_graduate"} or criteria.get("minimum_months") == 0:
        return RuleEvaluation(rule.rule_id, rule.required, "met", "경력 요건이 없습니다.", reason_code="no_experience_required", field="experience")
    if not confirmed:
        if criteria.get("maximum_months") == 0 or criteria.get("maximum_years") == 0:
            return RuleEvaluation(rule.rule_id, rule.required, "met", "신입 조건을 충족합니다.", reason_code="new_graduate_met", field="experience")
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "확정된 경력 정보가 없습니다.", reason_code="confirmed_experience_missing", field="experience")
    allowed_types = _criteria_values(criteria, "employment_types")
    if criteria.get("include_intern") is False:
        excluded = {"intern", "인턴"}
        confirmed = [item for item in confirmed if (item.employment_type or "") not in excluded]
        if not confirmed:
            return RuleEvaluation(rule.rule_id, rule.required, "not_met", "인턴 경력을 제외하면 요구 경력이 없습니다.", reason_code="experience_excluded_not_met", field="experience")
    if allowed_types:
        if any(item.employment_type is None for item in confirmed):
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "경력 형태가 없어 인턴·계약직 포함 여부를 확정할 수 없습니다.", reason_code="employment_type_unknown", field="experience")
        confirmed = [item for item in confirmed if item.employment_type in allowed_types]
        if not confirmed:
            return RuleEvaluation(rule.rule_id, rule.required, "not_met", "요구 경력 형태와 일치하는 경력이 없습니다.", reason_code="employment_type_not_met", field="experience")
    minimum_months = criteria.get("minimum_months")
    if minimum_months is None and isinstance(criteria.get("minimum_years"), (int, float)):
        minimum_months = int(criteria["minimum_years"] * 12)
    maximum_months = criteria.get("maximum_months")
    if maximum_months is None and isinstance(criteria.get("maximum_years"), (int, float)):
        maximum_months = int(criteria["maximum_years"] * 12)
    if any(
        value is not None and (not isinstance(value, (int, float)) or value < 0)
        for value in (minimum_months, maximum_months)
    ):
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "경력 기간 기준이 구조화되지 않았습니다.", reason_code="experience_rule_unparsed", field="experience")
    titles = _criteria_values(criteria, "titles")
    skills = _criteria_values(criteria, "skills")
    if minimum_months is not None or maximum_months is not None:
        total_months = _experience_total_months(confirmed, as_of)
        if total_months is None:
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "경력 기간 또는 겹치는 기간을 확정할 수 없습니다.", reason_code="experience_duration_unknown", field="experience")
        if minimum_months is not None and total_months < minimum_months:
            return RuleEvaluation(rule.rule_id, rule.required, "not_met", "요구 경력 기간을 충족하지 않습니다.", reason_code="experience_minimum_not_met", field="experience")
        if maximum_months is not None and total_months > maximum_months:
            return RuleEvaluation(rule.rule_id, rule.required, "not_met", "허용 경력 기간을 초과합니다.", reason_code="experience_maximum_not_met", field="experience")
    if titles:
        exact_titles = {
            _normalize(title)
            for item in confirmed
            for title in _criteria_values(criteria, "title_aliases")
        }
        exact_titles.update(_normalize(item.title) for item in confirmed)
        if not any(_normalize(title) in exact_titles for title in titles):
            if criteria.get("title_match_mode") == "exact":
                return RuleEvaluation(rule.rule_id, rule.required, "not_met", "요구 직무와 일치하는 경력이 없습니다.", reason_code="experience_title_not_met", field="experience")
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "요구 직무와의 의미상 일치 여부를 확인할 수 없습니다.", reason_code="experience_title_ambiguous", field="experience")
    if skills:
        available = {_normalize(skill) for item in confirmed for skill in item.skills}
        missing = [skill for skill in skills if _normalize(skill) not in available]
        if missing:
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "요구 역량의 의미상 일치 여부를 확인할 수 없습니다.", reason_code="experience_skill_ambiguous", field="experience")
    if minimum_months is None and not titles and not skills:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "경력 기준이 구조화되지 않았습니다.", reason_code="experience_rule_unparsed", field="experience")
    return RuleEvaluation(rule.rule_id, rule.required, "met", "요구 경력 조건을 충족합니다.", reason_code="experience_met", field="experience")


def _evaluate_certification(
    rule: EligibilityRule, profile: ApplicantProfile, as_of: date, posting: PostingRecord
) -> RuleEvaluation:
    names = _criteria_values(rule.criteria, "names") or _criteria_values(rule.criteria, "name")
    if not names:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자격증 기준이 구조화되지 않았습니다.", reason_code="certification_rule_unparsed", field="certification")
    if not profile.certifications:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자격증 정보가 없습니다.", reason_code="certification_info_missing", field="certification")
    comparison = rule.comparison_date or rule.criteria.get("comparison_date")
    if comparison in {"posting_deadline", "deadline"}:
        if not posting.deadline_at:
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자격증 유효기간 기준일이 공고 마감일로 지정됐지만 마감일이 없습니다.", reason_code="certification_comparison_date_unknown", field="certification")
        comparison = posting.deadline_at
    if comparison:
        try:
            as_of = date.fromisoformat(str(comparison)[:10])
        except ValueError:
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자격증 유효기간 기준일 형식을 확인할 수 없습니다.", reason_code="certification_comparison_date_invalid", field="certification")
    operator = rule.operator or rule.criteria.get("operator", "any")
    if operator not in {"any", "all"}:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자격증 OR·AND 조건을 해석할 수 없습니다.", reason_code="certification_operator_unknown", field="certification")
    outcomes: list[str] = []
    required_levels = _criteria_values(rule.criteria, "levels") or _criteria_values(rule.criteria, "level")
    for name in names:
        matching = [item for item in profile.certifications if _certification_match(name, item.name)]
        if not matching:
            outcomes.append("not_met")
            continue
        outcome = "not_met"
        for item in matching:
            if item.verified is not True:
                outcome = "unknown"
                continue
            if required_levels:
                if item.level is None:
                    outcome = "unknown"
                    continue
                if not any(_normalize(item.level) == _normalize(level) for level in required_levels):
                    continue
            if item.status == "expected":
                if not rule.criteria.get("allow_expected"):
                    outcome = "unknown"
                    continue
                if not item.expected_at:
                    outcome = "unknown"
                    continue
                try:
                    if date.fromisoformat(item.expected_at[:10]) > as_of:
                        outcome = "unknown"
                        continue
                except ValueError:
                    outcome = "unknown"
                    continue
            if item.status == "expired":
                continue
            if item.expires_at:
                try:
                    if date.fromisoformat(item.expires_at[:10]) < as_of:
                        continue
                except ValueError:
                    outcome = "unknown"
                    continue
            if item.status == "unknown":
                outcome = "unknown"
                continue
            outcome = "met"
            break
        outcomes.append(outcome)
    if operator == "all" and all(item == "met" for item in outcomes):
        return RuleEvaluation(rule.rule_id, rule.required, "met", "요구 자격증을 모두 보유하고 있습니다.", reason_code="certifications_all_met", field="certification")
    if operator == "any" and any(item == "met" for item in outcomes):
        return RuleEvaluation(rule.rule_id, rule.required, "met", "요구 자격증 중 하나를 보유하고 있습니다.", reason_code="certification_any_met", field="certification")
    if "unknown" in outcomes:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자격증 승인 상태 또는 유효기간을 확정할 수 없습니다.", reason_code="certification_status_unknown", field="certification")
    return RuleEvaluation(rule.rule_id, rule.required, "not_met", "유효한 요구 자격증이 없습니다.", reason_code="certification_not_met", field="certification")


def _evaluate_location(
    rule: EligibilityRule, profile: ApplicantProfile, as_of: date
) -> RuleEvaluation:
    allowed = _criteria_values(rule.criteria, "allowed") or _criteria_values(rule.criteria, "regions")
    if not allowed:
        if rule.criteria.get("mode") == "nationwide":
            return RuleEvaluation(rule.rule_id, rule.required, "met", "전국 지원 가능 조건입니다.", reason_code="nationwide_met", field="location")
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "지역 기준이 구조화되지 않았습니다.", reason_code="location_rule_unparsed", field="location")
    if rule.criteria.get("ambiguous") is True:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "지역 제한의 해석이 필요합니다.", reason_code="location_definition_unknown", field="location")
    kind = rule.criteria.get("location_type", rule.criteria.get("category", "work_location"))
    if kind not in _LOCATION_KINDS - {"unknown"}:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "지역 자격 유형을 해석할 수 없습니다.", reason_code="location_type_unknown", field="location")
    if kind == "work_location":
        candidates = [ApplicantLocation(item, "work_location") for item in profile.locations]
    else:
        candidates = [item for item in profile.location_records if item.kind == kind]
    if not candidates:
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "해당 유형의 지역 정보가 없습니다.", reason_code="location_info_missing", field="location")
    valid_candidates: list[ApplicantLocation] = []
    for item in candidates:
        try:
            if item.valid_from and date.fromisoformat(item.valid_from[:10]) > as_of:
                continue
            if item.valid_until and date.fromisoformat(item.valid_until[:10]) < as_of:
                continue
        except ValueError:
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "지역 기준일 형식을 확인할 수 없습니다.", reason_code="location_date_invalid", field="location")
        valid_candidates.append(item)
    if not valid_candidates:
        return RuleEvaluation(rule.rule_id, rule.required, "not_met", "기준일에 유효한 지역 정보가 없습니다.", reason_code="location_not_met", field="location")
    minimum_duration = rule.criteria.get("minimum_duration_months")
    if minimum_duration is not None:
        if any(item.duration_months is None for item in valid_candidates):
            return RuleEvaluation(rule.rule_id, rule.required, "unknown", "지역 거주·재직 기간을 확인할 수 없습니다.", reason_code="location_duration_unknown", field="location")
        valid_candidates = [item for item in valid_candidates if item.duration_months >= minimum_duration]
        if not valid_candidates:
            return RuleEvaluation(rule.rule_id, rule.required, "not_met", "요구 지역 기간을 충족하지 않습니다.", reason_code="location_duration_not_met", field="location")
    if any(_location_match(value, item.name) for value in allowed for item in valid_candidates):
        return RuleEvaluation(rule.rule_id, rule.required, "met", "지역 자격 조건을 충족합니다.", reason_code="location_met", field="location")
    return RuleEvaluation(rule.rule_id, rule.required, "not_met", "지역 자격 조건을 충족하지 않습니다.", reason_code="location_not_met", field="location")


def _evaluate_rule(
    rule: EligibilityRule, profile: ApplicantProfile, posting: PostingRecord, as_of: date
) -> RuleEvaluation:
    if rule.parse_status == "manual_review":
        return RuleEvaluation(rule.rule_id, rule.required, "unknown", "공고 조건을 구조화하지 못해 수동 검토가 필요합니다.", reason_code="rule_parse_manual_review", field=rule.kind)
    if rule.kind == "education":
        return _evaluate_education(rule, profile, as_of)
    if rule.kind == "experience":
        return _evaluate_experience(rule, profile, as_of)
    if rule.kind == "certification":
        return _evaluate_certification(rule, profile, as_of, posting)
    if rule.kind == "location":
        return _evaluate_location(rule, profile, as_of)
    return RuleEvaluation(rule.rule_id, rule.required, "unknown", "자연어 또는 미지원 조건은 수동 검토가 필요합니다.", reason_code="rule_unsupported", field=rule.kind)


def evaluate_eligibility(
    profile: ApplicantProfile,
    posting: PostingRecord,
    *,
    evaluated_at: str | None = None,
) -> EligibilityDecision:
    validate_applicant_profile(profile)
    validate_posting_record(posting)
    # Use only input-derived dates by default so identical inputs produce the
    # same result on different days. Callers may provide an explicit cutoff.
    evaluated_at = evaluated_at or posting.deadline_at or posting.retrieved_at
    try:
        as_of = date.fromisoformat(evaluated_at[:10])
    except ValueError:
        try:
            as_of = date.fromisoformat(posting.retrieved_at[:10])
        except ValueError as error:
            raise EligibilityValidationError(["evaluated_at and retrieved_at must begin with an ISO date"]) from error
    evaluations = tuple(
        _evaluate_rule(rule, profile, posting, as_of)
        for rule in (*posting.required_rules, *posting.preferred_rules)
    )
    reasons: list[DecisionReason] = []
    if not posting.required_rules:
        reasons.append(DecisionReason("required_rules_missing", "posting", "필수 조건이 구조화되어 있지 않아 수동 검토가 필요합니다."))
    if posting.source_status == "unverified":
        reasons.append(DecisionReason("posting_source_unverified", "posting", "공고 출처가 공식 출처로 확인되지 않았습니다."))
    required_not_met = [item for item in evaluations if item.required and item.status == "not_met"]
    required_unknown = [item for item in evaluations if item.required and item.status == "unknown"]
    preferred_gaps = [item for item in evaluations if not item.required and item.status != "met"]
    if required_not_met:
        reasons = [DecisionReason(item.reason_code, item.field, item.reason) for item in required_not_met]
    elif required_unknown:
        reasons.extend(DecisionReason(item.reason_code, item.field, item.reason) for item in required_unknown)
    elif preferred_gaps:
        reasons.extend(DecisionReason(item.reason_code, item.field, item.reason) for item in preferred_gaps)
    if required_not_met:
        status = "ineligible"
    elif required_unknown or posting.source_status == "unverified" or not posting.required_rules:
        status = "manual_review"
    elif preferred_gaps:
        status = "eligible_with_gaps"
    else:
        status = "eligible"
    decision_key = "|".join((posting.posting_id, profile.profile_id, posting.body_sha256, evaluated_at))
    decision = EligibilityDecision(
        schema_version=SCHEMA_VERSION,
        decision_id="eligibility-" + sha256(decision_key.encode("utf-8")).hexdigest()[:24],
        posting_id=posting.posting_id,
        profile_id=profile.profile_id,
        status=status,
        evaluated_at=evaluated_at,
        rule_evaluations=evaluations,
        reasons=tuple(
            reason
            for index, reason in enumerate(reasons)
            if (reason.code, reason.field, reason.message)
            not in {
                (item.code, item.field, item.message) for item in reasons[:index]
            }
        ),
        human_review_required=status in {"manual_review", "eligible_with_gaps"},
    )
    return validate_decision(decision)
