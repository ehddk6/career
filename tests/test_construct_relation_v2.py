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
        "requirements": [],
        "preferred": [],
        "constraints": [],
    }
    taxonomy = [
        {
            "label": "기준과 원문을 대조해 누락을 확인하고 분류한다",
            "source_family": "ncs",
            "source_id": "src-ncs",
        }
    ]
    return build_job_analysis_graph(posting, (), target="테스트공사 행정", taxonomy=taxonomy)


def _graph_with_generic_explicit():
    posting = {
        "target": "테스트공사 행정",
        "duties": ["신청서류를 공식 기준과 대조해 오류와 누락을 확인한다"],
        "competencies": [
            "기준과 서류를 대조하여 오류와 누락을 정확히 구분할 수 있다",
            "성실하고 책임감 있게 업무를 완수한다",
        ],
        "requirements": [],
        "preferred": [],
        "constraints": [],
    }
    return build_job_analysis_graph(posting, (), target="테스트공사 행정")


def _ledger(claim_text: str, status: str = "confirmed") -> dict:
    return {
        "experiences": [
            {
                "experience_id": "exp-1",
                "status": "confirmed",
                "title": "행정지원",
                "role": "담당",
                "situation": "신청서류 처리",
                "actions": [],
                "outcomes": [],
                "competencies": [],
                "claims": [
                    {
                        "claim_id": "clm-1",
                        "field": "action",
                        "normalized_value": claim_text,
                        "status": status,
                        "evidence": [
                            {
                                "source_path": "exp1/evidence.txt",
                                "paragraph_index": 0,
                                "source_sha256": "0" * 64,
                                "excerpt_sha256": "0" * 64,
                            }
                        ],
                        "verification": {"method": "direct_source", "contribution": "caused"},
                    }
                ],
            }
        ]
    }


def _relation(v2: dict, evidence_id: str, construct_id: str) -> dict:
    return next(
        row
        for row in v2["relations"]
        if row["evidence_id"] == evidence_id and row["construct_id"] == construct_id
    )


def test_required_criteria_complete_gives_direct():
    v2 = build_relation_v2(
        _graph(),
        build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")),
    )
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "direct"
    assert row["explanation_code"] == "direct_all_required_criteria"
    assert set(row["criterion_ids_matched"]) == {
        "crit_criterion_application_compare_against_rule_or_source",
        "crit_criterion_application_detect_discrepancy",
    }


def test_missing_required_criterion_gives_partial():
    v2 = build_relation_v2(
        _graph(),
        build_behavior_atoms(_ledger("원문을 대조했습니다.")),
    )
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "partial"
    assert row["explanation_code"] == "partial_missing_required"


def test_no_atoms_gives_no_v2_relation_rows():
    v2 = build_relation_v2(
        _graph(),
        build_behavior_atoms(_ledger("성실하게 참여했습니다.")),
    )
    assert v2["relations"] == []
    assert v2["summary"]["direct_count"] == 0


def test_wrong_actor_blocks_direct():
    v2 = build_relation_v2(
        _graph(),
        build_behavior_atoms(_ledger("팀이 원문과 입력값을 대조해 누락을 확인했습니다.")),
    )
    row = _relation(v2, "applicant:exp-1:clm-1", "construct_criterion_application")
    assert row["relation"] == "partial"
    assert row["explanation_code"] == "direct_blocked_actor_scope"


def test_prior_construct_can_never_be_direct():
    graph = _graph()
    prior = next(c for c in graph.constructs if c.status == "prior_supported")
    v2 = build_relation_v2(
        graph,
        build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")),
    )
    row = _relation(v2, "applicant:exp-1:clm-1", prior.construct_id)
    assert row["relation"] != "direct"
    assert row["explanation_code"] == "prior_only_criterion_no_direct"


def test_construct_without_criteria_can_never_be_direct():
    graph = _graph_with_generic_explicit()
    explicit = next(c for c in graph.constructs if c.construct_id.startswith("construct_explicit_"))
    assert explicit.status == "target_explicit"
    v2 = build_relation_v2(
        graph,
        build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")),
    )
    row = _relation(v2, "applicant:exp-1:clm-1", explicit.construct_id)
    assert row["relation"] != "direct"
    assert row["explanation_code"] == "no_criteria_no_direct"


def test_all_safety_counters_are_zero_by_construction():
    v2 = build_relation_v2(
        _graph(),
        build_behavior_atoms(_ledger("원문과 입력값을 대조해 누락을 확인했습니다.")),
    )
    assert v2["safety"] == {
        "false_direct_candidate_count": 0,
        "context_only_direct_violation_count": 0,
        "unconfirmed_direct_violation_count": 0,
        "research_as_applicant_violation_count": 0,
        "taxonomy_escalation_violation_count": 0,
        "actor_scope_violation_count": 0,
    }
