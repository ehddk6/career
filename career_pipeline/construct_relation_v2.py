"""Construct relation v2 shadow correctness repair (observation/audit only).

DIRECT requires source-backed factual BehaviorAtoms, full required criterion
matches, actor scope, and contribution scope. Lexical/token overlap is never a
DIRECT gate. Criterion matching is order-invariant and explicitly prefers:
FULL MATCH > ACTION-ONLY MATCH > NO MATCH.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .construct_criteria import ConstructCriterion, criteria_for_graph
from .job_analysis_schema import JobAnalysisGraph

SCHEMA_VERSION = 2
ARCHITECTURE = "construct_relation_shadow_v2_correctness_repair"
RELATION_V2_JSON = "06_구성개념관계v2.json"

_DIRECT_ACTORS = ("applicant", "unknown", "shared")
_DIRECT_CONTRIBUTIONS = ("caused", "contributed")


def _tokens(text: str) -> set[str]:
    import re
    return {
        item.casefold()
        for item in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
        if item.casefold() not in {
            "지원", "직무", "업무", "기관", "회사", "관련", "경험", "역량",
            "필요", "통해", "대한", "문항", "설명", "수행", "담당", "및", "등",
        }
    }


def _criterion_matches(criterion: ConstructCriterion, atom: Mapping[str, Any]) -> tuple[bool, bool]:
    action_ok = atom.get("action") in criterion.verbs
    object_tokens = _tokens(str(atom.get("object", "")))
    if not criterion.object_class:
        object_ok = True
    elif not object_tokens:
        object_ok = False
    else:
        object_ok = bool(object_tokens & set(criterion.object_class))
    return action_ok, object_ok


def _criterion_match_state(
    criterion: ConstructCriterion,
    atoms: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return repaired and legacy states without depending on atom ordering.

    Repaired state scans every candidate atom and returns the strongest match.
    Legacy state captures the pre-repair first-action-match behavior only for
    diagnostics and before/after audit accounting.
    """
    action_only_atom_id = ""
    legacy_state = "missing"
    legacy_atom_id = ""
    legacy_recorded = False
    for atom in atoms:
        action_ok, object_ok = _criterion_matches(criterion, atom)
        if action_ok and not legacy_recorded:
            legacy_recorded = True
            legacy_state = "full" if object_ok else "action_only"
            legacy_atom_id = str(atom.get("atom_id", ""))
        if action_ok and object_ok:
            return {
                "state": "full",
                "atom_id": str(atom.get("atom_id", "")),
                "legacy_state": legacy_state,
                "legacy_atom_id": legacy_atom_id,
                "object_match_fixed": legacy_state == "action_only",
            }
        if action_ok and not action_only_atom_id:
            action_only_atom_id = str(atom.get("atom_id", ""))
    if action_only_atom_id:
        return {
            "state": "action_only",
            "atom_id": action_only_atom_id,
            "legacy_state": legacy_state,
            "legacy_atom_id": legacy_atom_id,
            "object_match_fixed": False,
        }
    return {
        "state": "missing",
        "atom_id": "",
        "legacy_state": legacy_state,
        "legacy_atom_id": legacy_atom_id,
        "object_match_fixed": False,
    }


def _scope_summary(atoms: Sequence[Mapping[str, Any]]) -> tuple[str, str, bool, str | None]:
    scopes = sorted({str(atom.get("contribution_scope", "unknown") or "unknown") for atom in atoms})
    ceilings = sorted({str(atom.get("ownership_ceiling", "unknown_review_required") or "unknown_review_required") for atom in atoms})
    scope = scopes[0] if len(scopes) == 1 else "mixed"
    ceiling = ceilings[0] if len(ceilings) == 1 else "mixed_strictest_review_required"
    ok = bool(scopes) and all(item in _DIRECT_CONTRIBUTIONS for item in scopes)
    reason: str | None = None
    if not ok:
        if "observed" in scopes:
            reason = "observed_no_applicant_capability_direct"
        elif "unknown" in scopes:
            reason = "unknown_contribution_review_required"
        else:
            reason = "mixed_or_invalid_contribution_scope"
    return scope, ceiling, ok, reason


def _relation_from_states(
    *,
    construct_status: str,
    criteria: Sequence[ConstructCriterion],
    states: Mapping[str, str],
    candidate_atoms: Sequence[Mapping[str, Any]],
    v1_relation: str,
    apply_contribution: bool,
) -> tuple[str, str, dict[str, Any]]:
    if construct_status == "prior_supported":
        matched = [item.criterion_id for item in criteria if states.get(item.criterion_id) != "missing"]
        missing = [item.criterion_id for item in criteria if states.get(item.criterion_id) == "missing"]
        return (
            "partial" if candidate_atoms else "inferred" if v1_relation not in {"none", ""} else "none",
            "prior_only_criterion_no_direct",
            {"matched": matched, "missing": missing, "object_unverified": []},
        )
    if not candidate_atoms:
        return (
            "inferred" if v1_relation not in {"none", ""} else "none",
            "inferred_no_atom",
            {"matched": [], "missing": [item.criterion_id for item in criteria], "object_unverified": []},
        )
    if not criteria:
        return (
            "inferred" if v1_relation not in {"none", ""} else "none",
            "no_criteria_no_direct",
            {"matched": [], "missing": [], "object_unverified": []},
        )

    matched = [item.criterion_id for item in criteria if states.get(item.criterion_id) in {"full", "action_only"}]
    missing = [item.criterion_id for item in criteria if states.get(item.criterion_id) == "missing"]
    object_unverified = [item.criterion_id for item in criteria if states.get(item.criterion_id) == "action_only"]
    required = [item.criterion_id for item in criteria if item.required_for_direct]
    required_missing = [item for item in required if item in missing]
    required_unverified = [item for item in required if item in object_unverified]

    actor_ok = all(str(atom.get("actor", "unknown")) in _DIRECT_ACTORS for atom in candidate_atoms)
    source_kind_ok = all(str(atom.get("source_kind", "applicant")) == "applicant" for atom in candidate_atoms)
    confirmed_ok = all(str(atom.get("claim_status", "confirmed")) == "confirmed" for atom in candidate_atoms)
    context_ok = all(not bool(atom.get("context_only", False)) for atom in candidate_atoms)
    source_binding_ok = all(
        str(atom.get("source_binding_status", "valid")) == "valid"
        and bool(atom.get("source_ref_ids", []))
        for atom in candidate_atoms
    )
    _, _, contribution_ok, _ = _scope_summary(candidate_atoms)

    if required_missing or required_unverified:
        code = "partial_missing_required" if required_missing else "partial_object_unverified"
        return "partial", code, {
            "matched": matched, "missing": missing, "object_unverified": object_unverified,
            "required": required, "required_missing": required_missing,
            "required_object_unverified": required_unverified,
            "actor_ok": actor_ok, "source_kind_ok": source_kind_ok,
            "confirmed_ok": confirmed_ok, "context_ok": context_ok,
            "source_binding_ok": source_binding_ok, "contribution_ok": contribution_ok,
        }
    if not actor_ok:
        return "partial", "direct_blocked_actor_scope", {
            "matched": matched, "missing": missing, "object_unverified": object_unverified,
            "required": required, "required_missing": [], "required_object_unverified": [],
            "actor_ok": False, "source_kind_ok": source_kind_ok, "confirmed_ok": confirmed_ok,
            "context_ok": context_ok, "source_binding_ok": source_binding_ok,
            "contribution_ok": contribution_ok,
        }
    if not (source_kind_ok and confirmed_ok and context_ok and source_binding_ok):
        return "inferred", "direct_blocked_authority_or_source", {
            "matched": matched, "missing": missing, "object_unverified": object_unverified,
            "required": required, "required_missing": [], "required_object_unverified": [],
            "actor_ok": actor_ok, "source_kind_ok": source_kind_ok, "confirmed_ok": confirmed_ok,
            "context_ok": context_ok, "source_binding_ok": source_binding_ok,
            "contribution_ok": contribution_ok,
        }
    if apply_contribution and not contribution_ok:
        return "inferred", "direct_blocked_contribution_scope", {
            "matched": matched, "missing": missing, "object_unverified": object_unverified,
            "required": required, "required_missing": [], "required_object_unverified": [],
            "actor_ok": actor_ok, "source_kind_ok": source_kind_ok, "confirmed_ok": confirmed_ok,
            "context_ok": context_ok, "source_binding_ok": source_binding_ok,
            "contribution_ok": False,
        }
    return "direct", "direct_all_required_criteria", {
        "matched": matched, "missing": missing, "object_unverified": object_unverified,
        "required": required, "required_missing": [], "required_object_unverified": [],
        "actor_ok": actor_ok, "source_kind_ok": source_kind_ok, "confirmed_ok": confirmed_ok,
        "context_ok": context_ok, "source_binding_ok": source_binding_ok,
        "contribution_ok": contribution_ok,
    }


def _relation_for(
    construct: Any,
    criteria: Sequence[ConstructCriterion],
    atoms: Sequence[dict[str, Any]],
    v1_relation: str,
) -> dict[str, Any]:
    candidate_atoms = [atom for atom in atoms if atom.get("authority_status") == "factual"]
    matches = {criterion.criterion_id: _criterion_match_state(criterion, candidate_atoms) for criterion in criteria}
    repaired_states = {key: value["state"] for key, value in matches.items()}
    legacy_states = {key: value["legacy_state"] for key, value in matches.items()}

    relation, code, details = _relation_from_states(
        construct_status=str(construct.status), criteria=criteria, states=repaired_states,
        candidate_atoms=candidate_atoms, v1_relation=v1_relation, apply_contribution=True,
    )
    legacy_relation, _, _ = _relation_from_states(
        construct_status=str(construct.status), criteria=criteria, states=legacy_states,
        candidate_atoms=candidate_atoms, v1_relation=v1_relation, apply_contribution=True,
    )
    no_contribution_relation, _, _ = _relation_from_states(
        construct_status=str(construct.status), criteria=criteria, states=repaired_states,
        candidate_atoms=candidate_atoms, v1_relation=v1_relation, apply_contribution=False,
    )
    contribution_scope, ownership_ceiling, contribution_ok, contribution_reason = _scope_summary(candidate_atoms)
    fixed_ids = [criterion_id for criterion_id, state in matches.items() if state["object_match_fixed"]]
    return {
        "relation": relation,
        "explanation_code": code,
        "authority_ok": bool(details.get("source_kind_ok", True) and details.get("confirmed_ok", True) and details.get("source_binding_ok", True)),
        "context_only": not bool(details.get("context_ok", True)),
        "actor_ok_for_direct": bool(details.get("actor_ok", True)),
        "criterion_ids_matched": details.get("matched", []),
        "criterion_ids_missing": details.get("missing", []),
        "criterion_ids_object_unverified": details.get("object_unverified", []),
        "required_criterion_ids": details.get("required", [item.criterion_id for item in criteria if item.required_for_direct]),
        "required_criterion_ids_missing": details.get("required_missing", []),
        "required_criterion_ids_object_unverified": details.get("required_object_unverified", []),
        "criterion_match_states": {key: value["state"] for key, value in matches.items()},
        "object_match_fixed_criterion_ids": fixed_ids,
        "legacy_relation_without_object_match_fix": legacy_relation,
        "object_match_fix_changed_relation": legacy_relation != relation,
        "contribution_scope": contribution_scope,
        "ownership_ceiling": ownership_ceiling,
        "contribution_ok_for_direct": contribution_ok,
        "contribution_block_reason": contribution_reason if not contribution_ok else None,
        "relation_without_contribution_gate": no_contribution_relation,
        "contribution_blocked_direct": no_contribution_relation == "direct" and relation != "direct",
    }


def _criteria_lists(criteria: Sequence[ConstructCriterion], atoms: Sequence[dict[str, Any]]) -> tuple[list[str], list[str]]:
    matched, missing = [], []
    for criterion in criteria:
        state = _criterion_match_state(criterion, atoms)["state"]
        (matched if state != "missing" else missing).append(criterion.criterion_id)
    return matched, missing


def build_relation_v2(
    graph: JobAnalysisGraph,
    atoms_payload: Mapping[str, Any],
    v1_relations: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    criteria = criteria_for_graph(graph)
    criteria_by_construct: dict[str, list[ConstructCriterion]] = {}
    for criterion in criteria:
        criteria_by_construct.setdefault(criterion.construct_id, []).append(criterion)
    atoms_by_evidence: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms_payload.get("atoms", []) or []:
        if isinstance(atom, Mapping):
            atoms_by_evidence.setdefault(str(atom.get("applicant_evidence_id", "")), []).append(dict(atom))
    v1_relations = v1_relations or {}
    relations: list[dict[str, Any]] = []
    for construct in graph.constructs:
        construct_criteria = criteria_by_construct.get(construct.construct_id, [])
        for evidence_id, atoms in sorted(atoms_by_evidence.items()):
            v1_relation = str(v1_relations.get(evidence_id, {}).get(construct.construct_id, "") or "")
            outcome = _relation_for(construct, construct_criteria, atoms, v1_relation)
            atom_ids = [str(atom.get("atom_id", "")) for atom in atoms if atom.get("authority_status") == "factual"]
            relations.append({
                "evidence_id": evidence_id,
                "construct_id": construct.construct_id,
                "construct_status": str(construct.status),
                "behavior_atom_ids": atom_ids,
                **outcome,
            })
    relations.sort(key=lambda item: (item["evidence_id"], item["construct_id"]))
    direct_rows = [item for item in relations if item["relation"] == "direct"]
    summary = {
        "direct_count": len(direct_rows),
        "partial_count": sum(item["relation"] == "partial" for item in relations),
        "inferred_count": sum(item["relation"] == "inferred" for item in relations),
        "none_count": sum(item["relation"] == "none" for item in relations),
        "direct_run_count": 1 if direct_rows else 0,
        "object_match_fixed_relation_count": sum(bool(item.get("object_match_fix_changed_relation")) for item in relations),
        "object_match_fixed_criterion_count": sum(len(item.get("object_match_fixed_criterion_ids", [])) for item in relations),
        "contribution_blocked_direct_count": sum(bool(item.get("contribution_blocked_direct")) for item in relations),
    }

    false_direct = [
        item for item in direct_rows
        if item.get("required_criterion_ids_missing")
        or item.get("required_criterion_ids_object_unverified")
        or not item.get("actor_ok_for_direct", False)
        or not item.get("contribution_ok_for_direct", False)
        or not item.get("authority_ok", False)
        or item.get("context_only", False)
        or item.get("construct_status") == "prior_supported"
        or not str(item.get("evidence_id", "")).startswith("applicant:")
    ]
    safety = {
        "false_direct_candidate_count": len(false_direct),
        "context_only_direct_violation_count": sum(bool(item.get("context_only")) for item in direct_rows),
        "unconfirmed_direct_violation_count": sum(not bool(item.get("authority_ok")) for item in direct_rows),
        "research_as_applicant_violation_count": sum(not str(item.get("evidence_id", "")).startswith("applicant:") for item in direct_rows),
        "taxonomy_escalation_violation_count": sum(item.get("construct_status") == "prior_supported" for item in direct_rows),
        "actor_scope_violation_count": sum(not bool(item.get("actor_ok_for_direct")) for item in direct_rows),
        "contribution_scope_violation_count": sum(not bool(item.get("contribution_ok_for_direct")) for item in direct_rows),
    }
    counter_status = {
        "direct_run_count": "actually_computed",
        "false_direct_candidate_count": "actually_computed",
        "context_only_direct_violation_count": "impossible_by_construction",
        "unconfirmed_direct_violation_count": "impossible_by_construction",
        "research_as_applicant_violation_count": "impossible_by_construction",
        "taxonomy_escalation_violation_count": "impossible_by_construction",
        "actor_scope_violation_count": "impossible_by_construction",
        "contribution_scope_violation_count": "impossible_by_construction",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "policy": {
            "decision_effect": "none_shadow_mode",
            "factual_authority_granted": False,
            "criterion_match_priority": ["full", "action_only", "missing"],
            "contribution_direct_allow": list(_DIRECT_CONTRIBUTIONS),
            "contributed_solo_escalation": False,
        },
        "relations": relations,
        "summary": summary,
        "safety": safety,
        "counter_status": counter_status,
    }


def write_relation_v2(
    run_dir: Path,
    graph: JobAnalysisGraph,
    atoms_payload: Mapping[str, Any],
    v1_relations: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    payload = build_relation_v2(graph, atoms_payload, v1_relations)
    jp = run_dir / RELATION_V2_JSON
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mp = run_dir / "06_구성개념관계v2.md"
    lines = [
        "# 구성개념 관계 v2 (그림자)", "",
        "> 관측/감사 전용 그림자 계층이며 생산 선택에 영향을 주지 않는다.", "",
        f"- direct={payload['summary']['direct_count']} partial={payload['summary']['partial_count']} inferred={payload['summary']['inferred_count']} none={payload['summary']['none_count']}",
        f"- direct_run_count={payload['summary']['direct_run_count']} ({payload['counter_status']['direct_run_count']})",
        "",
    ]
    for item in payload["relations"]:
        if item["relation"] in {"direct", "partial", "inferred"}:
            lines.append(
                f"- `{item['evidence_id']}` → `{item['construct_id']}` : {item['relation']} "
                f"({item['explanation_code']}, contribution={item['contribution_scope']})"
            )
    lines += ["", "## Safety counter semantics", ""]
    for key, value in payload["safety"].items():
        lines.append(f"- `{key}` = {value} [{payload['counter_status'][key]}]")
    lines.append("")
    mp.write_text("\n".join(lines), encoding="utf-8")
    return jp, mp, payload
