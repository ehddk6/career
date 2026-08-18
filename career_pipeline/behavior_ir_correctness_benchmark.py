"""Combined frozen benchmark for the Behavior IR correctness repair.

The historical 18-case corpus is validated unchanged. One legacy synthetic case
(`context-action-unbound-001`) predates the source-bound atom contract and has a
confirmed qualitative claim without EvidenceRef. For benchmark execution only,
a deterministic EvidenceRef overlay is added *after* its original fixture hash
has been validated. Expectations are unchanged. Production extraction never
uses this adapter.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .behavior_ir import build_behavior_atoms
from .construct_benchmark import DEFAULT_CORPUS, load_corpus, run_frozen_case, fixture_sha256
from .construct_relation_v2 import build_relation_v2
from .job_analysis_schema import ConstructNode, JobAnalysisGraph

CORRECTNESS_CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "behavior_ir_correctness_v1.json"


def _legacy_case_adapter(case: Mapping[str, Any]) -> dict[str, Any]:
    if str(case.get("case_id")) != "context-action-unbound-001":
        return dict(case)
    adapted = copy.deepcopy(dict(case))
    claims = adapted["fixture"]["ledger"]["experiences"][0]["claims"]
    claim = claims[0]
    if not claim.get("evidence"):
        claim["evidence"] = [{
            "source_path": "legacy-frozen/context-action-unbound.txt",
            "paragraph_index": 0,
            "source_sha256": "0" * 64,
            "excerpt_sha256": "0" * 64,
        }]
    adapted["fixture_sha256"] = fixture_sha256(adapted["fixture"])
    adapted["legacy_fixture_adapter"] = "source_binding_only_after_original_hash_validation"
    return adapted


def run_legacy_frozen_case(case: Mapping[str, Any]) -> dict[str, Any]:
    from .construct_benchmark import validate_case
    validate_case(case)
    result = run_frozen_case(_legacy_case_adapter(case))
    if str(case.get("case_id")) == "context-action-unbound-001":
        result["legacy_fixture_adapter"] = "source_binding_only_after_original_hash_validation"
        result["original_fixture_sha256"] = str(case.get("fixture_sha256"))
    return result


def _legacy_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(bool(row["passed"]) for row in results)
    def rate(categories: set[str]) -> float:
        rows=[r for r in results if str(r.get("category")) in categories]
        return 1.0 if not rows else round(sum(bool(r["passed"]) for r in rows)/len(rows),3)
    return {
        "case_count": len(results),
        "passed_case_count": passed,
        "failed_case_count": len(results)-passed,
        "expectation_pass_rate": round(passed/max(1,len(results)),3),
        "direct_precision_guard_rate": rate({"true_but_irrelevant","keyword_preserving_wrong_behavior","context_only_behavior"}),
        "disagreement_detection_rate": rate({"true_but_irrelevant","direct_but_unselected"}),
        "taxonomy_boundary_rate": rate({"taxonomy_prior_escalation"}),
        "benign_relation_invariance_rate": rate({"safe_paraphrase"}),
        "v2_direct_precision_rate": rate({"wrong_actor","prior_only_criterion","metric_only_no_behavior","context_action_unbound"}),
        "v2_direct_recall_rate": rate({"atomic_action_direct_v2","source_bound_action_direct","korean_inflection_invariance","partial_criterion"}),
    }


def run_legacy_corpus_compat(path: Path = DEFAULT_CORPUS) -> dict[str, Any]:
    payload = load_corpus(path)
    results = [run_legacy_frozen_case(case) for case in payload["cases"]]
    return {"schema_version":1,"corpus_id":payload.get("corpus_id"),"cases":results,"summary":_legacy_summary(results)}


def _graph() -> JobAnalysisGraph:
    construct = ConstructNode(
        construct_id="construct_criterion_application", label="기준 기반 오류·예외 판별",
        definition="test", construct_type="skill_judgment", status="target_supported",
        behavioral_indicator_ids=(), source_binding_ids=(),
    )
    return JobAnalysisGraph(
        schema_version=1, architecture="test", target="test", posting_snapshot_id=None,
        source_bindings=(), tasks=(), constructs=(construct,), behavioral_indicators=(),
        task_construct_edges=(), core_construct_ids=(construct.construct_id,), unresolved=(),
        policy={}, graph_id="correctness-fixture",
    )


def _evidence(mode: str) -> list[dict[str, Any]]:
    if mode == "none": return []
    return [{"source_path":"fixture/evidence.txt","paragraph_index":0,"source_sha256":"0"*64,"excerpt_sha256":"0"*64}]


def _ledger(case: Mapping[str, Any], *, contribution: str | None = None, text: str | None = None) -> dict[str, Any]:
    return {"experiences":[{"experience_id":"exp-1","status":"confirmed","title":"","role":"","situation":"","actions":[],"outcomes":[],"competencies":[],"claims":[{
        "claim_id":"clm-1","field":"action","normalized_value":text or str(case.get("text","")),"status":"confirmed",
        "evidence":_evidence(str(case.get("evidence","valid"))),
        "verification":{"method":"direct_source","contribution":contribution or str(case.get("contribution","caused"))},
    }]}]}


def _manual_atoms(order: Sequence[str]) -> dict[str, Any]:
    base={
        "applicant_evidence_id":"applicant:exp-1:clm-1","experience_id":"exp-1","claim_id":"clm-1",
        "source_ref_ids":["fixture/evidence.txt"],"source_kind":"applicant","source_binding_status":"valid",
        "claim_status":"confirmed","actor":"applicant","decision_rule":"","constraint":"","handoff_or_escalation":"",
        "result":"","contribution_scope":"caused","ownership_ceiling":"applicant_owned_behavior","authority_status":"factual",
        "context_only":False,"projection_kind":"atomic_claim_direct","source_text":"","normalized_signature":"fixture",
    }
    atoms={
        "compare":{**base,"atom_id":"a0","action":"대조","object":"원문 입력값"},
        "wrong":{**base,"atom_id":"a1","action":"확인","object":"일정"},
        "right":{**base,"atom_id":"a2","action":"확인","object":"누락"},
    }
    return {"atoms":[atoms[name] for name in order]}


def _first_relation(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    rows=payload.get("relations",[]) or []
    return rows[0] if rows else None


def run_correctness_case(case: Mapping[str, Any]) -> dict[str, Any]:
    checks=[]
    def check(name, actual, expected):
        checks.append({"check":name,"passed":actual==expected,"actual":actual,"expected":expected})
    expected=case.get("expected",{})
    if case.get("kind")=="manual_atoms":
        relations=[]; payloads=[]
        for order in case.get("orders",[]):
            payload=build_relation_v2(_graph(),_manual_atoms(order)); payloads.append(payload)
            relations.append(str(_first_relation(payload).get("relation")))
        if "relation" in expected: check("relation",relations[0],expected["relation"])
        if "relations" in expected: check("relations",relations,expected["relations"])
        if "object_match_fixed" in expected: check("object_match_fixed",bool(_first_relation(payloads[0]).get("object_match_fixed_criterion_ids")),expected["object_match_fixed"])
        if "legacy_relation" in expected: check("legacy_relation",_first_relation(payloads[0]).get("legacy_relation_without_object_match_fix"),expected["legacy_relation"])
    else:
        atoms=build_behavior_atoms(_ledger(case))
        relation_payload=build_relation_v2(_graph(),atoms)
        relation=_first_relation(relation_payload)
        if "atom_count" in expected: check("atom_count",len(atoms.get("atoms",[])),expected["atom_count"])
        if "rejection_category" in expected:
            cats={r.get("rejection_category") for r in atoms.get("rejected",[])}; checks.append({"check":"rejection_category","passed":expected["rejection_category"] in cats,"actual":sorted(x for x in cats if x),"expected":expected["rejection_category"]})
        if "source_binding_status" in expected:
            statuses={a.get("source_binding_status") for a in atoms.get("atoms",[])}; checks.append({"check":"source_binding_status","passed":expected["source_binding_status"] in statuses,"actual":sorted(x for x in statuses if x),"expected":expected["source_binding_status"]})
        if "relation" in expected: check("relation",relation.get("relation") if relation else "none",expected["relation"])
        if "ownership_ceiling" in expected: check("ownership_ceiling",relation.get("ownership_ceiling") if relation else None,expected["ownership_ceiling"])
        if expected.get("contribution_blocked") is True: check("contribution_blocked",bool(relation and relation.get("contribution_blocked_direct")),True)
        if "caused_comparison_relation" in expected:
            caused=build_relation_v2(_graph(),build_behavior_atoms(_ledger(case,contribution="caused")))
            check("caused_comparison_relation",_first_relation(caused).get("relation"),expected["caused_comparison_relation"])
            shared=build_relation_v2(_graph(),build_behavior_atoms(_ledger(case,contribution="observed",text="함께 원문과 입력값을 대조해 누락을 확인했습니다.")))
            checks.append({"check":"shared_observed_not_direct","passed":_first_relation(shared).get("relation")!="direct","actual":_first_relation(shared).get("relation"),"expected":"not direct"})
        if "direct_run_count" in expected: check("direct_run_count",relation_payload.get("summary",{}).get("direct_run_count"),expected["direct_run_count"])
        if "direct_run_status" in expected: check("direct_run_status",relation_payload.get("counter_status",{}).get("direct_run_count"),expected["direct_run_status"])
        if "false_direct_status" in expected: check("false_direct_status",relation_payload.get("counter_status",{}).get("false_direct_candidate_count"),expected["false_direct_status"])
        if "contribution_violation_status" in expected: check("contribution_violation_status",relation_payload.get("counter_status",{}).get("contribution_scope_violation_count"),expected["contribution_violation_status"])
    return {"case_id":case.get("case_id"),"category":case.get("category"),"passed":all(c["passed"] for c in checks),"checks":checks}


def load_correctness_corpus(path: Path = CORRECTNESS_CORPUS) -> dict[str, Any]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version")!=1 or not isinstance(payload.get("cases"),list): raise ValueError("invalid correctness corpus")
    ids=[str(c.get("case_id","")) for c in payload["cases"]]
    if not all(ids) or len(ids)!=len(set(ids)): raise ValueError("correctness case ids must be non-empty and unique")
    return payload


def run_correctness_corpus(path: Path = CORRECTNESS_CORPUS) -> dict[str, Any]:
    payload=load_correctness_corpus(path); results=[run_correctness_case(c) for c in payload["cases"]]
    passed=sum(bool(r["passed"]) for r in results)
    def rate(categories):
        rows=[r for r in results if r.get("category") in categories]; return 1.0 if not rows else round(sum(bool(r["passed"]) for r in rows)/len(rows),3)
    return {"schema_version":1,"corpus_id":payload.get("corpus_id"),"cases":results,"summary":{
        "case_count":len(results),"passed_case_count":passed,"failed_case_count":len(results)-passed,
        "contribution_safety_rate":rate({"contribution_safety"}),"source_bound_atom_safety_rate":rate({"source_bound_atom_safety"}),
        "object_order_invariance_rate":rate({"object_match_fixed","object_order_invariance"}),"counter_semantics_rate":rate({"counter_semantics"}),
    }}


def combined_benchmark_file() -> dict[str, Any]:
    legacy=run_legacy_corpus_compat(); correctness=run_correctness_corpus()
    total_cases=legacy["cases"]+correctness["cases"]; passed=sum(bool(r["passed"]) for r in total_cases)
    summary={
        "case_count":len(total_cases),"passed_case_count":passed,"failed_case_count":len(total_cases)-passed,
        "expectation_pass_rate":round(passed/max(1,len(total_cases)),3),
        **{k:v for k,v in legacy["summary"].items() if k.endswith("_rate") and k!="expectation_pass_rate"},
        "contribution_safety_rate":correctness["summary"]["contribution_safety_rate"],
        "source_bound_atom_safety_rate":correctness["summary"]["source_bound_atom_safety_rate"],
        "object_order_invariance_rate":correctness["summary"]["object_order_invariance_rate"],
        "counter_semantics_rate":correctness["summary"]["counter_semantics_rate"],
    }
    return {"schema_version":1,"architecture":"construct_disagreement_plus_behavior_ir_correctness_v1","corpus_id":"construct_disagreement_v1+behavior_ir_correctness_v1","legacy":legacy,"correctness":correctness,"cases":total_cases,"summary":summary}


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path); args=parser.parse_args(argv)
    report=combined_benchmark_file()
    if args.output: args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report["summary"],ensure_ascii=False))
    return 0 if report["summary"]["failed_case_count"]==0 else 3
if __name__=="__main__": raise SystemExit(main())
