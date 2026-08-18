"""PRIVATE real-run re-audit for the Behavior IR correctness repair.

Detailed rows and human-calibration candidates are written only below
``career_runs/_audit`` (gitignored). ``review_label`` is always null here.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from .behavior_ir import build_behavior_atoms
from .construct_portfolio import build_construct_portfolio
from .construct_relation_v2 import build_relation_v2
from .evidence_portfolio import build_evidence_portfolio
from .job_analysis_compiler import build_job_analysis_graph
from .real_run_disagreement_audit import audit_run

BASELINE = {
    "run_count": 37,
    "behavior_ir": {"atom_count": 947, "rejected_projection_count": 279,
        "atomizable_claim_count": 359, "confirmed_claim_count": 797,
        "atomizable_claim_rate": 0.45, "source_bound_action_atom_count": 843},
    "v2": {"direct_count": 0, "direct_run_count": 0, "partial_count": 1051,
        "inferred_count": 19},
    "A": 218, "B": 0, "zero_signal_selected_count": 151,
    "defensibility_only_selected_count": 151, "partial_object_unverified": 68,
}
_REQUIRED = ("run.json", "00_채용공고분석.json", "02_확정경험원장.json", "04_공식근거.json")


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _claims(ledger: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for exp in ledger.get("experiences", []) or []:
        if not isinstance(exp, Mapping): continue
        eid = str(exp.get("experience_id", ""))
        for claim in exp.get("claims", []) or []:
            if not isinstance(claim, Mapping): continue
            cid = str(claim.get("claim_id") or claim.get("field") or "")
            out[f"applicant:{eid}:{cid}"] = dict(claim)
    return out


def _previous_v2(run: Path) -> dict[tuple[str, str], str]:
    payload = _read(run / "06_구성개념관계v2.json", {})
    return {(str(r.get("evidence_id", "")), str(r.get("construct_id", ""))): str(r.get("relation", ""))
            for r in payload.get("relations", []) or [] if isinstance(r, Mapping)}


def _source_binding_removed_atoms(ledger: Mapping[str, Any], repaired: Mapping[str, Any]) -> int:
    rejected = {(str(r.get("experience_id", "")), str(r.get("claim_id", "")))
        for r in repaired.get("rejected", []) or [] if isinstance(r, Mapping)
        and r.get("rejection_category") in {"rejected_no_evidence", "rejected_invalid_source_binding"}}
    if not rejected: return 0
    overlay = copy.deepcopy(dict(ledger))
    for exp in overlay.get("experiences", []) or []:
        if not isinstance(exp, dict): continue
        eid = str(exp.get("experience_id", ""))
        for claim in exp.get("claims", []) or []:
            if not isinstance(claim, dict): continue
            cid = str(claim.get("claim_id") or claim.get("field") or "")
            if (eid, cid) in rejected:
                claim["evidence"] = [{"source_path": f"__audit_overlay__/{eid}/{cid}.txt",
                    "paragraph_index": 0, "source_sha256": "0" * 64, "excerpt_sha256": "0" * 64}]
    permissive = build_behavior_atoms(overlay)
    return max(0, int(permissive["summary"]["atom_count"]) - int(repaired["summary"]["atom_count"]))


def _candidate(strata: str, run: str, q: int, evidence_id: str, construct_id: str | None,
               claim: str, atoms: list[dict[str, Any]], relation: Mapping[str, Any] | None,
               v1: str | None, previous: str | None, binding: str, **extra: Any) -> dict[str, Any]:
    scopes = sorted({str(a.get("contribution_scope", "unknown")) for a in atoms})
    actors = sorted({str(a.get("actor", "unknown")) for a in atoms})
    row = {"strata": strata, "run_identifier": run, "question_index": q,
        "evidence_id": evidence_id, "construct_id": construct_id, "atomic_claim": claim,
        "source_evidence_binding_status": binding,
        "contribution_scope": scopes[0] if len(scopes) == 1 else "mixed" if scopes else "unknown",
        "actor": actors[0] if len(actors) == 1 else "mixed" if actors else "unknown",
        "behavior_atoms": atoms, "matched_criteria": list((relation or {}).get("criterion_ids_matched", [])),
        "missing_criteria": list((relation or {}).get("criterion_ids_missing", [])),
        "v1_relation": v1, "previous_v2_relation": previous,
        "repaired_v2_relation": (relation or {}).get("relation"),
        "explanation_code": (relation or {}).get("explanation_code"), "review_label": None}
    row.update(extra)
    return row


def audit_correctness_run(run_dir: Path) -> dict[str, Any] | None:
    run = run_dir.resolve()
    if not all((run / name).is_file() for name in _REQUIRED): return None
    state, posting = _read(run / "run.json", {}), _read(run / "00_채용공고분석.json", {})
    ledger, research = _read(run / "02_확정경험원장.json", {}), _read(run / "04_공식근거.json", [])
    if not isinstance(state, Mapping) or not isinstance(posting, Mapping) or not isinstance(ledger, Mapping): return None
    if not isinstance(research, list): research = []
    graph = build_job_analysis_graph(posting, tuple(r for r in research if isinstance(r, Mapping)),
        target=str(state.get("target") or posting.get("target") or "").strip())
    ep = build_evidence_portfolio(run)
    cp = build_construct_portfolio(graph, ledger, evidence_portfolio=ep, run_state=state)
    atoms = build_behavior_atoms(ledger)
    v1: dict[str, dict[str, str]] = defaultdict(dict)
    for link in cp.get("links", []) or []:
        if isinstance(link, Mapping): v1[str(link.get("evidence_id", ""))][str(link.get("construct_id", ""))] = str(link.get("relation", "none"))
    repaired = build_relation_v2(graph, atoms, v1)
    relations = [dict(r) for r in repaired.get("relations", []) or [] if isinstance(r, Mapping)]
    relation_by = {(r["evidence_id"], r["construct_id"]): r for r in relations}
    atoms_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in atoms.get("atoms", []) or []:
        if isinstance(atom, Mapping): atoms_by[str(atom.get("applicant_evidence_id", ""))].append(dict(atom))
    claims, previous = _claims(ledger), _previous_v2(run)
    legacy = audit_run(run) or {}
    selected_by_q: dict[int, list[dict[str, Any]]] = {}
    for assignment in ep.get("assignments", []) or []:
        if isinstance(assignment, Mapping): selected_by_q[int(assignment.get("question_index", 0) or 0)] = [dict(r) for r in assignment.get("preferred_evidence", []) or [] if isinstance(r, Mapping)]
    selected = {str(r.get("evidence_id", "")) for rows in selected_by_q.values() for r in rows}
    core = set(graph.core_construct_ids)
    repaired_b = {str(r["evidence_id"]) for r in relations if r.get("relation") == "direct" and r.get("construct_id") in core and str(r.get("evidence_id")) not in selected}
    explanations = Counter(str(r.get("explanation_code", "")) for r in relations)
    confirmed = sum(1 for exp in ledger.get("experiences", []) or [] if isinstance(exp, Mapping) and exp.get("status") == "confirmed" for c in exp.get("claims", []) or [] if isinstance(c, Mapping) and c.get("status") == "confirmed")
    atomized = {(str(a.get("experience_id", "")), str(a.get("claim_id", ""))) for a in atoms.get("atoms", []) or [] if isinstance(a, Mapping)}

    candidates: list[dict[str, Any]] = []
    for d in legacy.get("disagreements", []) or []:
        if not isinstance(d, Mapping) or d.get("kind") != "lexical_high_construct_weak": continue
        eid, q = str(d.get("evidence_id", "")), int(d.get("question_index", 0) or 0)
        selected_row = next((x for x in selected_by_q.get(q, []) if str(x.get("evidence_id", "")) == eid), {})
        strata = "A_positive_signal" if float(selected_row.get("signal_relevance_contribution", 0) or 0) > 0 else "A_zero_signal"
        rel = next((r for r in relations if r.get("evidence_id") == eid and r.get("construct_id") in core), None)
        cid = str(rel.get("construct_id")) if rel else None; claim = claims.get(eid, {})
        candidates.append(_candidate(strata, run.name, q, eid, cid, str(claim.get("normalized_value", "")), atoms_by[eid], rel,
            v1.get(eid, {}).get(cid or ""), previous.get((eid, cid or "")), "valid" if atoms_by[eid] else "no_atom"))
    for r in relations:
        eid, cid = str(r["evidence_id"]), str(r["construct_id"]); claim = claims.get(eid, {})
        q = next((q for q, rows in selected_by_q.items() if any(str(x.get("evidence_id", "")) == eid for x in rows)), 0)
        strata = None
        if r.get("contribution_blocked_direct"): strata = "contribution_blocked"
        elif r.get("object_match_fixed_criterion_ids"): strata = "object_match_fixed"
        elif r.get("explanation_code") == "direct_blocked_actor_scope": strata = "actor_blocked"
        elif r.get("relation") == "partial" and len(r.get("required_criterion_ids_missing", [])) + len(r.get("required_criterion_ids_object_unverified", [])) <= 1: strata = "nearest_direct"
        if strata:
            candidates.append(_candidate(strata, run.name, q, eid, cid, str(claim.get("normalized_value", "")), atoms_by[eid], r,
                v1.get(eid, {}).get(cid), previous.get((eid, cid)), "valid"))
    for reject in atoms.get("rejected", []) or []:
        if not isinstance(reject, Mapping): continue
        cat = reject.get("rejection_category")
        strata = "context_only" if cat == "rejected_context_only" else "source_binding_rejected" if cat in {"rejected_no_evidence", "rejected_invalid_source_binding"} else None
        if not strata: continue
        eid = f"applicant:{reject.get('experience_id','')}:{reject.get('claim_id','')}"; claim = claims.get(eid, {})
        candidates.append(_candidate(strata, run.name, 0, eid, None, str(claim.get("normalized_value") or reject.get("source_text", "")), [], None, None, None, str(cat), rejection_reasons=list(reject.get("reasons", []))))
    for cid in cp.get("uncovered_core_construct_ids", []) or []:
        for q, rows in selected_by_q.items():
            row = next((x for x in rows if str(x.get("source_kind")) == "applicant"), None)
            if not row: continue
            eid = str(row.get("evidence_id", "")); claim = claims.get(eid, {}); rel = relation_by.get((eid, str(cid)))
            candidates.append(_candidate("uncovered_core", run.name, q, eid, str(cid), str(claim.get("normalized_value", "")), atoms_by[eid], rel,
                v1.get(eid, {}).get(str(cid), "none"), previous.get((eid, str(cid))), "valid" if atoms_by[eid] else "no_atom")); break
    dedup = {(c["strata"], c["run_identifier"], c["question_index"], c["evidence_id"], c.get("construct_id")): c for c in candidates}
    return {"run_name": run.name,
        "behavior_ir": {**dict(atoms.get("summary", {})), "confirmed_claim_count": confirmed,
            "atomizable_claim_count": len(atomized), "atomizable_claim_rate": round(len(atomized) / max(1, confirmed), 3)},
        "source_binding_removed_atom_count": _source_binding_removed_atoms(ledger, atoms),
        "v2": dict(repaired.get("summary", {})), "v2_safety": dict(repaired.get("safety", {})),
        "counter_status": dict(repaired.get("counter_status", {})), "explanation": dict(explanations),
        "A": sum(isinstance(d, Mapping) and d.get("kind") == "lexical_high_construct_weak" for d in legacy.get("disagreements", []) or []),
        "B": len(repaired_b), "B_v1": sum(isinstance(d, Mapping) and d.get("kind") == "construct_direct_not_selected" for d in legacy.get("disagreements", []) or []),
        "zero_signal_selected_count": int(legacy.get("portfolio_score_decomposition", {}).get("zero_signal_selected_count", 0)),
        "defensibility_only_selected_count": int(legacy.get("portfolio_score_decomposition", {}).get("defensibility_only_selected_count", 0)),
        "review_candidates": list(dedup.values())}


def run_audit(runs_root: Path) -> dict[str, Any]:
    records = [r for d in sorted(runs_root.resolve().iterdir()) if d.is_dir() and d.name != "_audit" for r in [audit_correctness_run(d)] if r is not None]
    rejection, explanation, safety, strata = Counter(), Counter(), Counter(), Counter(); candidates = []
    for r in records:
        rejection.update(r["behavior_ir"].get("rejection_breakdown", {})); explanation.update(r["explanation"]); safety.update(r["v2_safety"])
        candidates += r["review_candidates"]; strata.update(c["strata"] for c in r["review_candidates"])
    after = {"run_count": len(records), "behavior_ir": {
        "atom_count": sum(r["behavior_ir"]["atom_count"] for r in records),
        "rejected_projection_count": sum(r["behavior_ir"]["rejected_projection_count"] for r in records),
        "source_bound_action_atom_count": sum(r["behavior_ir"].get("source_bound_action_count", 0) for r in records),
        "source_bound_atom_count": sum(r["behavior_ir"].get("source_bound_atom_count", 0) for r in records),
        "confirmed_claim_count": sum(r["behavior_ir"]["confirmed_claim_count"] for r in records),
        "atomizable_claim_count": sum(r["behavior_ir"]["atomizable_claim_count"] for r in records),
        "rejection_breakdown": dict(rejection),
        "source_binding_removed_atom_count": sum(r["source_binding_removed_atom_count"] for r in records)},
        "v2": {k: sum(int(r["v2"].get(k, 0)) for r in records) for k in ("direct_count","direct_run_count","partial_count","inferred_count","none_count","object_match_fixed_relation_count","object_match_fixed_criterion_count","contribution_blocked_direct_count")},
        "A": sum(r["A"] for r in records), "B": sum(r["B"] for r in records), "B_v1": sum(r["B_v1"] for r in records),
        "zero_signal_selected_count": sum(r["zero_signal_selected_count"] for r in records),
        "defensibility_only_selected_count": sum(r["defensibility_only_selected_count"] for r in records),
        "partial_object_unverified": int(explanation.get("partial_object_unverified", 0)), "explanation": dict(explanation),
        "safety": dict(safety), "counter_status": records[0]["counter_status"] if records else {},
        "review_candidate_count": len(candidates), "review_candidate_strata": dict(strata)}
    after["behavior_ir"]["atomizable_claim_rate"] = round(after["behavior_ir"]["atomizable_claim_count"] / max(1, after["behavior_ir"]["confirmed_claim_count"]), 3)
    return {"schema_version": 1, "architecture": "behavior_ir_correctness_repair_real_run_audit_v1",
        "baseline": BASELINE, "after": after, "records": records, "review_candidates": candidates}


def write_private_outputs(runs_root: Path, report: Mapping[str, Any]) -> tuple[Path, Path]:
    out = runs_root.resolve() / "_audit"; out.mkdir(parents=True, exist_ok=True)
    detail, candidates = out / "behavior_ir_correctness_repair.detailed.json", out / "behavior_ir_review_candidates.json"
    detail.write_text(json.dumps({k:v for k,v in report.items() if k != "review_candidates"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidates.write_text(json.dumps({"schema_version":1,"private":True,"human_labels_performed":False,
        "review_label_policy":"must_remain_null_until_human_review","candidate_count":len(report.get("review_candidates",[])),
        "strata":report.get("after",{}).get("review_candidate_strata",{}),"candidates":report.get("review_candidates",[])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return detail, candidates


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("--runs",type=Path,default=Path("career_runs")); args=p.parse_args(argv)
    report=run_audit(args.runs); detail,candidates=write_private_outputs(args.runs,report)
    print(json.dumps({k:v for k,v in report.items() if k not in {"records","review_candidates"}},ensure_ascii=False,indent=2))
    print(f"PRIVATE detail: {detail}\nPRIVATE candidates: {candidates}")
    return 0 if report["after"]["run_count"] else 4
if __name__ == "__main__": raise SystemExit(main())
