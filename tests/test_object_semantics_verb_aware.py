from pathlib import Path

from career_pipeline.object_semantics_shadow import semantic_object_match_verb_aware
from career_pipeline.object_semantics_verb_aware_benchmark import (
    combined_frozen_all,
    load_verb_aware_corpus,
    run_verb_aware_case,
    run_verb_aware_corpus,
)

CORPUS = (
    Path(__file__).parent / "fixtures" / "object_semantics_verb_aware_v1.json"
)
DOC = "crit_documentation_record_decision_or_action"
DOC_CLASS = ("판단", "처리", "결과", "내역")


def _case(case_id: str):
    return next(
        row for row in load_verb_aware_corpus(CORPUS)["cases"]
        if row["case_id"] == case_id
    )


def test_frozen_corpus_has_6_unique_cases():
    payload = load_verb_aware_corpus(CORPUS)
    ids = [row["case_id"] for row in payload["cases"]]
    assert len(ids) == 6
    assert len(ids) == len(set(ids))
    assert {row["category"] for row in payload["cases"]} == {"verb_aware_documentation"}


def test_all_6_verb_aware_cases_pass():
    report = run_verb_aware_corpus(CORPUS)
    assert report["summary"]["case_count"] == 6
    assert report["summary"]["passed_case_count"] == 6
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["expectation_pass_rate"] == 1.0
    assert report["summary"]["blocked_precision_rate"] == 1.0


def test_organize_without_artifact_is_not_direct():
    result = run_verb_aware_case(_case("organize-method-role-no-artifact"))
    assert result["passed"] is True
    assert result["observed"]["relation"] != "direct"
    basis = [
        ev.get("object_match_basis", "")
        for ev in result["observed"]["criterion_evidence"].values()
    ]
    assert "blocked_weak_generic" in basis


def test_organize_schedule_artifact_is_direct():
    result = run_verb_aware_case(_case("organize-schedule-artifact"))
    assert result["passed"] is True
    assert result["observed"]["relation"] == "direct"


def test_generic_item_organize_without_artifact_is_not_direct():
    result = run_verb_aware_case(_case("organize-generic-item-no-artifact"))
    assert result["passed"] is True
    assert result["observed"]["relation"] != "direct"


def test_excel_table_organize_is_direct():
    result = run_verb_aware_case(_case("organize-excel-check-items"))
    assert result["passed"] is True
    assert result["observed"]["relation"] == "direct"


def test_combined_frozen_all_is_32_of_32():
    report = combined_frozen_all()
    assert report["summary"]["case_count"] == 32
    assert report["summary"]["passed_case_count"] == 32
    assert report["summary"]["failed_case_count"] == 0
    assert report["summary"]["expectation_pass_rate"] == 1.0


def test_matcher_blocks_organize_weak_generic():
    match = semantic_object_match_verb_aware(
        DOC, "정리", "출석 확인 방식과 담당 역할", DOC_CLASS
    )
    assert match.matched is False
    assert match.basis == "blocked_weak_generic"
    assert "역할" in match.matched_terms


def test_matcher_artifact_supported_for_organize():
    match = semantic_object_match_verb_aware(
        DOC, "정리", "일정표 또는 배치안", DOC_CLASS
    )
    assert match.matched is True
    assert match.basis == "artifact_supported"


def test_matcher_documentary_verb_accepts_content():
    match = semantic_object_match_verb_aware(DOC, "메모", "전화 문의", DOC_CLASS)
    assert match.matched is True
    assert match.basis == "bounded_alias"


def test_matcher_blocks_organize_generic_item():
    match = semantic_object_match_verb_aware(DOC, "정리", "확인 항목", DOC_CLASS)
    assert match.matched is False
    assert match.basis == "blocked_weak_generic"


def test_matcher_artifact_supported_for_excel_table():
    match = semantic_object_match_verb_aware(DOC, "정리", "확인 항목을 엑셀 표", DOC_CLASS)
    assert match.matched is True
    assert match.basis == "artifact_supported"


def test_non_documentation_criterion_keeps_bounded_behavior():
    match = semantic_object_match_verb_aware(
        "crit_analytical_diagnosis_compare_or_segment_information",
        "분석",
        "타 시장",
        ("자료", "데이터", "정보", "현황", "지표"),
    )
    assert match.matched is True
    assert match.basis == "bounded_alias"
