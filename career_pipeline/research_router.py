"""Route coverage-approved company evidence into Narrative Compiler blueprints.

The legacy blueprint selector remains intact for compatibility. This additive
layer replaces lexical-only research selection with the exact claims that filled
question-specific argument slots.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

SCHEMA_VERSION = 1


def _research_contract(claim: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "claim_id", "claim", "claim_type", "argument_role", "evidence_excerpt",
        "checked_at", "published_at", "basis_date", "effective_from", "effective_to",
        "freshness_class", "support_strength", "source_type", "source_tier", "publisher",
        "application_use", "source_url", "conflict_group", "subject_key",
    )
    return {key: claim.get(key, "") for key in keys}


def route_research_into_blueprint(
    packet: Mapping[str, Any],
    research_report: Mapping[str, Any],
) -> dict[str, Any]:
    routed = deepcopy(dict(packet))
    claims = {
        str(item.get("claim_id", "")): item
        for item in research_report.get("claims", []) or []
        if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
    }
    coverage_by_q = {
        int(item.get("question_index", 0)): item
        for item in research_report.get("coverage", {}).get("questions", []) or []
        if isinstance(item, Mapping)
    }
    routed_questions: list[dict[str, Any]] = []
    for raw_blueprint in routed.get("questions", []) or []:
        if not isinstance(raw_blueprint, Mapping):
            continue
        blueprint = dict(raw_blueprint)
        q = int(blueprint.get("question_index", 0))
        coverage = coverage_by_q.get(q, {})
        ordered_ids: list[str] = []
        slot_summary: list[dict[str, Any]] = []
        for slot in coverage.get("slots", []) or []:
            if not isinstance(slot, Mapping):
                continue
            accepted = [
                str(item) for item in slot.get("accepted_claim_ids", []) if str(item)
            ]
            for claim_id in accepted:
                if claim_id not in ordered_ids:
                    ordered_ids.append(claim_id)
            slot_summary.append(
                {
                    "argument_role": slot.get("argument_role"),
                    "required": bool(slot.get("required")),
                    "status": slot.get("status"),
                    "accepted_claim_ids": accepted,
                }
            )
        if coverage.get("research_required"):
            blueprint["research_claims"] = [
                _research_contract(claims[claim_id])
                for claim_id in ordered_ids
                if claim_id in claims
            ]
        blueprint["research_intelligence"] = {
            "schema_version": SCHEMA_VERSION,
            "coverage_status": "ready" if coverage.get("ready") else "not_ready",
            "slots": slot_summary,
            "selection_policy": "coverage_approved_argument_roles_before_lexical_similarity",
        }
        risks = list(blueprint.get("risk_controls", []) or [])
        for rule in (
            "Use only coverage-approved company claims; stale or superseded company facts are not factual authority.",
            "Prefer the research claim's argument_role over brochure-like company description.",
        ):
            if rule not in risks:
                risks.append(rule)
        blueprint["risk_controls"] = risks
        routed_questions.append(blueprint)
    routed["questions"] = routed_questions
    routed["research_intelligence"] = {
        "schema_version": SCHEMA_VERSION,
        "status": research_report.get("coverage", {}).get("status"),
        "coverage_ratio": research_report.get("coverage", {}).get("coverage_ratio"),
        "conflict_status": research_report.get("conflicts", {}).get("status"),
        "routing_policy": "question_slot_coverage",
    }
    return routed
