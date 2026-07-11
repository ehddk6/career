from career_pipeline.matching import match_questions, render_matches_markdown
from career_pipeline.models import Question
from career_pipeline.posting_schema import PostingAnalysis, PostingSourceMetadata
from career_pipeline.profile_schema import (
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
)


HASH = "a" * 64


def experience(
    experience_id: str,
    *,
    status: str = "confirmed",
    competencies: tuple[str, ...] = (),
    actions: tuple[str, ...] = (),
    outcomes: tuple[str, ...] = (),
    claim_status: str = "confirmed",
) -> Experience:
    evidence = EvidenceRef("career.txt", 0, HASH, "b" * 64)
    claim = ProfileClaim("case_count", "20건", claim_status, (evidence,))
    return Experience(
        experience_id,
        experience_id,
        "",
        None,
        "",
        "업무 상황",
        actions,
        outcomes,
        competencies,
        (claim,),
        status,
        "2026-06-21T12:00:00+09:00" if status == "confirmed" else None,
    )


def ledger_with(*experiences: Experience) -> ExperienceLedger:
    return ExperienceLedger(1, "2026-06-21T12:00:00+09:00", "C:/career", experiences)


def posting_with(
    *, duties: tuple[str, ...] = (), competencies: tuple[str, ...] = ()
) -> PostingAnalysis:
    source = PostingSourceMetadata(
        "url",
        "https://example.or.kr",
        "2026-06-21T12:00:00+09:00",
        HASH,
        "verified_domain",
        "text/html",
    )
    return PostingAnalysis(
        1,
        "기관 직무",
        source,
        "기관",
        "직무",
        (),
        duties,
        competencies,
        (),
        (),
        (),
        (),
        (),
    )


def test_confirmed_evidence_and_duty_overlap_rank_best_experience():
    ledger = ledger_with(
        experience(
            "exp_verify",
            competencies=("데이터 검증", "정확성"),
            actions=("자료 교차 확인",),
        ),
        experience(
            "exp_customer",
            competencies=("고객 안내",),
            actions=("절차 설명",),
        ),
    )
    posting = posting_with(duties=("신청 자료 확인",), competencies=("정확성",))
    question = Question(1, "문제를 발견하고 개선한 경험", 600)

    matches = match_questions(ledger, posting, [question])

    best = matches[0].candidates[0]
    assert best.experience_id == "exp_verify"
    assert best.evidence_score == 40
    assert "정확성" in best.matched_competencies


def test_matching_excludes_proposed_and_stale_experiences():
    ledger = ledger_with(
        experience("exp_confirmed"),
        experience("exp_proposed", status="proposed"),
        experience("exp_stale", status="stale"),
    )

    [match] = match_questions(
        ledger, posting_with(), [Question(1, "지원동기", 600)]
    )

    assert [item.experience_id for item in match.candidates] == ["exp_confirmed"]


def test_question_type_fit_rewards_relevant_experience():
    ledger = ledger_with(
        experience(
            "exp_collaboration",
            actions=("팀과 협업해 갈등을 조정",),
            outcomes=("공동 목표 달성",),
        ),
        experience("exp_other", actions=("자료 정리",)),
    )

    [match] = match_questions(
        ledger, posting_with(), [Question(1, "팀 갈등을 해결한 경험", 600)]
    )

    assert match.candidates[0].experience_id == "exp_collaboration"
    assert match.candidates[0].question_fit_score == 15


def test_zero_overlap_ties_are_deterministic_and_limited_to_three():
    ledger = ledger_with(*(experience(f"exp_{index}") for index in range(5)))

    [match] = match_questions(
        ledger,
        posting_with(duties=("무관한 업무",)),
        [Question(1, "지원동기", 600)],
    )

    assert [item.experience_id for item in match.candidates] == [
        "exp_0",
        "exp_1",
        "exp_2",
    ]
    assert all(item.duty_score == 0 for item in match.candidates)


def test_recommended_allocation_applies_reuse_penalty_only_after_first_use():
    ledger = ledger_with(experience("exp_one"))
    questions = [Question(1, "지원동기", 600), Question(2, "입사 후 목표", 600)]

    matches = match_questions(ledger, posting_with(), questions)

    assert matches[0].recommended.reuse_penalty == 0
    assert matches[1].recommended.reuse_penalty == 15
    assert all(candidate.reuse_penalty == 0 for match in matches for candidate in match.candidates)


def test_markdown_distinguishes_allowed_and_blocked_claims():
    candidate = experience("exp_one", claim_status="proposed")
    candidate = Experience(
        **{
            **candidate.__dict__,
            "status": "confirmed",
            "confirmed_at": "2026-06-21T12:00:00+09:00",
            "claims": (
                ProfileClaim("case_count", "20건", "confirmed", candidate.claims[0].evidence),
                candidate.claims[0],
            ),
        }
    )

    matches = match_questions(
        ledger_with(candidate), posting_with(), [Question(1, "지원동기", 600)]
    )
    markdown = render_matches_markdown(matches)

    assert "사용 가능" in markdown
    assert "사용 금지" in markdown
    assert "합격 확률" not in markdown
