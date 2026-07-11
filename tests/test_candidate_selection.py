from career_pipeline.candidate_selection import generate_and_select_candidates
from career_pipeline.models import DraftResponse, Question
from career_pipeline.patina_adapter import HumanizationResult
from career_pipeline.patina_adapter import PatinaScoreResult
from career_pipeline.quality import score_answer_quality


def test_quality_score_rewards_specific_action_result_and_job_connection():
    question = Question(1, "지원 동기와 인턴 목표", 600)
    generic = "HUG에서 성실하게 배우며 최선을 다하겠습니다. " * 11
    specific = (
        "HUG의 전세보증 업무가 임차인의 주거 불안을 줄이는 방식에 관심을 가졌습니다. "
        "이전 업무에서 자료를 항목별로 대조하고 오류 원인을 담당자와 확인했습니다. "
        "그 결과 누락을 줄이고 검토 기준을 정리했습니다. 인턴으로 근무하며 보증심사 자료의 "
        "근거를 빠르게 찾고 고객에게 정확히 설명하는 역량을 익히겠습니다. "
    ) * 3

    generic_score = score_answer_quality(
        question, generic[:590], "HUG 금융·기금", job_terms=("보증심사 자료 검토",)
    )
    specific_score = score_answer_quality(
        question, specific[:590], "HUG 금융·기금", job_terms=("보증심사 자료 검토",)
    )

    assert specific_score.total > generic_score.total
    assert specific_score.action_result > generic_score.action_result
    assert specific_score.job_fit > generic_score.job_fit


def test_generation_creates_three_candidates_and_selects_highest_score():
    question = Question(1, "지원 동기와 인턴 목표", 600)
    response = DraftResponse(
        1,
        "HUG에서 자료를 확인한 경험으로 정확하게 기여하겠습니다. " * 9,
        ("career.txt",),
    )

    def rewriter(text, **kwargs):
        if kwargs["profile"] == "formal":
            return HumanizationResult(
                "HUG의 보증심사 자료를 대조한 경험이 있습니다. "
                "검토 기준을 정리해 오류를 줄였고, 인턴으로서 고객 안내의 정확도를 높이겠습니다. "
                * 4,
                "humanized",
            )
        return HumanizationResult("HUG에서 열심히 배우겠습니다. " * 15, "humanized")

    selected, report = generate_and_select_candidates(
        [response],
        [question],
        "HUG 금융·기금",
        job_terms=("보증심사 자료 검토",),
        rewriter=rewriter,
    )

    assert len(report[0]["candidates"]) == 3
    assert report[0]["selected_variant"] == "formal"
    assert report[0]["patina_applied"] is True
    assert "검토 기준" in selected[0].answer


def test_failed_rewrite_candidate_never_beats_valid_original_on_tie():
    question = Question(1, "지원 동기", 600)
    original = "HUG의 보증 업무에서 자료를 확인하고 오류를 줄인 경험으로 기여하겠습니다. " * 8
    response = DraftResponse(1, original, ("career.txt",))

    def failed_rewriter(text, **kwargs):
        return HumanizationResult(text, "fallback_backend_error", "temporary error")

    selected, report = generate_and_select_candidates(
        [response],
        [question],
        "HUG",
        rewriter=failed_rewriter,
    )

    assert report[0]["selected_variant"] == "original"
    assert report[0]["patina_applied"] is False
    assert report[0]["patina_attempted"] is True
    assert selected[0].answer == original


def test_selection_prefers_candidate_that_meets_minimum_fill_ratio():
    question = Question(1, "지원 동기", 200, "spaces_excluded")
    response = DraftResponse(
        1,
        "농협에서 자료를 확인하고 분석해 개선한 결과로 고객 신뢰를 높였으며 현장 업무에 기여하겠습니다." * 4,
        ("career.txt",),
    )

    def short_rewriter(text, **kwargs):
        return HumanizationResult("농협에서 기여하겠습니다.", "ok")

    selected, report = generate_and_select_candidates(
        [response], [question], "농협", rewriter=short_rewriter
    )

    assert report[0]["selected_variant"] == "original"
    assert selected[0].answer == response.answer


def test_selection_uses_patina_ai_score_gate_and_reports_headroom():
    question = Question(1, "지원 동기", 80)
    response = DraftResponse(
        1,
        "HUG에서 자료를 확인하고 기준을 정리해 고객에게 정확히 안내하겠습니다." * 2,
        ("career.txt",),
    )

    def rewriter(text, **kwargs):
        if kwargs["profile"] == "formal":
            return HumanizationResult("HUG에서 자료를 직접 확인해 정확히 안내하겠습니다." * 2, "humanized")
        return HumanizationResult("HUG에서 기준을 확인해 고객에게 설명하겠습니다." * 2, "humanized")

    def scorer(text, **kwargs):
        if "정리해" in text:
            return PatinaScoreResult(55, "scored", "above threshold 30")
        if "직접" in text:
            return PatinaScoreResult(45, "scored", "above threshold 30")
        return PatinaScoreResult(18, "scored")

    selected, report = generate_and_select_candidates(
        [response],
        [question],
        "HUG",
        rewriter=rewriter,
        scorer=scorer,
        ai_score_threshold=30,
    )

    assert report[0]["selected_variant"] == "narrative"
    assert report[0]["selected_ai_score"] == 18
    assert report[0]["input_fill_ratio"] > 0.92
    assert report[0]["headroom_target_met"] is False
    assert "기준을 확인해" in selected[0].answer


def test_conditional_patina_skips_rewrite_when_copyedited_text_passes_score():
    question = Question(1, "지원 동기", 600)
    response = DraftResponse(1, "농협에서 자료를 확인해 정확히 안내하겠습니다." * 9, ("career.txt",))

    def rewriter(*args, **kwargs):
        raise AssertionError("score 통과 시 Patina rewrite를 호출하면 안 됨")

    def scorer(*args, **kwargs):
        return PatinaScoreResult(18, "scored")

    selected, report = generate_and_select_candidates(
        [response],
        [question],
        "농협",
        rewriter=rewriter,
        scorer=scorer,
        conditional_rewrite=True,
    )

    assert selected[0].answer == response.answer
    assert report[0]["selected_variant"] == "copyedited"
    assert report[0]["patina_attempted"] is False
    assert report[0]["patina_score_attempted"] is True
    assert report[0]["ai_score_gate"] == "passed"
