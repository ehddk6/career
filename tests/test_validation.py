from career_pipeline.models import DraftResponse, Question
from career_pipeline.validation import validate_draft


def test_validation_finds_empty_over_limit_blind_and_wrong_org_answers():
    questions = [Question(1, "지원동기", 20), Question(2, "문제해결", 10)]
    responses = [
        DraftResponse(
            1,
            "HUG에서 서울대학교 경험을 살려 한국주택금융공사보다 더 크게 기여하겠습니다.",
            ("경험정리/a.docx",),
        ),
        DraftResponse(2, "", ()),
    ]

    issues = validate_draft(
        questions,
        responses,
        target_org="HUG",
        known_sources={"경험정리/a.docx"},
    )
    codes = {issue.code for issue in issues}

    assert {"over_limit", "blind_term", "other_organization", "empty_answer"} <= codes


def test_validation_requires_known_evidence_paths():
    questions = [Question(1, "지원동기", 100)]
    responses = [
        DraftResponse(1, "검증 가능한 답변입니다.", ("없는파일.docx",))
    ]

    issues = validate_draft(
        questions, responses, target_org="HUG", known_sources={"근거.docx"}
    )

    assert "unknown_evidence" in {issue.code for issue in issues}
