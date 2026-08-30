"""Single CLI workflow surface for the converged career-pipeline path.

This module deliberately keeps migration planning and status inspection read-only.
Only ``workflow start`` and ``workflow resume`` may create or update run artifacts.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import golden_path as gp
from .golden_path import GoldenPathError
from .golden_path_converged import (
    advance_converged_golden_path,
    start_converged_golden_path,
)
from .system_benchmark import benchmark_run


MIGRATION_PLAN_SCHEMA = "career-pipeline-workflow-migration-plan-v1"
GOLDEN_MANIFEST = "13_골든패스.json"

_MIGRATION_ARTIFACTS = (
    "00_채용공고분석.json",
    "02_확정경험원장.json",
    "03_경험직무매칭.json",
    "04_리서치계획.json",
    "04_리서치출처.json",
    "04_공식근거.json",
    "04_근거충돌.json",
    "04_근거커버리지.json",
    "04_리서치실행.json",
    "draft.json",
    "05_NRS_서사선택.json",
    "12_최종산출물.json",
    "08_면접대비팩.md",
    "08_면접지능설계.json",
    GOLDEN_MANIFEST,
    "14_시스템불변성벤치마크.json",
)


class WorkflowError(ValueError):
    """Raised when a read-only workflow command cannot inspect its input."""


def add_workflow_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    workflow = subparsers.add_parser(
        "workflow",
        help="run or inspect the content-addressed golden workflow",
    )
    commands = workflow.add_subparsers(dest="workflow_command", required=True)

    start = commands.add_parser("start")
    start.add_argument("--workspace", "--root", dest="workspace", required=True, type=Path)
    start.add_argument("--target", required=True)
    start.add_argument("--draft", required=True, type=Path)
    start.add_argument("--posting", required=True)
    start.add_argument("--question-source")
    start.add_argument("--profile", required=True, type=Path)
    start.add_argument("--run-name")
    start.add_argument("--official-domain", action="append", default=[])
    start.add_argument("--research-domain", action="append", default=[])
    start.add_argument("--official-source", action="store_true")
    gp.add_cli_arguments(start)

    resume = commands.add_parser("resume")
    resume.add_argument("--run", required=True, type=Path)
    resume.add_argument(
        "--system-benchmark",
        choices=("off", "report", "required"),
        default="off",
        help="off: skip; report: write a diagnostic report; required: return review_required on failure",
    )
    gp.add_cli_arguments(resume)

    status = commands.add_parser("status")
    status.add_argument("--run", required=True, type=Path)
    status.add_argument("--format", choices=("human", "json"), default="human")

    migrate_plan = commands.add_parser("migrate-plan")
    migrate_plan.add_argument("--runs-root", required=True, type=Path)
    migrate_plan.add_argument("--format", choices=("human", "json"), default="human")


def _read_mapping(path: Path, *, label: str, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise WorkflowError(f"{label} 파일이 없습니다: {path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkflowError(f"{label} 파일을 읽을 수 없습니다: {path}") from error
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} 파일은 JSON 객체여야 합니다: {path}")
    return value


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_name(manifest: Mapping[str, Any]) -> str | None:
    stages = manifest.get("stages")
    if not isinstance(stages, Mapping) or not stages:
        return None
    return str(next(reversed(stages)))


def _reason_codes(value: Any) -> set[str]:
    codes: set[str] = set()
    if isinstance(value, str) and value:
        codes.add(value)
    elif isinstance(value, Mapping):
        code = value.get("code")
        if isinstance(code, str) and code:
            codes.add(code)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            codes.update(_reason_codes(item))
    return codes


def workflow_status(run: Path) -> dict[str, Any]:
    """Return a status envelope without creating or changing any file."""

    run = run.resolve()
    state = _read_mapping(run / "run.json", label="run.json")
    manifest = _read_mapping(run / GOLDEN_MANIFEST, label=GOLDEN_MANIFEST, required=False)
    status = str(manifest.get("status") or state.get("status") or "not_started")
    next_action = manifest.get("next_action") or state.get("next_step") or "workflow resume으로 최신 게이트를 점검합니다."
    current_stage = _stage_name(manifest)
    stage = (
        manifest.get("stages", {}).get(current_stage, {})
        if current_stage and isinstance(manifest.get("stages"), Mapping)
        else {}
    )
    if not isinstance(stage, Mapping):
        stage = {}
    details = manifest.get("status_details", {})
    codes = _reason_codes(details.get("reasons") if isinstance(details, Mapping) else None)
    codes.update(_reason_codes(state.get("issues")))
    if str(state.get("blocked_stage", "")):
        codes.add(f"stage:{state['blocked_stage']}")
    outputs = stage.get("outputs")
    return {
        "schema_version": "career-pipeline-workflow-status-v1",
        "status": status,
        "next_action": str(next_action),
        "run_dir": str(run),
        "current_stage": current_stage,
        "blocker_codes": sorted(codes),
        "input_sha256": stage.get("input_fingerprint"),
        "output_sha256": dict(outputs) if isinstance(outputs, Mapping) else {},
    }


def _migration_classification(run: Path, state: Mapping[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if state.get("quality_mode") != "v2":
        reasons.append("quality_mode_not_v2")
    if state.get("strict_quality") is not True:
        reasons.append("strict_quality_disabled")
    root_value = state.get("root")
    if not isinstance(root_value, str) or not root_value.strip():
        reasons.append("workspace_root_missing")
        return "incompatible", reasons
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        reasons.append("workspace_root_not_found")
    expected_runs_root = root / "career_runs"
    if not run.is_relative_to(expected_runs_root):
        reasons.append("run_outside_workspace_career_runs")
    return ("resume_candidate" if not reasons else "incompatible"), reasons


def migration_plan(runs_root: Path) -> dict[str, Any]:
    """Inspect direct run children and report migration readiness without writes."""

    runs_root = runs_root.resolve()
    if not runs_root.is_dir():
        raise WorkflowError(f"runs root 디렉터리가 없습니다: {runs_root}")
    rows: list[dict[str, Any]] = []
    for run in sorted((path for path in runs_root.iterdir() if path.is_dir()), key=lambda path: path.name.casefold()):
        state_path = run / "run.json"
        if not state_path.is_file():
            continue
        try:
            state = _read_mapping(state_path, label="run.json")
        except WorkflowError:
            rows.append({
                "run_dir": str(run),
                "classification": "incompatible",
                "reason_codes": ["invalid_run_json"],
                "present_artifacts": {},
                "missing_artifacts": list(_MIGRATION_ARTIFACTS),
                "recommended_command": None,
            })
            continue
        classification, reasons = _migration_classification(run, state)
        present = {
            name: digest
            for name in _MIGRATION_ARTIFACTS
            if (digest := _sha256(run / name)) is not None
        }
        missing = [name for name in _MIGRATION_ARTIFACTS if name not in present]
        rows.append({
            "run_dir": str(run),
            "classification": classification,
            "reason_codes": reasons,
            "present_artifacts": present,
            "missing_artifacts": missing,
            "recommended_command": (
                f'career-pipeline workflow resume --run "{run}"'
                if classification == "resume_candidate"
                else None
            ),
        })
    return {
        "schema_version": MIGRATION_PLAN_SCHEMA,
        "runs_root": str(runs_root),
        "run_count": len(rows),
        "runs": rows,
    }


def _benchmark_result(run: Path, mode: str) -> dict[str, Any] | None:
    if mode == "off":
        return None
    try:
        report = benchmark_run(run)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"mode": mode, "status": "unavailable", "reason": str(error)}
    summary = report.get("summary", {}) if isinstance(report, Mapping) else {}
    passed = (
        isinstance(summary, Mapping)
        and summary.get("mean_unsafe_detection_rate", 0) >= 1
        and summary.get("mean_benign_invariance_rate", 0) >= 0.9
    )
    return {"mode": mode, "status": "passed" if passed else "failed", "summary": summary}


def _exit_code(status: str) -> int:
    if status == "complete":
        return 0
    if status.startswith("waiting_") or status == "review_required":
        return 2
    return 3


def _print_payload(payload: Mapping[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"상태: {payload['status']}")
    print(f"다음 작업: {payload['next_action']}")
    print(f"현재 단계: {payload['current_stage'] or '없음'}")
    codes = payload.get("blocker_codes", [])
    print(f"차단 코드: {', '.join(codes) if codes else '없음'}")


def _print_migration_plan(plan: Mapping[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    print(f"검사한 실행: {plan['run_count']}건")
    for row in plan["runs"]:
        reasons = ", ".join(row["reason_codes"]) or "없음"
        print(f"{Path(row['run_dir']).name}: {row['classification']} · {reasons}")


def run_workflow_command(args: argparse.Namespace) -> int:
    command = args.workflow_command
    if command == "status":
        payload = workflow_status(args.run)
        _print_payload(payload, args.format)
        return 0 if payload["status"] == "complete" else 2
    if command == "migrate-plan":
        plan = migration_plan(args.runs_root)
        _print_migration_plan(plan, args.format)
        return 0

    config = gp.config_from_namespace(args)
    if command == "start":
        result = start_converged_golden_path(
            root=args.workspace,
            target=args.target,
            draft=args.draft,
            posting=args.posting,
            question_source=args.question_source,
            profile=args.profile,
            run_name=args.run_name,
            official_domains=tuple(args.official_domain),
            research_domains=tuple(args.research_domain),
            official_source=args.official_source,
            config=config,
        )
        benchmark = None
    else:
        result = advance_converged_golden_path(args.run, config=config)
        benchmark = _benchmark_result(args.run.resolve(), args.system_benchmark)

    payload = {
        "status": result.get("status"),
        "next_action": result.get("next_action"),
        "run_dir": result.get("run_dir"),
    }
    if benchmark is not None:
        payload["system_benchmark"] = benchmark
        if args.system_benchmark == "required" and benchmark.get("status") != "passed":
            payload["status"] = "review_required"
            payload["next_action"] = "시스템 불변성 벤치마크 오류를 검토한 뒤 다시 실행합니다."
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return _exit_code(str(payload["status"] or ""))
