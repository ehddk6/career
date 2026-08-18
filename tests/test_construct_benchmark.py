import copy
from pathlib import Path

import pytest

from career_pipeline.construct_benchmark import (
    FrozenCaseError,
    load_corpus,
    run_frozen_case,
    validate_case,
)
from career_pipeline.behavior_ir_correctness_benchmark import (
    combined_benchmark_file,
    run_correctness_corpus,
    run_legacy_corpus_compat,
    run_legacy_frozen_case,
)


CORPUS = Path(__file__).parent / "fixtures" / "construct_disagreement_v1.json"


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
        "true_but_irrelevant", "keyword_preserving_wrong_behavior", "context_only_behavior",
        "direct_but_unselected", "taxonomy_prior_escalation", "safe_paraphrase",
        "atomic_action_direct_v2", "metric_only_no_behavior", "context_action_unbound",
        "source_bound_action_direct", "korean_inflection_invariance", "wrong_actor",
        "prior_only_criterion", "partial_criterion",
    }.issubset(categories)
    ids = [row["case_id"] for row in payload["cases"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 18


def test_fixture_hash_detects_silent_input_mutation():
    case = copy.deepcopy(_case("true_but_irrelevant"))
    case["fixture"]["ledger"]["experiences"][0]["role"] = "tampered"
    with pytest.raises(FrozenCaseError, match="fixture hash mismatch"):
        validate_case(case)


def test_all_18_historical_frozen_expectations_pass_without_expectation_weakening():
    report = run_legacy_corpus_compat(CORPUS)
    assert report["summary"]["case_count"] == 18
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["expectation_pass_rate"] == 1.0
    assert report["summary"]["direct_precision_guard_rate"] == 1.0
    assert report["summary"]["disagreement_detection_rate"] == 1.0
    assert report["summary"]["taxonomy_boundary_rate"] == 1.0
    assert report["summary"]["benign_relation_invariance_rate"] == 1.0
    assert report["summary"]["v2_direct_precision_rate"] == 1.0
    assert report["summary"]["v2_direct_recall_rate"] == 1.0


def test_correctness_regression_corpus_has_8_cases_and_all_pass():
    report = run_correctness_corpus()
    assert report["summary"]["case_count"] == 8
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["contribution_safety_rate"] == 1.0
    assert report["summary"]["source_bound_atom_safety_rate"] == 1.0
    assert report["summary"]["object_order_invariance_rate"] == 1.0
    assert report["summary"]["counter_semantics_rate"] == 1.0


def test_combined_frozen_benchmark_is_26_of_26():
    report = combined_benchmark_file()
    assert report["summary"]["case_count"] == 26
    assert report["summary"]["passed_case_count"] == 26
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["expectation_pass_rate"] == 1.0


def test_true_but_irrelevant_is_selected_lexically_but_flagged_construct_weak():
    result = run_frozen_case(_case("true_but_irrelevant"))
    assert result["passed"] is True
    assert "applicant:exp-1:clm-1" in result["observed"]["selected_evidence_ids"]
    assert "lexical_high_construct_weak" in result["observed"]["disagreement_kinds"]


def test_keyword_preserving_wrong_behavior_is_not_direct():
    result = run_frozen_case(_case("keyword_preserving_wrong_behavior"))
    assert _relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") != "direct"


def test_context_only_behavior_is_not_direct():
    result = run_frozen_case(_case("context_only_behavior"))
    assert _relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") != "direct"
    context_check = next(row for row in result["checks"] if row["check"] == "context_match:applicant:exp-1:clm-1|construct_criterion_application")
    assert context_check["actual"] is True


def test_direct_construct_evidence_can_be_missed_by_current_lexical_portfolio():
    result = run_frozen_case(_case("direct_but_unselected"))
    assert result["passed"] is True
    assert "applicant:exp-weak:clm-weak" in result["observed"]["selected_evidence_ids"]
    assert "applicant:exp-direct:clm-direct" not in result["observed"]["selected_evidence_ids"]
    assert "construct_direct_not_selected" in result["observed"]["disagreement_kinds"]
    assert _relation(result, "applicant:exp-direct:clm-direct", "construct_criterion_application") == "direct"


def test_taxonomy_prior_never_escalates_to_target_core():
    result = run_frozen_case(_case("taxonomy_prior_escalation"))
    assert result["passed"] is True
    assert all(not construct_id.startswith("prior_") for construct_id in result["observed"]["core_construct_ids"])


def test_safe_paraphrase_preserves_direct_construct_relation():
    result = run_frozen_case(_case("safe_paraphrase"))
    assert result["passed"] is True
    group = next(row for row in result["checks"] if row["check"] == "same_relation_group:1")
    assert group["actual"] == ["direct", "direct"]


def _v2_relation(result, evidence_id: str, construct_id: str):
    key = f"v2:relation:{evidence_id}|{construct_id}"
    check = next(row for row in result["checks"] if row["check"] == key)
    return check["actual"]


def test_metric_only_claim_produces_no_v2_direct():
    result = run_frozen_case(_case("metric_only_no_behavior"))
    assert result["passed"] is True
    assert _v2_relation(result, "applicant:exp-1:clm-metric", "construct_criterion_application") in {"none", "inferred"}


def test_context_action_without_claim_backing_is_not_v2_direct():
    result = run_legacy_frozen_case(_case("context_action_unbound"))
    assert result["passed"] is True
    assert result.get("legacy_fixture_adapter") == "source_binding_only_after_original_hash_validation"
    assert _v2_relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") != "direct"


def test_atomic_action_direct_v2_is_v2_direct():
    result = run_frozen_case(_case("atomic_action_direct_v2"))
    assert result["passed"] is True
    assert _v2_relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") == "direct"


def test_source_bound_action_direct_is_v2_direct():
    result = run_frozen_case(_case("source_bound_action_direct"))
    assert result["passed"] is True
    assert _v2_relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") == "direct"


def test_korean_inflection_invariance_gives_identical_v2_relation():
    result = run_frozen_case(_case("korean_inflection_invariance"))
    assert result["passed"] is True
    left = _v2_relation(result, "applicant:exp-1:clm-1", "construct_criterion_application")
    right = _v2_relation(result, "applicant:exp-2:clm-1", "construct_criterion_application")
    assert left == right == "direct"


def test_wrong_actor_never_v2_direct():
    result = run_frozen_case(_case("wrong_actor"))
    assert result["passed"] is True
    assert _v2_relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") != "direct"


def test_prior_only_criterion_never_v2_direct():
    result = run_frozen_case(_case("prior_only_criterion"))
    assert result["passed"] is True
    prior_construct = next(row["check"].split("|")[1] for row in result["checks"] if row["check"].startswith("v2:relation:") and "|prior_" in row["check"])
    assert _v2_relation(result, "applicant:exp-1:clm-1", prior_construct) != "direct"


def test_partial_criterion_never_v2_direct():
    result = run_frozen_case(_case("partial_criterion"))
    assert result["passed"] is True
    assert _v2_relation(result, "applicant:exp-1:clm-1", "construct_criterion_application") != "direct"
