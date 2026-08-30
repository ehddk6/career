from career_pipeline.self_introduction_genre import blocking_genre_issues, validate_self_introduction_genre


def _codes(text: str) -> set[str]:
    return {issue.code for issue in validate_self_introduction_genre(text)}


def test_audit_meta_language_is_blocked():
    assert "audit_meta_leakage" in _codes(
        "온라인 제출 방식을 제안했습니다. 결과를 제 단독 성과로 확대해 말할 수는 없습니다."
    )


def test_defensive_disclaimer_at_answer_end_is_blocked():
    assert "defensive_disclaimer" in _codes(
        "현장 정보를 정리해 담당자에게 전달했습니다. 실제 개선 여부까지는 확인하지 않았습니다."
    )


def test_self_explanation_and_control_word_density_are_detected():
    text = (
        "이 답변은 결과의 범위를 설명합니다. 근거를 확인하고 검증 범위를 확인했습니다. "
        "근거와 검증 범위를 다시 확인해 단정이나 확대를 피했습니다."
    )
    codes = _codes(text)
    assert "self_explanation" in codes
    assert "control_lexicon_density" in codes


def test_natural_role_boundary_is_allowed():
    text = "이상 신호만으로 부정을 판단하지 않고 담당자에게 근거와 함께 보고하겠습니다."
    assert not blocking_genre_issues(text)


def test_natural_problem_analysis_boundary_is_allowed():
    text = "갈등의 원인을 개인 간 대립으로 단정하지 않고, 출석 기록과 물품 관리의 문제로 정리했습니다."
    assert not blocking_genre_issues(text)


def test_outcome_disclaimer_is_still_blocked():
    text = "물품 혼선과 행사 지연도 이 조치만으로 해결되었다고 단정하지 않았습니다."
    assert "audit_meta_leakage" in _codes(text)


def test_needless_structurization_is_blocked_as_report_diction():
    text = "문의 내용을 구조화해 효율적으로 관리했습니다."
    assert "institutional_report_diction" in _codes(text)


def test_technical_data_structuring_is_allowed():
    text = "SQL 테이블의 열을 기준에 맞춰 구조화하고 중복 행을 제거했습니다."
    assert "institutional_report_diction" not in _codes(text)
