from career_pipeline.style_diagnostics import diagnose_text


def test_same_ending_only_triggers_when_three_are_consecutive():
    nonconsecutive = diagnose_text(
        "자료를 확인합니다. 기준을 정리했습니다. 결과를 공유합니다. "
        "오류를 줄였습니다. 마지막으로 기록합니다."
    )
    consecutive = diagnose_text(
        "자료를 확인합니다. 기준을 정리합니다. 결과를 공유합니다. "
        "마지막에는 오류를 줄였습니다."
    )

    assert not any("종결" in reason for reason in nonconsecutive.style_reasons)
    assert any("종결" in reason for reason in consecutive.style_reasons)
