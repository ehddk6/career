from __future__ import annotations

import json
from pathlib import Path

from career_pipeline.__main__ import build_parser, main
from career_pipeline.golden_path import GoldenPathError
from career_pipeline.workflow import migration_plan


def _run(tmp_path: Path, name: str = "sample") -> Path:
    root = tmp_path / "workspace"
    run = root / "career_runs" / name
    run.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps(
            {
                "quality_mode": "v2",
                "strict_quality": True,
                "root": str(root),
                "status": "ready_for_research",
                "issues": [{"code": "missing_research"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return run


def test_parser_exposes_workflow_without_changing_existing_status_contract():
    parser = build_parser()
    legacy = parser.parse_args(["status", "--input", "readiness.json"])
    resume = parser.parse_args(
        [
            "workflow",
            "resume",
            "--run",
            "career_runs/sample",
            "--system-benchmark",
            "report",
        ]
    )
    migrate = parser.parse_args(
        ["workflow", "migrate-plan", "--runs-root", "career_runs", "--format", "json"]
    )

    assert legacy.command == "status"
    assert resume.workflow_command == "resume"
    assert resume.writer_strategy == "nrs_v2"
    assert resume.system_benchmark == "report"
    assert migrate.workflow_command == "migrate-plan"
    assert migrate.format == "json"


def test_workflow_start_accepts_separate_question_source():
    parser = build_parser()
    start = parser.parse_args(
        [
            "workflow",
            "start",
            "--workspace",
            "workspace",
            "--target",
            "기관 행정",
            "--draft",
            "application.docx",
            "--posting",
            "https://official.example.go.kr/posting.pdf",
            "--question-source",
            "https://official.example.go.kr/form.pdf",
            "--profile",
            "profile.json",
        ]
    )

    assert start.question_source == "https://official.example.go.kr/form.pdf"


def test_workflow_status_is_read_only_and_reports_stage_hashes(tmp_path, capsys):
    run = _run(tmp_path)
    manifest = {
        "status": "waiting_for_research",
        "next_action": "공식 근거를 확인합니다.",
        "status_details": {"reasons": ["required_research_coverage_incomplete"]},
        "stages": {
            "research": {
                "status": "waiting",
                "input_fingerprint": "a" * 64,
                "outputs": {"04_공식근거.json": None},
            }
        },
    }
    manifest_path = run / "13_골든패스.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in (run / "run.json", manifest_path)}

    assert main(["workflow", "status", "--run", str(run), "--format", "json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "waiting_for_research"
    assert payload["current_stage"] == "research"
    assert payload["input_sha256"] == "a" * 64
    assert payload["output_sha256"] == {"04_공식근거.json": None}
    assert set(payload["blocker_codes"]) == {
        "missing_research",
        "required_research_coverage_incomplete",
    }
    assert {path.name: path.read_bytes() for path in (run / "run.json", manifest_path)} == before


def test_migration_plan_is_read_only_and_marks_only_strict_v2_runs_resumable(tmp_path):
    candidate = _run(tmp_path, "candidate")
    legacy = _run(tmp_path, "legacy")
    legacy_state = json.loads((legacy / "run.json").read_text(encoding="utf-8"))
    legacy_state["quality_mode"] = "v1"
    (legacy / "run.json").write_text(json.dumps(legacy_state), encoding="utf-8")
    corrupt = tmp_path / "workspace" / "career_runs" / "corrupt"
    corrupt.mkdir()
    (corrupt / "run.json").write_text("{", encoding="utf-8")
    before = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in (candidate / "run.json", legacy / "run.json", corrupt / "run.json")
    }

    plan = migration_plan(tmp_path / "workspace" / "career_runs")
    rows = {Path(row["run_dir"]).name: row for row in plan["runs"]}

    assert plan["schema_version"] == "career-pipeline-workflow-migration-plan-v1"
    assert rows["candidate"]["classification"] == "resume_candidate"
    assert rows["candidate"]["recommended_command"].endswith(f'--run "{candidate}"')
    assert "05_NRS_서사선택.json" in rows["candidate"]["missing_artifacts"]
    assert rows["legacy"]["classification"] == "incompatible"
    assert "quality_mode_not_v2" in rows["legacy"]["reason_codes"]
    assert rows["corrupt"]["reason_codes"] == ["invalid_run_json"]
    assert {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in (candidate / "run.json", legacy / "run.json", corrupt / "run.json")
    } == before


def test_workflow_resume_uses_converged_path_and_report_benchmark(monkeypatch, tmp_path, capsys):
    import career_pipeline.workflow as workflow

    run = _run(tmp_path)
    calls: list[object] = []

    def advance(value, *, config):
        calls.append((value, config.writer_strategy))
        return {"status": "complete", "next_action": "done", "run_dir": str(value)}

    monkeypatch.setattr(workflow, "advance_converged_golden_path", advance)
    monkeypatch.setattr(
        workflow,
        "benchmark_run",
        lambda value: {
            "summary": {"mean_unsafe_detection_rate": 1, "mean_benign_invariance_rate": 1}
        },
    )

    assert main(
        [
            "workflow",
            "resume",
            "--run",
            str(run),
            "--system-benchmark",
            "report",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == [(run, "nrs_v2")]
    assert payload["status"] == "complete"
    assert payload["system_benchmark"]["status"] == "passed"


def test_workflow_reports_golden_path_errors_without_secondary_name_error(
    monkeypatch, tmp_path, capsys
):
    import career_pipeline.workflow as workflow

    run = _run(tmp_path)
    monkeypatch.setattr(
        workflow,
        "advance_converged_golden_path",
        lambda value, *, config: (_ for _ in ()).throw(
            GoldenPathError("writer backend unavailable")
        ),
    )

    assert main(["workflow", "resume", "--run", str(run)]) == 4
    assert capsys.readouterr().out.strip() == "writer backend unavailable"


def test_workflow_required_benchmark_returns_review_required(monkeypatch, tmp_path, capsys):
    import career_pipeline.workflow as workflow

    run = _run(tmp_path)
    monkeypatch.setattr(
        workflow,
        "advance_converged_golden_path",
        lambda value, *, config: {"status": "complete", "next_action": "done", "run_dir": str(value)},
    )
    monkeypatch.setattr(
        workflow,
        "benchmark_run",
        lambda value: {
            "summary": {"mean_unsafe_detection_rate": 0.5, "mean_benign_invariance_rate": 1}
        },
    )

    assert main(
        [
            "workflow",
            "resume",
            "--run",
            str(run),
            "--system-benchmark",
            "required",
        ]
    ) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "review_required"
    assert payload["system_benchmark"]["status"] == "failed"
