from career_pipeline.models import Question
from career_pipeline.questions import extract_questions


def test_extracts_questions_and_character_limits():
    paragraphs = (
        "우리 공사 체험형 인턴에 지원하게 된 동기를 기술해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
        "HUG의 주요 사업 중 관심 있는 1가지를 선택해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
    )

    questions = extract_questions(paragraphs)

    assert [question.character_limit for question in questions] == [600, 600]
    assert [question.count_mode for question in questions] == [
        "spaces_included",
        "spaces_included",
    ]
    assert questions[0].prompt.startswith("우리 공사")


def test_extracts_spaces_excluded_count_mode():
    paragraphs = (
        "본인의 성장 가능성을 기술하시오.",
        "0/500 (글자 수, 공백 제외)",
    )

    questions = extract_questions(paragraphs)

    assert questions == [
        Question(1, "본인의 성장 가능성을 기술하시오.", 500, "spaces_excluded")
    ]


def test_extracts_extended_character_limit_formats_and_same_line_limits():
    paragraphs = (
        "지원동기를 기술해 주십시오. 600자 이내",
        "입사 후 목표를 기술해 주십시오. 최대 700자",
        "직무 역량을 기술해 주십시오.",
        "600 bytes",
    )

    questions = extract_questions(paragraphs)

    assert [question.character_limit for question in questions] == [600, 700, 600]
    assert questions[0].prompt == "지원동기를 기술해 주십시오."
