import json

from career_pipeline.object_semantics_reaudit import write_private_outputs


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
    _, review_path = write_private_outputs(tmp_path, report)
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
