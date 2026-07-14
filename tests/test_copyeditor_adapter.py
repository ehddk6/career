import json
from subprocess import CompletedProcess

from career_pipeline.copyeditor_adapter import copyedit_responses, copyedit_text
from career_pipeline.models import DraftResponse


def completed(text: str, *, returncode: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(
        args=["codex"],
        returncode=returncode,
        stdout=json.dumps({"text": text, "applied_rules": ["T-2"]}, ensure_ascii=False),
        stderr="" if returncode == 0 else "backend failed",
    )


def test_copyeditor_uses_integrated_prompt_and_accepts_conservative_edit():
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return completed("자료를 확인하고 오류를 줄였습니다.")

    result = copyedit_text(
        "자료를 확인해 오류를 줄였습니다.",
        protected_terms=("자료",),
        runner=runner,
    )

    assert result.status == "copyedited"
    assert "Correct spelling and grammar" in captured["input"]
    assert "Use the installed im-ai-copyeditor skill" not in captured["input"]
    assert "--output-schema" in captured["command"]


def test_copyeditor_accepts_identical_output_as_unchanged():
    original = "HUG 금융·기금 직무에서 고객 신뢰를 높이겠습니다."

    def runner(*args, **kwargs):
        return completed(original)

    result = copyedit_text(
        original,
        protected_terms=("HUG 금융·기금",),
        runner=runner,
    )

    assert result.status == "unchanged"
    assert result.text == original


def test_copyeditor_rejects_sentence_count_or_meaning_change():
    original = "HUG 자료 20건을 확인했습니다. 반려하지 않고 재검토했습니다."

    def runner(*args, **kwargs):
        return completed("HUG 자료 30건을 확인하고 승인했습니다.")

    result = copyedit_text(original, protected_terms=("HUG",), runner=runner)

    assert result.status == "fallback_validation"
    assert result.text == original


def test_copyeditor_rejects_over_editing():
    original = "자료를 확인했습니다. 기준을 기록했습니다."

    def runner(*args, **kwargs):
        return completed("완전히 다른 표현입니다. 새 내용을 길게 덧붙였습니다.")

    result = copyedit_text(original, runner=runner)

    assert result.status == "fallback_overedit"
    assert result.text == original


def test_copyeditor_batches_multiple_responses_in_one_backend_call():
    calls = 0

    def runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        payload = {
            "items": [
                {"question_index": 1, "text": "자료를 확인하고 오류를 줄였습니다.", "applied_rules": ["S-1"]},
                {"question_index": 2, "text": "기준을 기록하고 공유했습니다.", "applied_rules": ["ST-1"]},
            ]
        }
        return CompletedProcess(args=["codex"], returncode=0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    responses = [
        DraftResponse(1, "자료를 확인해 오류를 줄였습니다.", ("a.txt",)),
        DraftResponse(2, "기준을 기록해 공유했습니다.", ("b.txt",)),
    ]

    edited, report = copyedit_responses(
        responses,
        target_org="농협",
        runner=runner,
    )

    assert calls == 1
    assert [item.answer for item in edited] == ["자료를 확인하고 오류를 줄였습니다.", "기준을 기록하고 공유했습니다."]
    assert [item["status"] for item in report] == ["copyedited", "copyedited"]


def test_copyeditor_reports_actionable_usage_limit_reason():
    def runner(*args, **kwargs):
        return CompletedProcess(
            args=["codex"],
            returncode=1,
            stdout="",
            stderr="ERROR: You've hit your usage limit.",
        )

    result = copyedit_text("자료를 확인했습니다.", runner=runner)

    assert result.status == "fallback_backend_error"
    assert result.message == "copyeditor backend usage limit"


def test_copyeditor_rejects_modality_change_from_ability_to_completion():
    original = "자료를 검토할 수 있었습니다."

    def runner(*args, **kwargs):
        return completed("자료를 검토했습니다.")

    result = copyedit_text(original, runner=runner)

    assert result.status == "fallback_validation"
    assert result.text == original
    assert "서술 양태 변경" in result.message


def test_copyeditor_batch_prompt_receives_only_selected_style_reasons():
    captured = {}

    def runner(command, **kwargs):
        captured["input"] = kwargs["input"]
        payload = {
            "items": [
                {
                    "question_index": 1,
                    "text": "자료를 확인했습니다.",
                    "applied_rules": [],
                }
            ]
        }
        return CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    copyedit_responses(
        [DraftResponse(1, "자료를 확인했습니다.", ("a.txt",))],
        target_org="농협",
        diagnostics_by_index={1: ("연결어 반복: 또한",)},
        runner=runner,
    )

    assert "연결어 반복: 또한" in captured["input"]
    assert "style_reasons에 적힌 문제만" in captured["input"]
