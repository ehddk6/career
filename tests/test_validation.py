from career_pipeline.models import DraftResponse, ExperienceClaimRef, Question
from career_pipeline.profile_schema import (
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
)
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


def test_validation_uses_spaces_excluded_character_count():
    questions = [Question(1, "성장 경험", 5, "spaces_excluded")]
    responses = [DraftResponse(1, "가 나 다 라 마", ("근거.docx",))]

    issues = validate_draft(
        questions, responses, target_org="농협", known_sources={"근거.docx"}
    )

    assert "over_limit" not in {issue.code for issue in issues}


def test_validation_rejects_duplicate_and_unknown_question_indexes():
    questions = [Question(1, "지원 동기", 100)]
    responses = [
        DraftResponse(1, "첫 번째 답변입니다.", ("evidence.txt",)),
        DraftResponse(1, "중복 답변입니다.", ("evidence.txt",)),
        DraftResponse(2, "정의되지 않은 문항입니다.", ("evidence.txt",)),
    ]

    issues = validate_draft(
        questions, responses, target_org="HUG", known_sources={"evidence.txt"}
    )

    assert {"duplicate_response", "unknown_question_index"} <= {
        issue.code for issue in issues
    }


def test_v2_validation_rejects_unknown_unconfirmed_missing_and_mismatched_claims():
    evidence = EvidenceRef("career.txt", 0, "a" * 64, "b" * 64)
    experience = Experience(
        "exp_verify",
        "검증 경험",
        "",
        None,
        "",
        "상황",
        (),
        (),
        (),
        (
            ProfileClaim("budget_savings", "10000000원", "confirmed", (evidence,)),
            ProfileClaim("case_count", "20건", "proposed", (evidence,)),
        ),
        "confirmed",
        "2026-06-21T12:00:00+09:00",
    )
    ledger = ExperienceLedger(1, "2026-06-21", "C:/career", (experience,))
    questions = [Question(1, "성과", 600)]
    responses = [
        DraftResponse(
            1,
            "예산 2,000만원을 절감했습니다.",
            ("career.txt",),
            (
                ExperienceClaimRef(
                    "exp_verify", ("budget_savings", "case_count", "missing")
                ),
                ExperienceClaimRef("exp_unknown", ("budget_savings",)),
            ),
        )
    ]

    issues = validate_draft(
        questions,
        responses,
        "HUG",
        {"career.txt"},
        profile_ledger=ledger,
        require_experience_refs=True,
    )
    codes = {issue.code for issue in issues}

    assert {
        "unknown_experience_ref",
        "unconfirmed_claim_ref",
        "unknown_claim_field",
        "unapproved_metric",
    } <= codes
