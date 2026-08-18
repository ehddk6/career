"""Frozen verb-aware documentation semantics benchmark (shadow only).

Runs the six verb+artifact frozen regressions through the same semantic
relation path the PRIVATE 3-way audit uses (``_shadow_relation``), so a
regression failure means the shadow matcher policy drifted.

Existing legacy 18 + correctness 8 frozen expectations are untouched;
``combined_frozen_all`` merely runs the three corpora side by side.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .construct_criteria import criteria_for_graph
from .job_analysis_schema import ConstructNode, JobAnalysisGraph

ARCHITECTURE = "object_semantics_verb_aware_frozen_v1"
CORPUS = (
    Path(__file__).resolve().parents[1]
    / "tests" / "fixtures" / "object_semantics_verb_aware_v1.json"
)


def _graph() -> JobAnalysisGraph:
    construct = ConstructNode(
        construct_id="construct_documentation",
        label="문서화·기록",
        definition="test",
        construct_type="skill_documentation",
        status="target_supported",
        behavioral_indicator_ids=(),
        source_binding_ids=(),
    )
    return JobAnalysisGraph(
        schema_version=1,
        architecture="test",
        target="test",
        posting_snapshot_id=None,
        source_bindings=(),
        tasks=(),
        constructs=(construct,),
        behavioral_indicators=(),
        task_construct_edges=(),
        core_construct_ids=(construct.construct_id,),
        unresolved=(),
        policy={},
        graph_id="verb-aware-fixture",
    )


def _atom(action: str, object_text: str) -> dict[str, Any]:
    return {
        "atom_id": "a0",
        "action": action,
        "object": object_text,
        "actor": "applicant",
        "source_kind": "applicant",
        "source_binding_status": "valid",
        "source_ref_ids": ["fixture/evidence.txt"],
        "claim_status": "confirmed",
        "contribution_scope": "caused",
        "ownership_ceiling": "applicant_owned_behavior",
        "authority_status": "factual",
        "context_only": False,
    }


def run_verb_aware_case(case: Mapping[str, Any]) -> dict[str, Any]:
    from .object_semantics_reaudit import _shadow_relation

    graph = _graph()
    construct = graph.constructs[0]
    criteria = criteria_for_graph(graph)
    atoms = [_atom(str(case["action"]), str(case["object"]))]
    row = _shadow_relation(construct, criteria, atoms, "", semantic=True)
    relation = str(row.get("relation", "none"))
    expected = str(case.get("expected", {}).get("relation", "not_direct"))
    want_direct = expected == "direct"
    checks = [
        {
            "check": "relation",
            "passed": (relation == "direct") if want_direct else (relation != "direct"),
            "actual": relation,
            "expected": expected,
        }
    ]
    expected_basis = case.get("expected", {}).get("basis")
    if expected_basis:
        bases = [
            str(ev.get("object_match_basis", ""))
            for ev in row.get("criterion_evidence", {}).values()
        ]
        checks.append(
            {
                "check": "semantic_basis",
                "passed": expected_basis in bases,
                "actual": bases,
                "expected": expected_basis,
            }
        )
    return {
        "case_id": str(case.get("case_id", "")),
        "category": str(case.get("category", "")),
        "passed": all(bool(c["passed"]) for c in checks),
        "checks": checks,
        "observed": {
            "relation": relation,
            "criterion_evidence": row.get("criterion_evidence", {}),
        },
    }


def load_verb_aware_corpus(path: Path = CORPUS) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("invalid verb-aware corpus")
    ids = [str(c.get("case_id", "")) for c in payload["cases"]]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("verb-aware case ids must be non-empty and unique")
    return payload


def run_verb_aware_corpus(path: Path = CORPUS) -> dict[str, Any]:
    payload = load_verb_aware_corpus(path)
    results = [run_verb_aware_case(case) for case in payload["cases"]]
    passed = sum(bool(r["passed"]) for r in results)
    blocked_cases = [r for r in results if "not_direct" in str(
        next((c["expected"] for c in r["checks"] if c["check"] == "relation"), "")
    )]
    return {
        "schema_version": 1,
        "architecture": ARCHITECTURE,
        "corpus_id": payload.get("corpus_id"),
        "cases": results,
        "summary": {
            "case_count": len(results),
            "passed_case_count": passed,
            "failed_case_count": len(results) - passed,
            "expectation_pass_rate": round(passed / max(1, len(results)), 3),
            "blocked_precision_rate": round(
                sum(bool(r["passed"]) for r in blocked_cases) / max(1, len(blocked_cases)),
                3,
            )
            if blocked_cases
            else 1.0,
        },
    }


def combined_frozen_all() -> dict[str, Any]:
    from .behavior_ir_correctness_benchmark import (
        run_correctness_corpus,
        run_legacy_corpus_compat,
    )

    legacy = run_legacy_corpus_compat()
    correctness = run_correctness_corpus()
    verb_aware = run_verb_aware_corpus()
    total_cases = legacy["cases"] + correctness["cases"] + verb_aware["cases"]
    passed = sum(bool(r["passed"]) for r in total_cases)
    summary = {
        "case_count": len(total_cases),
        "passed_case_count": passed,
        "failed_case_count": len(total_cases) - passed,
        "expectation_pass_rate": round(passed / max(1, len(total_cases)), 3),
    }
    return {
        "schema_version": 1,
        "architecture": (
            "construct_disagreement_plus_behavior_ir_correctness_plus_verb_aware_v1"
        ),
        "corpus_id": (
            "construct_disagreement_v1+behavior_ir_correctness_v1"
            "+object_semantics_verb_aware_v1"
        ),
        "legacy": legacy,
        "correctness": correctness,
        "verb_aware": verb_aware,
        "cases": total_cases,
        "summary": summary,
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = combined_frozen_all()
    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["failed_case_count"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
