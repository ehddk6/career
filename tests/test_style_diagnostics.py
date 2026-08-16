from career_pipeline.models import DraftResponse
from career_pipeline.style_diagnostics import (
    diagnose_responses,
    diagnose_text,
    editor_axis_scores,
    style_repair_details,
)


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


def test_formal_ending_repetition_is_an_independent_editor_axis():
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


def test_style_repair_details_identifies_exact_repeated_starts_and_ending_run():
    details = style_repair_details(
        "환율 변화가 큽니다. 환율 위험을 봅니다. "
        "자료를 확인합니다. 기준을 확인합니다. 결과를 확인합니다."
    )

    assert "환율" in details["repeated_start_tokens"]
    assert details["consecutive_ending_runs"][-1] == {
        "ending_class": "합니다",
        "sentence_indexes": [3, 4, 5],
    }


def test_editor_axes_score_human_scene_above_procedural_ai_voice():
    human = editor_axis_scores(
        "태블릿 서명 앞에서 고객이 한참 머뭇거리셨습니다. 저는 먼저 속도를 늦춰 설명했습니다. "
        "직접 동작을 보여 드리자 굳어 있던 표정이 풀렸고, 그때 설명은 전달보다 확인이라는 점을 배웠습니다."
    )
    procedural = editor_axis_scores(
        "입사 후에는 업무 흐름을 체계적으로 파악하겠습니다. 확인한 사실과 추가 확인 사항을 구분하겠습니다. "
        "임의로 판단하지 않고 근거와 함께 보고하겠습니다. 이를 통해 신뢰받는 인턴으로 기여하겠습니다."
    )

    assert human["editor_total"] > procedural["editor_total"]
    assert human["naturalness"] > procedural["naturalness"]
    assert human["translationese_ai_safety"] > procedural["translationese_ai_safety"]


def test_procedural_template_is_reported_as_voice_risk():
    result = diagnose_text(
        "입사 초기에는 업무 흐름을 익히겠습니다. 이후에는 자료를 확인하겠습니다. 처리 후에는 결과를 기록하겠습니다."
    )

    assert result.metrics["procedural_template_count"] >= 3
    assert any("절차 템플릿" in reason for reason in result.style_reasons)


def test_style_diagnostics_exposes_all_editor_contract_axes():
    result = diagnose_text("자료를 확인했습니다. 고객에게 이유를 설명했습니다. 다음 절차를 함께 확인했습니다.")

    assert {
        "naturalness",
        "sentence_rhythm",
        "ending_variety",
        "sentence_length_balance",
        "translationese_ai_safety",
        "nominalization_control",
        "editor_total",
    }.issubset(result.metrics)


def test_cross_question_procedural_formula_is_an_actionable_voice_risk():
    results = diagnose_responses(
        [
            DraftResponse(1, "원자료를 확인하고 근거와 함께 보고하겠습니다.", ()),
            DraftResponse(2, "고객 문의를 정리해 근거와 함께 보고하겠습니다.", ()),
        ]
    )

    assert all(item.should_rewrite for item in results)
    assert all(any("문항 간" in reason for reason in item.style_reasons) for item in results)
    assert all(item.metrics["cross_question_formula_count"] == 1 for item in results)
