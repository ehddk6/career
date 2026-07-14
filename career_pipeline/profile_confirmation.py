"""Human approval gate for proposed experience ledgers."""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .profile_builder import build_experience_review_queue
from .profile_schema import (
    ClaimVerification,
    ExperienceLedger,
    ProfileValidationError,
    claim_submission_issues,
    validate_ledger,
)


DECISIONS = {"pending", "confirmed", "needs_verification", "rejected"}


def write_review_template(ledger: ExperienceLedger, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "experience_id", "claim_id", "claim_field", "claim_value",
                "source_path", "paragraph_index", "decision", "method",
                "baseline", "result", "formula", "measurement_period", "scope",
                "contribution", "notes",
            ),
        )
        writer.writeheader()
        queued = {item["experience_id"] for item in build_experience_review_queue(ledger)}
        for experience in ledger.experiences:
            if experience.experience_id not in queued:
                continue
            for claim in experience.claims:
                evidence = claim.evidence[0] if claim.evidence else None
                verification = claim.verification or ClaimVerification()
                writer.writerow({
                    "experience_id": experience.experience_id,
                    "claim_id": claim.claim_id,
                    "claim_field": claim.field,
                    "claim_value": claim.normalized_value,
                    "source_path": evidence.source_path if evidence else "",
                    "paragraph_index": evidence.paragraph_index if evidence else "",
                    "decision": "pending",
                    "method": verification.method,
                    "baseline": verification.baseline or "",
                    "result": verification.result or "",
                    "formula": verification.formula or "",
                    "measurement_period": verification.measurement_period or "",
                    "scope": verification.scope or "",
                    "contribution": verification.contribution,
                    "notes": "",
                })


def _optional(row: dict[str, str], key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def _claim_decisions(path: Path) -> dict[str, tuple[str, ClaimVerification]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as error:
        raise ProfileValidationError([f"decisions file: {error}"]) from error
    result: dict[str, tuple[str, ClaimVerification]] = {}
    issues: list[str] = []
    for index, row in enumerate(rows, start=2):
        claim_id = (row.get("claim_id") or "").strip()
        decision = (row.get("decision") or "pending").strip().lower()
        if not claim_id:
            issues.append(f"row {index}: claim_id is required for schema v2")
            continue
        if decision not in DECISIONS:
            issues.append(f"row {index}: invalid decision {decision!r}")
            continue
        if claim_id in result:
            issues.append(f"row {index}: duplicate claim_id {claim_id}")
            continue
        result[claim_id] = (
            decision,
            ClaimVerification(
                method=(row.get("method") or "none").strip(),
                baseline=_optional(row, "baseline"),
                result=_optional(row, "result"),
                formula=_optional(row, "formula"),
                measurement_period=_optional(row, "measurement_period"),
                scope=_optional(row, "scope"),
                contribution=(row.get("contribution") or "unknown").strip(),
            ),
        )
    if issues:
        raise ProfileValidationError(issues)
    return result


def _decisions(path: Path) -> dict[str, tuple[str, bool]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as error:
        raise ProfileValidationError([f"decisions file: {error}"]) from error
    result: dict[str, tuple[str, bool]] = {}
    issues: list[str] = []
    for index, row in enumerate(rows, start=2):
        experience_id = (row.get("experience_id") or "").strip()
        decision = (row.get("decision") or "pending").strip().lower()
        confirmed = (row.get("claims_confirmed") or "no").strip().lower() in {"yes", "y", "true", "1"}
        if not experience_id:
            issues.append(f"row {index}: experience_id is required")
        elif decision not in DECISIONS:
            issues.append(f"row {index}: invalid decision {decision!r}")
        elif experience_id in result:
            issues.append(f"row {index}: duplicate experience_id {experience_id}")
        else:
            result[experience_id] = (decision, confirmed)
    if issues:
        raise ProfileValidationError(issues)
    return result


def confirm_ledger(proposed: ExperienceLedger, decisions_path: Path) -> tuple[ExperienceLedger, dict[str, int]]:
    if proposed.schema_version >= 2:
        decisions = _claim_decisions(decisions_path)
        known_claims = {
            claim.claim_id
            for experience in proposed.experiences
            for claim in experience.claims
        }
        unknown = sorted(set(decisions).difference(known_claims))
        if unknown:
            raise ProfileValidationError([f"unknown claim_id: {item}" for item in unknown])
        confirmed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        counts = {
            "confirmed": 0, "rejected": 0, "pending": 0,
            "needs_verification": 0, "blocked_unsafe_claim": 0,
        }
        experiences = []
        for experience in proposed.experiences:
            claims = []
            for claim in experience.claims:
                decision, verification = decisions.get(
                    claim.claim_id, ("pending", claim.verification or ClaimVerification())
                )
                candidate = replace(claim, status=decision if decision != "pending" else claim.status, verification=verification)
                if decision == "confirmed" and claim_submission_issues(candidate):
                    candidate = replace(candidate, status="needs_verification")
                    counts["blocked_unsafe_claim"] += 1
                    counts["needs_verification"] += 1
                else:
                    counts[candidate.status if candidate.status in counts else "pending"] += 1
                claims.append(candidate)
            is_confirmed = any(item.status == "confirmed" for item in claims)
            experiences.append(replace(
                experience,
                claims=tuple(claims),
                status="confirmed" if is_confirmed else "proposed",
                confirmed_at=confirmed_at if is_confirmed else None,
            ))
        result = replace(proposed, experiences=tuple(experiences))
        return validate_ledger(result), counts

    # Legacy compatibility: only schema-v1 ledgers accept experience-level rows.
    decisions = _decisions(decisions_path)
    known_ids = {item.experience_id for item in proposed.experiences}
    unknown = sorted(set(decisions).difference(known_ids))
    if unknown:
        raise ProfileValidationError([f"unknown experience_id: {item}" for item in unknown])
    confirmed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    experiences = []
    counts = {"confirmed": 0, "rejected": 0, "pending": 0, "blocked_missing_claim_confirmation": 0}
    for experience in proposed.experiences:
        decision, claims_confirmed = decisions.get(experience.experience_id, ("pending", False))
        if decision == "confirmed" and not claims_confirmed:
            counts["blocked_missing_claim_confirmation"] += 1
            decision = "pending"
        if decision == "confirmed":
            experiences.append(replace(experience, status="confirmed", confirmed_at=confirmed_at, claims=tuple(replace(claim, status="confirmed") for claim in experience.claims)))
            counts["confirmed"] += 1
        elif decision == "rejected":
            experiences.append(replace(experience, status="rejected", confirmed_at=None, claims=tuple(replace(claim, status="rejected") for claim in experience.claims)))
            counts["rejected"] += 1
        else:
            experiences.append(experience)
            counts["pending"] += 1
    return replace(proposed, experiences=tuple(experiences)), counts
