"""Conservative conflict resolution for company-research claims.

Claims are compared only when they explicitly share ``conflict_group`` or
``subject_key``. This avoids inventing conflicts between merely related facts.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1

_SUPPORT_RANK = {"direct": 3, "strong": 3, "corroborated": 2, "indirect": 1, "unknown": 0, "": 0}
_FRESHNESS_RANK = {"current": 4, "posting_bound": 4, "stable": 3, "historical": 2, "unknown": 1, "stale": 0, "": 1}
_VERIFY_RANK = {"verified": 3, "confirmed": 3, "contextual": 1, "unverified": 0, "rejected": -1}


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _group_key(claim: Mapping[str, Any]) -> str:
    return str(claim.get("conflict_group", "")).strip() or str(claim.get("subject_key", "")).strip()


def _date_ordinal(value: str) -> int:
    value = value.strip()
    if not value:
        return 0
    try:
        return date.fromisoformat(value[:10]).toordinal()
    except ValueError:
        return 0


def _rank(claim: Mapping[str, Any]) -> tuple[int, int, int, int, int, str]:
    verify = _VERIFY_RANK.get(str(claim.get("verification_status", "confirmed")).lower(), 0)
    support = _SUPPORT_RANK.get(str(claim.get("support_strength", "unknown")).lower(), 0)
    freshness = _FRESHNESS_RANK.get(str(claim.get("freshness_class", "unknown")).lower(), 1)
    try:
        tier = int(claim.get("source_tier", 5))
    except (TypeError, ValueError):
        tier = 5
    recency = max(
        _date_ordinal(str(claim.get("effective_from", ""))),
        _date_ordinal(str(claim.get("basis_date", ""))),
        _date_ordinal(str(claim.get("published_at", ""))),
    )
    return (verify, support, freshness, -tier, recency, str(claim.get("claim_id", "")))


def resolve_research_conflicts(claims: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for claim in claims:
        key = _group_key(claim)
        if key:
            groups.setdefault(key, []).append(claim)

    items: list[dict[str, Any]] = []
    losing_ids: set[str] = set()
    unresolved_groups: list[str] = []
    for key, rows in sorted(groups.items()):
        distinct = {_norm_text(str(item.get("claim", ""))) for item in rows if str(item.get("claim", "")).strip()}
        if len(distinct) <= 1:
            continue
        ranked = sorted(rows, key=_rank, reverse=True)
        winner = ranked[0]
        winner_rank = _rank(winner)[:-1]
        tied = [item for item in ranked if _rank(item)[:-1] == winner_rank]
        unresolved = len(tied) > 1 and len({_norm_text(str(item.get("claim", ""))) for item in tied}) > 1
        if unresolved:
            unresolved_groups.append(key)
        else:
            losing_ids.update(str(item.get("claim_id", "")) for item in ranked[1:] if str(item.get("claim_id", "")))
        items.append(
            {
                "conflict_group": key,
                "status": "unresolved" if unresolved else "resolved",
                "winner_claim_id": None if unresolved else str(winner.get("claim_id", "")),
                "competing_claim_ids": [str(item.get("claim_id", "")) for item in ranked],
                "reason": (
                    "top claims tie on verification/support/freshness/source tier/recency"
                    if unresolved
                    else "selected by verification, support, freshness, source tier, then effective/published recency"
                ),
                "human_review_required": unresolved,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "conflicts": items,
        "losing_claim_ids": sorted(losing_ids),
        "unresolved_groups": unresolved_groups,
        "status": "needs_review" if unresolved_groups else "resolved",
    }
