from career_pipeline.matching import match_questions, render_matches_markdown
from career_pipeline.models import DraftResponse, Question
from career_pipeline.nonghyup_guidance import classify_nonghyup_prompt
from career_pipeline.posting_schema import PostingAnalysis, PostingSourceMetadata
from career_pipeline.profile_schema import EvidenceRef, Experience, ExperienceLedger, ProfileClaim
from career_pipeline.quality import validate_answer_quality


HASH = "a" * 64


def test_classifies_real_nonghyup_prompts_from_user_materials():
    prompts = [
        "본인의 발전을 위해 노력했던 경험 중 성장 가능성을 가장 잘 보여주는 사례를 제시하고, 해당 경험이 농협 업무 수행에 어떻게 활용될 수 있을지 기술하시오.",
        "판단이 쉽지 않은 상황에서 의사결정을 내렸던 경험을 제시하고, 당시 어떤 기준으로 정보를 검토하고 분석하여 최종 결정을 내렸는지 구체적으로 기술하시오.",
        "농협이 교육지원·경제·금융 사업을 동시에 수행하는 구조가 가지는 경쟁력은 무엇이며, 이를 강화하기 위해 본인이 기여할 수 있는 부분을 구체적으로 기술하시오.",
    ]

    assert [classify_nonghyup_prompt(prompt).question_type for prompt in prompts] == [
        "growth",
        "decision",
        "integrated_business",
    ]


def test_matching_report_includes_nonghyup_writing_guidance():
    evidence = EvidenceRef("career.txt", 0, HASH, "b" * 64)
    claim = ProfileClaim("role", "예산 관리", "confirmed", (evidence,))
    experience = Experience(
        "exp_decision",
        "예산 판단 경험",
        "총무",
        None,
        "",
        "선택지가 충돌한 상황",
        ("자료를 비교하고 기준에 따라 검토했습니다.",),
        ("행사 운영을 완료했습니다.",),
        ("분석", "조율"),
        (claim,),
        "confirmed",
        "2026-06-21T12:00:00+09:00",
    )
    ledger = ExperienceLedger(1, "2026-06-21T12:00:00+09:00", "C:/career", (experience,))
    posting = PostingAnalysis(
        1,
        "지역농협 일반관리직",
        PostingSourceMetadata(
            "url",
            "https://example.or.kr",
            "2026-06-21T12:00:00+09:00",
            HASH,
            "verified_domain",
            "text/html",
        ),
        "지역농협",
        "일반관리직",
        (),
        ("예산 관리와 고객 응대",),
        ("분석", "조율"),
        (),
        (),
        (),
        (),
        (),
    )
    question = Question(
        1,
        "판단이 쉽지 않은 상황에서 의사결정을 내렸던 경험을 제시하고, 당시 어떤 기준으로 정보를 검토하고 분석하여 최종 결정을 내렸는지 구체적으로 기술하시오.",
        500,
    )

    markdown = render_matches_markdown(match_questions(ledger, posting, [question]))

    assert "지역농협 작성 포인트: 판단 기준이 있는 의사결정" in markdown
    assert "상황과 선택지" in markdown
    assert "고객·조직 관점의 판단 기준" in markdown


def test_nonghyup_quality_blocks_missing_growth_application():
    question = Question(
        1,
        "본인의 발전을 위해 노력했던 경험 중 성장 가능성을 가장 잘 보여주는 사례를 제시하고, 해당 경험이 농협 업무 수행에 어떻게 활용될 수 있을지 기술하시오.",
        500,
    )
    answer = "처음 발표가 미숙해 반복 연습과 피드백을 통해 설명 방식을 개선했습니다. 결과적으로 발표를 안정적으로 마쳤습니다." * 5

    issues = validate_answer_quality(
        [question],
        [DraftResponse(1, answer, ("career.txt",))],
        "지역농협 일반관리직",
    )

    assert "nonghyup_missing_application" in {issue.code for issue in issues}


def test_nonghyup_quality_accepts_integrated_business_structure():
    question = Question(
        1,
        "농협이 교육지원·경제·금융 사업을 동시에 수행하는 구조가 가지는 경쟁력은 무엇이며, 이를 강화하기 위해 본인이 기여할 수 있는 부분을 구체적으로 기술하시오.",
        500,
    )
    answer = (
        "농협의 경쟁력은 교육지원, 경제, 금융이 지역 현장에서 연결되는 종합 지원 구조에 있습니다. "
        "교육지원은 조합원 역량을 높이고, 경제사업은 지역 농산물 유통과 판로를 넓히며, 금융사업은 필요한 자금과 상담을 제공합니다. "
        "저는 고객 요청을 확인하고 자료를 분석해 지역과 조합원에게 맞는 서비스를 연결하는 역할로 기여하겠습니다. "
        "현장에서 주민 의견을 정리하고 사업 담당자와 공유해 교육지원·경제·금융이 선순환하도록 돕겠습니다."
    )

    issues = validate_answer_quality(
        [question],
        [DraftResponse(1, answer, ("career.txt",))],
        "지역농협 일반관리직",
        job_terms=("고객 응대", "사업 안내", "자료 분석"),
    )

    assert not any(issue.code.startswith("nonghyup_") for issue in issues)
