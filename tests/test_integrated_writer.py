import json
from pathlib import Path

import career_pipeline.integrated_writer as iw


def test_integrated_writer_injects_strategy_prior_without_replacing_deep_writer(tmp_path: Path, monkeypatch):
    run = tmp_path / "career_runs" / "current"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"root": str(tmp_path), "target": "테스트기관"}, ensure_ascii=False), encoding="utf-8")
    (run / "02_확정경험원장.json").write_text('{"experiences":[]}', encoding="utf-8")
    (run / "03_경험직무매칭.json").write_text('[]', encoding="utf-8")
    (run / "04_공식근거.json").write_text('[]', encoding="utf-8")
    captured = {}

    def fake_deep_writer(run_dir, **kwargs):
        captured["run_dir"] = run_dir
        captured.update(kwargs)
        kwargs["runner"]("deep_route_plan_q1", "ORIGINAL_DEEP_WRITER_PROMPT", "writer", 1000)
        return [], {
            "schema_version": 1,
            "architecture": "evidence_to_argument_search_v1",
            "deterministic_validation": {"status": "passed"},
            "semantic_validation": {"status": "passed"},
        }

    prompts = []
    def base_runner(stage, prompt, model_id, timeout_ms):
        prompts.append((stage, prompt))
        return {}

    monkeypatch.setattr(iw, "generate_deep_draft", fake_deep_writer)
    responses, report = iw.generate_integrated_draft(run, writer_model_id="writer", runner=base_runner)
    assert responses == []
    assert captured["run_dir"] == run.resolve()
    assert captured["prose_strategy"] == "nrs_v2"
    assert prompts and prompts[0][0] == "deep_route_plan_q1"
    assert "<strategy_prior_context>" in prompts[0][1]
    assert "STRATEGY ONLY" in prompts[0][1]
    assert "ORIGINAL_DEEP_WRITER_PROMPT" in prompts[0][1]
    assert report["upstream_pipeline_contract"]["experience_pipeline"] == "preserved_and_authoritative"
    assert report["upstream_pipeline_contract"]["deep_writer"] == "preserved_as_argument_search_engine"
    assert report["strategy_prior"]["raw_historical_prose_forwarded"] is False
    assert (run / "05_통합전략선행정보.json").is_file()


def test_nrs_stages_do_not_receive_strategy_prior():
    seen = []

    def base_runner(stage, prompt, model_id, timeout_ms):
        seen.append(prompt)
        return {}

    runner = iw.strategy_aware_runner({"policy": "fixture"}, base_runner)
    runner("nrs_production_generate_q1_1", "LEAN_NRS_PROMPT", "writer", 1000)

    assert seen == ["LEAN_NRS_PROMPT"]


def test_integrated_writer_resolves_default_backend_before_context_wrapper(
    tmp_path: Path, monkeypatch
):
    import career_pipeline.nrs_paired_reconstruction as nrs

    run = tmp_path / "career_runs" / "current"
    run.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps({"root": str(tmp_path), "target": "테스트기관"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run / "02_확정경험원장.json").write_text('{"experiences":[]}', encoding="utf-8")
    (run / "03_경험직무매칭.json").write_text('[]', encoding="utf-8")
    (run / "04_공식근거.json").write_text('[]', encoding="utf-8")
    captured = {}
    backend_calls = []

    def fake_deep_writer(run_dir, **kwargs):
        captured.update(kwargs)
        kwargs["runner"](
            "deep_route_plan_q1",
            "PROMPT",
            iw.DEFAULT_BACKEND_SENTINEL,
            1000,
        )
        return [], {
            "schema_version": 1,
            "deterministic_validation": {"status": "passed"},
            "semantic_validation": {"status": "passed"},
        }

    def default_runner(stage, prompt, model_id, timeout_ms):
        backend_calls.append((stage, model_id, prompt))
        return {}

    monkeypatch.setattr(iw, "resolve_model", lambda _: type("Model", (), {"model_id": None})())
    monkeypatch.setattr(iw, "generate_deep_draft", fake_deep_writer)
    monkeypatch.setattr(
        nrs,
        "resolve_writer_backend",
        lambda: {"command_available": True, "writer_backend": "codex_cli_default"},
    )
    monkeypatch.setattr(nrs, "default_backend_runner", default_runner)

    iw.generate_integrated_draft(run)

    assert captured["writer_model_id"] == iw.DEFAULT_BACKEND_SENTINEL
    assert backend_calls[0][1] == iw.DEFAULT_BACKEND_SENTINEL
    assert "<strategy_prior_context>" in backend_calls[0][2]
