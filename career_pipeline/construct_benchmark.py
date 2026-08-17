"""Frozen benchmark for lexical-portfolio vs construct-relevance disagreement.

This benchmark is deterministic and synthetic. It exercises the current
Evidence Portfolio together with the shadow JobAnalysis/Construct mapper.
It does not call an LLM and does not change production decisions.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from .behavior_ir import build_behavior_atoms
from .construct_portfolio import build_construct_portfolio
from .construct_relation_v2 import build_relation_v2
from .evidence_portfolio import build_evidence_portfolio
from .job_analysis_compiler import build_job_analysis_graph

SCHEMA_VERSION = 1
ARCHITECTURE = "construct_disagreement_frozen_benchmark_v1"
DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "construct_disagreement_v1.json"
)
REPORT_FILE = "15_구성개념불일치벤치마크.json"


class FrozenCaseError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def fixture_sha256(fixture: Mapping[str, Any]) -> str:
    return sha256(_canonical(dict(fixture)).encode("utf-8")).hexdigest()


def validate_case(case: Mapping[str, Any]) -> None:
    case_id = str(case.get("case_id", ""))
    if not case_id:
        raise FrozenCaseError("frozen case is missing case_id")
    fixture = case.get("fixture")
    if not isinstance(fixture, Mapping):
        raise FrozenCaseError(f"{case_id}: fixture must be an object")
    expected_hash = str(case.get("fixture_sha256", ""))
    actual_hash = fixture_sha256(fixture)
    if expected_hash != actual_hash:
        raise FrozenCaseError(
            f"{case_id}: fixture hash mismatch "
            f"(expected {expected_hash or '<missing>'}, actual {actual_hash})"
        )
    expected = case.get("expected")
    if not isinstance(expected, Mapping):
        raise FrozenCaseError(f"{case_id}: expected must be an object")


def load_corpus(path: Path = DEFAULT_CORPUS) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise FrozenCaseError("corpus root must be an object")
    if int(payload.get("schema_version", 0) or 0) != SCHEMA_VERSION:
        raise FrozenCaseError("unsupported frozen corpus schema_version")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise FrozenCaseError("corpus cases must be a list")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise FrozenCaseError("each frozen case must be an object")
        validate_case(case)
        case_id = str(case["case_id"])
        if case_id in ids:
            raise FrozenCaseError(f"duplicate case_id: {case_id}")
        ids.add(case_id)
    return dict(payload)


def _write_case_run(root: Path, fixture: Mapping[str, Any]) -> None:
    files = {
        "run.json": fixture.get("run_state", {}),
        "00_채용공고분석.json": fixture.get("posting", {}),
        "02_확정경험원장.json": fixture.get("ledger", {}),
        "04_공식근거.json": fixture.get("research", []),
    }
    for name, value in files.items():
        (root / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _relation_lookup(matrix: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in matrix.get("links", []) or []:
        if not isinstance(row, Mapping):
            continue
        key = f"{row.get('evidence_id')}|{row.get('construct_id')}"
        result[key] = row
    return result


def _selected_evidence(portfolio: Mapping[str, Any]) -> set[str]:
    selected: set[str] = set()
    for assignment in portfolio.get("assignments", []) or []:
        if not isinstance(assignment, Mapping):
            continue
        for row in assignment.get("preferred_evidence", []) or []:
            if isinstance(row, Mapping) and row.get("evidence_id"):
                selected.add(str(row["evidence_id"]))
    return selected


def _evaluate_expected(
    expected: Mapping[str, Any],
    *,
    graph: Any,
    portfolio: Mapping[str, Any],
    matrix: Mapping[str, Any],
    atoms_payload: Mapping[str, Any],
    v2_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any, wanted: Any) -> None:
        checks.append(
            {
                "check": name,
                "passed": bool(passed),
                "actual": actual,
                "expected": wanted,
            }
        )

    core = set(graph.core_construct_ids)
    required_core = {
        str(value)
        for value in expected.get("core_construct_ids_contains", []) or []
    }
    add(
        "core_construct_ids_contains",
        required_core.issubset(core),
        sorted(core),
        sorted(required_core),
    )

    excluded_prefixes = [
        str(value)
        for value in expected.get("core_construct_ids_excludes_prefix", []) or []
    ]
    bad_core = sorted(
        value
        for value in core
        if any(value.startswith(prefix) for prefix in excluded_prefixes)
    )
    add(
        "core_construct_ids_excludes_prefix",
        not bad_core,
        bad_core,
        excluded_prefixes,
    )

    relations = _relation_lookup(matrix)
    for row in expected.get("relation_expectations", []) or []:
        if not isinstance(row, Mapping):
            continue
        key = f"{row.get('evidence_id')}|{row.get('construct_id')}"
        actual_row = relations.get(key)
        relation = (
            str(actual_row.get("relation"))
            if isinstance(actual_row, Mapping)
            else "none"
        )
        allowed = [str(value) for value in row.get("allowed", []) or []]
        add(f"relation:{key}", relation in allowed, relation, allowed)
        if "atomic_match" in row:
            actual = bool(actual_row.get("atomic_match")) if actual_row else False
            add(
                f"atomic_match:{key}",
                actual is bool(row.get("atomic_match")),
                actual,
                bool(row.get("atomic_match")),
            )
        if "context_match" in row:
            actual = bool(actual_row.get("context_match")) if actual_row else False
            add(
                f"context_match:{key}",
                actual is bool(row.get("context_match")),
                actual,
                bool(row.get("context_match")),
            )

    disagreement_kinds = {
        str(row.get("kind"))
        for row in matrix.get("disagreements", []) or []
        if isinstance(row, Mapping)
    }
    required_disagreements = {
        str(value)
        for value in expected.get("disagreement_kinds_contains", []) or []
    }
    add(
        "disagreement_kinds_contains",
        required_disagreements.issubset(disagreement_kinds),
        sorted(disagreement_kinds),
        sorted(required_disagreements),
    )

    required_uncovered = {
        str(value)
        for value in expected.get(
            "uncovered_core_construct_ids_contains", []
        )
        or []
    }
    add(
        "uncovered_core_construct_ids_contains",
        required_uncovered.issubset(
            set(
                str(value)
                for value in matrix.get(
                    "uncovered_core_construct_ids", []
                )
                or []
            )
        ),
        sorted(
            str(value)
            for value in matrix.get(
                "uncovered_core_construct_ids", []
            )
            or []
        ),
        sorted(required_uncovered),
    )

    binding_by_id = {
        binding.source_id: binding for binding in graph.source_bindings
    }
    for row in expected.get("source_authority", []) or []:
        if not isinstance(row, Mapping):
            continue
        source_id = str(row.get("source_id", ""))
        binding = binding_by_id.get(source_id)
        actual = (
            {
                "authority_class": binding.authority_class,
                "company_factual_authority": binding.company_factual_authority,
            }
            if binding is not None
            else None
        )
        wanted = {
            "authority_class": row.get("authority_class"),
            "company_factual_authority": bool(
                row.get("company_factual_authority")
            ),
        }
        add(f"source_authority:{source_id}", actual == wanted, actual, wanted)

    prefixes = [
        str(value)
        for value in expected.get("no_evidence_prefixes", []) or []
    ]
    bad_evidence = sorted(
        str(row.get("evidence_id"))
        for row in matrix.get("links", []) or []
        if isinstance(row, Mapping)
        and any(
            str(row.get("evidence_id", "")).startswith(prefix)
            for prefix in prefixes
        )
    )
    add(
        "no_evidence_prefixes",
        not bad_evidence,
        bad_evidence,
        prefixes,
    )

    selected = _selected_evidence(portfolio)
    required_selected = {
        str(value)
        for value in expected.get("portfolio_selected_contains", []) or []
    }
    add(
        "portfolio_selected_contains",
        required_selected.issubset(selected),
        sorted(selected),
        sorted(required_selected),
    )
    required_excluded = {
        str(value)
        for value in expected.get("portfolio_selected_excludes", []) or []
    }
    add(
        "portfolio_selected_excludes",
        not bool(required_excluded & selected),
        sorted(selected),
        sorted(required_excluded),
    )

    for index, group in enumerate(
        expected.get("same_relation_groups", []) or [], 1
    ):
        if not isinstance(group, Mapping):
            continue
        keys = [str(value) for value in group.get("keys", []) or []]
        actual_relations = [
            (
                str(relations[key].get("relation"))
                if key in relations
                else "none"
            )
            for key in keys
        ]
        allowed = [
            str(value) for value in group.get("allowed", []) or []
        ]
        passed = (
            bool(actual_relations)
            and len(set(actual_relations)) == 1
            and actual_relations[0] in allowed
        )
        add(
            f"same_relation_group:{index}",
            passed,
            actual_relations,
            {"same": True, "allowed": allowed},
        )

    policy = matrix.get("policy", {})
    if isinstance(policy, Mapping):
        add(
            "matrix_grants_no_authority",
            policy.get("factual_authority_granted") is False
            and policy.get("construct_authority_added") is False,
            {
                "factual_authority_granted": policy.get(
                    "factual_authority_granted"
                ),
                "construct_authority_added": policy.get(
                    "construct_authority_added"
                ),
            },
            {
                "factual_authority_granted": False,
                "construct_authority_added": False,
            },
        )

    _evaluate_v2_expected(
        expected,
        add=add,
        atoms_payload=atoms_payload,
        v2_payload=v2_payload,
    )

    return checks


def _evaluate_v2_expected(
    expected: Mapping[str, Any],
    *,
    add: Any,
    atoms_payload: Mapping[str, Any],
    v2_payload: Mapping[str, Any],
) -> None:
    atoms = atoms_payload.get("atoms", []) or []
    atoms_by_evidence: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        if isinstance(atom, Mapping):
            atoms_by_evidence.setdefault(
                str(atom.get("applicant_evidence_id", "")), []
            ).append(atom)
    rejected_codes = {
        str(row.get("code"))
        for row in atoms_payload.get("rejected", []) or []
        if isinstance(row, Mapping)
    }
    ir_expected = expected.get("behavior_ir_expectations", {})
    if isinstance(ir_expected, Mapping):
        if "atom_count" in ir_expected:
            wanted = int(ir_expected["atom_count"])
            add("v2:atom_count", len(atoms) == wanted, len(atoms), wanted)
        required_rejected = {
            str(value)
            for value in ir_expected.get("rejected_codes_contains", []) or []
        }
        add(
            "v2:rejected_codes_contains",
            required_rejected.issubset(rejected_codes),
            sorted(rejected_codes),
            sorted(required_rejected),
        )
        for evidence_id, actions in (
            ir_expected.get("atom_actions_contains", {}) or {}
        ).items():
            actual = sorted(
                {
                    str(atom.get("action"))
                    for atom in atoms_by_evidence.get(str(evidence_id), [])
                }
            )
            required = sorted(str(value) for value in actions or [])
            add(
                f"v2:atom_actions:{evidence_id}",
                set(required).issubset(set(actual)),
                actual,
                required,
            )
        for evidence_id, kinds in (
            ir_expected.get("projection_kinds_contains", {}) or {}
        ).items():
            actual = sorted(
                {
                    str(atom.get("projection_kind"))
                    for atom in atoms_by_evidence.get(str(evidence_id), [])
                }
            )
            required = sorted(str(value) for value in kinds or [])
            add(
                f"v2:projection_kinds:{evidence_id}",
                set(required).issubset(set(actual)),
                actual,
                required,
            )
        for evidence_id, actors in (
            ir_expected.get("actors_for", {}) or {}
        ).items():
            actual = sorted(
                {
                    str(atom.get("actor"))
                    for atom in atoms_by_evidence.get(str(evidence_id), [])
                }
            )
            required = sorted(str(value) for value in actors or [])
            add(
                f"v2:actors_for:{evidence_id}",
                set(required).issubset(set(actual)),
                actual,
                required,
            )

    v2_relations = {
        (str(row.get("evidence_id")), str(row.get("construct_id"))): str(
            row.get("relation")
        )
        for row in v2_payload.get("relations", []) or []
        if isinstance(row, Mapping)
    }
    for row in expected.get("relation_v2_expectations", []) or []:
        if not isinstance(row, Mapping):
            continue
        evidence_id = str(row.get("evidence_id", ""))
        prefix = str(row.get("construct_id_prefix", ""))
        if prefix:
            candidates = [
                relation
                for (eid, cid), relation in v2_relations.items()
                if eid == evidence_id and cid.startswith(prefix)
            ]
            label = f"{evidence_id}|{prefix}*"
        else:
            candidates = [
                v2_relations.get((evidence_id, str(row.get("construct_id", ""))), "none")
            ]
            label = f"{evidence_id}|{row.get('construct_id', '')}"
        actual = candidates[0] if candidates else "none"
        allowed = [str(value) for value in row.get("allowed", []) or []]
        add(f"v2:relation:{label}", actual in allowed, actual, allowed)

    if expected.get("v2_safety_zero", False):
        safety = v2_payload.get("safety", {})
        violations = {
            key: int(value)
            for key, value in safety.items()
            if int(value or 0) != 0
        }
        add("v2:safety_zero", not violations, violations, {})


def run_frozen_case(case: Mapping[str, Any]) -> dict[str, Any]:
    validate_case(case)
    fixture = case["fixture"]
    with TemporaryDirectory(prefix="career-construct-benchmark-") as tmp:
        run = Path(tmp)
        _write_case_run(run, fixture)
        max_per_question = int(
            fixture.get("max_per_question", 2) or 2
        )
        lexical = build_evidence_portfolio(
            run, max_per_question=max_per_question
        )
        posting = fixture.get("posting", {})
        research = fixture.get("research", [])
        taxonomy = fixture.get("taxonomy", [])
        state = fixture.get("run_state", {})
        target = (
            str(state.get("target", ""))
            if isinstance(state, Mapping)
            else ""
        )
        graph = build_job_analysis_graph(
            posting if isinstance(posting, Mapping) else {},
            tuple(
                row for row in research
                if isinstance(row, Mapping)
            )
            if isinstance(research, list)
            else (),
            target=target,
            taxonomy=tuple(
                row for row in taxonomy
                if isinstance(row, Mapping)
            )
            if isinstance(taxonomy, list)
            else (),
        )
        ledger = fixture.get("ledger", {})
        matrix = build_construct_portfolio(
            graph,
            ledger if isinstance(ledger, Mapping) else {},
            evidence_portfolio=lexical,
            run_state=state if isinstance(state, Mapping) else {},
        )
        atoms_payload = build_behavior_atoms(
            ledger if isinstance(ledger, Mapping) else {}
        )
        v1_relations = {
            str(row.get("evidence_id")): {
                str(row.get("construct_id")): str(row.get("relation"))
            }
            for row in matrix.get("links", []) or []
            if isinstance(row, Mapping)
        }
        v2_payload = build_relation_v2(graph, atoms_payload, v1_relations)
    checks = _evaluate_expected(
        case["expected"],
        graph=graph,
        portfolio=lexical,
        matrix=matrix,
        atoms_payload=atoms_payload,
        v2_payload=v2_payload,
    )
    return {
        "case_id": case["case_id"],
        "category": case.get("category"),
        "description": case.get("description"),
        "fixture_sha256": case["fixture_sha256"],
        "passed": all(row["passed"] for row in checks),
        "checks": checks,
        "observed": {
            "graph_id": graph.graph_id,
            "matrix_id": matrix.get("matrix_id"),
            "core_construct_ids": list(graph.core_construct_ids),
            "selected_evidence_ids": sorted(_selected_evidence(lexical)),
            "disagreement_kinds": sorted(
                {
                    str(row.get("kind"))
                    for row in matrix.get("disagreements", []) or []
                    if isinstance(row, Mapping)
                }
            ),
        },
    }


def run_corpus(payload: Mapping[str, Any]) -> dict[str, Any]:
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise FrozenCaseError("corpus cases must be a list")
    results = [run_frozen_case(case) for case in cases]
    passed = sum(bool(row["passed"]) for row in results)

    def category_rate(categories: set[str]) -> float:
        rows = [
            row
            for row in results
            if str(row.get("category")) in categories
        ]
        if not rows:
            return 1.0
        return round(
            sum(bool(row["passed"]) for row in rows) / len(rows), 3
        )

    summary = {
        "case_count": len(results),
        "passed_case_count": passed,
        "failed_case_count": len(results) - passed,
        "expectation_pass_rate": round(
            passed / max(1, len(results)), 3
        ),
        "direct_precision_guard_rate": category_rate(
            {
                "true_but_irrelevant",
                "keyword_preserving_wrong_behavior",
                "context_only_behavior",
            }
        ),
        "disagreement_detection_rate": category_rate(
            {"true_but_irrelevant", "direct_but_unselected"}
        ),
        "taxonomy_boundary_rate": category_rate(
            {"taxonomy_prior_escalation"}
        ),
        "benign_relation_invariance_rate": category_rate(
            {"safe_paraphrase"}
        ),
        "v2_direct_precision_rate": category_rate(
            {
                "wrong_actor",
                "prior_only_criterion",
                "metric_only_no_behavior",
                "context_action_unbound",
            }
        ),
        "v2_direct_recall_rate": category_rate(
            {
                "atomic_action_direct_v2",
                "source_bound_action_direct",
                "korean_inflection_invariance",
                "partial_criterion",
            }
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "corpus_id": payload.get("corpus_id"),
        "cases": results,
        "summary": summary,
    }


def benchmark_file(path: Path = DEFAULT_CORPUS) -> dict[str, Any]:
    return run_corpus(load_corpus(path))


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run frozen Evidence Portfolio × Construct disagreement benchmark"
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = benchmark_file(args.corpus)
    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["failed_case_count"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
