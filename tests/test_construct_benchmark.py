import copy
from pathlib import Path

import pytest

from career_pipeline.construct_benchmark import (
    FrozenCaseError,
    load_corpus,
    run_corpus,
    run_frozen_case,
    validate_case,
)


CORPUS = (
    Path(__file__).parent
    / "fixtures"
    / "construct_disagreement_v1.json"
)


def _cases():
    return load_corpus(CORPUS)["cases"]


def _case(category: str):
    return next(row for row in _cases() if row["category"] == category)


def _relation(result, evidence_id: str, construct_id: str):
    key = f"relation:{evidence_id}|{construct_id}"
    check = next(row for row in result["checks"] if row["check"] == key)
    return check["actual"]


def test_frozen_corpus_has_required_categories_and_unique_ids():
    payload = load_corpus(CORPUS)
    categories = {row["category"] for row in payload["cases"]}
    assert {
        "true_but_irrelevant",
        "keyword_preserving_wrong_behavior",
        "context_only_behavior",
        "direct_but_unselected",
        "taxonomy_prior_escalation",
        "safe_paraphrase",
    }.issubset(categories)
    ids = [row["case_id"] for row in payload["cases"]]
    assert len(ids) == len(set(ids))


def test_fixture_hash_detects_silent_input_mutation():
    case = copy.deepcopy(_case("true_but_irrelevant"))
    case["fixture"]["ledger"]["experiences"][0]["role"] = "tampered"
    with pytest.raises(FrozenCaseError, match="fixture hash mismatch"):
        validate_case(case)


def test_all_frozen_expectations_pass():
    report = run_corpus(load_corpus(CORPUS))
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["expectation_pass_rate"] == 1.0
    assert report["summary"]["direct_precision_guard_rate"] == 1.0
    assert report["summary"]["disagreement_detection_rate"] == 1.0
    assert report["summary"]["taxonomy_boundary_rate"] == 1.0
    assert report["summary"]["benign_relation_invariance_rate"] == 1.0


def test_true_but_irrelevant_is_selected_lexically_but_flagged_construct_weak():
    result = run_frozen_case(_case("true_but_irrelevant"))
    assert result["passed"] is True
    assert "applicant:exp-1:clm-1" in result["observed"]["selected_evidence_ids"]
    assert "lexical_high_construct_weak" in result["observed"]["disagreement_kinds"]


def test_keyword_preserving_wrong_behavior_is_not_direct():
    result = run_frozen_case(_case("keyword_preserving_wrong_behavior"))
    relation = _relation(
        result,
        "applicant:exp-1:clm-1",
        "construct_criterion_application",
    )
    assert relation != "direct"


def test_context_only_behavior_is_not_direct():
    result = run_frozen_case(_case("context_only_behavior"))
    relation = _relation(
        result,
        "applicant:exp-1:clm-1",
        "construct_criterion_application",
    )
    assert relation != "direct"
    context_check = next(
        row
        for row in result["checks"]
        if row["check"]
        == "context_match:applicant:exp-1:clm-1|construct_criterion_application"
    )
    assert context_check["actual"] is True


def test_direct_construct_evidence_can_be_missed_by_current_lexical_portfolio():
    result = run_frozen_case(_case("direct_but_unselected"))
    assert result["passed"] is True
    assert "applicant:exp-weak:clm-weak" in result["observed"]["selected_evidence_ids"]
    assert "applicant:exp-direct:clm-direct" not in result["observed"]["selected_evidence_ids"]
    assert "construct_direct_not_selected" in result["observed"]["disagreement_kinds"]
    assert (
        _relation(
            result,
            "applicant:exp-direct:clm-direct",
            "construct_criterion_application",
        )
        == "direct"
    )


def test_taxonomy_prior_never_escalates_to_target_core():
    result = run_frozen_case(_case("taxonomy_prior_escalation"))
    assert result["passed"] is True
    assert all(
        not construct_id.startswith("prior_")
        for construct_id in result["observed"]["core_construct_ids"]
    )


def test_safe_paraphrase_preserves_direct_construct_relation():
    result = run_frozen_case(_case("safe_paraphrase"))
    assert result["passed"] is True
    group = next(
        row for row in result["checks"]
        if row["check"] == "same_relation_group:1"
    )
    assert group["actual"] == ["direct", "direct"]
