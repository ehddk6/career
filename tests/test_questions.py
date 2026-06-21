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
    assert questions[0].prompt.startswith("우리 공사")
