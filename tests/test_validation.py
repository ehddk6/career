from career_pipeline.models import DraftResponse, ExperienceClaimRef, Question
from career_pipeline.profile_schema import (
    ClaimVerification,
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
    stable_claim_id,
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


def test_v2_validation_requires_referenced_claim_to_appear_in_answer():
    evidence = EvidenceRef("career.txt", 0, "a" * 64, "b" * 64)
    experience = Experience(
        "exp_visible", "비교 경험", "", None, "", "상황", (), (), (),
        (ProfileClaim("experience_summary", "수식과 외주 프로그램의 결과 비교 분석 보고서", "confirmed", (evidence,)),),
        "confirmed", "2026-06-21T12:00:00+09:00",
    )
    ledger = ExperienceLedger(1, "2026-06-21", "C:/career", (experience,))
    question = Question(1, "경험", 600)
    response = DraftResponse(
        1, "자료를 확인하고 기준을 정리했습니다.", ("career.txt",),
        (ExperienceClaimRef("exp_visible", ("experience_summary",)),),
    )
    issues = validate_draft([question], [response], "HUG", {"career.txt"}, profile_ledger=ledger, require_experience_refs=True)
    assert "experience_claim_not_visible" in {issue.code for issue in issues}

    visible = DraftResponse(
        1, "수식과 외주 프로그램의 결과 비교 분석 보고서를 작성해 확인했습니다.", ("career.txt",),
        (ExperienceClaimRef("exp_visible", ("experience_summary",)),),
    )
    assert "experience_claim_not_visible" not in {
        issue.code for issue in validate_draft([question], [visible], "HUG", {"career.txt"}, profile_ledger=ledger, require_experience_refs=True)
    }


def test_v2_allows_embedded_counts_from_the_referenced_narrative_claim():
    evidence = EvidenceRef("career.txt", 0, "a" * 64, "b" * 64)
    provisional = ProfileClaim(
        "experience_summary",
        "상인 50명 인터뷰와 5개 시장 비교를 수행함",
        "confirmed",
        (evidence,),
        verification=ClaimVerification(
            method="direct_source", scope="source excerpt", contribution="observed"
        ),
    )
    claim = ProfileClaim(
        provisional.field,
        provisional.normalized_value,
        provisional.status,
        provisional.evidence,
        stable_claim_id("exp_counts", provisional),
        provisional.verification,
    )
    ledger = ExperienceLedger(
        2,
        "2026-07-14",
        "C:/career",
        (Experience(
            "exp_counts", "시장 조사", "", None, "", "", (), (), (),
            (claim,), "confirmed", "2026-07-14",
        ),),
    )
    response = DraftResponse(
        1,
        "상인 50명 인터뷰와 5개 시장 비교를 수행했습니다.",
        ("career.txt",),
        (ExperienceClaimRef("exp_counts", (), (claim.claim_id,)),),
    )

    issues = validate_draft(
        [Question(1, "경험을 설명하시오", 600)],
        [response],
        "HUG",
        {"career.txt"},
        profile_ledger=ledger,
        require_experience_refs=True,
    )

    assert "unapproved_metric" not in {issue.code for issue in issues}


def test_v2_research_only_question_uses_official_research_instead_of_forced_experience():
    ledger = ExperienceLedger(1, "2026-07-13", "C:/career", ())
    question = Question(
        1,
        "최근 중소기업에 영향을 미치는 경제·사회 이슈를 선택하고 이유를 서술하십시오.",
        600,
    )
    response = DraftResponse(
        1,
        "고환율은 14조원 규모의 지원과 원재료 수입 비용, 운전자금 부담에 영향을 줄 수 있습니다.",
        (),
        research_refs=("official-fx-risk",),
    )

    issues = validate_draft(
        [question],
        [response],
        "신용보증기금",
        set(),
        profile_ledger=ledger,
        require_experience_refs=True,
    )

    assert not {"missing_evidence", "missing_experience_ref"}.intersection(
        issue.code for issue in issues
    )
    assert "unapproved_metric" not in {issue.code for issue in issues}


def test_v2_experience_question_still_requires_confirmed_experience_reference():
    ledger = ExperienceLedger(1, "2026-07-13", "C:/career", ())
    question = Question(1, "문제를 해결한 경험을 기술하십시오.", 600)
    response = DraftResponse(1, "자료를 확인해 문제를 해결했습니다.", ())

    issues = validate_draft(
        [question],
        [response],
        "신용보증기금",
        set(),
        profile_ledger=ledger,
        require_experience_refs=True,
    )

    assert {"missing_evidence", "missing_experience_ref"} <= {
        issue.code for issue in issues
    }


def test_v2_pure_company_business_question_uses_research_without_forced_experience():
    ledger = ExperienceLedger(1, "2026-07-13", "C:/career", ())
    question = Question(1, "HUG의 주요 사업과 기관의 역할을 설명하십시오.", 600)
    response = DraftResponse(
        1,
        "전세보증금반환보증은 임차인의 보증금 반환 위험을 줄이는 사업입니다.",
        (),
        research_refs=("hug-program",),
    )

    issues = validate_draft(
        [question],
        [response],
        "HUG",
        set(),
        profile_ledger=ledger,
        require_experience_refs=True,
    )

    assert not {"missing_evidence", "missing_experience_ref"}.intersection(
        issue.code for issue in issues
    )
