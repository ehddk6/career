"""Question-specific evidence coverage and adaptive stopping for company research."""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1

_GOOD_VERIFICATION = {"confirmed", "verified"}
_GOOD_SUPPORT = {"direct", "strong", "corroborated"}
_BAD_FRESHNESS = {"stale"}


def _question_mentions(application_use: str, question_index: int) -> bool:
    compact = re.sub(r"\s+", "", application_use or "")
    if not compact:
        return False
    if "전체문항" in compact or "공통문항" in compact:
        return True
    return bool(re.search(rf"문항[^\d]{{0,3}}{question_index}(?!\d)", compact))


def _eligible_for_slot(
    claim: Mapping[str, Any],
    slot: Mapping[str, Any],
    question_index: int,
    losing_claim_ids: set[str],
    unresolved_groups: set[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    claim_id = str(claim.get("claim_id", ""))
    if not claim_id or not str(claim.get("claim", "")).strip():
        reasons.append("missing_claim_identity")
    if claim_id in losing_claim_ids:
        reasons.append("superseded_conflict_claim")
    conflict_group = str(claim.get("conflict_group", "")).strip() or str(claim.get("subject_key", "")).strip()
    if conflict_group and conflict_group in unresolved_groups:
        reasons.append("unresolved_conflict")
    if str(claim.get("verification_status", "confirmed")) not in _GOOD_VERIFICATION:
        reasons.append("unverified")

    role = str(claim.get("argument_role", "")).strip()
    types = {str(item) for item in slot.get("claim_types", [])}
    claim_type = str(claim.get("claim_type", "unspecified"))
    if role != str(slot.get("argument_role", "")) and claim_type not in types:
        reasons.append("role_or_type_mismatch")

    support = str(claim.get("support_strength", "direct") or "direct").lower()
    if support not in _GOOD_SUPPORT:
        reasons.append("weak_support")
    try:
        tier = int(claim.get("source_tier", 2))
    except (TypeError, ValueError):
        tier = 5
    if tier > int(slot.get("maximum_source_tier", 2)):
        reasons.append("source_tier_too_low")
    freshness = str(claim.get("freshness_class", "unknown") or "unknown").lower()
    requirement = str(slot.get("freshness_requirement", "stable_or_current"))
    if freshness in _BAD_FRESHNESS:
        reasons.append("stale")
    if requirement in {"current", "posting_bound"} and freshness not in {"current", "posting_bound"}:
        reasons.append("freshness_not_current")
    if requirement == "stable_or_current" and freshness not in {"stable", "current", "posting_bound"}:
        reasons.append("freshness_unknown")

    application_use = str(claim.get("application_use", ""))
    if application_use and not _question_mentions(application_use, question_index):
        reasons.append("assigned_to_other_question")
    return not reasons, reasons


def build_research_coverage(
    plan: Mapping[str, Any],
    claims: Iterable[Mapping[str, Any]],
    conflict_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    claim_rows = [item for item in claims if isinstance(item, Mapping)]
    conflict_report = conflict_report or {}
    losing = {str(item) for item in conflict_report.get("losing_claim_ids", [])}
    unresolved = {str(item) for item in conflict_report.get("unresolved_groups", [])}

    question_rows: list[dict[str, Any]] = []
    total_required = 0
    covered_required = 0
    next_queries: list[str] = []
    for question in plan.get("questions", []) or []:
        if not isinstance(question, Mapping):
            continue
        index = int(question.get("question_index", 0))
        slot_rows: list[dict[str, Any]] = []
        for slot in question.get("slots", []) or []:
            if not isinstance(slot, Mapping):
                continue
            required = bool(slot.get("required", False))
            minimum = max(1, int(slot.get("minimum_claims", 1)))
            if required:
                total_required += 1
            matching: list[str] = []
            rejected: dict[str, list[str]] = {}
            for claim in claim_rows:
                ok, reasons = _eligible_for_slot(claim, slot, index, losing, unresolved)
                claim_id = str(claim.get("claim_id", ""))
                if ok:
                    matching.append(claim_id)
                elif claim_id and (
                    str(claim.get("argument_role", "")) == str(slot.get("argument_role", ""))
                    or str(claim.get("claim_type", "")) in {str(x) for x in slot.get("claim_types", [])}
                ):
                    rejected[claim_id] = reasons
            passed = len(matching) >= minimum
            if required and passed:
                covered_required += 1
            status = "pass" if passed else "missing" if not rejected else "weak"
            if required and not passed:
                query = str(slot.get("suggested_query", "")).strip()
                if query and query not in next_queries:
                    next_queries.append(query)
            slot_rows.append(
                {
                    "slot_id": slot.get("slot_id"),
                    "argument_role": slot.get("argument_role"),
                    "required": required,
                    "status": status,
                    "minimum_claims": minimum,
                    "accepted_claim_ids": matching,
                    "rejected_claims": rejected,
                    "suggested_query": slot.get("suggested_query"),
                }
            )
        required_slots = [item for item in slot_rows if item["required"]]
        ready = all(item["status"] == "pass" for item in required_slots)
        question_rows.append(
            {
                "question_index": index,
                "intent": question.get("intent"),
                "research_required": bool(question.get("research_required")),
                "ready": ready,
                "slots": slot_rows,
            }
        )
    stop = total_required == covered_required
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan.get("plan_id"),
        "required_slots": total_required,
        "covered_required_slots": covered_required,
        "coverage_ratio": 1.0 if total_required == 0 else round(covered_required / total_required, 4),
        "stop_research": stop,
        "status": "ready" if stop else "needs_research",
        "next_queries": next_queries,
        "questions": question_rows,
    }


def should_stop_research(coverage: Mapping[str, Any]) -> bool:
    return bool(coverage.get("stop_research", False))
