from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


PROFILE_STATUSES = {"proposed", "confirmed", "rejected", "stale"}
CLAIM_STATUSES = {
    "proposed", "confirmed", "needs_verification", "rejected", "stale", "unknown"
}
CONTRIBUTIONS = {"observed", "contributed", "caused", "unknown"}
VERIFICATION_METHODS = {
    "none", "direct_source", "direct_count", "before_after", "system_record",
    "documented_total",
}
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
class ClaimVerification:
    method: str = "none"
    baseline: str | None = None
    result: str | None = None
    formula: str | None = None
    measurement_period: str | None = None
    scope: str | None = None
    contribution: str = "unknown"


@dataclass(frozen=True)
class ProfileClaim:
    field: str
    normalized_value: str
    status: str
    evidence: tuple[EvidenceRef, ...]
    claim_id: str = ""
    verification: ClaimVerification | None = None


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


def stable_claim_id(experience_id: str, claim: ProfileClaim) -> str:
    evidence = "|".join(
        f"{item.source_path}:{item.paragraph_index}:{item.excerpt_sha256}"
        for item in claim.evidence
    )
    raw = f"{experience_id}\0{claim.field}\0{claim.normalized_value}\0{evidence}"
    return "clm_" + sha256(raw.encode("utf-8")).hexdigest()[:20]


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def _is_metric(claim: ProfileClaim) -> bool:
    return claim.field.startswith("metric:") or bool(
        re.fullmatch(r"[\s,]*-?\d+(?:\.\d+)?\s*(?:%|건|명|원|페이지|시간|일|개월|회)[\s]*", claim.normalized_value)
    )


def claim_submission_issues(claim: ProfileClaim) -> tuple[str, ...]:
    """Return deterministic reasons why a confirmed claim cannot be submitted."""
    if claim.status != "confirmed":
        return ("claim_not_confirmed",)
    verification = claim.verification
    if verification is None:
        return ("verification_missing",) if _is_metric(claim) else ()
    issues: list[str] = []
    if verification.method not in VERIFICATION_METHODS:
        issues.append("verification_method_invalid")
    if verification.contribution not in CONTRIBUTIONS:
        issues.append("contribution_invalid")
    if _is_metric(claim):
        if verification.method == "none":
            issues.append("metric_method_missing")
        if not verification.scope:
            issues.append("metric_scope_missing")
        if verification.contribution == "unknown":
            issues.append("metric_contribution_unknown")
        if "%" in claim.normalized_value:
            baseline = _number(verification.baseline)
            result = _number(verification.result)
            stated = _number(claim.normalized_value)
            if verification.method != "before_after":
                issues.append("percentage_before_after_required")
            if baseline is None or result is None or not verification.formula:
                issues.append("percentage_formula_incomplete")
            elif baseline == 0:
                issues.append("percentage_baseline_zero")
            else:
                direction = verification.formula.strip().lower()
                computed = (
                    (baseline - result) / baseline * 100
                    if direction == "decrease_percent"
                    else (result - baseline) / baseline * 100
                    if direction == "increase_percent"
                    else None
                )
                if computed is None:
                    issues.append("percentage_formula_invalid")
                elif stated is None or abs(abs(computed) - abs(stated)) > 0.5:
                    issues.append("percentage_value_mismatch")
        elif verification.method == "direct_count" and not verification.measurement_period:
            issues.append("direct_count_period_missing")
    return tuple(dict.fromkeys(issues))


def claim_is_submission_safe(claim: ProfileClaim) -> bool:
    return not claim_submission_issues(claim)


def validate_ledger(ledger: ExperienceLedger) -> ExperienceLedger:
    issues: list[str] = []
    if ledger.schema_version not in {1, 2}:
        issues.append("schema_version: expected 1 or 2")
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
            if ledger.schema_version >= 2:
                if not claim.claim_id:
                    issues.append(f"{claim_base}.claim_id: required for schema v2")
                elif claim.claim_id != stable_claim_id(experience.experience_id, claim):
                    issues.append(f"{claim_base}.claim_id: unstable or incorrect")
                verification = claim.verification
                if verification is None:
                    issues.append(f"{claim_base}.verification: required for schema v2")
                else:
                    if verification.method not in VERIFICATION_METHODS:
                        issues.append(f"{claim_base}.verification.method: invalid")
                    if verification.contribution not in CONTRIBUTIONS:
                        issues.append(f"{claim_base}.verification.contribution: invalid")
                if claim.status == "confirmed":
                    for reason in claim_submission_issues(claim):
                        issues.append(f"{claim_base}: unsafe confirmed claim ({reason})")
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
    verification_payload = mapping.get("verification")
    verification = None
    if verification_payload is not None:
        verification_mapping = _require_mapping(verification_payload, f"{path}.verification")
        verification = ClaimVerification(
            method=str(verification_mapping.get("method", "none")),
            baseline=verification_mapping.get("baseline"),
            result=verification_mapping.get("result"),
            formula=verification_mapping.get("formula"),
            measurement_period=verification_mapping.get("measurement_period"),
            scope=verification_mapping.get("scope"),
            contribution=str(verification_mapping.get("contribution", "unknown")),
        )
    return ProfileClaim(
        field=_require_string(mapping, "field", path),
        normalized_value=_require_string(mapping, "normalized_value", path),
        status=_require_string(mapping, "status", path),
        evidence=tuple(
            _evidence_from_dict(item, f"{path}.evidence[{index}]")
            for index, item in enumerate(evidence)
        ),
        claim_id=str(mapping.get("claim_id", "")),
        verification=verification,
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


def migrate_ledger_v1(ledger: ExperienceLedger) -> ExperienceLedger:
    """Create a v2 proposal without mutating the source ledger.

    Qualitative confirmed claims remain confirmed. Legacy numeric claims are
    quarantined until their measurement and contribution are reviewed.
    """
    if ledger.schema_version != 1:
        raise ProfileValidationError(["profile migrate: source must be schema v1"])
    experiences: list[Experience] = []
    for experience in ledger.experiences:
        claims: list[ProfileClaim] = []
        for claim in experience.claims:
            metric = _is_metric(claim)
            status = "needs_verification" if metric and claim.status == "confirmed" else claim.status
            verification = ClaimVerification(
                method="none" if metric else "direct_source",
                scope=None if metric else "source excerpt",
                contribution="unknown" if metric else "observed",
            )
            provisional = ProfileClaim(
                field=claim.field,
                normalized_value=claim.normalized_value,
                status=status,
                evidence=claim.evidence,
                verification=verification,
            )
            claims.append(
                ProfileClaim(
                    field=provisional.field,
                    normalized_value=provisional.normalized_value,
                    status=provisional.status,
                    evidence=provisional.evidence,
                    claim_id=stable_claim_id(experience.experience_id, provisional),
                    verification=verification,
                )
            )
        if not any(not _is_metric(claim) for claim in claims):
            summary_parts = [
                experience.role,
                experience.situation,
                *experience.actions,
                *experience.outcomes,
            ]
            metric_text = re.compile(
                r"\d[\d,.]*\s*(?:%|\uac74|\uba85|\uc6d0|\ub9cc\uc6d0|\uc5b5\uc6d0|"
                r"\ud398\uc774\uc9c0|\uc2dc\uac04|\uc77c|\uac1c\uc6d4|\ud68c)"
            )
            summary = " ".join(
                metric_text.sub("", part).strip()
                for part in summary_parts
                if isinstance(part, str)
                and part.strip()
                and metric_text.sub("", part).strip()
            )
            evidence = claims[0].evidence if claims else ()
            if summary and evidence:
                verification = ClaimVerification(
                    method="direct_source", scope="source excerpt", contribution="observed"
                )
                status = "confirmed" if experience.status == "confirmed" else "proposed"
                provisional = ProfileClaim(
                    field="experience_summary",
                    normalized_value=summary,
                    status=status,
                    evidence=evidence,
                    verification=verification,
                )
                claims.append(ProfileClaim(
                    field=provisional.field,
                    normalized_value=provisional.normalized_value,
                    status=provisional.status,
                    evidence=provisional.evidence,
                    claim_id=stable_claim_id(experience.experience_id, provisional),
                    verification=verification,
                ))
        experience_status = experience.status
        if experience_status == "confirmed" and not any(c.status == "confirmed" for c in claims):
            experience_status = "proposed"
        experiences.append(
            Experience(
                experience_id=experience.experience_id,
                title=experience.title,
                organization_alias=experience.organization_alias,
                period=experience.period,
                role=experience.role,
                situation=experience.situation,
                actions=experience.actions,
                outcomes=experience.outcomes,
                competencies=experience.competencies,
                claims=tuple(claims),
                status=experience_status,
                confirmed_at=experience.confirmed_at if experience_status == "confirmed" else None,
            )
        )
    migrated = ExperienceLedger(
        schema_version=2,
        generated_at=ledger.generated_at,
        workspace_root=ledger.workspace_root,
        experiences=tuple(experiences),
    )
    return validate_ledger(migrated)
