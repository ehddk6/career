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
    assert prompts and prompts[0][0] == "deep_route_plan_q1"
    assert "<strategy_prior_context>" in prompts[0][1]
    assert "STRATEGY ONLY" in prompts[0][1]
    assert "ORIGINAL_DEEP_WRITER_PROMPT" in prompts[0][1]
    assert report["upstream_pipeline_contract"]["experience_pipeline"] == "preserved_and_authoritative"
    assert report["upstream_pipeline_contract"]["deep_writer"] == "preserved_as_argument_search_engine"
    assert report["strategy_prior"]["raw_historical_prose_forwarded"] is False
    assert (run / "05_통합전략선행정보.json").is_file()
