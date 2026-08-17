"""ConstructCriterion micro-decomposition rules (shadow only)."""
from __future__ import annotations

from career_pipeline.construct_criteria import _CRITERIA_BY_FAMILY, criteria_for_graph
from career_pipeline.job_analysis_compiler import build_job_analysis_graph


def _graph() -> object:
    posting = {
        "target": "테스트공사 행정",
        "duties": ["신청서류를 공식 기준과 대조해 오류와 누락을 확인한다"],
        "competencies": [],
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


def _by_id(criteria) -> dict:
    return {item.criterion_id: item for item in criteria}


def test_criterion_application_decomposition():
    criteria = criteria_for_graph(_graph())
    by_id = _by_id(criteria)
    assert "crit_criterion_application_compare_against_rule_or_source" in by_id
    assert "crit_criterion_application_detect_discrepancy" in by_id
    assert "crit_criterion_application_classify_exception" in by_id
    assert "crit_criterion_application_preserve_decision_basis" in by_id
    compare = by_id["crit_criterion_application_compare_against_rule_or_source"]
    assert compare.verbs == ("대조", "비교")
    assert compare.required_for_direct is True
    assert compare.optional_support is False
    classify = by_id["crit_criterion_application_classify_exception"]
    assert classify.required_for_direct is False
    assert classify.optional_support is True


def test_all_required_families_are_decomposed():
    assert set(_CRITERIA_BY_FAMILY) == {
        "criterion_application",
        "analytical_diagnosis",
        "stakeholder_explanation",
        "coordination",
        "boundary_escalation",
        "documentation",
        "execution_control",
    }
    graph = _graph()
    criteria = criteria_for_graph(graph)
    criteria_ids = {item.construct_id for item in criteria}
    for construct in graph.constructs:
        if construct.construct_id in criteria_ids:
            assert len([item for item in criteria if item.construct_id == construct.construct_id]) >= 2
        else:
            assert all(item.construct_id != construct.construct_id for item in criteria)


def test_prior_criteria_are_taxonomy_basis_and_target_never_escalates():
    criteria = criteria_for_graph(_graph())
    for item in criteria:
        if item.construct_id.startswith("prior_"):
            assert item.source_basis == "taxonomy_prior"
        else:
            assert item.source_basis == "target"
    assert any(
        item.source_basis == "taxonomy_prior" for item in criteria
    ), "fixture must include a taxonomy prior construct"
