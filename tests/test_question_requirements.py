from __future__ import annotations

from career_pipeline.models import DraftResponse, Question
from career_pipeline.question_requirements import (
    build_question_requirement_map,
    validate_question_requirement_map,
)


def test_requirement_map_uses_actual_question_count_and_character_limits():
    questions = [
        Question(1, "신용보증기금 지원동기와 입사 후 기여를 작성해 주십시오.", 600),
        Question(2, "협업 경험과 배운 점을 작성해 주십시오.", 500),
        Question(3, "경제 이슈의 영향과 대응을 설명해 주십시오.", 1000),
    ]
    value = build_question_requirement_map(
        questions,
        target="신용보증기금 체험형 인턴",
        posting={"duties": ["보증기업 관리"], "competencies": ["의사소통"]},
    )

    assert [item["question_index"] for item in value["questions"]] == [1, 2, 3]
    assert value["questions"][0]["preferred_character_range"] == {
        "minimum": 510,
        "preferred_maximum": 558,
    }
    ids = {
        row["requirement_id"] for row in value["questions"][0]["requirements"]
    }
    assert {"direct_answer", "motivation_reason", "contribution_plan"} <= ids


def test_requirement_validator_blocks_generic_company_and_missing_subrequirements():
    question = Question(
        1,
        "신용보증기금 지원동기와 입사 후 기여를 작성해 주십시오.",
        600,
    )
    requirement_map = build_question_requirement_map(
        [question],
        target="신용보증기금 체험형 인턴",
        posting={"duties": ["보증기업 관리"], "competencies": []},
    )
    generic = DraftResponse(1, "공공기관의 가치에 공감합니다.", ())
    codes = {
        issue.code
        for issue in validate_question_requirement_map(
            [generic], requirement_map, target="신용보증기금 체험형 인턴"
        )
    }
    assert "missing_target_specificity" in codes
    assert "missing_requirement_contribution_plan" in codes

    concrete = DraftResponse(
        1,
        "신용보증기금이 보증기업을 관리하는 방식에 의미를 느껴 지원했습니다. "
        "입사 후에는 자료를 대조하고 누락을 기록해 담당자에게 보고하겠습니다.",
        (),
    )
    assert validate_question_requirement_map(
        [concrete], requirement_map, target="신용보증기금 체험형 인턴"
    ) == []


def test_max_quality_requirement_gate_enforces_preferred_minimum():
    question = Question(
        1,
        "자유롭게 작성해 주십시오.",
        600,
        minimum_character_limit=400,
    )
    requirement_map = build_question_requirement_map(
        [question], target="테스트기관", posting={}
    )
    assert requirement_map["questions"][0]["preferred_character_range"]["minimum"] == 510
    response = DraftResponse(1, "가" * 509, ())

    assert validate_question_requirement_map(
        [response], requirement_map, target="테스트기관"
    ) == []
    assert {
        issue.code
        for issue in validate_question_requirement_map(
            [response],
            requirement_map,
            target="테스트기관",
            enforce_preferred_range=True,
        )
    } == {"under_preferred_minimum"}
