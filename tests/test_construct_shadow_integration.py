from pathlib import Path
from types import SimpleNamespace

import career_pipeline.deep_writer as deep_writer
import career_pipeline.golden_path_converged as converged
import career_pipeline.integrated_writer as integrated_writer


def _write_json(path: Path, value):
    import json

    path.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def test_converged_writer_emits_construct_shadow_without_injecting_it_into_writer_prior(
    tmp_path: Path,
    monkeypatch,
):
    run = tmp_path / "run"
    run.mkdir()
    _write_json(
        run / "run.json",
        {
            "target": "테스트공사 행정",
            "questions": [
                {
                    "index": 1,
                    "prompt": "행정 직무에서 본인의 강점을 설명해 주십시오.",
                }
            ],
        },
    )
    _write_json(
        run / "00_채용공고분석.json",
        {
            "target": "테스트공사 행정",
            "source": {"content_sha256": "a" * 64},
            "duties": [
                "신청 서류를 공식 기준과 원문에 대조해 누락과 예외를 검토한다."
            ],
            "competencies": [],
            "requirements": [],
            "preferred": [],
            "constraints": [],
        },
    )
    _write_json(
        run / "02_확정경험원장.json",
        {
            "experiences": [
                {
                    "experience_id": "exp-1",
                    "status": "confirmed",
                    "title": "행정지원",
                    "role": "자료 검토",
                    "situation": "",
                    "actions": [],
                    "outcomes": [],
                    "competencies": [],
                    "claims": [
                        {
                            "field": "experience_summary",
                            "normalized_value": "원문과 입력값을 대조해 누락을 구분했습니다.",
                            "status": "confirmed",
                            "claim_id": "clm-1",
                            "verification": {
                                "method": "direct_source",
                                "contribution": "contributed",
                            },
                        }
                    ],
                }
            ]
        },
    )
    _write_json(run / "04_공식근거.json", [])

    observed = {}

    def base_write_draft(run_dir, config):
        observed["prior"] = integrated_writer.strategy_prior_for_stage(
            {"fixture": True},
            "deep_prose_generate_q1_1",
        )
        return {"status": "fixture"}

    base = SimpleNamespace(
        research_gate=lambda run_dir: {},
        strategy_fingerprint=lambda run_dir: "base",
        write_draft=base_write_draft,
        interview_gate=lambda run_dir, draft: [],
        finalize=lambda run_dir, config: {},
        resolve_final_draft=lambda run_dir: run_dir / "draft.json",
        compile_interview=lambda run_dir: {},
        audit=lambda run_dir: {},
    )
    monkeypatch.setattr(converged, "_BASE_DEFAULT_SERVICES", lambda: base)
    monkeypatch.setattr(
        integrated_writer,
        "strategy_prior_for_stage",
        lambda packet, stage: {"existing_prior": True},
    )
    monkeypatch.setattr(
        deep_writer,
        "_generate_prose",
        lambda *args, **kwargs: {},
    )

    services = converged.converged_services()
    report = services.write_draft(run, SimpleNamespace())

    assert (run / "04_직무구성개념.json").is_file()
    assert (run / "04_직무구성개념.md").is_file()
    assert (run / "05_구성개념근거매트릭스.json").is_file()
    assert (run / "05_구성개념근거매트릭스.md").is_file()

    assert "evidence_portfolio" in observed["prior"]
    assert "construct_shadow" not in observed["prior"]
    assert report["construct_shadow"]["decision_effect"] == "none_shadow_mode"
    assert report["construct_shadow"]["artifact"] == "05_구성개념근거매트릭스.json"
