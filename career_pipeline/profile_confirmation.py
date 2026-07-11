"""Human approval gate for proposed experience ledgers."""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .profile_builder import build_experience_review_queue
from .profile_schema import ExperienceLedger, ProfileValidationError


DECISIONS = {"pending", "confirmed", "rejected"}


def write_review_template(ledger: ExperienceLedger, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "experience_id",
                "source_path",
                "paragraph_index",
                "review_priority",
                "summary",
                "check",
                "decision",
                "claims_confirmed",
                "notes",
            ),
        )
        writer.writeheader()
        for item in build_experience_review_queue(ledger):
            writer.writerow({**item, "decision": "pending", "claims_confirmed": "no", "notes": ""})


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
