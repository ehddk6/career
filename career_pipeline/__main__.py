"""career_pipeline CLI 진입점. prepare, finalize, profile, posting 서브커맨드를 제공합니다."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence

from .audit import run_quality_audit
from .extractors import extract_path
from .inventory import build_inventory
from .orchestrator import finalize_run, prepare_run
from .posting_loader import (
    PostingSourceError,
    load_posting_source,
    write_posting_snapshot,
)
from .posting_parser import parse_posting, render_posting_analysis
from .profile_builder import (
    build_experience_review_queue,
    build_proposed_ledger,
    render_experience_review_queue,
    render_proposed_ledger_review,
)
from .profile_confirmation import confirm_ledger, write_review_template
from .portfolio import build_portfolio, write_portfolio
from .profile_refresh import refresh_profile, write_refresh_outputs
from .profile_schema import (
    ProfileValidationError,
    ledger_to_dict,
    load_ledger,
)
from .state import write_json


PATINA_BACKENDS = {
    "codex-cli",
    "openai-http",
    "claude-cli",
    "gemini-cli",
    "kimi-cli",
}


def _patina_backend_chain(value: str) -> str:
    backends = [item.strip() for item in value.split(",") if item.strip()]
    invalid = [item for item in backends if item not in PATINA_BACKENDS]
    if not backends or invalid:
        raise argparse.ArgumentTypeError(
            "invalid Patina backend chain: " + ", ".join(invalid or [value])
        )
    return ",".join(backends)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--root", required=True)
    prepare.add_argument("--target", required=True)
    prepare.add_argument("--draft", required=True)
    prepare.add_argument("--posting")
    prepare.add_argument("--run-name")
    prepare.add_argument("--resume")
    prepare.add_argument("--profile")
    prepare.add_argument("--official-domain", action="append", default=[])
    prepare.add_argument("--research-domain", action="append", default=[])
    prepare.add_argument("--official-source", action="store_true")

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run", required=True)
    finalize.add_argument("--no-copyeditor", action="store_true")
    finalize.add_argument("--copyeditor-timeout-ms", type=int, default=180_000)
    finalize.add_argument("--no-patina", action="store_true")
    finalize.add_argument(
        "--patina-backend",
        type=_patina_backend_chain,
        default="codex-cli",
    )
    finalize.add_argument("--patina-timeout-ms", type=int, default=180_000)
    finalize.add_argument("--patina-max-retries", type=int, default=1)
    finalize.add_argument("--patina-voice-sample")
    finalize.add_argument("--patina-ai-threshold", type=int, default=30)
    finalize.add_argument("--no-patina-score", action="store_true")

    profile = subparsers.add_parser("profile")
    profile_commands = profile.add_subparsers(
        dest="profile_command", required=True
    )

    profile_build = profile_commands.add_parser("build")
    profile_build.add_argument("--root", required=True)
    profile_build.add_argument("--output", required=True)

    profile_refresh = profile_commands.add_parser("refresh")
    profile_refresh.add_argument("--root", required=True)
    profile_refresh.add_argument("--profile", required=True)

    profile_validate = profile_commands.add_parser("validate")
    profile_validate.add_argument("--profile", required=True)

    profile_confirm = profile_commands.add_parser("confirm")
    profile_confirm.add_argument("--proposed", required=True)
    profile_confirm.add_argument("--decisions", required=True)
    profile_confirm.add_argument("--output", required=True)

    portfolio = subparsers.add_parser("portfolio")
    portfolio_commands = portfolio.add_subparsers(dest="portfolio_command", required=True)
    portfolio_build = portfolio_commands.add_parser("build")
    portfolio_build.add_argument("--root", required=True)
    portfolio_build.add_argument("--output-dir", required=True)

    posting = subparsers.add_parser("posting")
    posting_commands = posting.add_subparsers(
        dest="posting_command", required=True
    )
    posting_analyze = posting_commands.add_parser("analyze")
    posting_analyze.add_argument("--target", required=True)
    posting_analyze.add_argument("--source", required=True)
    posting_analyze.add_argument("--official-source", action="store_true")
    posting_analyze.add_argument("--official-domain", action="append", default=[])
    posting_analyze.add_argument("--output", required=True)

    audit = subparsers.add_parser("audit")
    audit.add_argument("--run", required=True)
    return parser


def _extract_workspace(root: Path):
    sources = build_inventory(root)
    has_dedicated_experience_folder = any(
        Path(source.relative_path).parts[:1] == ("경험정리",)
        for source in sources
    )
    return [
        extract_path(source)
        for source in sources
        if source.status == "use"
        and (
            not has_dedicated_experience_folder
            or Path(source.relative_path).parts[:1] == ("경험정리",)
        )
    ]


def run_profile_build(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    output = Path(args.output)
    ledger = build_proposed_ledger(root, _extract_workspace(root))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(ledger_to_dict(ledger), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output.with_suffix(".md").write_text(
        render_proposed_ledger_review(ledger), encoding="utf-8"
    )
    queue = build_experience_review_queue(ledger)
    output.with_name("experience_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output.with_name("experience_review_queue.md").write_text(
        render_experience_review_queue(queue), encoding="utf-8"
    )
    write_review_template(ledger, output.with_name("experience_review_decisions.csv"))
    print(output)
    return 0


def run_profile_refresh(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    profile_path = Path(args.profile)
    confirmed = load_ledger(profile_path)
    review = refresh_profile(root, confirmed)
    proposed = build_proposed_ledger(root, _extract_workspace(root))
    write_refresh_outputs(profile_path.parent, review, proposed)
    print(profile_path.parent / "profile_review.md")
    return 2 if any(item.status != "unchanged" for item in review.items) else 0


def run_profile_validate(args: argparse.Namespace) -> int:
    try:
        load_ledger(Path(args.profile))
    except (OSError, ProfileValidationError) as error:
        print(error)
        return 4
    print("valid")
    return 0


def run_profile_confirm(args: argparse.Namespace) -> int:
    try:
        confirmed, counts = confirm_ledger(load_ledger(Path(args.proposed)), Path(args.decisions))
    except (OSError, ProfileValidationError) as error:
        print(error)
        return 4
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger_to_dict(confirmed), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output.parent / "profile_confirmation_report.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


def run_portfolio_build(args: argparse.Namespace) -> int:
    payload = build_portfolio(Path(args.root).resolve())
    output = Path(args.output_dir)
    write_portfolio(payload, output)
    print(output)
    return 0


def run_posting_analyze(args: argparse.Namespace) -> int:
    is_url = args.source.lower().startswith(("http://", "https://"))
    if is_url and args.official_source:
        raise PostingSourceError("--official-source is only valid for local files")
    if not is_url and args.official_domain:
        raise PostingSourceError("--official-domain is only valid for URL sources")
    loaded = load_posting_source(
        args.source,
        official_source=args.official_source,
        official_domains=tuple(args.official_domain),
    )
    analysis = parse_posting(loaded, target=args.target)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_posting_snapshot(output, loaded)
    write_json(output / "00_채용공고분석.json", asdict(analysis))
    (output / "00_채용공고분석.md").write_text(
        render_posting_analysis(analysis), encoding="utf-8"
    )
    print(output)
    required_missing = {"organization", "role", "duties"}.intersection(
        analysis.uncertainties
    )
    return 2 if analysis.source.official_status == "unverified" or required_missing else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "posting":
        try:
            return run_posting_analyze(args)
        except (OSError, PostingSourceError) as error:
            print(error)
            return 4
    if args.command == "portfolio":
        return run_portfolio_build(args)
    if args.command == "audit":
        try:
            audit = run_quality_audit(Path(args.run))
        except (OSError, ValueError) as error:
            print(error)
            return 4
        print(f"{audit['score']}/100 {audit['recommendation']}")
        return 0 if int(audit["score"]) >= 90 else 2
    if args.command == "profile":
        if args.profile_command == "build":
            return run_profile_build(args)
        if args.profile_command == "refresh":
            try:
                return run_profile_refresh(args)
            except (OSError, ProfileValidationError) as error:
                print(error)
                return 4
        if args.profile_command == "confirm":
            return run_profile_confirm(args)
        return run_profile_validate(args)
    if args.command == "prepare":
        state = prepare_run(
            Path(args.root),
            args.target,
            Path(args.draft),
            args.posting,
            args.run_name,
            Path(args.resume) if args.resume else None,
            profile=Path(args.profile) if args.profile else None,
            official_domains=tuple(args.official_domain),
            research_domains=tuple(args.research_domain),
            official_source=args.official_source,
        )
        print(state["run_dir"])
        return 2 if state["status"].startswith("blocked_") else 0
    state = finalize_run(
        Path(args.run),
        copyedit=not args.no_copyeditor,
        copyeditor_timeout_ms=args.copyeditor_timeout_ms,
        humanize=not args.no_patina,
        patina_backend=args.patina_backend,
        patina_timeout_ms=args.patina_timeout_ms,
        patina_max_retries=args.patina_max_retries,
        patina_voice_sample=(
            Path(args.patina_voice_sample).resolve()
            if args.patina_voice_sample
            else None
        ),
        patina_ai_threshold=args.patina_ai_threshold,
        patina_score=not args.no_patina_score,
    )
    print(state["status"])
    if state["status"] == "complete":
        return 0
    return 2 if state["status"].startswith("blocked_") else 3


if __name__ == "__main__":
    raise SystemExit(main())
