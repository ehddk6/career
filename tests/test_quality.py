from career_pipeline.quality import (
    STRICT_MIN_ANSWER_SCORE,
    validate_answer_quality,
    validate_interview_pack,
    validate_matching_gate,
    validate_posting_gate,
    validate_profile_gate,
)
from career_pipeline.matching import MatchCandidate, QuestionMatch
from career_pipeline.models import DraftResponse, ExperienceClaimRef, Question
from career_pipeline.posting_schema import PostingAnalysis, PostingSourceMetadata
from career_pipeline.profile_schema import (
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
)


HASH = "a" * 64


def stale_ledger() -> ExperienceLedger:
    evidence = EvidenceRef("career.txt", 0, HASH, "b" * 64)
    claim = ProfileClaim("case_count", "20건", "stale", (evidence,))
    experience = Experience(
        "exp_stale",
        "경험",
        "",
        None,
        "",
        "상황",
        (),
        (),
        (),
        (claim,),
        "stale",
        None,
    )
    return ExperienceLedger(1, "2026-06-21T12:00:00+09:00", "C:/career", (experience,))


def posting(status: str) -> PostingAnalysis:
    source = PostingSourceMetadata(
        "url", "https://example.or.kr", "2026-06-21", HASH, status, "text/html"
    )
    return PostingAnalysis(
        1, "기관 직무", source, "기관", "직무", (), ("업무",), (), (), (), (), (), ()
    )


def test_profile_gate_blocks_stale_claim_selected_for_matching():
    issues = validate_profile_gate(
        stale_ledger(), selected_experience_ids={"exp_stale"}
    )

    assert issues[0].code == "stale_profile_evidence"


def test_profile_gate_allows_multiple_generic_metrics_from_same_evidence():
    evidence = EvidenceRef("career.txt", 0, HASH, "b" * 64)
    experience = Experience(
        "exp_metrics", "개선", "", None, "", "", (), (), (),
        (
            ProfileClaim("metric:percentage", "50%", "confirmed", (evidence,)),
            ProfileClaim("metric:percentage", "90%", "confirmed", (evidence,)),
        ),
        "confirmed", "2026-07-11T09:00:00+09:00",
    )
    ledger = ExperienceLedger(1, "2026-07-11", "C:/career", (experience,))

    issues = validate_profile_gate(ledger, selected_experience_ids=set())

    assert not any(issue.code == "conflicting_profile_claim" for issue in issues)


def test_posting_gate_blocks_unverified_source():
    issues = validate_posting_gate(posting("unverified"))

    assert issues[0].code == "unverified_posting"


def test_posting_gate_blocks_when_official_questions_are_not_publicly_available():
    issues = validate_posting_gate(posting("verified_domain"))

    assert any(issue.code == "missing_posting_questions" for issue in issues)


def test_matching_gate_requires_reliable_candidate_for_every_question():
    match = QuestionMatch(Question(1, "지원동기", 600), "motivation", (), None)

    issues = validate_matching_gate((match,))

    assert issues[0].code == "missing_reliable_match"


def test_matching_gate_rejects_confirmed_but_irrelevant_candidate():
    candidate = MatchCandidate(
        "exp_confirmed",
        40,
        40,
        0,
        0,
        0,
        0,
        (),
        (),
        ("case_count=20건",),
        (),
    )
    match = QuestionMatch(
        Question(1, "변화를 만든 경험", 600),
        "problem_solving",
        (candidate,),
        candidate,
    )

    issues = validate_matching_gate((match,))

    assert issues[0].code == "missing_relevant_match"


def test_answer_quality_blocks_underfilled_600_character_answer():
    questions = [Question(1, "지원 동기", 600)]
    responses = [DraftResponse(1, "HUG에서 정확하게 일하겠습니다.", ("career.txt",))]

    issues = validate_answer_quality(questions, responses, "HUG")

    assert "underfilled_answer" in {issue.code for issue in issues}


def test_answer_quality_uses_spaces_excluded_fill_ratio():
    questions = [Question(1, "성장 경험", 10, "spaces_excluded")]
    responses = [DraftResponse(1, "가 나 다 라 마 바 사 아", ("career.txt",))]

    issues = validate_answer_quality(questions, responses, "농협")

    assert "underfilled_answer" not in {issue.code for issue in issues}


def test_integrated_business_question_requires_all_three_businesses_and_linkage():
    question = Question(
        1,
        "농협이 교육지원·경제·금융 사업을 동시에 수행하는 구조의 경쟁력과 기여를 기술하시오.",
        500,
        "spaces_excluded",
    )
    answer = (
        "농협의 금융사업을 정확히 안내하겠습니다. 자료를 확인하고 분석한 결과 고객 신뢰를 높였습니다. "
        "농협에서도 같은 방식으로 기여하겠습니다. " * 4
    )

    issues = validate_answer_quality(
        [question], [DraftResponse(1, answer, ("career.txt",))], "농협"
    )

    assert "missing_integrated_business_structure" in {
        issue.code for issue in issues
    }


def test_portfolio_flags_reused_experience_across_different_questions():
    questions = [Question(i, f"문항 {i}", 500) for i in range(1, 5)]
    responses = [
        DraftResponse(
            i,
            "농협에서 자료를 확인하고 분석해 개선한 결과를 바탕으로 기여하겠습니다. " * 7,
            ("career.txt",),
            (ExperienceClaimRef("exp_same", ()),),
        )
        for i in range(1, 5)
    ]

    issues = validate_answer_quality(questions, responses, "농협")

    assert "reused_experience" in {issue.code for issue in issues}


def test_answer_quality_blocks_nearly_identical_answers_across_questions():
    answer = "HUG의 업무를 이해하고 자료를 교차 확인한 경험으로 기여하겠습니다. " * 9
    questions = [Question(1, "지원 동기", 600), Question(2, "주요 사업", 600)]
    responses = [
        DraftResponse(1, answer, ("career.txt",)),
        DraftResponse(2, answer, ("career.txt",)),
    ]

    issues = validate_answer_quality(questions, responses, "HUG")

    assert "duplicate_answer" in {issue.code for issue in issues}


def test_answer_quality_flags_abstract_language_and_missing_job_connection():
    answer = (
        "HUG에서 성실하게 최선을 다하고 적극적으로 노력하겠습니다. "
        "맡은 역할에서 최선을 다해 기여하겠습니다. "
    ) * 6
    questions = [Question(1, "지원 동기", 600)]
    responses = [DraftResponse(1, answer, ("career.txt",))]

    issues = validate_answer_quality(
        questions,
        responses,
        "HUG",
        job_terms=("보증심사 자료 검토",),
    )

    codes = {issue.code for issue in issues}
    assert "abstract_expression" in codes
    assert "missing_job_connection" in codes


def test_strict_answer_quality_uses_submission_ready_thresholds():
    answer = "HUG에서 성실하게 최선을 다하고 적극적으로 노력하겠습니다. " * 10
    questions = [Question(1, "지원 동기", 600)]
    responses = [DraftResponse(1, answer, ("career.txt",))]

    issues = validate_answer_quality(
        questions,
        responses,
        "HUG",
        job_terms=("보증심사 자료 검토",),
        minimum_score=STRICT_MIN_ANSWER_SCORE,
        average_minimum_score=90,
    )

    assert "low_quality_score" in {issue.code for issue in issues}


def test_interview_pack_requires_timed_answers_evaluation_and_evidence():
    questions = [Question(1, "성과 경험", 600)]
    responses = [DraftResponse(1, "HUG에서 20건을 확인했습니다.", ("career.txt",))]
    interview = "# 면접\n1분 자기소개\n꼬리질문\n압박질문\n근거\n20건"

    issues = validate_interview_pack(
        interview,
        questions,
        responses,
        allowed_metric_values={"20건"},
    )

    codes = {issue.code for issue in issues}
    assert "missing_interview_section" in codes
    assert "missing_interview_question" in codes
