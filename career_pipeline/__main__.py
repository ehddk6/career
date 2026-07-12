"""career_pipeline CLI 진입점. prepare, finalize, profile, posting 서브커맨드를 제공합니다."""
import argparse
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import sys
from typing import Sequence

from .audit import run_quality_audit
from .application_package import (
    ApplicationPackageError,
    build_application_package,
    load_application_package,
    materialize_package_values,
    persist_application_package,
)
from .eligibility import (
    EligibilityValidationError,
    applicant_profile_from_ledger,
    applicant_profile_to_dict,
    evaluate_eligibility,
    compare_postings,
    decision_from_dict,
    load_applicant_profile,
    load_posting_record,
    normalized_posting_content_sha256,
    posting_record_from_analysis,
    posting_record_to_dict,
    posting_record_from_dict,
)
from .discovery import (
    DiscoveryValidationError,
    add_discovery_source,
    discovery_source_from_dict,
    discovery_source_to_dict,
    load_discovery_sources,
    run_discovery,
)
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
from .models import DiscoverySource
from .form_adapter import (
    FixtureFormDriver,
    FormAdapterError,
    ReviewRequiredFormAdapter,
    write_form_result,
    load_form_result,
)
from .application_execution import (
    ApplicationExecutionError,
    approve_application,
    authorize_execution,
    load_review,
    write_workflow_artifact,
)
from .registry import PostingRegistry, RegistryError, queue_item_to_dict
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
    finalize.add_argument(
        "--postprocess", choices=("auto", "always", "never"), default="auto"
    )
    finalize.add_argument("--postprocess-tier", choices=("luna", "terra", "sol"))
    finalize.add_argument("--postprocess-timeout-ms", type=int)
    finalize.add_argument("--max-model-calls", type=int)
    finalize.add_argument("--max-postprocess-calls", type=int, default=1)
    finalize.add_argument("--max-stage-seconds", type=float)
    finalize.add_argument("--no-patina", action="store_true")
    finalize.add_argument("--legacy-patina", action="store_true")
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

    profile_applicant = profile_commands.add_parser("applicant")
    profile_applicant.add_argument("--ledger", required=True)
    profile_applicant.add_argument("--profile-id", required=True)
    profile_applicant.add_argument("--output", required=True)
    profile_applicant.add_argument("--force", action="store_true")
    profile_applicant.add_argument("--run-dir")

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

    posting_record = posting_commands.add_parser("record")
    posting_record.add_argument("--target", required=True)
    posting_record.add_argument("--source", required=True)
    posting_record.add_argument("--official-source", action="store_true")
    posting_record.add_argument("--official-domain", action="append", default=[])
    posting_record.add_argument("--posting-id")
    posting_record.add_argument("--output", required=True)
    posting_record.add_argument("--force", action="store_true")
    posting_record.add_argument("--run-dir")

    eligibility = subparsers.add_parser("eligibility")
    eligibility_commands = eligibility.add_subparsers(
        dest="eligibility_command", required=True
    )
    eligibility_evaluate = eligibility_commands.add_parser("evaluate")
    eligibility_evaluate.add_argument("--profile", required=True)
    eligibility_evaluate.add_argument("--posting", required=True)
    eligibility_evaluate.add_argument("--output", required=True)
    eligibility_evaluate.add_argument("--evaluation-date")
    eligibility_evaluate.add_argument("--force", action="store_true")
    eligibility_evaluate.add_argument("--run-dir")

    discovery = subparsers.add_parser("discovery")
    discovery_commands = discovery.add_subparsers(dest="discovery_command", required=True)
    source_add = discovery_commands.add_parser("source-add")
    source_add.add_argument("--root", default=".")
    source_add.add_argument("--source-id")
    source_add.add_argument("--organization", required=True)
    source_add.add_argument("--type", dest="source_type", choices=("manual_url", "official_list_page", "official_rss", "official_sitemap", "official_json_api"), required=True)
    source_add.add_argument("--url", required=True)
    source_add.add_argument("--allow-domain", action="append", required=True)
    source_add.add_argument("--role-keyword", action="append", default=[])
    source_add.add_argument("--location-keyword", action="append", default=[])
    source_add.add_argument("--include-pattern")
    source_add.add_argument("--items-path")
    source_add.add_argument("--url-field")
    source_add.add_argument("--id-field")
    source_add.add_argument("--posting-id-pattern")
    source_add.add_argument("--detail-pattern")
    source_add.add_argument("--force", action="store_true")
    source_list = discovery_commands.add_parser("source-list")
    source_list.add_argument("--root", default=".")
    discovery_run = discovery_commands.add_parser("run")
    discovery_run.add_argument("--root", default=".")
    discovery_run.add_argument("--source-id", required=True)
    discovery_run.add_argument("--applicant-profile")
    discovery_run.add_argument("--evaluation-time", required=True)
    discovery_run.add_argument("--run-id")

    registry = subparsers.add_parser("registry")
    registry_commands = registry.add_subparsers(dest="registry_command", required=True)
    registry_list = registry_commands.add_parser("list")
    registry_list.add_argument("--root", default=".")
    registry_list.add_argument("--status")
    registry_show = registry_commands.add_parser("show")
    registry_show.add_argument("--root", default=".")
    registry_show.add_argument("--posting-id", required=True)
    registry_compare = registry_commands.add_parser("compare")
    registry_compare.add_argument("--root", default=".")
    registry_compare.add_argument("--posting-id", required=True)
    registry_compare.add_argument("--current", required=True)

    queue = subparsers.add_parser("queue")
    queue_commands = queue.add_subparsers(dest="queue_command", required=True)
    queue_list = queue_commands.add_parser("list")
    queue_list.add_argument("--root", default=".")
    queue_list.add_argument("--status")
    queue_show = queue_commands.add_parser("show")
    queue_show.add_argument("--root", default=".")
    queue_show.add_argument("--queue-id", required=True)
    queue_decide = queue_commands.add_parser("decide")
    queue_decide.add_argument("--root", default=".")
    queue_decide.add_argument("--queue-id", required=True)
    queue_decide.add_argument("--decision", choices=("approved", "rejected", "deferred"), required=True)
    queue_decide.add_argument("--at")

    application = subparsers.add_parser("application")
    application_commands = application.add_subparsers(dest="application_command", required=True)
    application_package = application_commands.add_parser("package")
    application_package.add_argument("--root", default=".")
    application_package.add_argument("--run", required=True)
    application_package.add_argument("--profile", required=True)
    application_package.add_argument("--posting", required=True)
    application_package.add_argument("--decision", required=True)
    application_package.add_argument("--private-data", required=True)
    application_package.add_argument("--attachment", action="append", default=[])
    application_package.add_argument("--output", required=True)
    application_package.add_argument("--created-at")
    application_validate = application_commands.add_parser("validate")
    application_validate.add_argument("--root", default=".")
    application_validate.add_argument("--package", required=True)
    application_validate.add_argument("--private-data", required=True)
    application_validate.add_argument("--attachment", action="append", default=[])
    application_dry_run = application_commands.add_parser("dry-run")
    application_dry_run.add_argument("--root", default=".")
    application_dry_run.add_argument("--package", required=True)
    application_dry_run.add_argument("--private-data", required=True)
    application_dry_run.add_argument("--attachment", action="append", default=[])
    application_dry_run.add_argument("--html", required=True)
    application_dry_run.add_argument("--output", required=True)
    application_dry_run.add_argument("--evaluation-time", required=True)
    application_dry_run.add_argument("--page-url", default="https://fixture.invalid/application")
    application_review = application_commands.add_parser("review")
    application_review.add_argument("--root", default=".")
    application_review.add_argument("--package", required=True)
    application_review.add_argument("--dry-run-result", required=True)
    application_review.add_argument("--decision", choices=("approved", "rejected", "deferred"), required=True)
    application_review.add_argument("--output", required=True)
    application_review.add_argument("--at", required=True)
    application_review.add_argument("--approver-id", required=True)
    application_authorize = application_commands.add_parser("authorize")
    application_authorize.add_argument("--root", default=".")
    application_authorize.add_argument("--package", required=True)
    application_authorize.add_argument("--dry-run-result", required=True)
    application_authorize.add_argument("--review", required=True)
    application_authorize.add_argument("--allowed-origin", required=True)
    application_authorize.add_argument("--mode", choices=("fill_only", "submit"), required=True)
    application_authorize.add_argument("--output", required=True)
    application_authorize.add_argument("--at", required=True)
    application_authorize.add_argument("--expires-at", required=True)
    application_authorize.add_argument("--approver-id", required=True)

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


def run_profile_applicant(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    profile = applicant_profile_from_ledger(
        load_ledger(ledger_path),
        profile_id=args.profile_id,
        ledger_path=str(ledger_path),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_phase2_json(
        output, applicant_profile_to_dict(profile), force=args.force, run_dir=args.run_dir
    )
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


def run_posting_record(args: argparse.Namespace) -> int:
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
    record = posting_record_from_analysis(
        parse_posting(loaded, target=args.target),
        posting_id=args.posting_id,
        normalized_content_sha256=normalized_posting_content_sha256(loaded.content),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_phase2_json(
        output, posting_record_to_dict(record), force=args.force, run_dir=args.run_dir
    )
    print(output)
    return 0 if record.source_status != "unverified" else 2


def run_eligibility_evaluate(args: argparse.Namespace) -> int:
    profile = load_applicant_profile(Path(args.profile))
    posting = load_posting_record(Path(args.posting))
    decision = evaluate_eligibility(profile, posting, evaluated_at=args.evaluation_date)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_phase2_json(
        output,
        {
            **asdict(decision),
            "internal_status": decision.status,
            "human_review_recommended": decision.human_review_required,
        },
        force=args.force,
        run_dir=args.run_dir,
    )
    print(f"{output} {decision.status}")
    return 0 if decision.status == "eligible" else 2


def _write_phase2_json(
    output: Path, payload: dict, *, force: bool, run_dir: str | None
) -> None:
    if run_dir is not None:
        root = Path(run_dir).resolve()
        if not root.is_dir():
            raise ValueError(f"run directory does not exist: {root}")
        try:
            output.parent.resolve().relative_to(root)
        except ValueError as error:
            raise ValueError("Phase 2 output must remain inside --run-dir") from error
    if output.is_symlink():
        raise ValueError("Phase 2 output must not be a symbolic link")
    if output.exists() and output.is_dir():
        raise ValueError("Phase 2 output path must be a file")
    if output.exists() and not force:
        raise ValueError(f"output already exists; use --force to replace: {output}")
    write_json(output, payload)


def _phase3_root(root: str | Path) -> tuple[Path, Path, Path]:
    workspace = Path(root).resolve()
    profile_dir = workspace / ".career_profile"
    registry_dir = profile_dir / "posting_registry"
    return workspace, profile_dir / "discovery_sources.json", registry_dir / "registry.json"


def _phase3_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_discovery_source_add(args: argparse.Namespace) -> int:
    _workspace, source_path, registry_path = _phase3_root(args.root)
    created_at = _phase3_now()
    source_id = args.source_id or (
        "source-" + sha256(f"{args.organization}|{args.url}".encode("utf-8")).hexdigest()[:24]
    )
    config = {
        key: value
        for key, value in {
            "include_pattern": args.include_pattern,
            "items_path": args.items_path,
            "url_field": args.url_field,
            "id_field": args.id_field,
            "posting_id_pattern": args.posting_id_pattern,
            "detail_pattern": args.detail_pattern,
        }.items()
        if value
    }
    source = DiscoverySource(
        schema_version=1,
        source_id=source_id,
        organization=args.organization,
        source_type=args.source_type,
        entry_url=args.url,
        allowed_domains=tuple(args.allow_domain),
        role_keywords=tuple(args.role_keyword),
        location_keywords=tuple(args.location_keyword),
        enabled=True,
        created_at=created_at,
        updated_at=created_at,
        config=config,
    )
    add_discovery_source(source_path, source, force=args.force)
    registry = PostingRegistry.load(registry_path)
    registry.record_event(
        "source_added",
        occurred_at=created_at,
        source_id=source_id,
        posting_id=None,
        run_id=None,
    )
    print(source_id)
    return 0


def run_discovery_source_list(args: argparse.Namespace) -> int:
    _workspace, source_path, _registry_path = _phase3_root(args.root)
    sources = load_discovery_sources(source_path)
    print(json.dumps([discovery_source_to_dict(sources[key]) for key in sorted(sources)], ensure_ascii=False, indent=2))
    return 0


def run_discovery_command(args: argparse.Namespace) -> int:
    _workspace, source_path, registry_path = _phase3_root(args.root)
    sources = load_discovery_sources(source_path)
    source = sources.get(args.source_id)
    if source is None:
        raise DiscoveryValidationError(f"source not found: {args.source_id}")
    profile = load_applicant_profile(Path(args.applicant_profile)) if args.applicant_profile else None
    registry = PostingRegistry.load(registry_path)
    run = run_discovery(
        source,
        registry=registry,
        evaluation_time=args.evaluation_time,
        applicant_profile=profile,
        run_id=args.run_id,
    )
    print(json.dumps(asdict(run), ensure_ascii=False, indent=2))
    return 0 if run.status in {"completed", "completed_with_errors"} else 4


def run_registry_command(args: argparse.Namespace) -> int:
    _workspace, _source_path, registry_path = _phase3_root(args.root)
    registry = PostingRegistry.load(registry_path)
    if args.registry_command == "list":
        rows = [
            {
                "posting_id": posting.posting_id,
                "organization": posting.organization,
                "role": posting.role,
                "status": posting.status,
                "body_sha256": posting.body_sha256,
                "last_seen_at": posting.last_seen_at,
            }
            for posting in registry.postings.values()
            if args.status is None or posting.status == args.status
        ]
        print(json.dumps(sorted(rows, key=lambda item: item["posting_id"]), ensure_ascii=False, indent=2))
        return 0
    posting = registry.postings.get(args.posting_id)
    if posting is None:
        raise RegistryError(f"posting not found: {args.posting_id}")
    if args.registry_command == "show":
        print(json.dumps(posting_record_to_dict(posting), ensure_ascii=False, indent=2))
        return 0
    current = posting_record_from_dict(json.loads(Path(args.current).read_text(encoding="utf-8")))
    print(json.dumps(asdict(compare_postings(posting, current)), ensure_ascii=False, indent=2))
    return 0


def run_queue_command(args: argparse.Namespace) -> int:
    _workspace, _source_path, registry_path = _phase3_root(args.root)
    registry = PostingRegistry.load(registry_path)
    if args.queue_command == "list":
        rows = [
            queue_item_to_dict(item)
            for item in registry.queue.values()
            if args.status is None or item.queue_status == args.status
        ]
        print(json.dumps(sorted(rows, key=lambda item: (-item["priority"], item["queue_id"])), ensure_ascii=False, indent=2))
        return 0
    if args.queue_command == "show":
        item = registry.queue.get(args.queue_id)
        if item is None:
            raise RegistryError(f"queue item not found: {args.queue_id}")
        print(json.dumps(queue_item_to_dict(item), ensure_ascii=False, indent=2))
        return 0
    at = args.at or _phase3_now()
    item = registry.decide_queue(args.queue_id, args.decision, at=at)
    print(json.dumps(queue_item_to_dict(item), ensure_ascii=False, indent=2))
    return 0


def _phase4_path(root: Path, value: str, *, must_exist: bool = False) -> Path:
    root = root.resolve()
    windows = PureWindowsPath(value)
    if windows.is_absolute() or windows.drive or value.startswith(("\\\\", "//")):
        candidate = Path(value)
        if not candidate.is_absolute():
            raise ApplicationPackageError("Phase 4 paths must not be UNC or drive-relative")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ApplicationPackageError("Phase 4 paths must remain inside the workspace") from error
    current = root
    for part in resolved.relative_to(root).parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise ApplicationPackageError("Phase 4 paths must not traverse symlinks")
    if path.is_symlink():
        raise ApplicationPackageError("Phase 4 paths must not be symlinks")
    return resolved


def _application_attachments(root: Path, values: list[str]) -> dict[str, Path]:
    attachments: dict[str, Path] = {}
    for item in values:
        if "=" not in item:
            raise ApplicationPackageError("--attachment must use field_key=path")
        key, raw_path = item.split("=", 1)
        if not key or not raw_path or key in attachments:
            raise ApplicationPackageError("attachment field keys and paths must be unique and non-empty")
        attachments[key] = _phase4_path(root, raw_path, must_exist=True)
    return attachments


def run_application_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.application_command == "package":
        run_dir = _phase4_path(root, args.run, must_exist=True)
        state_path = run_dir / "run.json"
        if not state_path.is_file() or state_path.is_symlink():
            raise ApplicationPackageError("run.json is missing or unsafe")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        profile_path = _phase4_path(root, args.profile, must_exist=True)
        profile = load_applicant_profile(profile_path)
        posting = load_posting_record(_phase4_path(root, args.posting, must_exist=True))
        decision = decision_from_dict(
            json.loads(_phase4_path(root, args.decision, must_exist=True).read_text(encoding="utf-8"))
        )
        output = _phase4_path(root, args.output)
        package = build_application_package(
            root=root,
            run_dir=run_dir,
            run_state=state,
            profile=profile,
            posting=posting,
            decision=decision,
            private_data_path=_phase4_path(root, args.private_data, must_exist=True),
            profile_sha256=sha256(profile_path.read_bytes()).hexdigest(),
            attachments=_application_attachments(root, args.attachment),
            created_at=args.created_at,
        )
        persist_application_package(
            root, output, package,
            private_data_path=_phase4_path(root, args.private_data, must_exist=True),
            attachments=_application_attachments(root, args.attachment),
        )
        print(package.package_id)
        return 0 if package.validation_status == "ready_for_review" else 2
    package = load_application_package(_phase4_path(root, args.package, must_exist=True))
    if args.application_command == "review":
        signing_key = os.environ.get("CAREER_EXECUTION_SIGNING_KEY", "").encode("utf-8")
        result = load_form_result(_phase4_path(root, args.dry_run_result, must_exist=True))
        review = approve_application(package, result, decision=args.decision, decided_at=args.at, approver_id=args.approver_id, signing_key=signing_key)
        write_workflow_artifact(_phase4_path(root, args.output), review)
        print(f"{review.review_id} {review.decision}")
        return 0 if review.decision == "approved" else 2
    if args.application_command == "authorize":
        signing_key = os.environ.get("CAREER_EXECUTION_SIGNING_KEY", "").encode("utf-8")
        result = load_form_result(_phase4_path(root, args.dry_run_result, must_exist=True))
        review = load_review(_phase4_path(root, args.review, must_exist=True), signing_key)
        authorization = authorize_execution(package, result, review, allowed_origin=args.allowed_origin,
            mode=args.mode, authorized_at=args.at, expires_at=args.expires_at, approver_id=args.approver_id, signing_key=signing_key)
        write_workflow_artifact(_phase4_path(root, args.output), authorization)
        print(f"{authorization.authorization_id} {authorization.mode}")
        return 0
    private_path = _phase4_path(root, args.private_data, must_exist=True)
    attachments = _application_attachments(root, args.attachment)
    if args.application_command == "validate":
        materialize_package_values(root, package, private_data_path=private_path, attachments=attachments)
        print(f"{package.package_id} {package.validation_status}")
        return 0 if package.validation_status == "ready_for_review" else 2
    html_path = _phase4_path(root, args.html, must_exist=True)
    output = _phase4_path(root, args.output)
    driver = FixtureFormDriver.from_path(html_path, url=args.page_url)
    result = ReviewRequiredFormAdapter().run(
        driver,
        root=root,
        package=package,
        private_data_path=private_path,
        attachments=attachments,
        evaluation_time=args.evaluation_time,
    )
    write_form_result(output, result)
    print(f"{result.run_id} {result.status}")
    return 0 if result.status == "review_required" else 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "application":
        try:
            return run_application_command(args)
        except (
            OSError,
            json.JSONDecodeError,
            ApplicationPackageError,
            FormAdapterError,
            ApplicationExecutionError,
            EligibilityValidationError,
            ValueError,
        ) as error:
            print(error)
            return 4
    if args.command == "discovery":
        try:
            if args.discovery_command == "source-add":
                return run_discovery_source_add(args)
            if args.discovery_command == "source-list":
                return run_discovery_source_list(args)
            return run_discovery_command(args)
        except (OSError, DiscoveryValidationError, PostingSourceError, RegistryError, EligibilityValidationError, ValueError) as error:
            print(error)
            return 4
    if args.command == "registry":
        try:
            return run_registry_command(args)
        except (OSError, RegistryError, EligibilityValidationError, ValueError) as error:
            print(error)
            return 4
    if args.command == "queue":
        try:
            return run_queue_command(args)
        except (OSError, RegistryError, ValueError) as error:
            print(error)
            return 4
    if args.command == "posting":
        try:
            if args.posting_command == "record":
                return run_posting_record(args)
            return run_posting_analyze(args)
        except (OSError, PostingSourceError, EligibilityValidationError, ValueError) as error:
            print(error)
            return 4
    if args.command == "eligibility":
        try:
            return run_eligibility_evaluate(args)
        except (OSError, EligibilityValidationError, ValueError) as error:
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
        if args.profile_command == "applicant":
            try:
                return run_profile_applicant(args)
            except (OSError, ProfileValidationError, EligibilityValidationError, ValueError) as error:
                print(error)
                return 4
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
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    legacy_option_names = {
        "--patina-backend",
        "--patina-timeout-ms",
        "--patina-max-retries",
        "--patina-voice-sample",
        "--patina-ai-threshold",
        "--no-patina-score",
    }
    explicit_legacy_options = any(
        item.split("=", 1)[0] in legacy_option_names for item in raw_args
    )
    if explicit_legacy_options and args.no_patina:
        print("legacy Patina 옵션과 --no-patina는 함께 사용할 수 없습니다.")
        return 4
    if explicit_legacy_options and not args.legacy_patina:
        print("경고: --patina-* 옵션은 호환성을 위해 legacy Patina 모드로 실행됩니다. --legacy-patina 사용을 권장합니다.")
        args.legacy_patina = True
    if args.no_copyeditor and args.postprocess == "always":
        print("--no-copyeditor와 --postprocess always는 함께 사용할 수 없습니다.")
        return 4
    if args.legacy_patina and args.postprocess == "always":
        print("--legacy-patina와 --postprocess always는 함께 사용할 수 없습니다.")
        return 4
    if args.legacy_patina and args.postprocess_tier is not None:
        print("--legacy-patina와 --postprocess-tier는 함께 사용할 수 없습니다.")
        return 4
    if args.no_copyeditor and args.postprocess_tier is not None:
        print("--no-copyeditor와 --postprocess-tier는 함께 사용할 수 없습니다.")
        return 4
    if args.postprocess == "never" and args.postprocess_tier is not None:
        print("--postprocess never와 --postprocess-tier는 함께 사용할 수 없습니다.")
        return 4
    if args.legacy_patina and args.no_patina:
        print("--legacy-patina와 --no-patina는 함께 사용할 수 없습니다.")
        return 4
    if args.max_model_calls is not None and args.max_model_calls < 0:
        print("--max-model-calls는 0 이상이어야 합니다.")
        return 4
    if args.max_postprocess_calls < 0:
        print("--max-postprocess-calls는 0 이상이어야 합니다.")
        return 4
    state = finalize_run(
        Path(args.run),
        copyedit=False,
        copyeditor_timeout_ms=args.copyeditor_timeout_ms,
        humanize=args.legacy_patina and not args.no_patina,
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
        postprocess="never" if args.no_copyeditor else args.postprocess,
        postprocess_tier=args.postprocess_tier,
        postprocess_timeout_ms=args.postprocess_timeout_ms,
        max_model_calls=args.max_model_calls,
        max_postprocess_calls=args.max_postprocess_calls,
        max_stage_seconds=args.max_stage_seconds,
    )
    print(state["status"])
    if state["status"] == "complete":
        return 0
    return 2 if state["status"].startswith("blocked_") else 3


if __name__ == "__main__":
    raise SystemExit(main())
