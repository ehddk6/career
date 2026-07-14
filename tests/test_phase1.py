import json
from pathlib import Path
from subprocess import CompletedProcess

from career_pipeline.copyeditor_adapter import copyedit_responses, copyedit_text
from career_pipeline.__main__ import main
from career_pipeline.model_policy import resolve_model
from career_pipeline.orchestrator import finalize_run
from career_pipeline.rewrite_validation import (
    MAX_CHANGE_RATIO,
    WARNING_CHANGE_RATIO,
    meaning_preservation_issue,
    validate_rewrite,
)
from career_pipeline.state import write_json, write_state


def _write_minimal_run(run_dir: Path, answers: list[str]) -> None:
    run_dir.mkdir(exist_ok=True)
    state = {
        "status": "ready_for_research",
        "quality_mode": "legacy",
        "strict_quality": False,
        "target": "기관 행정",
        "root": str(run_dir),
        "questions": [
            {"index": index, "prompt": f"문항 {index}", "character_limit": 600}
            for index in range(1, len(answers) + 1)
        ],
    }
    write_state(run_dir, state)
    write_json(run_dir / "02_사실원장.json", [{"source_path": "source.txt"}])
    write_json(
        run_dir / "draft.json",
        [
            {
                "question_index": index,
                "answer": answer,
                "evidence_paths": ["source.txt"],
            }
            for index, answer in enumerate(answers, 1)
        ],
    )
    (run_dir / "04_기업직무조사.md").write_text(
        "[공식](https://example.com)", encoding="utf-8"
    )
    (run_dir / "05_문항전략.md").write_text("# 전략", encoding="utf-8")
    (run_dir / "08_면접대비팩.md").write_text(
        "1분 자기소개\n꼬리질문\n압박질문\n근거", encoding="utf-8"
    )


def _batch_runner(payload: dict, calls: list[int]):
    def runner(*args, **kwargs):
        calls.append(1)
        return CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
        )

    return runner


def test_natural_draft_auto_postprocess_calls_zero(tmp_path: Path):
    _write_minimal_run(tmp_path, ["자료를 확인하고 기준을 기록했습니다."])
    calls: list[int] = []
    state = finalize_run(
        tmp_path,
        postprocess="auto",
        postprocess_runner=_batch_runner({"items": []}, calls),
    )
    assert state["status"] == "complete"
    assert calls == []
    assert state["postprocess_attempted"] is False
    assert (tmp_path / "12_최종산출물.json").exists()


def test_formal_ending_warning_alone_does_not_call_postprocess(tmp_path: Path):
    answer = (
        "자료를 확인합니다. 여러 기준과 예외를 차례로 검토합니다. "
        "검토 결과를 담당자에게 공유합니다."
    )
    _write_minimal_run(tmp_path, [answer])
    calls: list[int] = []

    state = finalize_run(
        tmp_path,
        postprocess="auto",
        postprocess_runner=_batch_runner({"items": []}, calls),
    )

    diagnostics = json.loads(
        (tmp_path / "09_style_diagnostics.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "complete"
    assert calls == []
    assert diagnostics[0]["should_rewrite"] is False
    assert any("종결" in item for item in diagnostics[0]["style_reasons"])


def test_nonlegacy_finalize_clears_stale_legacy_patina_state(tmp_path: Path):
    _write_minimal_run(tmp_path, ["자료를 확인하고 기준을 기록했습니다."])
    state = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    state.update(
        legacy_patina=True,
        patina_attempted=True,
        patina_score_attempted=True,
        patina_applied=True,
        patina_status="applied",
        patina_score_enabled=True,
        patina_voice_sample_used="stale-voice.txt",
        patina_summary={"attempted_questions": 1},
    )
    write_state(tmp_path, state)

    finalized = finalize_run(tmp_path, postprocess="never", humanize=False)

    assert finalized["status"] == "complete"
    assert finalized["legacy_patina"] is False
    assert finalized["patina_attempted"] is False
    assert finalized["patina_score_attempted"] is False
    assert finalized["patina_applied"] is False
    assert finalized["patina_status"] == "disabled"
    assert finalized["patina_score_enabled"] is False
    assert finalized["patina_voice_sample_used"] is None
    assert "patina_summary" not in finalized


def test_structural_style_risk_is_sent_to_one_targeted_terra_batch(tmp_path: Path):
    answer = (
        "이를 통해 오류를 줄일 수 있습니다. 또한 기준을 정리할 수 있습니다. "
        "이를 통해 기록을 남길 수 있습니다. 또한 결과를 공유합니다."
    )
    _write_minimal_run(tmp_path, [answer])
    captured: list[str] = []

    def runner(*args, **kwargs):
        captured.append(kwargs["input"])
        return CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=json.dumps(
                {
                    "items": [
                        {
                            "question_index": 1,
                            "text": answer,
                            "applied_rules": [],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            stderr="",
        )

    state = finalize_run(
        tmp_path,
        postprocess="auto",
        postprocess_runner=runner,
    )

    assert state["status"] == "complete"
    assert len(captured) == 1
    assert "연결어 반복" in captured[0]
    assert "'할 수 있습니다' 반복" in captured[0]
    assert state["postprocess_tier"] == "terra"


def test_multiple_style_risk_items_use_one_batch_call(tmp_path: Path):
    answers = [
        "자료를 확인했습니다. 기준을 기록했습니다. 결과를 공유했습니다.",
        "자료를 확인했습니다. 기준을 기록했습니다. 결과를 공유했습니다.",
    ]
    _write_minimal_run(tmp_path, answers)
    calls: list[int] = []
    payload = {"items": [{"question_index": 1, "text": answers[0]}, {"question_index": 2, "text": answers[1]}]}
    state = finalize_run(
        tmp_path,
        postprocess="auto",
        postprocess_runner=_batch_runner(payload, calls),
    )
    assert state["status"] == "complete"
    assert len(calls) == 1
    assert state["postprocess_attempted"] is True
    assert state["postprocess_applied"] is False


def test_model_call_budget_exceeded_stops_safely(tmp_path: Path):
    answer = "자료를 확인했습니다. 기준을 기록했습니다. 결과를 공유했습니다."
    _write_minimal_run(tmp_path, [answer])
    calls: list[int] = []
    state = finalize_run(
        tmp_path,
        postprocess="always",
        max_model_calls=0,
        postprocess_runner=_batch_runner({"items": [{"question_index": 1, "text": answer}]}, calls),
    )
    assert state["status"] == "complete"
    assert calls == []
    assert state["postprocess_status"] == "budget_exceeded"


def test_unconfigured_real_model_skips_external_postprocess(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CAREER_MODEL_LUNA", raising=False)
    monkeypatch.delenv("CAREER_MODEL_TERRA", raising=False)
    monkeypatch.delenv("CAREER_MODEL_SOL", raising=False)
    _write_minimal_run(tmp_path, ["자료를 확인했습니다. 기준을 기록했습니다. 결과를 공유했습니다."])

    state = finalize_run(tmp_path, postprocess="always")

    assert state["status"] == "complete"
    assert state["postprocess_status"] == "model_unconfigured"
    assert state["model_calls"]["total"] == 0


def test_validation_reverts_only_the_invalid_question(tmp_path: Path):
    original_long = "가" * 599
    good_original = "자료를 확인하고 오류를 줄였습니다."
    _write_minimal_run(tmp_path, [original_long, good_original])
    payload = {
        "items": [
            {"question_index": 1, "text": "가" * 600 + "나"},
            {"question_index": 2, "text": "자료를 확인하며 오류를 줄였습니다."},
        ]
    }
    calls: list[int] = []
    state = finalize_run(
        tmp_path,
        postprocess="always",
        postprocess_runner=_batch_runner(payload, calls),
    )
    final = json.loads((tmp_path / "draft_final.json").read_text(encoding="utf-8"))

    assert state["status"] == "complete"
    assert len(calls) == 1
    assert final[0]["answer"] == original_long
    assert final[1]["answer"] == "자료를 확인하며 오류를 줄였습니다."


def test_batch_failure_does_not_fan_out_retries():
    calls: list[int] = []

    def runner(*args, **kwargs):
        calls.append(1)
        return CompletedProcess(args=["codex"], returncode=1, stdout="", stderr="backend failed")

    responses = [
        type("R", (), {"question_index": 1, "answer": "자료를 확인했습니다.", "evidence_paths": (), "experience_refs": (), "research_refs": ()})(),
        type("R", (), {"question_index": 2, "answer": "기준을 기록했습니다.", "evidence_paths": (), "experience_refs": (), "research_refs": ()})(),
    ]
    edited, report = copyedit_responses(responses, target_org="기관", runner=runner)
    assert len(calls) == 1
    assert all(item.answer == original.answer for item, original in zip(edited, responses))
    assert all(str(item["status"]).startswith("fallback_") for item in report)


def test_duplicate_batch_question_indexes_are_rejected():
    calls: list[int] = []
    payload = {"items": [{"question_index": 1, "text": "자료를 확인했습니다."}] * 2}
    responses = [
        type("R", (), {"question_index": 1, "answer": "자료를 확인했습니다.", "evidence_paths": (), "experience_refs": (), "research_refs": ()})(),
    ]
    edited, report = copyedit_responses(
        responses,
        target_org="기관",
        runner=_batch_runner(payload, calls),
    )
    assert edited[0].answer == responses[0].answer
    assert report[0]["status"] == "fallback_backend_error"


def test_rewrite_validation_rejects_numbers_negation_causation_and_sentence_count():
    assert meaning_preservation_issue("자료 20건을 확인했습니다.", "자료 30건을 확인했습니다.")
    assert meaning_preservation_issue("반려하지 않았습니다.", "승인했습니다.")
    assert meaning_preservation_issue("오류 때문에 재검토했습니다.", "오류를 재검토했습니다.")
    result = validate_rewrite("자료를 확인했습니다. 기준을 기록했습니다.", "자료를 확인했습니다.")
    assert result.valid is False
    assert "문장 수 변경" in result.issues


def test_change_ratio_warning_and_maximum_are_separate():
    original = "가" * 50
    warned = "가" * 43 + "나" * 7
    warning = validate_rewrite(original, warned)
    assert WARNING_CHANGE_RATIO < warning.change_ratio <= MAX_CHANGE_RATIO
    assert warning.valid is True
    rejected = validate_rewrite(original, "나" * 50)
    assert rejected.valid is False
    assert any("변경률" in issue for issue in rejected.issues)
    assert validate_rewrite("자료를 확인했습니다.", "자료를 확인했습니다!").valid is True


def test_numeric_change_returns_original_from_copyeditor():
    def runner(*args, **kwargs):
        return CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=json.dumps({"text": "자료 30건을 확인했습니다.", "applied_rules": []}, ensure_ascii=False),
            stderr="",
        )

    original = "자료 20건을 확인했습니다."
    result = copyedit_text(original, runner=runner)
    assert result.text == original
    assert result.status == "fallback_validation"


def test_model_tier_environment_mapping(monkeypatch):
    monkeypatch.setenv("CAREER_MODEL_TERRA", "configured-model-id")
    config = resolve_model("terra")
    assert config.tier == "terra"
    assert config.model_id == "configured-model-id"


def test_atomic_state_write_leaves_no_temp_files(tmp_path: Path):
    write_json(tmp_path / "state.json", {"ok": True})
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["ok"] is True
    assert list(tmp_path.glob(".state.json.*.tmp")) == []
    state = {"status": "complete"}
    write_state(tmp_path, state)
    write_state(tmp_path, state)
    assert state["state_history"][-1]["status"] == "complete"
    assert len(state["state_history"]) == 1


def test_cli_rejects_conflicting_finalize_options(tmp_path: Path):
    assert main(["finalize", "--run", str(tmp_path), "--no-copyeditor", "--postprocess", "always"]) == 4
    assert main(["finalize", "--run", str(tmp_path), "--legacy-patina", "--no-patina"]) == 4
