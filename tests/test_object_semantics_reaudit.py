import json

from career_pipeline.object_semantics_reaudit import (
    _unique_recovery_summary,
    write_private_outputs,
)
from career_pipeline.object_semantics_shadow import SEMANTIC_POLICY_VERSION


def test_recovered_direct_output_cannot_become_human_label(tmp_path):
    report = {
        "recovered_exact_direct_review_candidates": [
            {
                "run_identifier": "run-1",
                "evidence_id": "applicant:exp-1:clm-1",
                "construct_id": "construct_documentation",
                "recovery_basis": "parser_v2_exact",
                # Even if a caller accidentally supplies labels, the PRIVATE writer
                # must clear them. Shadow recovery is a review candidate, not gold.
                "review_label": "direct",
                "human_label": "direct",
            }
        ],
        "recovered_semantic_direct_review_candidates": [],
    }
    _, review_path, _ = write_private_outputs(tmp_path, report)
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    assert payload["private"] is True
    assert payload["human_labels_performed"] is False
    assert payload["review_label_policy"] == "review_label_must_remain_null_until_human_review"
    assert payload["candidate_count"] == 1
    row = payload["candidates"][0]
    assert row["review_label"] is None
    assert row["human_label"] is None
    assert row["review_status"] == "candidate_only_not_human_labeled"


def test_parser_authority_does_not_require_legacy_atom(monkeypatch):
    import sys
    import types
    from types import SimpleNamespace
    from career_pipeline.object_semantics_reaudit import _verified_claim_authority

    behavior_ir = types.ModuleType("career_pipeline.behavior_ir")
    behavior_ir._OWNERSHIP_CEILING = {"caused": "applicant_owned_behavior"}
    behavior_ir._actor = lambda text: "applicant"
    behavior_ir._canonical_source_binding_issues = lambda eid, profile: ()
    behavior_ir._is_metric_claim = lambda claim: False
    profile = SimpleNamespace(
        evidence=(SimpleNamespace(source_path="exp1/evidence.txt"),),
        verification=SimpleNamespace(contribution="caused"),
    )
    behavior_ir._profile_claim = lambda claim: profile
    monkeypatch.setitem(sys.modules, "career_pipeline.behavior_ir", behavior_ir)

    profile_schema = types.ModuleType("career_pipeline.profile_schema")
    profile_schema.claim_submission_issues = lambda profile: ()
    monkeypatch.setitem(sys.modules, "career_pipeline.profile_schema", profile_schema)

    ledger = {"experiences": [{
        "experience_id": "exp-1",
        "claims": [{
            "claim_id": "clm-memo",
            "field": "action",
            "normalized_value": "전화 문의를 메모함",
            "status": "confirmed",
        }],
    }]}
    authority = _verified_claim_authority(ledger)
    row = authority["applicant:exp-1:clm-memo"]
    assert row["source_binding_status"] == "valid"
    assert row["claim_status"] == "confirmed"
    assert row["contribution_scope"] == "caused"


def _synthetic_rows():
    runs = [f"run-{i}" for i in range(1, 6)]
    return [
        {
            "run_identifier": run,
            "evidence_id": evidence,
            "construct_id": "construct_documentation",
            "recovery_basis": "bounded_semantic_only",
        }
        for evidence in ("eid-a", "eid-b", "eid-c")
        for run in runs
    ]


def test_unique_recovery_summary_groups_by_evidence_construct_basis():
    summary = _unique_recovery_summary(_synthetic_rows())
    assert len(summary) == 3
    assert {row["evidence_id"] for row in summary} == {"eid-a", "eid-b", "eid-c"}
    for row in summary:
        assert row["construct_id"] == "construct_documentation"
        assert row["recovery_basis"] == "bounded_semantic_only"
        assert row["row_count"] == 5
        assert row["unique_count"] == 1
        assert row["occurrence_count"] == 5
        assert row["run_identifiers"] == ["run-1", "run-2", "run-3", "run-4", "run-5"]
        assert row["review_label"] is None
        assert row["human_label"] is None


def test_write_private_outputs_writes_unique_summary_file(tmp_path):
    report = {
        "semantic_policy_version": SEMANTIC_POLICY_VERSION,
        "recovered_exact_direct_review_candidates": [],
        "recovered_semantic_direct_review_candidates": [],
        "recovered_direct_unique_summary": _unique_recovery_summary(
            _synthetic_rows()
        ),
    }
    _, _, unique_path = write_private_outputs(tmp_path, report)
    payload = json.loads(unique_path.read_text(encoding="utf-8"))
    assert payload["private"] is True
    assert payload["human_labels_performed"] is False
    assert payload["semantic_policy_version"] == SEMANTIC_POLICY_VERSION
    assert payload["unique_count"] == 3
    assert payload["row_count"] == 15
    for row in payload["unique_summary"]:
        assert row["review_label"] is None
        assert row["human_label"] is None
        assert row["review_status"] == "candidate_only_not_human_labeled"


def test_semantic_policy_version_present_in_shadow_payload():
    from career_pipeline.job_analysis_schema import JobAnalysisGraph
    from career_pipeline.object_semantics_reaudit import (
        build_parser_object_shadow_relations,
    )

    empty_graph = JobAnalysisGraph(
        schema_version=1,
        architecture="test",
        target="test",
        posting_snapshot_id=None,
        source_bindings=(),
        tasks=(),
        constructs=(),
        behavioral_indicators=(),
        task_construct_edges=(),
        core_construct_ids=(),
        unresolved=(),
        policy={},
        graph_id="empty-test",
    )
    payload = build_parser_object_shadow_relations(
        empty_graph, {}, {"atoms": []}, {}
    )
    assert payload["semantic_policy_version"] == SEMANTIC_POLICY_VERSION
    assert payload["schema_version"] == 1
    assert "precision_diagnostics" in payload
    assert "weak_alias_blocked_keys" in payload
