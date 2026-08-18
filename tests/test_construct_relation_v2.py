"""Construct relation v2 shadow rules (parallel to v1, observation only)."""
from __future__ import annotations

from career_pipeline.behavior_ir import build_behavior_atoms
from career_pipeline.construct_relation_v2 import build_relation_v2
from career_pipeline.job_analysis_compiler import build_job_analysis_graph


def _graph():
    posting = {
        "target": "테스트공사 행정",
        "duties": ["신청서류를 공식 기준과 대조해 오류와 누락을 확인한다"],
        "competencies": ["기준과 서류를 대조하여 오류와 누락을 정확히 구분할 수 있다"],
        "requirements": [], "preferred": [], "constraints": [],
    }
    taxonomy = [{"label": "기준과 원문을 대조해 누락을 확인하고 분류한다", "source_family": "ncs", "source_id": "src-ncs"}]
    return build_job_analysis_graph(posting, (), target="테스트공사 행정", taxonomy=taxonomy)


def _graph_with_generic_explicit():
    posting = {
        "target": "테스트공사 행정",
        "duties": ["신청서류를 공식 기준과 대조해 오류와 누락을 확인한다"],
        "competencies": ["기준과 서류를 대조하여 오류와 누락을 정확히 구분할 수 있다", "성실하고 책임감 있게 업무를 완수한다"],
        "requirements": [], "preferred": [], "constraints": [],
    }
    return build_job_analysis_graph(posting, (), target="테스트공사 행정")


def _ledger(claim_text: str, status: str = "confirmed", contribution: str = "caused") -> dict:
    return {"experiences": [{
        "experience_id": "exp-1", "status": "confirmed", "title": "행정지원", "role": "담당",
        "situation": "신청서류 처리", "actions": [], "outcomes": [], "competencies": [],
        "claims": [{
            "claim_id": "clm-1", "field": "action", "normalized_value": claim_text, "status": status,
            "evidence": [{"source_path": "exp1/evidence.txt", "paragraph_index": 0, "source_sha256": "0" * 64, "excerpt_sha256": "0" * 64}],
            "verification": {"method": "direct_source", "contribution": contribution},
        }],
    }]}


def _relation(v2: dict, evidence_id: str, construct_id: str) -> dict:
    return next(row for row in v2["relations"] if row["evidence_id"] == evidence_id and row["construct_id"] == construct_id)


def test_required_criteria_complete_gives_direct():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "direct"
    assert row["explanation_code"] == "direct_all_required_criteria"
    assert set(row["criterion_ids_matched"]) >= {"crit_criterion_application_compare_against_rule_or_source", "crit_criterion_application_detect_discrepancy"}
    assert row["contribution_scope"] == "caused"
    assert row["contribution_ok_for_direct"] is True


def test_missing_required_criterion_gives_partial():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문을 대조했습니다.")))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "partial"
    assert row["explanation_code"] == "partial_missing_required"


def test_no_atoms_gives_no_v2_relation_rows():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("성실하게 참여했습니다.")))
    assert v2["relations"] == []
    assert v2["summary"]["direct_count"] == 0
    assert v2["summary"]["direct_run_count"] == 0


def test_wrong_actor_blocks_direct():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("팀이 원문과 입력값을 대조해 누락을 확인했습니다.")))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "partial"
    assert row["explanation_code"] == "direct_blocked_actor_scope"


def test_prior_construct_can_never_be_direct():
    graph = _graph(); prior = next(c for c in graph.constructs if c.status == "prior_supported")
    v2 = build_relation_v2(graph, build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")))
    row = _relation(v2, "applicant:exp-1:clm-1", prior.construct_id)
    assert row["relation"] != "direct"
    assert row["explanation_code"] == "prior_only_criterion_no_direct"


def test_construct_without_criteria_can_never_be_direct():
    graph = _graph_with_generic_explicit(); explicit = next(c for c in graph.constructs if c.construct_id.startswith("construct_explicit_"))
    assert explicit.status == "target_explicit"
    v2 = build_relation_v2(graph, build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")))
    row = _relation(v2, "applicant:exp-1:clm-1", explicit.construct_id)
    assert row["relation"] != "direct"
    assert row["explanation_code"] == "no_criteria_no_direct"


def test_all_safety_counters_are_zero_with_explicit_status():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")))
    assert v2["safety"] == {
        "false_direct_candidate_count": 0,
        "context_only_direct_violation_count": 0,
        "unconfirmed_direct_violation_count": 0,
        "research_as_applicant_violation_count": 0,
        "taxonomy_escalation_violation_count": 0,
        "actor_scope_violation_count": 0,
        "contribution_scope_violation_count": 0,
    }
    assert v2["counter_status"]["direct_run_count"] == "actually_computed"
    assert v2["counter_status"]["false_direct_candidate_count"] == "actually_computed"
    assert v2["counter_status"]["contribution_scope_violation_count"] == "impossible_by_construction"


def _manual_atoms(order: list[str]) -> dict:
    base = {
        "applicant_evidence_id": "applicant:exp-1:clm-1", "experience_id": "exp-1", "claim_id": "clm-1",
        "source_ref_ids": ["exp1/evidence.txt"], "source_kind": "applicant", "source_binding_status": "valid",
        "claim_status": "confirmed", "actor": "applicant", "decision_rule": "", "constraint": "",
        "handoff_or_escalation": "", "result": "", "contribution_scope": "caused",
        "ownership_ceiling": "applicant_owned_behavior", "authority_status": "factual", "context_only": False,
        "projection_kind": "atomic_claim_direct", "source_text": "", "normalized_signature": "fixture",
    }
    atoms = {
        "compare": {**base, "atom_id": "a0", "action": "대조", "object": "원문 입력값"},
        "wrong": {**base, "atom_id": "a1", "action": "확인", "object": "일정"},
        "right": {**base, "atom_id": "a2", "action": "확인", "object": "누락"},
    }
    return {"atoms": [atoms[name] for name in order]}


def test_second_action_atom_full_match_beats_first_action_only_match():
    v2 = build_relation_v2(_graph(), _manual_atoms(["compare", "wrong", "right"]))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "direct"
    assert "crit_criterion_application_detect_discrepancy" in row["object_match_fixed_criterion_ids"]
    assert row["legacy_relation_without_object_match_fix"] == "partial"
    assert row["object_match_fix_changed_relation"] is True


def test_atom_order_does_not_change_relation():
    left = build_relation_v2(_graph(), _manual_atoms(["compare", "wrong", "right"]))
    right = build_relation_v2(_graph(), _manual_atoms(["compare", "right", "wrong"]))
    lrow = _relation(left, "applicant:exp-1:clm-1", "construct_criterion_application")
    rrow = _relation(right, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert lrow["relation"] == rrow["relation"] == "direct"
    assert lrow["criterion_match_states"] == rrow["criterion_match_states"]


def test_observed_contribution_blocks_direct_but_caused_allows_it():
    caused = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.", contribution="caused")))
    observed = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.", contribution="observed")))
    crow = _relation(caused, "applicant:exp-1:clm-1", "construct_criterion_application")
    orow = _relation(observed, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert crow["relation"] == "direct"
    assert orow["relation"] == "inferred"
    assert orow["explanation_code"] == "direct_blocked_contribution_scope"
    assert orow["contribution_blocked_direct"] is True


def test_unknown_contribution_blocks_direct():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.", contribution="unknown")))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "inferred"
    assert row["contribution_ok_for_direct"] is False
    assert row["contribution_block_reason"] == "unknown_contribution_review_required"


def test_contributed_never_escalates_to_solo_ownership():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.", contribution="contributed")))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "direct"
    assert row["contribution_scope"] == "contributed"
    assert row["ownership_ceiling"] == "contribution_only_no_solo"


def test_shared_actor_observed_contribution_is_not_direct():
    v2 = build_relation_v2(_graph(), build_behavior_atoms(_ledger("함께 원문과 입력값을 대조해 누락을 확인했습니다.", contribution="observed")))
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] != "direct"
    assert row["contribution_ok_for_direct"] is False
