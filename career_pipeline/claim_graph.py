"""Typed, question-scoped claim graph for shadow-mode provenance analysis.

This module does not create new factual authority. It projects already-referenced
applicant and research claims into an atomic representation that separates the
claim proposition from surrounding writing context.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .authority_contract import metric_values, research_is_submission_authority
from .profile_schema import claim_submission_issues

SCHEMA_VERSION = 1
ARCHITECTURE = "typed_claim_graph_shadow_v1"


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _clean_strings(values: Sequence[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _source_ref_dict(value: Any) -> dict[str, Any]:
    return {
        "source_path": str(_get(value, "source_path", "")),
        "paragraph_index": int(_get(value, "paragraph_index", 0) or 0),
        "source_sha256": str(_get(value, "source_sha256", "")),
        "excerpt_sha256": str(_get(value, "excerpt_sha256", "")),
    }


@dataclass(frozen=True)
class AuthorityLabel:
    authority_kind: str
    subject: str
    factual_authority: bool
    question_indexes: tuple[int, ...]
    metric_values: tuple[str, ...]
    contribution_ceiling: str
    temporal_scope: str | None = None
    source_tier: int | None = None
    freshness_class: str | None = None


@dataclass(frozen=True)
class ClaimNode:
    node_id: str
    source_kind: str
    proposition: str
    context: tuple[str, ...]
    label: AuthorityLabel
    source_refs: tuple[Mapping[str, Any], ...]
    proposition_sha256: str
    provenance_sha256: str


@dataclass(frozen=True)
class ClaimGraph:
    schema_version: int
    architecture: str
    nodes: tuple[ClaimNode, ...]

    def by_id(self) -> dict[str, ClaimNode]:
        return {node.node_id: node for node in self.nodes}


def _question_references(
    responses: Sequence[Any],
) -> tuple[
    dict[tuple[str, str], set[int]],
    dict[tuple[str, str], set[int]],
    dict[str, set[int]],
]:
    applicant_by_id: dict[tuple[str, str], set[int]] = {}
    applicant_by_field: dict[tuple[str, str], set[int]] = {}
    research: dict[str, set[int]] = {}

    for response in responses:
        question_index = int(_get(response, "question_index", 0) or 0)
        for ref in _get(response, "experience_refs", ()) or ():
            experience_id = str(_get(ref, "experience_id", ""))
            if not experience_id:
                continue
            claim_ids = tuple(_get(ref, "claim_ids", ()) or ())
            claim_fields = tuple(_get(ref, "claim_fields", ()) or ())
            for claim_id in claim_ids:
                applicant_by_id.setdefault(
                    (experience_id, str(claim_id)), set()
                ).add(question_index)
            if not claim_ids:
                for field_name in claim_fields:
                    applicant_by_field.setdefault(
                        (experience_id, str(field_name)), set()
                    ).add(question_index)
        for claim_id in _get(response, "research_refs", ()) or ():
            research.setdefault(str(claim_id), set()).add(question_index)

    return applicant_by_id, applicant_by_field, research


def _applicant_nodes(
    responses: Sequence[Any],
    ledger: Any,
) -> list[ClaimNode]:
    by_id, by_field, _ = _question_references(responses)
    nodes: list[ClaimNode] = []

    for experience in _get(ledger, "experiences", ()) or ():
        if str(_get(experience, "status", "")) != "confirmed":
            continue
        experience_id = str(_get(experience, "experience_id", ""))
        if not experience_id:
            continue

        context = _clean_strings(
            (
                _get(experience, "role", ""),
                _get(experience, "situation", ""),
                *(_get(experience, "actions", ()) or ()),
                *(_get(experience, "outcomes", ()) or ()),
            )
        )

        for claim in _get(experience, "claims", ()) or ():
            if str(_get(claim, "status", "")) != "confirmed":
                continue
            claim_id = str(_get(claim, "claim_id", ""))
            field_name = str(_get(claim, "field", ""))
            question_indexes = set()
            if claim_id:
                question_indexes.update(by_id.get((experience_id, claim_id), set()))
            if not claim_id and field_name:
                question_indexes.update(
                    by_field.get((experience_id, field_name), set())
                )
            if not question_indexes:
                continue

            proposition = str(_get(claim, "normalized_value", "")).strip()
            verification = _get(claim, "verification", None)
            contribution = (
                str(_get(verification, "contribution", "unknown"))
                if verification is not None
                else "unknown"
            )
            measurement_period = (
                _get(verification, "measurement_period", None)
                if verification is not None
                else None
            )
            source_refs = tuple(
                _source_ref_dict(item)
                for item in (_get(claim, "evidence", ()) or ())
            )
            label = AuthorityLabel(
                authority_kind="factual",
                subject="applicant",
                factual_authority=not bool(claim_submission_issues(claim)),
                question_indexes=tuple(sorted(question_indexes)),
                metric_values=tuple(metric_values(proposition)),
                contribution_ceiling=contribution,
                temporal_scope=(
                    str(measurement_period).strip()
                    if measurement_period is not None
                    and str(measurement_period).strip()
                    else None
                ),
            )
            node_id = f"applicant:{experience_id}:{claim_id or field_name}"
            proposition_sha = sha256(proposition.encode("utf-8")).hexdigest()
            provenance = {
                "node_id": node_id,
                "proposition_sha256": proposition_sha,
                "label": asdict(label),
                "source_refs": list(source_refs),
            }
            nodes.append(
                ClaimNode(
                    node_id=node_id,
                    source_kind="applicant",
                    proposition=proposition,
                    context=context,
                    label=label,
                    source_refs=source_refs,
                    proposition_sha256=proposition_sha,
                    provenance_sha256=_stable_hash(provenance),
                )
            )
    return nodes


def _research_nodes(
    responses: Sequence[Any],
    research_claims: Sequence[Any],
    research_raw: Mapping[str, Mapping[str, Any]] | None,
) -> list[ClaimNode]:
    _, _, references = _question_references(responses)
    raw_by_id = dict(research_raw or {})
    nodes: list[ClaimNode] = []

    for claim in research_claims:
        claim_id = str(_get(claim, "claim_id", ""))
        if not claim_id or claim_id not in references:
            continue
        raw = raw_by_id.get(claim_id, {})
        proposition = str(
            _get(claim, "claim", raw.get("claim", ""))
        ).strip()
        excerpt = str(
            _get(claim, "evidence_excerpt", raw.get("evidence_excerpt", ""))
        ).strip()
        source_type = str(
            _get(claim, "source_type", raw.get("source_type", ""))
        ).strip()
        source_tier_value = raw.get("source_tier")
        source_tier: int | None = None
        if isinstance(source_tier_value, int) and not isinstance(
            source_tier_value, bool
        ):
            source_tier = source_tier_value
        elif (
            isinstance(source_tier_value, str)
            and source_tier_value.strip().isdigit()
        ):
            source_tier = int(source_tier_value.strip())

        temporal_scope = next(
            (
                str(value).strip()
                for value in (
                    _get(claim, "basis_date", raw.get("basis_date", "")),
                    _get(claim, "published_at", raw.get("published_at", "")),
                    _get(claim, "checked_at", raw.get("checked_at", "")),
                )
                if value and str(value).strip()
            ),
            None,
        )
        source_refs = (
            {
                "claim_id": claim_id,
                "source_url": str(
                    _get(claim, "source_url", raw.get("source_url", ""))
                ),
                "source_type": source_type,
                "claim_type": str(
                    _get(claim, "claim_type", raw.get("claim_type", ""))
                ),
                "checked_at": str(
                    _get(claim, "checked_at", raw.get("checked_at", ""))
                ),
                "published_at": str(
                    _get(claim, "published_at", raw.get("published_at", ""))
                ),
                "basis_date": str(
                    _get(claim, "basis_date", raw.get("basis_date", ""))
                ),
                "argument_role": raw.get("argument_role"),
                "support_strength": raw.get("support_strength"),
                "freshness_class": raw.get("freshness_class"),
            },
        )
        label = AuthorityLabel(
            authority_kind="factual",
            subject="organization",
            factual_authority=research_is_submission_authority(claim, raw),
            question_indexes=tuple(sorted(references[claim_id])),
            metric_values=tuple(metric_values(proposition)),
            contribution_ceiling="not_applicable",
            temporal_scope=temporal_scope,
            source_tier=source_tier,
            freshness_class=(
                str(raw.get("freshness_class")).strip()
                if raw.get("freshness_class") is not None
                and str(raw.get("freshness_class")).strip()
                else None
            ),
        )
        node_id = f"research:{claim_id}"
        proposition_sha = sha256(proposition.encode("utf-8")).hexdigest()
        provenance = {
            "node_id": node_id,
            "proposition_sha256": proposition_sha,
            "label": asdict(label),
            "source_refs": list(source_refs),
        }
        nodes.append(
            ClaimNode(
                node_id=node_id,
                source_kind="research",
                proposition=proposition,
                context=(excerpt,) if excerpt else (),
                label=label,
                source_refs=source_refs,
                proposition_sha256=proposition_sha,
                provenance_sha256=_stable_hash(provenance),
            )
        )
    return nodes


def build_claim_graph(
    responses: Sequence[Any],
    ledger: Any,
    research_claims: Sequence[Any] = (),
    *,
    research_raw: Mapping[str, Mapping[str, Any]] | None = None,
) -> ClaimGraph:
    nodes = _applicant_nodes(responses, ledger) + _research_nodes(
        responses, research_claims, research_raw
    )
    deduplicated = {node.node_id: node for node in nodes}
    return ClaimGraph(
        schema_version=SCHEMA_VERSION,
        architecture=ARCHITECTURE,
        nodes=tuple(
            sorted(deduplicated.values(), key=lambda node: node.node_id)
        ),
    )


def claim_graph_to_dict(graph: ClaimGraph) -> dict[str, Any]:
    rows = []
    for node in graph.nodes:
        rows.append(
            {
                "node_id": node.node_id,
                "source_kind": node.source_kind,
                "proposition": node.proposition,
                "context": list(node.context),
                "label": {
                    **asdict(node.label),
                    "question_indexes": list(node.label.question_indexes),
                    "metric_values": list(node.label.metric_values),
                },
                "source_refs": [dict(row) for row in node.source_refs],
                "proposition_sha256": node.proposition_sha256,
                "provenance_sha256": node.provenance_sha256,
            }
        )
    return {
        "schema_version": graph.schema_version,
        "architecture": graph.architecture,
        "nodes": rows,
        "summary": {
            "total_nodes": len(rows),
            "factual_authority_nodes": sum(
                bool(node.label.factual_authority) for node in graph.nodes
            ),
            "by_source_kind": {
                kind: sum(node.source_kind == kind for node in graph.nodes)
                for kind in sorted({node.source_kind for node in graph.nodes})
            },
        },
    }
