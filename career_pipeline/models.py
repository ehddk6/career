"""Career Pipeline 데이터 모델. SourceRecord, Question, DraftResponse, ValidationIssue 등을 정의합니다."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .character_count import CharacterCountMode


@dataclass(frozen=True)
class SourceRecord:
    path: Path
    relative_path: str
    extension: str
    size: int
    sha256: str
    status: Literal["use", "excluded", "duplicate", "failed"]
    reason: str = ""


@dataclass(frozen=True)
class ExtractedDocument:
    source: SourceRecord
    text: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Question:
    index: int
    prompt: str
    character_limit: int | None
    count_mode: CharacterCountMode = "spaces_included"


@dataclass(frozen=True)
class FactClaim:
    source_path: str
    paragraph_index: int
    context: str
    field: str
    raw_value: str
    normalized_value: str
    unit_kind: str
    tokens: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Conflict:
    field: str
    claim_indexes: tuple[int, ...]
    values: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ExperienceClaimRef:
    experience_id: str
    claim_fields: tuple[str, ...]


@dataclass(frozen=True)
class DraftResponse:
    question_index: int
    answer: str
    evidence_paths: tuple[str, ...]
    experience_refs: tuple[ExperienceClaimRef, ...] = ()
    research_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    question_index: int
    message: str


# Phase 2 models deliberately do not contain raw personal information. An
# ApplicantProfile points to the confirmed experience ledger and stores only
# the structured facts needed for deterministic eligibility checks.
@dataclass(frozen=True)
class EducationRecord:
    level: str
    field: str = ""
    completed: bool | None = None
    graduation_date: str | None = None
    status: Literal["graduated", "expected", "enrolled", "unknown"] = "unknown"


@dataclass(frozen=True)
class ApplicantExperience:
    experience_id: str
    title: str
    months: int | None = None
    skills: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    status: Literal["confirmed", "proposed", "stale", "unknown"] = "unknown"
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    employment_type: str | None = None
    claim_fields: tuple[str, ...] = ()
    evidence_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class CertificationRecord:
    name: str
    issued_at: str | None = None
    expires_at: str | None = None
    status: Literal["valid", "expired", "expected", "unknown"] = "unknown"
    verified: bool | None = None
    level: str | None = None
    expected_at: str | None = None


@dataclass(frozen=True)
class ApplicantLocation:
    name: str
    kind: Literal[
        "work_location",
        "residence",
        "school_region",
        "regional_talent",
        "unknown",
    ] = "unknown"
    valid_from: str | None = None
    valid_until: str | None = None
    duration_months: int | None = None


@dataclass(frozen=True)
class ApplicantProfile:
    schema_version: int
    profile_id: str
    generated_at: str
    experience_ledger_path: str | None
    experiences: tuple[ApplicantExperience, ...]
    education: tuple[EducationRecord, ...]
    certifications: tuple[CertificationRecord, ...]
    locations: tuple[str, ...]
    personal_info_ref: str | None = None
    experience_ledger_sha256: str | None = None
    location_records: tuple[ApplicantLocation, ...] = ()
    projection_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EligibilityRule:
    rule_id: str
    kind: Literal[
        "education",
        "experience",
        "certification",
        "location",
        "work_authorization",
        "custom",
    ]
    description: str
    required: bool
    criteria: dict[str, Any]
    parse_status: Literal["parsed", "manual_review"] = "parsed"
    source_excerpt: str | None = None
    source_location: str | None = None
    operator: str | None = None
    expected_value: Any | None = None
    comparison_date: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class PostingRecord:
    schema_version: int
    posting_id: str
    url: str
    official_domain: str | None
    published_at: str | None
    deadline_at: str | None
    title: str
    organization: str
    role: str
    body_sha256: str
    retrieved_at: str
    source_status: Literal["verified_domain", "user_attested", "unverified"]
    locations: tuple[str, ...]
    required_rules: tuple[EligibilityRule, ...]
    preferred_rules: tuple[EligibilityRule, ...]
    question_hash: str | None = None
    canonical_url: str | None = None
    timezone: str | None = None
    parser_version: str = "1"
    raw_sha256: str | None = None
    normalized_content_sha256: str | None = None
    source_id: str | None = None
    employment_type: tuple[str, ...] = ()
    status: Literal["active", "expired", "closed", "manual_review"] = "active"
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    source_excerpt: str | None = None
    unparsed_requirements: tuple[str, ...] = ()
    alias_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    required: bool
    status: Literal["met", "not_met", "unknown"]
    reason: str
    evidence: tuple[str, ...] = ()
    reason_code: str = "unspecified"
    field: str | None = None


@dataclass(frozen=True)
class DecisionReason:
    code: str
    field: str | None
    message: str


@dataclass(frozen=True)
class EligibilityDecision:
    schema_version: int
    decision_id: str
    posting_id: str
    profile_id: str
    status: Literal[
        "eligible",
        "eligible_with_gaps",
        "manual_review",
        "ineligible",
    ]
    evaluated_at: str
    rule_evaluations: tuple[RuleEvaluation, ...]
    reasons: tuple[DecisionReason, ...]
    human_review_required: bool


@dataclass(frozen=True)
class DiscoverySource:
    schema_version: int
    source_id: str
    organization: str
    source_type: Literal[
        "manual_url",
        "official_list_page",
        "official_rss",
        "official_sitemap",
        "official_json_api",
    ]
    entry_url: str
    allowed_domains: tuple[str, ...]
    role_keywords: tuple[str, ...]
    location_keywords: tuple[str, ...]
    enabled: bool
    created_at: str
    updated_at: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryCandidate:
    source_id: str
    url: str
    canonical_url: str
    discovered_at: str
    title_hint: str | None = None
    external_id: str | None = None


@dataclass(frozen=True)
class DiscoveryRun:
    schema_version: int
    run_id: str
    source_id: str
    started_at: str
    completed_at: str | None
    evaluation_time: str
    status: Literal["running", "completed", "completed_with_errors", "failed"]
    discovered_count: int
    fetched_count: int
    new_count: int
    changed_count: int
    duplicate_count: int
    expired_count: int
    failed_count: int
    errors: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ReviewQueueItem:
    schema_version: int
    queue_id: str
    posting_id: str
    source_id: str | None
    created_at: str
    updated_at: str
    priority: int
    priority_reasons: tuple[str, ...]
    queue_status: Literal[
        "pending",
        "approved",
        "rejected",
        "deferred",
        "superseded",
        "expired",
    ]
    discovery_status: str
    eligibility_status: str | None
    human_review_required: bool
    reasons: tuple[DecisionReason, ...]


@dataclass(frozen=True)
class RegistryEvent:
    event_id: str
    event_type: str
    occurred_at: str
    source_id: str | None
    posting_id: str | None
    run_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
