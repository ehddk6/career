"""Integrate evidence, research intelligence, strategy priors, and Deep Writer.

Confirmed experience and coverage-approved official research remain the only
factual authority. Strategy priors influence argument search but never authorize
facts. Company research is compiled and gated before prose generation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .answer_blueprint import render_blueprint_markdown
from .deep_writer import DeepWriterError, generate_deep_draft, subprocess_model_runner
from .narrative_compiler import compile_run_blueprint
from .research_router import route_research_into_blueprint
from .research_workspace import assert_research_ready
from .state import write_json
from .strategy_prior import build_strategy_prior, render_strategy_prior_markdown, strategy_prior_for_stage

ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]
PRIOR_JSON = "05_통합전략선행정보.json"
PRIOR_MD = "05_통합전략선행정보.md"
REPORT_JSON = "05_통합논증검색_검증.json"


def _prefix(stage: str, prior: Mapping[str, Any]) -> str:
    return (
        "<strategy_prior_context>\n"
        "AUTHORITY RULE: this context is STRATEGY ONLY. It cannot authorize any applicant fact, "
        "number, date, motive, result, company fact, or causal claim. The blueprint's confirmed "
        "experience claims and coverage-approved official research remain authoritative. If this context conflicts "
        "with blueprint evidence, ignore it. Never copy legacy or YouTube wording. Use it only for "
        "argument structure, emphasis, candidate comparison, anti-repetition, and review. Historical "
        "outcomes are diagnostics, never hiring probability.\n"
        + json.dumps(strategy_prior_for_stage(prior, stage), ensure_ascii=False, separators=(",", ":"))
        + "\n</strategy_prior_context>\n"
    )


def strategy_aware_runner(prior: Mapping[str, Any], base_runner: ModelRunner) -> ModelRunner:
    def run(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any] | str:
        return base_runner(stage, _prefix(stage, prior) + prompt, model_id, timeout_ms)
    return run


def _routed_packet(run_dir: Path, research_report: Mapping[str, Any]) -> dict[str, Any] | None:
    state_path = run_dir / "run.json"
    if not state_path.is_file():
        return None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, Mapping) or not state.get("questions"):
        return None
    packet = compile_run_blueprint(run_dir)
    routed = route_research_into_blueprint(packet, research_report)
    write_json(run_dir / "05_답변설계도.json", routed)
    (run_dir / "05_답변설계도.md").write_text(
        render_blueprint_markdown(routed), encoding="utf-8"
    )
    return routed


def generate_integrated_draft(
    run_dir: Path,
    *,
    writer_model_id: str | None = None,
    judge_model_ids: Sequence[str] = (),
    route_count: int = 3,
    prose_realisations: int = 2,
    timeout_ms: int = 300_000,
    surface_preference_profile_path: Path | None = None,
    semantic_preference_profile_path: Path | None = None,
    runner: ModelRunner = subprocess_model_runner,
) -> tuple[list[Any], dict[str, Any]]:
    run_dir = run_dir.resolve()
    try:
        research_report = assert_research_ready(run_dir)
    except ValueError as error:
        raise DeepWriterError(str(error)) from error
    packet = _routed_packet(run_dir, research_report)

    prior = build_strategy_prior(run_dir)
    write_json(run_dir / PRIOR_JSON, prior)
    (run_dir / PRIOR_MD).write_text(render_strategy_prior_markdown(prior), encoding="utf-8")
    responses, report = generate_deep_draft(
        run_dir,
        packet=packet,
        writer_model_id=writer_model_id,
        judge_model_ids=judge_model_ids,
        route_count=route_count,
        prose_realisations=prose_realisations,
        timeout_ms=timeout_ms,
        surface_preference_profile_path=surface_preference_profile_path,
        semantic_preference_profile_path=semantic_preference_profile_path,
        runner=strategy_aware_runner(prior, runner),
    )
    integrated = dict(report)
    integrated["schema_version"] = max(3, int(report.get("schema_version", 1)))
    integrated["architecture"] = "integrated_research_to_argument_search_v3"
    integrated["upstream_pipeline_contract"] = {
        "experience_pipeline": "preserved_and_authoritative",
        "matching_pipeline": "preserved",
        "official_research_pipeline": "coverage_gated_and_authoritative",
        "research_requirement_compiler": "enabled",
        "research_conflict_resolution": "enabled",
        "research_argument_router": "enabled",
        "narrative_compiler": "preserved_as_blueprint_layer",
        "deep_writer": "preserved_as_argument_search_engine",
        "finalize": "preserved_as_validation_rendering_interview_boundary",
    }
    coverage = research_report.get("coverage", {}) if isinstance(research_report.get("coverage"), Mapping) else {}
    conflicts = research_report.get("conflicts", {}) if isinstance(research_report.get("conflicts"), Mapping) else {}
    registry = research_report.get("registry", {}) if isinstance(research_report.get("registry"), Mapping) else {}
    integrated["research_intelligence"] = {
        "plan_id": research_report.get("plan", {}).get("plan_id") if isinstance(research_report.get("plan"), Mapping) else None,
        "coverage_status": coverage.get("status"),
        "coverage_ratio": coverage.get("coverage_ratio"),
        "stop_research": coverage.get("stop_research"),
        "required_slots": coverage.get("required_slots"),
        "covered_required_slots": coverage.get("covered_required_slots"),
        "unresolved_conflicts": conflicts.get("unresolved_groups", []),
        "official_domains": registry.get("official_domains", []),
        "factual_authority": "coverage_approved_official_claims_only",
    }
    youtube = prior.get("youtube", {}) if isinstance(prior.get("youtube"), Mapping) else {}
    legacy = prior.get("legacy_writing_pipeline", {}) if isinstance(prior.get("legacy_writing_pipeline"), Mapping) else {}
    history = prior.get("historical_run_usage", {}) if isinstance(prior.get("historical_run_usage"), Mapping) else {}
    outcomes = prior.get("historical_outcomes", {}) if isinstance(prior.get("historical_outcomes"), Mapping) else {}
    integrated["strategy_prior"] = {
        "artifact": PRIOR_JSON,
        "policy": prior.get("policy"),
        "youtube_status": youtube.get("status"),
        "youtube_freshness": youtube.get("freshness", {}).get("status") if isinstance(youtube.get("freshness"), Mapping) else None,
        "target_specific_youtube": youtube.get("target_specific", {}).get("status") if isinstance(youtube.get("target_specific"), Mapping) else None,
        "legacy_question_strategy_used": bool(legacy.get("general_rules") or legacy.get("per_question")),
        "historical_run_usage_used": history.get("status") == "available",
        "historical_outcomes_status": outcomes.get("status"),
        "raw_historical_prose_forwarded": False,
        "factual_authority_granted": False,
    }
    return responses, integrated


def write_integrated_draft(run_dir: Path, *, output: Path | None = None, force: bool = False, **kwargs: Any) -> tuple[Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    responses, report = generate_integrated_draft(run_dir, **kwargs)
    output = output or run_dir / "draft.json"
    if not output.is_absolute():
        output = run_dir / output
    output = output.resolve()
    if output.exists() and not force:
        raise DeepWriterError(f"output already exists: {output}; use --force")
    write_json(output, [asdict(item) for item in responses])
    write_json(run_dir / REPORT_JSON, report)
    write_json(run_dir / "05_논증검색_검증.json", report)
    return output, report


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Integrate company research, career strategy, and Deep Writer")
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--writer-model-id")
    p.add_argument("--judge-model-id", action="append", default=[])
    p.add_argument("--routes", type=int, default=3)
    p.add_argument("--prose-realisations", type=int, default=2)
    p.add_argument("--timeout-ms", type=int, default=300_000)
    p.add_argument("--surface-preference-profile", type=Path)
    p.add_argument("--semantic-preference-profile", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--force", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output, report = write_integrated_draft(
        args.run,
        output=args.output,
        force=args.force,
        writer_model_id=args.writer_model_id,
        judge_model_ids=tuple(args.judge_model_id),
        route_count=args.routes,
        prose_realisations=args.prose_realisations,
        timeout_ms=args.timeout_ms,
        surface_preference_profile_path=args.surface_preference_profile,
        semantic_preference_profile_path=args.semantic_preference_profile,
    )
    print(output)
    print(args.run.resolve() / REPORT_JSON)
    return 0 if report.get("deterministic_validation", {}).get("status") == "passed" and report.get("semantic_validation", {}).get("status") == "passed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
