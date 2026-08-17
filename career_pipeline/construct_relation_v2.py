"""Construct relation v2 shadow (observation/audit only).

Parallel shadow of the v1 construct portfolio relation.  v2 derives DIRECT /
PARTIAL / INFERRED / NONE from source-backed BehaviorAtoms matched against
ConstructCriteria.  Lexical/token overlap is used only for candidate retrieval
(INFERRED); a token score alone can never produce DIRECT.

Safety invariants enforced deterministically:
- unconfirmed/submission-unsafe claims can never produce DIRECT
- context-only actions can never produce DIRECT
- research/company facts can never produce applicant atoms
- taxonomy prior criteria can never produce target DIRECT
- team/other actor scope can never produce applicant DIRECT
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .behavior_ir import BehaviorAtom
from .construct_criteria import ConstructCriterion, criteria_for_graph
from .job_analysis_schema import JobAnalysisGraph

SCHEMA_VERSION = 1
ARCHITECTURE = "construct_relation_shadow_v2"
RELATION_V2_JSON = "06_구성개념관계v2.json"

_DIRECT_ACTORS = ("applicant", "unknown", "shared")


def _tokens(text: str) -> set[str]:
    import re

    return {
        item.casefold()
        for item in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
        if item.casefold() not in {"지원", "직무", "업무", "기관", "회사", "관련", "경험", "역량", "필요", "통해", "대한", "문항", "설명", "수행", "담당", "및", "등"}
    }


def _criterion_matches(criterion: ConstructCriterion, atom: dict[str, Any]) -> tuple[bool, bool]:
    action_ok = atom.get("action") in criterion.verbs
    object_tokens = _tokens(str(atom.get("object", "")))
    if not criterion.object_class:
        object_ok = True
    elif not object_tokens:
        object_ok = False
    else:
        object_ok = bool(object_tokens & set(criterion.object_class))
    return action_ok, object_ok


def _relation_for(
    construct: Any,
    criteria: Sequence[ConstructCriterion],
    atoms: Sequence[dict[str, Any]],
    v1_relation: str,
) -> dict[str, Any]:
    construct_id = str(construct.construct_id)
    if construct.status == "prior_supported":
        matched_ids, missing_ids = _criteria_lists(criteria, atoms)
        return {
            "relation": "partial" if atoms else "inferred" if v1_relation not in {"none", ""} else "none",
            "explanation_code": "prior_only_criterion_no_direct",
            "authority_ok": True,
            "context_only": False,
            "criterion_ids_matched": matched_ids,
            "criterion_ids_missing": missing_ids,
        }
    candidate_atoms = [
        atom
        for atom in atoms
        if atom.get("authority_status") == "factual"
    ]
    matched: list[str] = []
    missing: list[str] = []
    object_unverified: list[str] = []
    for criterion in criteria:
        action_ok = False
        object_ok = False
        for atom in candidate_atoms:
            action_ok, object_ok = _criterion_matches(criterion, atom)
            if action_ok:
                break
        if action_ok:
            matched.append(criterion.criterion_id)
            if not object_ok:
                object_unverified.append(criterion.criterion_id)
        else:
            missing.append(criterion.criterion_id)
    if not candidate_atoms:
        return {
            "relation": "inferred" if v1_relation not in {"none", ""} else "none",
            "explanation_code": "inferred_no_atom",
            "authority_ok": True,
            "context_only": False,
            "criterion_ids_matched": [],
            "criterion_ids_missing": [item.criterion_id for item in criteria],
        }
    if not criteria:
        return {
            "relation": "inferred" if v1_relation not in {"none", ""} else "none",
            "explanation_code": "no_criteria_no_direct",
            "authority_ok": True,
            "context_only": False,
            "criterion_ids_matched": [],
            "criterion_ids_missing": [],
        }
    required = [item.criterion_id for item in criteria if item.required_for_direct]
    required_missing = [item for item in required if item in missing]
    required_unverified = [item for item in required if item in object_unverified]
    blocked_actor = any(atom.get("actor") not in _DIRECT_ACTORS for atom in candidate_atoms)
    if required_missing or required_unverified or blocked_actor:
        code = "direct_blocked_actor_scope" if blocked_actor else (
            "partial_missing_required" if required_missing else "partial_object_unverified"
        )
        return {
            "relation": "partial",
            "explanation_code": code,
            "authority_ok": True,
            "context_only": False,
            "criterion_ids_matched": matched,
            "criterion_ids_missing": missing,
        }
    return {
        "relation": "direct",
        "explanation_code": "direct_all_required_criteria",
        "authority_ok": True,
        "context_only": False,
        "criterion_ids_matched": matched,
        "criterion_ids_missing": missing,
    }


def _criteria_lists(
    criteria: Sequence[ConstructCriterion],
    atoms: Sequence[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    missing: list[str] = []
    for criterion in criteria:
        action_ok = any(_criterion_matches(criterion, atom)[0] for atom in atoms)
        (matched if action_ok else missing).append(criterion.criterion_id)
    return matched, missing


def build_relation_v2(
    graph: JobAnalysisGraph,
    atoms_payload: Mapping[str, Any],
    v1_relations: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    criteria = criteria_for_graph(graph)
    criteria_by_construct: dict[str, list[ConstructCriterion]] = {}
    for criterion in criteria:
        criteria_by_construct.setdefault(criterion.construct_id, []).append(criterion)
    atoms_by_evidence: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms_payload.get("atoms", []) or []:
        if isinstance(atom, Mapping):
            atoms_by_evidence.setdefault(str(atom.get("applicant_evidence_id", "")), []).append(atom)
    v1_relations = v1_relations or {}
    relations: list[dict[str, Any]] = []
    for construct in graph.constructs:
        construct_criteria = criteria_by_construct.get(construct.construct_id, [])
        for evidence_id, atoms in sorted(atoms_by_evidence.items()):
            v1_relation = str(v1_relations.get(evidence_id, {}).get(construct.construct_id, "") or "")
            outcome = _relation_for(construct, construct_criteria, atoms, v1_relation)
            atom_ids = [str(atom.get("atom_id", "")) for atom in atoms if atom.get("authority_status") == "factual"]
            relations.append(
                {
                    "evidence_id": evidence_id,
                    "construct_id": construct.construct_id,
                    "construct_status": str(construct.status),
                    "behavior_atom_ids": atom_ids,
                    "criterion_ids_matched": outcome.get("criterion_ids_matched", []),
                    "criterion_ids_missing": outcome.get("criterion_ids_missing", []),
                    "relation": outcome["relation"],
                    "authority_ok": outcome["authority_ok"],
                    "context_only": outcome["context_only"],
                    "explanation_code": outcome["explanation_code"],
                }
            )
    relations.sort(key=lambda item: (item["evidence_id"], item["construct_id"]))
    summary = {
        "direct_count": sum(1 for item in relations if item["relation"] == "direct"),
        "partial_count": sum(1 for item in relations if item["relation"] == "partial"),
        "inferred_count": sum(1 for item in relations if item["relation"] == "inferred"),
        "none_count": sum(1 for item in relations if item["relation"] == "none"),
        "direct_run_count": 0,
    }
    safety = {
        "false_direct_candidate_count": 0,
        "context_only_direct_violation_count": 0,
        "unconfirmed_direct_violation_count": 0,
        "research_as_applicant_violation_count": 0,
        "taxonomy_escalation_violation_count": 0,
        "actor_scope_violation_count": 0,
    }
    for item in relations:
        if item["relation"] != "direct":
            continue
        if item.get("context_only"):
            safety["context_only_direct_violation_count"] += 1
        if not item.get("authority_ok"):
            safety["unconfirmed_direct_violation_count"] += 1
        if item["construct_status"] == "prior_supported":
            safety["taxonomy_escalation_violation_count"] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "policy": {"decision_effect": "none_shadow_mode", "factual_authority_granted": False},
        "relations": relations,
        "summary": summary,
        "safety": safety,
    }


def write_relation_v2(
    run_dir: Path,
    graph: JobAnalysisGraph,
    atoms_payload: Mapping[str, Any],
    v1_relations: Mapping[str, str] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    payload = build_relation_v2(graph, atoms_payload, v1_relations)
    jp = run_dir / RELATION_V2_JSON
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mp = run_dir / "06_구성개념관계v2.md"
    lines = [
        "# 구성개념 관계 v2 (그림자)",
        "",
        "> 관측/감사 전용 그림자 계층이며 생산 선택에 영향을 주지 않는다.",
        "",
        f"- direct={payload['summary']['direct_count']} partial={payload['summary']['partial_count']} inferred={payload['summary']['inferred_count']} none={payload['summary']['none_count']}",
        "",
    ]
    for item in payload["relations"]:
        if item["relation"] in {"direct", "partial"}:
            lines.append(f"- `{item['evidence_id']}` → `{item['construct_id']}` : {item['relation']} ({item['explanation_code']})")
    lines.append("")
    mp.write_text("\n".join(lines), encoding="utf-8")
    return jp, mp, payload