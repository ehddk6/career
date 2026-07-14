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


def test_formal_ending_repetition_is_advisory_but_message_repetition_rewrites():
    text = (
        "자료를 확인합니다. 여러 기준과 예외를 차례로 검토합니다. "
        "검토 결과를 담당자에게 공유합니다."
    )

    self_introduction = diagnose_text(text, document_type="self_introduction")
    message = diagnose_text(text, document_type="message")

    assert any("종결" in reason for reason in self_introduction.style_reasons)
    assert self_introduction.should_rewrite is False
    assert message.should_rewrite is True


def test_repeated_connectors_and_ability_phrases_are_explainable_risks():
    result = diagnose_text(
        "이를 통해 오류를 줄일 수 있습니다. 또한 기준을 정리할 수 있습니다. "
        "이를 통해 기록을 남길 수 있습니다. 또한 결과를 공유합니다."
    )

    assert any("연결어 반복" in reason for reason in result.style_reasons)
    assert any("할 수 있습니다" in reason for reason in result.style_reasons)
    assert result.metrics["repeated_connector_count"] == 2
    assert result.metrics["ability_phrase_count"] == 3
    assert result.should_rewrite is True


def test_single_common_connector_is_not_a_ban_word():
    result = diagnose_text(
        "자료를 확인했습니다. 이를 통해 오류 원인을 찾았습니다. 담당자에게 결과를 공유했습니다."
    )

    assert not any("연결어 반복" in reason for reason in result.style_reasons)


def test_abstract_nouns_and_conclusion_cliches_require_contextual_rewrite():
    result = diagnose_text(
        "효율성 제고가 중요합니다. 역량 강화가 필요합니다. "
        "가치 창출에 도움이 됩니다."
    )

    assert any("추상 명사" in reason for reason in result.style_reasons)
    assert any("결론형 상투어" in reason for reason in result.style_reasons)
    assert result.should_rewrite is True


def test_trailing_sentence_without_punctuation_is_included():
    result = diagnose_text("자료를 확인했습니다. 마지막 결과를 공유합니다")

    assert result.metrics["sentence_count"] == 2
