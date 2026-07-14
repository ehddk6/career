from career_pipeline.quality import (
    STRICT_MIN_ANSWER_SCORE,
    score_answer_quality,
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


def test_strict_interview_pack_checks_each_question_block_not_only_global_headings():
    questions = [Question(1, "성과 경험", 600), Question(2, "협업", 600)]
    responses = [
        DraftResponse(1, "HUG에서 20건을 확인했습니다.", ("career.txt",)),
        DraftResponse(2, "HUG에서 10건을 정리했습니다.", ("career.txt",)),
    ]
    interview = (
        "# 면접\n1분 자기소개\n꼬리질문\n압박질문\n근거\n"
        "문항 1\n30초\n60초\n90초\n꼬리질문\n압박질문\n근거: 20건\n"
        "문항 2\n30초\n60초\n90초\n꼬리질문\n압박질문\n"
    )
    issues = validate_interview_pack(interview, questions, responses, strict=True)
    assert "interview_question_block_incomplete" in {issue.code for issue in issues}


def test_generic_role_word_does_not_fake_target_specificity():
    question = Question(1, "신용보증기금 지원 동기를 기술하십시오.", 600)
    score = score_answer_quality(
        question,
        "보증 업무에서 자료를 확인하고 결과를 개선하겠습니다.",
        "신용보증기금 청년인턴 보증 사무",
    )

    assert score.target_specificity == 0
    assert "missing_target" in score.issues


def test_issue_question_scores_analysis_and_response_without_forced_org_name():
    question = Question(
        1,
        "최근 중소기업에 영향을 미치는 경제·사회 이슈와 이유를 설명하십시오.",
        600,
    )
    score = score_answer_quality(
        question,
        "고환율은 수입 원재료 비용 부담을 높여 현금흐름을 악화시킵니다. 기업별 영향 경로를 구분해 운전자금 지원과 환위험 관리를 연계할 필요가 있습니다.",
        "신용보증기금 청년인턴",
        evidence_verified=True,
    )

    assert score.target_specificity == 20
    assert score.job_fit == 15
    assert not {"missing_target", "missing_analysis", "missing_response"}.intersection(
        score.issues
    )


def test_job_fit_normalizes_korean_particles_in_duty_terms():
    score = score_answer_quality(
        Question(1, "업무수행계획", 600),
        "신용보증기금에서 기한연장과 기업신용 상시관리의 처리 기준을 확인하겠습니다.",
        "신용보증기금",
        job_terms=("신용보증 기한연장, 기업신용 상시관리",),
        evidence_verified=True,
    )

    assert score.job_fit == 15
    assert "missing_job_connection" not in score.issues


def test_strict_interview_pack_requires_substantive_progressive_answers():
    question = Question(1, "성과 경험", 600)
    response = DraftResponse(1, "자료를 대조해 오류를 줄였습니다.", ("career.txt",))
    intro = (
        "저는 자료의 기준과 출처를 먼저 확인하고 상대가 이해하기 쉽게 설명하는 사람입니다. "
        "접수 자료를 항목별로 대조해 누락 원인을 찾고 검토 기준을 정리한 경험이 있습니다. "
        "이 과정에서 판단이 필요한 항목은 담당자에게 근거와 함께 보고하고 확인된 내용만 안내했습니다. "
        "입사 후에도 확인된 사실과 추정을 구분해 정확한 업무 처리와 고객 안내를 함께 이루겠습니다."
    )
    answer30 = "자료의 기준과 출처를 대조해 누락 원인을 찾고, 확인 결과를 표로 정리해 검토 오류를 줄였습니다. 판단이 필요한 항목은 근거와 함께 바로 보고했습니다."
    answer60 = answer30 + " 담당자와 불일치 항목을 다시 확인하고, 같은 오류가 반복되지 않도록 확인 순서를 체크리스트로 남겼습니다."
    answer90 = answer60 + " 이 경험을 바탕으로 업무를 받으면 목적과 마감을 먼저 확인하고, 원자료와 입력값을 대조한 뒤 불일치는 근거와 함께 보고하겠습니다."
    interview = (
        "# 면접대비팩\n\n"
        f"## 1분 자기소개\n\n{intro}\n\n"
        "## 문항 1 대응\n\n"
        f"- 30초 답변: {answer30}\n"
        f"- 60초 답변: {answer60}\n"
        f"- 90초 답변: {answer90}\n"
        "- 꼬리질문: 자료를 대조할 때 가장 먼저 정한 기준은 무엇입니까?\n"
        "- 꼬리답변: 업무 목적과 제출 기준을 먼저 확인하고, 누락 여부와 입력값 일치 여부를 순서대로 점검했습니다.\n"
        "- 압박질문: 꼼꼼하게 확인하다가 마감을 놓치면 어떻게 하겠습니까?\n"
        "- 압박답변: 마감과 위험도를 기준으로 우선순위를 정하고, 판단이 필요한 불일치는 즉시 담당자에게 보고해 정확성과 속도를 함께 관리하겠습니다.\n"
        "- 평가 기준: 사실 확인과 설명의 구체성\n"
        "- 근거: 승인된 자료 검증 경험\n"
    )

    assert validate_interview_pack(
        interview, [question], [response], strict=True
    ) == []


def test_interview_question_marker_does_not_match_incidental_sentence_text():
    question = Question(1, "성과 경험", 600)
    interview = "# 면접\n\n이 설명은 문항 1 답변을 준비하기 위한 메모일 뿐입니다."

    issues = validate_interview_pack(
        interview,
        [question],
        [DraftResponse(1, "자료를 확인했습니다.", ("career.txt",))],
        strict=True,
    )

    assert "missing_interview_question" in {issue.code for issue in issues}


def test_prompt_coverage_detects_missing_motivation_learning_and_execution_sequence():
    questions = [
        Question(1, "지원하게 된 동기와 근무 중 배우고 기여할 부분을 기술하십시오.", 600),
        Question(2, "실제 업무수행계획을 기술하십시오.", 600),
    ]
    responses = [
        DraftResponse(1, "기관에서 자료를 확인하고 개선하겠습니다. " * 10, ("career.txt",)),
        DraftResponse(2, "자료를 확인하겠습니다. " * 12, ("career.txt",)),
    ]

    issues = validate_answer_quality(questions, responses, "HUG")
    codes = {issue.code for issue in issues}

    assert "missing_motivation_reason" in codes
    assert "missing_learning_plan" in codes
    assert "missing_execution_sequence" in codes


def test_issue_prompt_requires_reason_and_impact_path():
    question = Question(1, "최근 경제·사회 이슈를 선택하고 그 이유를 설명하십시오.", 600)
    response = DraftResponse(1, "고환율을 선택했습니다. 지원이 필요합니다. " * 12, (), research_refs=("issue",))

    issues = validate_answer_quality([question], [response], "신용보증기금")

    assert "missing_issue_reasoning" in {issue.code for issue in issues}


def test_strict_interview_rejects_timed_answers_unrelated_to_final_answer():
    question = Question(1, "자료 검증 경험", 600)
    response = DraftResponse(
        1,
        "계약서와 납부 내역을 대조해 보증 서류의 누락 원인을 찾았습니다.",
        ("career.txt",),
    )
    intro = "저는 기준과 출처를 먼저 살피고 불일치 원인을 설명하는 사람입니다. " * 4
    answer30 = "행사 운영에서 참가자 동선을 살피고 안내판 위치를 바꾸어 대기 시간을 줄였습니다."
    answer60 = answer30 + " 현장 담당자와 역할을 나누고 안내 방송 순서를 조정해 혼선을 줄였으며 의견을 기록했습니다."
    answer90 = answer60 + " 이후 설문을 정리해 다음 행사 운영 계획에 반영하고 팀원에게 개선된 절차를 공유했습니다."
    interview = (
        "# 면접대비팩\n\n"
        f"## 1분 자기소개\n\n{intro}\n\n"
        "## 문항 1 대응\n\n"
        f"- 30초 답변: {answer30}\n"
        f"- 60초 답변: {answer60}\n"
        f"- 90초 답변: {answer90}\n"
        "- 꼬리질문: 가장 먼저 바꾼 기준은 무엇입니까?\n"
        "- 꼬리답변: 현장 흐름을 관찰하고 반복되는 혼선의 위치부터 기록해 변경 우선순위를 정했습니다.\n"
        "- 압박질문: 개선 효과가 우연이었다면 어떻게 검증하겠습니까?\n"
        "- 압박답변: 변경 전후의 같은 시간대 기록을 비교하고 담당자 의견을 함께 확인해 다른 요인의 영향을 구분하겠습니다.\n"
        "- 평가 기준: 경험과 답변의 일치\n"
        "- 근거: 승인 경험\n"
    )

    issues = validate_interview_pack(interview, [question], [response], strict=True)

    assert "interview_answer_not_aligned" in {issue.code for issue in issues}


def test_strict_interview_requires_material_growth_between_timed_answers():
    question = Question(1, "자료 검증 경험", 600)
    response = DraftResponse(1, "자료 기준을 대조해 오류 원인을 찾았습니다.", ("career.txt",))
    base = "자료 기준을 대조해 오류 원인을 찾고 담당자에게 근거와 함께 보고했습니다."
    interview = (
        "# 면접대비팩\n\n"
        f"## 1분 자기소개\n\n{'기준과 출처를 확인해 오류를 줄인 경험이 있습니다. ' * 6}\n\n"
        "## 문항 1 대응\n\n"
        f"- 30초 답변: {base}\n"
        f"- 60초 답변: {base} 확인 순서를 기록했습니다.\n"
        f"- 90초 답변: {base} 확인 순서를 기록하고 공유했습니다.\n"
        "- 꼬리질문: 확인 순서는 무엇입니까?\n"
        "- 꼬리답변: 기준과 출처를 먼저 확인하고 불일치를 별도로 표시해 담당자에게 보고했습니다.\n"
        "- 압박질문: 시간이 부족하면 어떻게 합니까?\n"
        "- 압박답변: 위험도가 높은 항목을 먼저 대조하고 판단이 필요한 내용은 즉시 담당자에게 보고하겠습니다.\n"
        "- 평가 기준: 단계적 답변 확장\n"
        "- 근거: 승인 경험\n"
    )

    issues = validate_interview_pack(interview, [question], [response], strict=True)

    assert "interview_timed_answer_progression" in {
        issue.code for issue in issues
    }
