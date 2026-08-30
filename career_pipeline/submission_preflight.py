"""Deterministic application-input preflight.

Writing quality and application completeness are intentionally independent.
An excellent cover letter must not hide an expired credential or a missing
required attachment, and these checks are not a hiring-probability estimate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping

from .models import ApplicantProfile


PREFLIGHT_CONTRACT_VERSION = "submission_preflight_v1"


@dataclass(frozen=True)
class SubmissionPreflight:
    contract_version: str
    metric: str
    status: str
    evaluated_on: str
    reason_codes: tuple[str, ...]
    excluded_credentials: tuple[str, ...]
    usable_credentials: tuple[str, ...]
    missing_required_attachments: tuple[str, ...]
    selected_credential_attachments: tuple[tuple[str, str], ...] = ()


_LANGUAGE_CREDENTIAL = re.compile(
    r"(?:TOEIC|TOEFL|OPIC|OPIc|IELTS|TEPS|토익|토플|오픽|아이엘츠|텝스)", re.I
)


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(text[:10])


def assess_submission_preflight(
    profile: ApplicantProfile,
    *,
    as_of: date | datetime | str,
    included_credential_names: Iterable[str] | None = None,
    selected_credential_attachments: Mapping[str, str] | None = None,
    supplied_attachment_keys: Iterable[str] = (),
    required_attachment_keys: Iterable[str] = (),
) -> SubmissionPreflight:
    """Check credential usability and required uploads without scoring prose."""
    evaluation_date = _as_date(as_of)
    supplied = {str(key).strip() for key in supplied_attachment_keys if str(key).strip()}
    selected_bindings = {
        str(name).strip(): str(key).strip()
        for name, key in (selected_credential_attachments or {}).items()
        if str(name).strip() and str(key).strip()
    }
    required = {str(key).strip() for key in required_attachment_keys if str(key).strip()}
    required.update(selected_bindings.values())
    missing = tuple(sorted(required - supplied))
    reasons = [f"required_attachment_missing:{key}" for key in missing]
    excluded: list[str] = []
    usable: list[str] = []
    included = (
        set(selected_bindings)
        if selected_credential_attachments is not None
        else
        None
        if included_credential_names is None
        else {
            str(name).strip()
            for name in included_credential_names
            if str(name).strip()
        }
    )
    profile_names = {credential.name for credential in profile.certifications}
    if included is None and profile.certifications:
        reasons.append("credential_selection_unconfirmed")
    elif included is not None:
        reasons.extend(
            f"credential_not_in_profile:{name}"
            for name in sorted(included - profile_names)
        )

    for selected_name in sorted(included or ()):
        if sum(credential.name == selected_name for credential in profile.certifications) > 1:
            reasons.append(f"credential_ambiguous:{selected_name}")

    for credential in profile.certifications:
        selected = included is not None and credential.name in included
        expired = credential.status == "expired"
        if credential.expires_at:
            try:
                expired = expired or _as_date(credential.expires_at) < evaluation_date
            except ValueError:
                excluded.append(credential.name)
                if selected:
                    reasons.append(f"credential_expiry_invalid:{credential.name}")
                continue
        if expired:
            excluded.append(credential.name)
            if selected:
                reasons.append(f"credential_expired:{credential.name}")
            continue
        if not selected:
            continue
        if credential.issued_at:
            try:
                if _as_date(credential.issued_at) > evaluation_date:
                    reasons.append(f"credential_not_yet_issued:{credential.name}")
                    excluded.append(credential.name)
                    continue
            except ValueError:
                reasons.append(f"credential_issued_at_invalid:{credential.name}")
                excluded.append(credential.name)
                continue
        if _LANGUAGE_CREDENTIAL.search(credential.name) and not credential.expires_at:
            reasons.append(f"language_credential_expiry_missing:{credential.name}")
            excluded.append(credential.name)
            continue
        if credential.status not in {"valid"}:
            reasons.append(f"credential_status_unconfirmed:{credential.name}")
            excluded.append(credential.name)
            continue
        if credential.verified is not True:
            reasons.append(f"credential_evidence_unverified:{credential.name}")
            excluded.append(credential.name)
            continue
        usable.append(credential.name)

    blocking_prefixes = (
        "required_attachment_missing:",
        "credential_expired:",
        "credential_not_in_profile:",
        "credential_not_yet_issued:",
    )
    status = (
        "blocked"
        if missing or any(reason.startswith(blocking_prefixes) for reason in reasons)
        else "manual_review"
        if reasons
        else "ready"
    )
    return SubmissionPreflight(
        contract_version=PREFLIGHT_CONTRACT_VERSION,
        metric="application_completeness_not_writing_score_or_hire_probability",
        status=status,
        evaluated_on=evaluation_date.isoformat(),
        reason_codes=tuple(sorted(set(reasons))),
        excluded_credentials=tuple(sorted(set(excluded))),
        usable_credentials=tuple(sorted(set(usable))),
        missing_required_attachments=missing,
        selected_credential_attachments=tuple(sorted(selected_bindings.items())),
    )


def submission_preflight_sha256(report: SubmissionPreflight) -> str:
    payload = json.dumps(
        asdict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


__all__ = [
    "PREFLIGHT_CONTRACT_VERSION",
    "SubmissionPreflight",
    "assess_submission_preflight",
    "submission_preflight_sha256",
]
