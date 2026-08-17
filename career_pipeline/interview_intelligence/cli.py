"""CLI for structured-adaptive interview intelligence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from ..state import write_json
from .core import _load_plan, write_interview_plan
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_dir = args.run.resolve()
    if args.command == "compile":
        json_path, md_path, plan = write_interview_plan(run_dir, draft_path=args.draft)
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
    output = run_dir / EVALUATION_JSON
    write_json(output, evaluation)
    print(output)
    if args.update_profile:
        state = _load_state(run_dir)
        root_value = state.get("root")
        if not isinstance(root_value, str) or not root_value:
            raise InterviewIntelligenceError("run.json.root is required for --update-profile")
        print(update_weakness_profile(Path(root_value), evaluation))
    next_question = evaluation.get("next_question")
    if isinstance(next_question, Mapping):
        print(json.dumps({"next_question_id": next_question.get("question_id"), "prompt": next_question.get("prompt")}, ensure_ascii=False))
    return 0
