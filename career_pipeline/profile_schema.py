from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


PROFILE_STATUSES = {"proposed", "confirmed", "rejected", "stale"}
CLAIM_STATUSES = {"proposed", "confirmed", "rejected", "stale", "unknown"}
_SHA256_LENGTH = 64


class ProfileValidationError(ValueError):
    def __init__(self, issues: list[str] | tuple[str, ...]):
        self.issues = tuple(issues)
        super().__init__("\n".join(self.issues))


@dataclass(frozen=True)
class EvidenceRef:
    source_path: str
    paragraph_index: int
    source_sha256: str
    excerpt_sha256: str


@dataclass(frozen=True)
class ProfileClaim:
    field: str
    normalized_value: str
    status: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class Experience:
    experience_id: str
    title: str
    organization_alias: str
    period: dict[str, Any] | None
    role: str
    situation: str
    actions: tuple[str, ...]
    outcomes: tuple[str, ...]
    competencies: tuple[str, ...]
    claims: tuple[ProfileClaim, ...]
    status: str
    confirmed_at: str | None


@dataclass(frozen=True)
class ExperienceLedger:
    schema_version: int
    generated_at: str
    workspace_root: str
    experiences: tuple[Experience, ...]


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def validate_ledger(ledger: ExperienceLedger) -> ExperienceLedger:
    issues: list[str] = []
    if ledger.schema_version != 1:
        issues.append("schema_version: expected 1")
    if not ledger.generated_at:
        issues.append("generated_at: must not be empty")
    if not ledger.workspace_root:
        issues.append("workspace_root: must not be empty")

    seen_ids: set[str] = set()
    for experience_index, experience in enumerate(ledger.experiences):
        base = f"experiences[{experience_index}]"
        if not experience.experience_id:
            issues.append(f"{base}.experience_id: must not be empty")
        elif experience.experience_id in seen_ids:
            issues.append(f"{base}.experience_id: duplicate experience ID")
        seen_ids.add(experience.experience_id)

        if experience.status not in PROFILE_STATUSES:
            issues.append(
                f"{base}.status: expected one of {sorted(PROFILE_STATUSES)}"
            )
        if experience.status == "confirmed" and not any(
            claim.status == "confirmed" for claim in experience.claims
        ):
            issues.append(f"{base}.claims: confirmed experience needs a confirmed claim")
        if experience.status == "confirmed" and not experience.confirmed_at:
            issues.append(f"{base}.confirmed_at: required for confirmed experience")

        for claim_index, claim in enumerate(experience.claims):
            claim_base = f"{base}.claims[{claim_index}]"
            if claim.status not in CLAIM_STATUSES:
                issues.append(
                    f"{claim_base}.status: expected one of {sorted(CLAIM_STATUSES)}"
                )
            if claim.status == "confirmed" and not claim.evidence:
                issues.append(f"{claim_base}.evidence: required for confirmed claim")
            for evidence_index, evidence in enumerate(claim.evidence):
                evidence_base = f"{claim_base}.evidence[{evidence_index}]"
                if not evidence.source_path:
                    issues.append(f"{evidence_base}.source_path: must not be empty")
                if evidence.paragraph_index < 0:
                    issues.append(
                        f"{evidence_base}.paragraph_index: must be zero or greater"
                    )
                for field_name, value in (
                    ("source_sha256", evidence.source_sha256),
                    ("excerpt_sha256", evidence.excerpt_sha256),
                ):
                    if not _is_sha256(value):
                        issues.append(
                            f"{evidence_base}.{field_name}: expected lowercase SHA-256"
                        )

    if issues:
        raise ProfileValidationError(issues)
    return ledger


def ledger_to_dict(ledger: ExperienceLedger) -> dict[str, Any]:
    return asdict(ledger)


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileValidationError([f"{path}: expected object"])
    return value


def _require_string(mapping: dict[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ProfileValidationError([f"{path}.{key}: expected string"])
    return value


def _string_tuple(mapping: dict[str, Any], key: str, path: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProfileValidationError([f"{path}.{key}: expected string array"])
    return tuple(value)


def _evidence_from_dict(value: Any, path: str) -> EvidenceRef:
    mapping = _require_mapping(value, path)
    paragraph_index = mapping.get("paragraph_index")
    if not isinstance(paragraph_index, int) or isinstance(paragraph_index, bool):
        raise ProfileValidationError([f"{path}.paragraph_index: expected integer"])
    return EvidenceRef(
        source_path=_require_string(mapping, "source_path", path),
        paragraph_index=paragraph_index,
        source_sha256=_require_string(mapping, "source_sha256", path),
        excerpt_sha256=_require_string(mapping, "excerpt_sha256", path),
    )


def _claim_from_dict(value: Any, path: str) -> ProfileClaim:
    mapping = _require_mapping(value, path)
    evidence = mapping.get("evidence")
    if not isinstance(evidence, list):
        raise ProfileValidationError([f"{path}.evidence: expected array"])
    return ProfileClaim(
        field=_require_string(mapping, "field", path),
        normalized_value=_require_string(mapping, "normalized_value", path),
        status=_require_string(mapping, "status", path),
        evidence=tuple(
            _evidence_from_dict(item, f"{path}.evidence[{index}]")
            for index, item in enumerate(evidence)
        ),
    )


def _experience_from_dict(value: Any, path: str) -> Experience:
    mapping = _require_mapping(value, path)
    claims = mapping.get("claims")
    if not isinstance(claims, list):
        raise ProfileValidationError([f"{path}.claims: expected array"])
    period = mapping.get("period")
    if period is not None and not isinstance(period, dict):
        raise ProfileValidationError([f"{path}.period: expected object or null"])
    confirmed_at = mapping.get("confirmed_at")
    if confirmed_at is not None and not isinstance(confirmed_at, str):
        raise ProfileValidationError([f"{path}.confirmed_at: expected string or null"])
    return Experience(
        experience_id=_require_string(mapping, "experience_id", path),
        title=_require_string(mapping, "title", path),
        organization_alias=_require_string(mapping, "organization_alias", path),
        period=period,
        role=_require_string(mapping, "role", path),
        situation=_require_string(mapping, "situation", path),
        actions=_string_tuple(mapping, "actions", path),
        outcomes=_string_tuple(mapping, "outcomes", path),
        competencies=_string_tuple(mapping, "competencies", path),
        claims=tuple(
            _claim_from_dict(item, f"{path}.claims[{index}]")
            for index, item in enumerate(claims)
        ),
        status=_require_string(mapping, "status", path),
        confirmed_at=confirmed_at,
    )


def _ledger_from_dict(value: Any) -> ExperienceLedger:
    mapping = _require_mapping(value, "$.")
    schema_version = mapping.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ProfileValidationError(["schema_version: expected integer"])
    experiences = mapping.get("experiences")
    if not isinstance(experiences, list):
        raise ProfileValidationError(["experiences: expected array"])
    return ExperienceLedger(
        schema_version=schema_version,
        generated_at=_require_string(mapping, "generated_at", "$"),
        workspace_root=_require_string(mapping, "workspace_root", "$"),
        experiences=tuple(
            _experience_from_dict(item, f"experiences[{index}]")
            for index, item in enumerate(experiences)
        ),
    )


def load_ledger(path: Path) -> ExperienceLedger:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProfileValidationError(
            [f"$: invalid JSON at line {error.lineno}, column {error.colno}"]
        ) from error
    ledger = _ledger_from_dict(payload)
    return validate_ledger(ledger)
