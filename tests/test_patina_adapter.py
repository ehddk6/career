import json
from subprocess import CompletedProcess

from career_pipeline.models import DraftResponse, Question
from career_pipeline.patina_adapter import (
    PatinaScoreResult,
    humanize_responses,
    humanize_text,
    score_text,
)


def completed(output: str, *, returncode: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(
        args=["patina"],
        returncode=returncode,
        stdout=json.dumps({"output": output}, ensure_ascii=False),
        stderr="backend failed" if returncode else "",
    )


def test_humanize_text_extracts_only_rewritten_body():
    def runner(*args, **kwargs):
        return completed(
            "자료를 교차 확인해 정확도를 높였습니다.\n\n"
            "---\ntone: professional\ntone_source: user\n---"
        )

    result = humanize_text(
        "자료를 교차 확인하여 정확도를 높였습니다.",
        character_limit=600,
        runner=runner,
    )

    assert result.status == "humanized"
    assert result.text == "자료를 교차 확인해 정확도를 높였습니다."


def test_humanize_text_falls_back_when_numeric_claim_changes():
    original = "민원 20건을 확인하고 오류를 줄였습니다."

    def runner(*args, **kwargs):
        return completed("민원 30건을 확인하고 오류를 줄였습니다.")

    result = humanize_text(original, character_limit=600, runner=runner)

    assert result.status == "fallback_fact_change"
    assert result.text == original


def test_humanize_responses_preserves_metadata_and_reports_each_question():
    responses = [DraftResponse(1, "민원 20건을 확인했습니다.", ("career.txt",))]
    questions = [Question(1, "경험", 600)]

    def runner(*args, **kwargs):
        return completed("민원 20건을 직접 확인했습니다.")

    rewritten, reports = humanize_responses(responses, questions, runner=runner)

    assert rewritten[0].answer == "민원 20건을 직접 확인했습니다."
    assert rewritten[0].evidence_paths == ("career.txt",)
    assert reports[0]["question_index"] == 1
    assert reports[0]["status"] == "humanized"


def test_backend_error_summary_never_repeats_input_text():
    secret = "사용자 자기소개서 원문은 보고서에 남으면 안 됩니다."

    def runner(*args, **kwargs):
        return CompletedProcess(
            args=["patina"],
            returncode=1,
            stdout="",
            stderr=f"prompt={secret}\nERROR: You've hit your usage limit.",
        )

    result = humanize_text(secret, character_limit=600, runner=runner)

    assert result.status == "fallback_backend_error"
    assert "limit" in result.message.lower() or "한계" in result.message
    assert secret not in result.message


def test_humanize_text_passes_voice_sample_restyle_and_retry_options(tmp_path):
    voice_sample = tmp_path / "voice.txt"
    voice_sample.write_text("제가 직접 쓴 문장입니다.", encoding="utf-8")
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        return completed("자료를 다시 확인했습니다.")

    result = humanize_text(
        "자료를 확인했습니다.",
        character_limit=600,
        backend="codex-cli,openai-http",
        voice_sample=voice_sample,
        max_retries=1,
        runner=runner,
    )

    assert result.status == "humanized"
    assert "--voice-sample" in captured["command"]
    assert str(voice_sample) in captured["command"]
    assert captured["command"][captured["command"].index("--restyle") + 1] == "sentence"
    assert captured["command"][captured["command"].index("--max-retries") + 1] == "1"
    assert "codex-cli,openai-http" in captured["command"]


def test_humanize_text_rejects_semantic_anchor_change():
    original = 'HUG에서는 "반려"하지 않고 추가 확인했습니다.'

    def runner(*args, **kwargs):
        return completed('HUG에서는 "승인"하고 추가 확인했습니다.')

    result = humanize_text(
        original,
        character_limit=600,
        protected_terms=("HUG",),
        runner=runner,
    )

    assert result.status == "fallback_semantic_change"
    assert result.text == original


def test_humanize_text_compacts_safe_phrases_before_over_limit_fallback():
    original = "자료를 확인했습니다."
    rewritten = "자료를 교차 확인하기 위해 검토를 진행할 수 있었습니다."

    def runner(*args, **kwargs):
        return completed(rewritten)

    result = humanize_text(original, character_limit=22, runner=runner)

    assert result.status == "humanized_compacted"
    assert len(result.text) <= 22


def test_score_text_accepts_exit_code_three_as_valid_gate_result():
    def runner(*args, **kwargs):
        return CompletedProcess(
            args=["patina"],
            returncode=3,
            stdout=json.dumps({"overall": 42}),
            stderr="",
        )

    result = score_text("문장", threshold=30, runner=runner)

    assert result == PatinaScoreResult(42, "scored", "above threshold 30")
