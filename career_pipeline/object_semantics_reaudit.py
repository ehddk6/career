"""PRIVATE 3-way audit: current v2 vs parser-v2 exact vs bounded semantics.

This module is shadow-only. It does not change production relation, criterion,
portfolio, writer, judge, interview, or gate semantics. Recovered shadow DIRECT
rows are review candidates only; human/review labels are always null in outputs.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .behavior_span_parser_v2 import BehaviorSpan, extract_behavior_spans
from .object_semantics_shadow import (
    SEMANTIC_POLICY_VERSION,
    semantic_object_match_verb_aware,
)

ARCHITECTURE = "parser_first_object_semantics_3way_private_audit_v1"
_REQUIRED = (
    "run.json",
    "00_채용공고분석.json",
    "02_확정경험원장.json",
    "04_공식근거.json",
)
# Deliberately shadow-only. Official ConstructCriterion verbs remain unchanged.
_SEMANTIC_VERB_ALIAS = {"crit_documentation_record_decision_or_action": {"메모"}}


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _claim_texts(ledger: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for exp in ledger.get("experiences", []) or []:
        if not isinstance(exp, Mapping):
            continue
        eid = str(exp.get("experience_id", ""))
        for claim in exp.get("claims", []) or []:
            if not isinstance(claim, Mapping):
                continue
            cid = str(claim.get("claim_id") or claim.get("field") or "")
            if cid:
                out[f"applicant:{eid}:{cid}"] = str(claim.get("normalized_value", ""))
    return out


def _v1_relations(portfolio: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for row in portfolio.get("links", []) or []:
        if isinstance(row, Mapping):
            out[str(row.get("evidence_id", ""))][str(row.get("construct_id", ""))] = str(
                row.get("relation", "none")
            )
    return dict(out)


def _atoms_by_evidence(payload: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in payload.get("atoms", []) or []:
        if isinstance(atom, Mapping):
            out[str(atom.get("applicant_evidence_id", ""))].append(dict(atom))
    return dict(out)


def _verified_claim_authority(ledger: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Apply the current canonical claim/source gate without requiring old atoms.

    Parser-first recall must be able to recover a true predicate missed by the
    legacy extractor. Authority therefore comes from the same confirmed,
    submission-safe, canonical EvidenceRef gate used by Behavior IR, not from an
    already-existing BehaviorAtom.
    """
    from .behavior_ir import (
        _OWNERSHIP_CEILING,
        _actor,
        _canonical_source_binding_issues,
        _is_metric_claim,
        _profile_claim,
    )
    from .profile_schema import claim_submission_issues

    out: dict[str, dict[str, Any]] = {}
    for exp in ledger.get("experiences", []) or []:
        if not isinstance(exp, Mapping):
            continue
        eid = str(exp.get("experience_id", ""))
        for claim in exp.get("claims", []) or []:
            if not isinstance(claim, Mapping):
                continue
            cid = str(claim.get("claim_id") or claim.get("field") or "")
            text = str(claim.get("normalized_value", "")).strip()
            if not cid or not text or str(claim.get("status", "")) != "confirmed":
                continue
            if _is_metric_claim(claim):
                continue
            profile = _profile_claim(claim)
            if profile is None or claim_submission_issues(profile) or not profile.evidence:
                continue
            if _canonical_source_binding_issues(eid, profile):
                continue
            contribution = profile.verification.contribution if profile.verification else "unknown"
            out[f"applicant:{eid}:{cid}"] = {
                "actor": _actor(text),
                "source_kind": "applicant",
                "source_binding_status": "valid",
                "source_ref_ids": [item.source_path for item in profile.evidence],
                "claim_status": "confirmed",
                "contribution_scope": contribution,
                "ownership_ceiling": _OWNERSHIP_CEILING.get(
                    contribution, "unknown_review_required"
                ),
                "authority_status": "factual",
                "context_only": False,
            }
    return out


def _project(
    spans: Sequence[BehaviorSpan], authority: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    if not spans or not authority:
        return []
    return [
        {
            "atom_id": f"parser_v2_shadow_{index}",
            "action": span.action,
            "object": span.object,
            "actor": authority.get("actor", "unknown"),
            "source_kind": authority.get("source_kind", "applicant"),
            "source_binding_status": authority.get("source_binding_status", ""),
            "source_ref_ids": list(authority.get("source_ref_ids", []) or []),
            "claim_status": authority.get("claim_status", ""),
            "contribution_scope": authority.get("contribution_scope", "unknown"),
            "ownership_ceiling": authority.get(
                "ownership_ceiling", "unknown_review_required"
            ),
            "authority_status": "factual",
            "context_only": bool(authority.get("context_only", False)),
            "predicate_basis": span.predicate_basis,
            "object_basis": span.object_basis,
            "source_segment": span.source_segment,
        }
        for index, span in enumerate(spans)
    ]


def _criterion_state(
    criterion: Any, atoms: Sequence[Mapping[str, Any]], *, semantic: bool
) -> dict[str, Any]:
    from .construct_relation_v2 import _tokens

    first_action_only: dict[str, Any] | None = None
    verbs = set(criterion.verbs)
    if semantic:
        verbs |= _SEMANTIC_VERB_ALIAS.get(criterion.criterion_id, set())
    for atom in atoms:
        if str(atom.get("action", "")) not in verbs:
            continue
        object_text = str(atom.get("object", ""))
        if not criterion.object_class:
            object_ok, basis, terms = True, "no_object_requirement", []
        elif semantic:
            match = semantic_object_match_verb_aware(
                criterion.criterion_id,
                str(atom.get("action", "")),
                object_text,
                criterion.object_class,
            )
            object_ok, basis, terms = match.matched, match.basis, list(match.matched_terms)
        else:
            terms = sorted(_tokens(object_text) & set(criterion.object_class))
            object_ok, basis = bool(terms), "exact" if terms else "none"
        detail = {
            "state": "full" if object_ok else "action_only",
            "action": atom.get("action", ""),
            "object": object_text,
            "object_match_basis": basis,
            "matched_terms": terms,
            "predicate_basis": atom.get("predicate_basis", ""),
            "object_basis": atom.get("object_basis", ""),
            "source_segment": atom.get("source_segment", ""),
        }
        if object_ok:
            return detail
        if first_action_only is None:
            first_action_only = detail
    return first_action_only or {
        "state": "missing",
        "action": "",
        "object": "",
        "object_match_basis": "none",
        "matched_terms": [],
    }


def _shadow_relation(
    construct: Any,
    criteria: Sequence[Any],
    atoms: Sequence[Mapping[str, Any]],
    v1_relation: str,
    *,
    semantic: bool,
) -> dict[str, Any]:
    from .construct_relation_v2 import _relation_from_states

    evidence = {
        criterion.criterion_id: _criterion_state(criterion, atoms, semantic=semantic)
        for criterion in criteria
    }
    states = {key: value["state"] for key, value in evidence.items()}
    relation, code, details = _relation_from_states(
        construct_status=str(construct.status),
        criteria=criteria,
        states=states,
        candidate_atoms=atoms,
        v1_relation=v1_relation,
        apply_contribution=True,
    )
    return {
        "relation": relation,
        "explanation_code": code,
        "criterion_match_states": states,
        "criterion_evidence": evidence,
        "criterion_ids_matched": list(details.get("matched", [])),
        "criterion_ids_missing": list(details.get("missing", [])),
        "criterion_ids_object_unverified": list(details.get("object_unverified", [])),
        "required_criterion_ids_missing": list(details.get("required_missing", [])),
        "required_criterion_ids_object_unverified": list(
            details.get("required_object_unverified", [])
        ),
        "authority_ok": bool(
            details.get("source_kind_ok", True)
            and details.get("confirmed_ok", True)
            and details.get("source_binding_ok", True)
        ),
        "actor_ok_for_direct": bool(details.get("actor_ok", True)),
        "contribution_ok_for_direct": bool(details.get("contribution_ok", True)),
        "context_only": not bool(details.get("context_ok", True)),
    }


def _relation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    direct = sum(row.get("relation") == "direct" for row in rows)
    return {
        "direct_count": direct,
        "direct_run_count": int(bool(direct)),
        "partial_count": sum(row.get("relation") == "partial" for row in rows),
        "inferred_count": sum(row.get("relation") == "inferred" for row in rows),
        "none_count": sum(row.get("relation") == "none" for row in rows),
    }


def build_parser_object_shadow_relations(
    graph: Any,
    ledger: Mapping[str, Any],
    atoms_payload: Mapping[str, Any],
    v1_relations: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    from .construct_criteria import criteria_for_graph

    v1_relations = v1_relations or {}
    texts = _claim_texts(ledger)
    current_atoms = _atoms_by_evidence(atoms_payload)
    verified_authority = _verified_claim_authority(ledger)
    criteria_by_construct: dict[str, list[Any]] = defaultdict(list)
    for criterion in criteria_for_graph(graph):
        criteria_by_construct[criterion.construct_id].append(criterion)

    exact_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []
    diagnostics = Counter()
    precision = Counter()
    weak_alias_blocked_keys: list[tuple[str, str]] = []
    for evidence_id, authority in sorted(verified_authority.items()):
        old_atoms = current_atoms.get(evidence_id, [])
        spans = extract_behavior_spans(texts.get(evidence_id, ""))
        parser_atoms = _project(spans, authority)
        diagnostics["evaluated_evidence_count"] += 1
        diagnostics["parser_span_count"] += len(spans)
        diagnostics["parser_recovered_no_current_atom_claim_count"] += int(
            bool(spans) and not old_atoms
        )
        actions = {span.action for span in spans}
        diagnostics["parser_suppressed_current_atom_count"] += sum(
            str(atom.get("action", "")) not in actions for atom in old_atoms
        )
        diagnostics["object_span_change_count"] += sum(
            any(
                span.action == str(atom.get("action", ""))
                and span.object != str(atom.get("object", ""))
                for span in spans
            )
            for atom in old_atoms
        )
        for construct in graph.constructs:
            criteria = criteria_by_construct.get(construct.construct_id, [])
            old_v1 = str(
                v1_relations.get(evidence_id, {}).get(construct.construct_id, "") or ""
            )
            base = {
                "evidence_id": evidence_id,
                "construct_id": construct.construct_id,
                "construct_status": str(construct.status),
                "parsed_spans": [span.to_dict() for span in spans],
            }
            exact_rows.append(
                {
                    **base,
                    **_shadow_relation(
                        construct, criteria, parser_atoms, old_v1, semantic=False
                    ),
                }
            )
            semantic_row = _shadow_relation(
                construct, criteria, parser_atoms, old_v1, semantic=True
            )
            semantic_rows.append({**base, **semantic_row})
            semantic_bases = [
                str(ev.get("object_match_basis", ""))
                for ev in semantic_row.get("criterion_evidence", {}).values()
            ]
            if any(
                basis in {"blocked_weak_generic", "blocked_no_artifact"}
                for basis in semantic_bases
            ):
                precision["weak_alias_blocked_count"] += 1
                weak_alias_blocked_keys.append((evidence_id, construct.construct_id))
            if semantic_row.get("relation") == "direct" and any(
                basis == "artifact_supported" for basis in semantic_bases
            ):
                precision["artifact_supported_direct_count"] += 1
    exact_rows.sort(key=lambda row: (row["evidence_id"], row["construct_id"]))
    semantic_rows.sort(key=lambda row: (row["evidence_id"], row["construct_id"]))
    return {
        "schema_version": 1,
        "architecture": "parser_first_object_semantics_relation_shadow_v1",
        "policy": {
            "decision_effect": "none_shadow_mode",
            "production_relation_v2_changed": False,
            "official_criterion_vocabulary_changed": False,
            "multi_claim_enabled": False,
            "authority_source": "canonical_confirmed_submission_safe_source_bound_claim_gate",
            "parser_recall_does_not_depend_on_legacy_atom_existence": True,
        },
        "semantic_policy_version": SEMANTIC_POLICY_VERSION,
        "diagnostics": dict(diagnostics),
        "precision_diagnostics": dict(precision),
        "weak_alias_blocked_keys": [list(k) for k in weak_alias_blocked_keys],
        "exact": {"relations": exact_rows, "summary": _relation_summary(exact_rows)},
        "semantic": {
            "relations": semantic_rows,
            "summary": _relation_summary(semantic_rows),
        },
    }


def _index(payload: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row.get("evidence_id", "")), str(row.get("construct_id", ""))): dict(row)
        for row in payload.get("relations", []) or []
        if isinstance(row, Mapping)
    }


def _selected(ep: Mapping[str, Any]) -> tuple[dict[int, list[str]], set[str]]:
    by_question: dict[int, list[str]] = {}
    for assignment in ep.get("assignments", []) or []:
        if not isinstance(assignment, Mapping):
            continue
        q = int(assignment.get("question_index", 0) or 0)
        by_question[q] = [
            str(row.get("evidence_id"))
            for row in assignment.get("preferred_evidence", []) or []
            if isinstance(row, Mapping)
            and row.get("source_kind") == "applicant"
            and row.get("evidence_id")
        ]
    return by_question, {eid for rows in by_question.values() for eid in rows}


def _a_count(
    by_question: Mapping[int, Sequence[str]],
    relations: Mapping[tuple[str, str], Mapping[str, Any]],
    core: set[str],
) -> int:
    return sum(
        not any(
            relations.get((evidence_id, construct_id), {}).get("relation")
            in {"direct", "partial"}
            for construct_id in core
        )
        for rows in by_question.values()
        for evidence_id in rows
    )


def _b_count(
    relations: Mapping[tuple[str, str], Mapping[str, Any]],
    core: set[str],
    selected: set[str],
) -> int:
    return len(
        {
            evidence_id
            for (evidence_id, construct_id), row in relations.items()
            if row.get("relation") == "direct"
            and construct_id in core
            and evidence_id not in selected
        }
    )


def audit_parser_object_run(run_dir: Path) -> dict[str, Any] | None:
    run = run_dir.resolve()
    if not all((run / name).is_file() for name in _REQUIRED):
        return None
    state = _read(run / "run.json", {})
    posting = _read(run / "00_채용공고분석.json", {})
    ledger = _read(run / "02_확정경험원장.json", {})
    research = _read(run / "04_공식근거.json", [])
    if not isinstance(state, Mapping) or not isinstance(posting, Mapping):
        return None
    if not isinstance(ledger, Mapping):
        ledger = {}
    if not isinstance(research, list):
        research = []

    from .behavior_ir import build_behavior_atoms
    from .construct_portfolio import build_construct_portfolio
    from .construct_relation_v2 import build_relation_v2
    from .evidence_portfolio import build_evidence_portfolio
    from .job_analysis_compiler import build_job_analysis_graph
    from .real_run_disagreement_audit import audit_run

    graph = build_job_analysis_graph(
        posting,
        tuple(row for row in research if isinstance(row, Mapping)),
        target=str(state.get("target") or posting.get("target") or "").strip(),
    )
    ep = build_evidence_portfolio(run)
    cp = build_construct_portfolio(
        graph, ledger, evidence_portfolio=ep, run_state=state
    )
    atoms = build_behavior_atoms(ledger)
    v1 = _v1_relations(cp)
    current = build_relation_v2(graph, atoms, v1)
    shadow = build_parser_object_shadow_relations(graph, ledger, atoms, v1)

    current_index = _index(current)
    exact_index = _index(shadow["exact"])
    semantic_index = _index(shadow["semantic"])
    core = set(graph.core_construct_ids)
    texts = _claim_texts(ledger)
    by_question, selected = _selected(ep)

    recovered_exact: list[dict[str, Any]] = []
    recovered_semantic: list[dict[str, Any]] = []
    keys = sorted(set(current_index) | set(exact_index) | set(semantic_index))
    for evidence_id, construct_id in keys:
        key = (evidence_id, construct_id)
        current_relation = str(current_index.get(key, {}).get("relation", "none"))
        exact_relation = str(exact_index.get(key, {}).get("relation", "none"))
        semantic_relation = str(semantic_index.get(key, {}).get("relation", "none"))
        base = {
            "run_identifier": run.name,
            "evidence_id": evidence_id,
            "construct_id": construct_id,
            "atomic_claim": texts.get(evidence_id, ""),
            "selected_question_indices": sorted(
                q for q, ids in by_question.items() if evidence_id in ids
            ),
            "current_v2_relation": current_relation,
            "parser_v2_exact_relation": exact_relation,
            "parser_v2_semantic_relation": semantic_relation,
            "review_label": None,
            "human_label": None,
            "review_status": "candidate_only_not_human_labeled",
        }
        if exact_relation == "direct" and current_relation != "direct":
            recovered_exact.append(
                {**base, "recovery_basis": "parser_v2_exact", "shadow": exact_index[key]}
            )
        if semantic_relation == "direct" and current_relation != "direct":
            recovered_semantic.append(
                {
                    **base,
                    "recovery_basis": (
                        "bounded_semantic_only"
                        if exact_relation != "direct"
                        else "parser_v2_exact_also_direct"
                    ),
                    "shadow": semantic_index[key],
                }
            )

    authority_blocked = [
        row
        for row in semantic_index.values()
        if not row.get("required_criterion_ids_missing")
        and not row.get("required_criterion_ids_object_unverified")
        and row.get("relation") != "direct"
        and str(row.get("explanation_code", "")).startswith(
            ("direct_blocked", "prior_only")
        )
    ]
    legacy = audit_run(run) or {}
    current_a = sum(
        isinstance(row, Mapping) and row.get("kind") == "lexical_high_construct_weak"
        for row in legacy.get("disagreements", []) or []
    )
    return {
        "run_name": run.name,
        "current_v2": dict(current.get("summary", {})),
        "parser_v2_exact": dict(shadow["exact"]["summary"]),
        "parser_v2_semantic": dict(shadow["semantic"]["summary"]),
        "parser_diagnostics": dict(shadow["diagnostics"]),
        "precision_diagnostics": dict(shadow["precision_diagnostics"]),
        "weak_alias_blocked_keys": [
            list(k) for k in shadow.get("weak_alias_blocked_keys", [])
        ],
        "A": {
            "current_v2": current_a,
            "parser_v2_exact": _a_count(by_question, exact_index, core),
            "parser_v2_semantic": _a_count(by_question, semantic_index, core),
        },
        "B": {
            "current_v2": _b_count(current_index, core, selected),
            "parser_v2_exact": _b_count(exact_index, core, selected),
            "parser_v2_semantic": _b_count(semantic_index, core, selected),
        },
        "recovered_exact_direct": recovered_exact,
        "recovered_semantic_direct": recovered_semantic,
        "authority_blocked_semantic_direct_count": len(authority_blocked),
        "authority_blocked_semantic_direct": authority_blocked,
    }


def _unique_recovery_summary(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate recovered DIRECT rows by (evidence_id, construct_id, recovery_basis).

    Row-level candidates are preserved as-is; this is additive audit metadata.
    Labels stay null until human review.
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = (
            str(row.get("evidence_id", "")),
            str(row.get("construct_id", "")),
            str(row.get("recovery_basis", "")),
        )
        group = groups.setdefault(
            key,
            {
                "evidence_id": key[0],
                "construct_id": key[1],
                "recovery_basis": key[2],
                "row_count": 0,
                "unique_count": 1,
                "occurrence_count": 0,
                "run_identifiers": [],
                "review_label": None,
                "human_label": None,
            },
        )
        group["row_count"] += 1
        run_id = str(row.get("run_identifier", ""))
        if run_id and run_id not in group["run_identifiers"]:
            group["run_identifiers"].append(run_id)
    result = []
    for group in groups.values():
        group["run_identifiers"] = sorted(group["run_identifiers"])
        group["occurrence_count"] = len(group["run_identifiers"])
        result.append(group)
    result.sort(key=lambda g: (g["evidence_id"], g["construct_id"], g["recovery_basis"]))
    return result


def run_audit(runs_root: Path) -> dict[str, Any]:
    records = [
        result
        for directory in sorted(runs_root.resolve().iterdir())
        if directory.is_dir() and directory.name != "_audit"
        for result in [audit_parser_object_run(directory)]
        if result is not None
    ]
    current, exact, semantic, diagnostics, precision, a_counts, b_counts = (
        Counter() for _ in range(7)
    )
    recovered_exact: list[dict[str, Any]] = []
    recovered_semantic: list[dict[str, Any]] = []
    authority_blocked = 0
    weak_blocked_keys: set[tuple[str, str]] = set()
    for record in records:
        current.update(record["current_v2"])
        exact.update(record["parser_v2_exact"])
        semantic.update(record["parser_v2_semantic"])
        diagnostics.update(record["parser_diagnostics"])
        a_counts.update(record["A"])
        b_counts.update(record["B"])
        recovered_exact += record["recovered_exact_direct"]
        recovered_semantic += record["recovered_semantic_direct"]
        authority_blocked += record["authority_blocked_semantic_direct_count"]
        precision.update(record["precision_diagnostics"])
        weak_blocked_keys.update(
            (str(k[0]), str(k[1]))
            for k in record.get("weak_alias_blocked_keys", [])
            if isinstance(k, (list, tuple)) and len(k) >= 2
        )
    unique_summary = _unique_recovery_summary(
        [*recovered_exact, *recovered_semantic]
    )
    summary = {
        "run_count": len(records),
        "current_v2": dict(current),
        "parser_v2_exact": dict(exact),
        "parser_v2_semantic": dict(semantic),
        "parser_diagnostics": dict(diagnostics),
        "precision_diagnostics": dict(precision),
        "A": dict(a_counts),
        "B": dict(b_counts),
        "recovered_exact_direct_count": len(recovered_exact),
        "recovered_semantic_direct_count": len(recovered_semantic),
        "recovered_semantic_direct_row_count": len(recovered_semantic),
        "recovered_semantic_direct_unique_count": sum(
            1 for row in unique_summary if row["recovery_basis"] != "parser_v2_exact"
        ),
        "recovered_semantic_only_direct_count": sum(
            row.get("recovery_basis") == "bounded_semantic_only"
            for row in recovered_semantic
        ),
        "weak_alias_blocked_row_count": precision["weak_alias_blocked_count"],
        "weak_alias_blocked_unique_count": len(weak_blocked_keys),
        "authority_blocked_semantic_direct_count": authority_blocked,
        "recovered_direct_unique_summary": unique_summary,
    }
    return {
        "schema_version": 1,
        "architecture": ARCHITECTURE,
        "semantic_policy_version": SEMANTIC_POLICY_VERSION,
        "private": True,
        "human_labels_performed": False,
        "multi_claim_enabled": False,
        "summary": summary,
        "records": records,
        "recovered_direct_unique_summary": unique_summary,
        "recovered_exact_direct_review_candidates": recovered_exact,
        "recovered_semantic_direct_review_candidates": recovered_semantic,
    }


def write_private_outputs(
    runs_root: Path, report: Mapping[str, Any]
) -> tuple[Path, Path]:
    out = runs_root.resolve() / "_audit"
    out.mkdir(parents=True, exist_ok=True)
    detail = out / "parser_object_semantics_3way.detailed.json"
    review = out / "parser_object_semantics_recovered_direct.review.json"
    detail.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    candidates = [
        *report.get("recovered_exact_direct_review_candidates", []),
        *report.get("recovered_semantic_direct_review_candidates", []),
    ]
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        safe = dict(row)
        safe["review_label"] = None
        safe["human_label"] = None
        safe["review_status"] = "candidate_only_not_human_labeled"
        key = (
            str(safe.get("run_identifier", "")),
            str(safe.get("evidence_id", "")),
            str(safe.get("construct_id", "")),
            str(safe.get("recovery_basis", "")),
        )
        dedup[key] = safe
    review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "private": True,
                "human_labels_performed": False,
                "review_label_policy": "review_label_must_remain_null_until_human_review",
                "candidate_count": len(dedup),
                "candidates": list(dedup.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    unique = out / "parser_object_semantics_recovered_direct.unique.json"
    unique_summary = report.get("recovered_direct_unique_summary", []) or []
    safe_unique = []
    for row in unique_summary:
        if not isinstance(row, Mapping):
            continue
        safe = dict(row)
        safe["review_label"] = None
        safe["human_label"] = None
        safe["review_status"] = "candidate_only_not_human_labeled"
        safe_unique.append(safe)
    unique.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "private": True,
                "human_labels_performed": False,
                "semantic_policy_version": report.get(
                    "semantic_policy_version", ""
                ),
                "review_label_policy": "review_label_must_remain_null_until_human_review",
                "unique_count": len(safe_unique),
                "row_count": sum(int(row.get("row_count", 0)) for row in safe_unique),
                "unique_summary": safe_unique,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return detail, review, unique


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, default=Path("career_runs"))
    args = parser.parse_args(argv)
    if not args.runs.is_dir():
        print(
            json.dumps(
                {"error": "career_runs_not_found", "runs": str(args.runs)},
                ensure_ascii=False,
            )
        )
        return 4
    report = run_audit(args.runs)
    detail, review, unique = write_private_outputs(args.runs, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(
        f"PRIVATE detail: {detail}\n"
        f"PRIVATE review candidates: {review}\n"
        f"PRIVATE unique summary: {unique}"
    )
    return 0 if report["summary"]["run_count"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
