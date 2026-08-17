from career_pipeline.object_semantics_shadow import semantic_object_match

def test_documentation_artifacts_have_bounded_aliases():
    cls=("판단","처리","결과","내역")
    assert semantic_object_match(
        "crit_documentation_record_decision_or_action","일정표 또는 배치안",cls
    ).matched
    assert semantic_object_match(
        "crit_documentation_record_decision_or_action","병원용 군의관용 안내 초안",cls
    ).matched
    assert not semantic_object_match(
        "crit_documentation_record_decision_or_action","엑셀 정렬 필터 함수",cls
    ).matched

def test_schedule_alias_does_not_leak_into_discrepancy():
    assert semantic_object_match(
        "crit_execution_control_inspect_status_or_deadline",
        "가능한 날짜와 시간",
        ("일정","마감","상태","진행","현황"),
    ).matched
    assert not semantic_object_match(
        "crit_criterion_application_detect_discrepancy",
        "가능한 날짜와 시간",
        ("누락","오류","예외","불일치","차이"),
    ).matched

def test_bad_role_span_remains_blocked():
    assert not semantic_object_match(
        "crit_criterion_application_detect_discrepancy",
        "담당자가",
        ("누락","오류","예외","불일치","차이"),
    ).matched

def test_analytical_comparison_target_is_bounded_alias():
    assert semantic_object_match(
        "crit_analytical_diagnosis_compare_or_segment_information",
        "타 시장",
        ("자료","데이터","정보","현황","지표"),
    ).matched

def test_stable_discrepancy_aliases():
    assert semantic_object_match(
        "crit_criterion_application_detect_discrepancy",
        "출석 미기재",
        ("누락","오류","예외","불일치","차이"),
    ).matched
    assert semantic_object_match(
        "crit_criterion_application_detect_discrepancy",
        "평균 이탈",
        ("누락","오류","예외","불일치","차이"),
    ).matched


def test_documentation_memo_content_is_bounded_alias():
    assert semantic_object_match(
        "crit_documentation_record_decision_or_action",
        "전화 문의",
        ("판단","처리","결과","내역"),
    ).matched
