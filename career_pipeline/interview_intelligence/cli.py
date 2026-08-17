"""CLI for structured-adaptive interview intelligence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from ..interview_calibration import (
    calibrated_select_next_question,
    update_calibration,
    write_calibration_artifact,
)
from ..state import write_json
from .core import _load_plan, render_question_bank_markdown, write_interview_plan
from .evaluation import evaluate_transcript, update_weakness_profile
from .schema import EVALUATION_JSON, InterviewIntelligenceError, _load_state, _read_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Structured-adaptive interview intelligence")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="compile claim-defense graph and question bank")
    compile_parser.add_argument("--run", required=True, type=Path)
    compile_parser.add_argument("--draft", type=Path)

    evaluate_parser = sub.add_parser("evaluate", help="evaluate a mock-interview transcript and select the next probe")
    evaluate_parser.add_argument("--run", required=True, type=Path)
    evaluate_parser.add_argument("--plan", type=Path)
    evaluate_parser.add_argument("--transcript", required=True, type=Path)
    evaluate_parser.add_argument("--judge-model-id", action="append", default=[])
    evaluate_parser.add_argument("--timeout-ms", type=int, default=180_000)
    evaluate_parser.add_argument("--update-profile", action="store_true")
    return parser


def _root_from_state(run_dir: Path) -> Path | None:
    state = _load_state(run_dir)
    root_value = state.get("root")
    return Path(root_value).resolve() if isinstance(root_value, str) and root_value else None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_dir = args.run.resolve()
    root = _root_from_state(run_dir)
    if args.command == "compile":
        json_path, md_path, plan = write_interview_plan(run_dir, draft_path=args.draft)
        _, plan = write_calibration_artifact(run_dir, plan, root)
        write_json(json_path, plan)
        md_path.write_text(render_question_bank_markdown(plan), encoding="utf-8")
        print(json_path)
        print(md_path)
        print(json.dumps(plan.get("summary", {}), ensure_ascii=False))
        return 0

    plan = _load_plan(run_dir, args.plan)
    transcript = _read_json(args.transcript)
    if not isinstance(transcript, list):
        raise InterviewIntelligenceError("transcript must be an array")
    runner = None
    if args.judge_model_id:
        from ..deep_writer import subprocess_model_runner

        runner = subprocess_model_runner
    evaluation = evaluate_transcript(
        plan,
        transcript,
        judge_model_ids=tuple(args.judge_model_id),
        runner=runner,
        timeout_ms=args.timeout_ms,
    )
    profile_paths: list[str] = []
    if args.update_profile:
        if root is None:
            raise InterviewIntelligenceError("run.json.root is required for --update-profile")
        profile_paths.append(str(update_weakness_profile(root, evaluation)))
        profile_paths.append(str(update_calibration(root, plan, evaluation)))

    session = {
        "turns": [
            {"question_id": turn.get("question_id")}
            for turn in evaluation.get("turns", [])
            if isinstance(turn, Mapping)
        ],
        "weak_dimensions": list(
            evaluation.get("summary", {}).get("weak_dimensions", [])
            if isinstance(evaluation.get("summary"), Mapping)
            else []
        ),
    }
    next_question = calibrated_select_next_question(plan, session, root)
    evaluation["next_question"] = next_question
    evaluation["calibration"] = {
        "enabled": True,
        "profile_updated": bool(args.update_profile),
        "profile_paths": profile_paths,
        "quantity": "diagnostic_yield_proxy_not_hiring_probability",
    }
    output = run_dir / EVALUATION_JSON
    write_json(output, evaluation)
    print(output)
    for path in profile_paths:
        print(path)
    if isinstance(next_question, Mapping):
        print(
            json.dumps(
                {
                    "next_question_id": next_question.get("question_id"),
                    "prompt": next_question.get("prompt"),
                    "selection_reason": next_question.get("selection_reason"),
                },
                ensure_ascii=False,
            )
        )
    return 0
