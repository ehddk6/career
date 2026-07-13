"""career_pipeline CLI 진입점. prepare, finalize, profile, posting 서브커맨드를 제공합니다."""
import argparse
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
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
    load_authorization,
    write_workflow_artifact,
)
from .registry import PostingRegistry, RegistryError, queue_item_to_dict
from .origin_policy import OriginPolicyError, normalize_origin
from .offline_acceptance import (
    AcceptanceInputs,
    OfflineAcceptanceError,
    OfflineAcceptanceBlockedResult,
    offline_acceptance_to_dict,
    run_offline_acceptance,
)
from .readiness import (
    ReadinessAxisName,
    ReadinessContractError,
    RequirementClassification,
    canonical_readiness_json,
    readiness_report_from_dict,
    readiness_report_sha256,
)
from .state import write_json


PATINA_BACKENDS = {
    "codex-cli",
    "openai-http",
    "claude-cli",
    "gemini-cli",
    "kimi-cli",
}

_M5_KEYS = frozenset({
    "acceptance", "acceptance_sha256", "artifact_sha256", "blocker_codes",
    "command", "error_code", "external_inputs_status", "kind",
    "live_execution_status", "local_status", "message",
    "offline_acceptance_status", "outcome", "package_sha256",
    "readiness_sha256", "schema_version", "submission_status",
})
_M5_SHA256 = re.compile(r"[0-9a-f]{64}")
_M5_COUNTER_KEYS = frozenset({"network", "browser", "credential", "pii", "upload", "click", "submit"})
_M5_SYNTHETIC_SIGNING_KEY = b"career-pipeline-m5-public-synthetic-key"
_M5_SYNTHETIC_KEY_ID = "m5-public-synthetic"


class M5InputError(ValueError):
    """Raised for parsed M5 command inputs that violate the public contract."""


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

    offline_acceptance = subparsers.add_parser("offline-acceptance")
    offline_acceptance.add_argument("--workspace", required=True)
    offline_acceptance.add_argument("--at", required=True)
    offline_acceptance.add_argument("--site-valid-until", required=True)
    offline_acceptance.add_argument("--test-evidence-sha256", required=True)
    offline_acceptance.add_argument("--format", choices=("human", "json"), default="human")
    offline_acceptance.add_argument("--output")

    status = subparsers.add_parser("status")
    status.add_argument("--input", required=True)
    status.add_argument("--format", choices=("human", "json"), default="human")

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
    application_platform = application_commands.add_parser("platform")
    platform_commands = application_platform.add_subparsers(dest="platform_command", required=True)
    platform_list = platform_commands.add_parser("list")
    platform_list.add_argument("--role", choices=("discovery", "application_family", "both"))
    platform_show = platform_commands.add_parser("show")
    platform_show.add_argument("platform_id")
    platform_detect = platform_commands.add_parser("detect")
    platform_detect.add_argument("--url", required=True)
    platform_detect.add_argument("--discovery-platform", required=True)
    platform_detect.add_argument("--posting-url")
    platform_detect.add_argument("--at", required=True)
    application_intake = application_commands.add_parser("site-intake")
    intake_commands = application_intake.add_subparsers(dest="intake_command", required=True)
    intake_create = intake_commands.add_parser("create")
    intake_create.add_argument("--root", default=".")
    intake_create.add_argument("--posting-url")
    intake_create.add_argument("--resolved-application-url")
    intake_create.add_argument("--platform-family", default="auto", choices=("auto","jobkorea_jrs","saramin_applyin","saramin_direct","unknown"))
    intake_create.add_argument("--fixture-resource-id")
    intake_create.add_argument("--discovery-platform")
    intake_create.add_argument("--login-status",choices=("unknown","none","required"),default="unknown")
    for name in ("mfa-status","captcha-status","iframe-status","popup-status","redirect-status"):
        intake_create.add_argument("--"+name,choices=("unknown","none","present"),default="unknown")
    intake_create.add_argument("--attachment-status",choices=("unknown","unsupported","required"),default="unknown")
    intake_create.add_argument("--registry", default=".career_profile/site_intake/registry.json")
    intake_create.add_argument("--expected-version", type=int)
    intake_create.add_argument("--at", required=True)
    intake_schema = intake_commands.add_parser("schema")
    intake_schema.add_argument("--root", default=".")
    intake_schema.add_argument("--resolved-application-url", required=True)
    intake_schema.add_argument("--fixture-resource-id", required=True)
    intake_show = intake_commands.add_parser("show")
    intake_show.add_argument("--root", default=".")
    intake_show.add_argument("--registry", default=".career_profile/site_intake/registry.json")
    intake_show.add_argument("--intake-id", required=True)
    intake_list = intake_commands.add_parser("list")
    intake_list.add_argument("--root", default=".")
    intake_list.add_argument("--registry", default=".career_profile/site_intake/registry.json")
    intake_commands.add_parser("platform-status")
    application_adapter = application_commands.add_parser("adapter")
    adapter_commands = application_adapter.add_subparsers(dest="adapter_command", required=True)
    adapter_commands.add_parser("list")
    from .platform_catalog import list_fixture_adapters
    fixture_adapters = list_fixture_adapters()
    for name in ("show", "schema", "validate"):
        command = adapter_commands.add_parser(name)
        command.add_argument("adapter_id", choices=fixture_adapters)
        command.add_argument("--root", default=".")
    application_fill_fixture = application_commands.add_parser("fill-fixture")
    application_fill_fixture.add_argument("--root", default=".")
    application_fill_fixture.add_argument("--adapter", choices=fixture_adapters, required=True)
    application_fill_fixture.add_argument("--package", required=True)
    application_fill_fixture.add_argument("--dry-run-result", required=True)
    application_fill_fixture.add_argument("--authorization", required=True)
    application_fill_fixture.add_argument("--values", required=True)
    application_fill_fixture.add_argument("--ledger", required=True)
    application_fill_fixture.add_argument("--output", required=True)
    application_fill_fixture.add_argument("--at", required=True)
    application_fixture_result = application_commands.add_parser("fixture-result")
    application_fixture_result.add_argument("--root", default=".")
    application_fixture_result.add_argument("--result", required=True)

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


def _m5_canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _m5_sha256(value: object) -> str:
    return sha256(_m5_canonical_json(value)).hexdigest()


def _m5_require_fields(value: object, expected: frozenset[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise M5InputError(f"invalid {label}")
    return value


def _m5_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _M5_SHA256.fullmatch(value) is None:
        raise M5InputError(f"invalid {label}")
    return value


def _m5_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise M5InputError(f"invalid {label}")
    return value


def _m5_timestamp(value: object, label: str) -> str:
    text = _m5_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise M5InputError(f"invalid {label}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise M5InputError(f"invalid {label}")
    return text


def _m5_counters(value: object) -> None:
    counters = _m5_require_fields(value, _M5_COUNTER_KEYS, "counters")
    if any(type(item) is not int or item != 0 for item in counters.values()):
        raise M5InputError("invalid counters")


def _m5_origin(value: object) -> None:
    origin = _m5_text(value, "exact_origin")
    try:
        canonical = normalize_origin(origin)
    except OriginPolicyError as error:
        raise M5InputError("invalid exact_origin") from error
    if origin != canonical:
        raise M5InputError("invalid exact_origin")


def _m5_axis_values(report: object) -> dict[str, str]:
    return {item.axis.value: item.status.value for item in report.axes}


def _m5_classify_readiness(report: object) -> tuple[str, int]:
    axes = _m5_axis_values(report)
    local_missing = any(
        item.classification is RequirementClassification.LOCALLY_MISSING
        for item in report.requirements
    )
    locally_complete = (
        axes["local_foundation"] == "complete"
        and axes["offline_acceptance"] == "passed"
        and not local_missing
    )
    if not locally_complete:
        return "local_unsafe", 2
    if not report.blockers:
        return "local_complete", 0
    classifications = {
        item.requirement_id: item.classification
        for item in report.requirements
    }
    if all(
        classifications.get(item.requirement_id) is RequirementClassification.EXTERNAL_ONLY
        for item in report.blockers
    ):
        return "external_only_blocked", 3
    return "local_unsafe", 2


def _m5_status_envelope(report: object, outcome: str) -> dict[str, object]:
    axes = _m5_axis_values(report)
    return {
        "acceptance": None,
        "acceptance_sha256": None,
        "artifact_sha256": None,
        "blocker_codes": sorted({item.code.value for item in report.blockers}),
        "command": "status",
        "error_code": None,
        "external_inputs_status": axes["external_inputs"],
        "kind": "status",
        "live_execution_status": axes["live_execution"],
        "local_status": "complete" if outcome != "local_unsafe" else "unsafe",
        "message": None,
        "offline_acceptance_status": axes["offline_acceptance"],
        "outcome": outcome,
        "package_sha256": None,
        "readiness_sha256": readiness_report_sha256(report),
        "schema_version": "career-pipeline-cli-status-v1",
        "submission_status": axes["submission"],
    }


def _m5_validate_positive_acceptance(acceptance: object) -> object:
    expected = frozenset({
        "authorization_candidate", "counters", "eligibility_decision_id",
        "final_manifest_sha256", "live_status", "local_status", "package_id",
        "package_sha256", "posting_id", "profile_id", "readiness_report",
        "readiness_sha256", "review_id", "run_id", "schema_version",
        "site_contract_id", "site_contract_sha256", "submission_status",
    })
    data = _m5_require_fields(acceptance, expected, "positive acceptance")
    if data["schema_version"] != "career-pipeline-offline-acceptance-v1":
        raise M5InputError("invalid positive acceptance")
    for key in ("run_id", "posting_id", "profile_id", "eligibility_decision_id", "final_manifest_sha256", "package_id", "package_sha256", "site_contract_id", "site_contract_sha256", "review_id", "readiness_sha256"):
        _m5_text(data[key], key)
    for key in ("final_manifest_sha256", "package_sha256", "site_contract_sha256", "readiness_sha256"):
        _m5_sha(data[key], key)
    if (data["local_status"], data["live_status"], data["submission_status"]) != ("awaiting_external_live_enablement", "disabled", "not_attempted"):
        raise M5InputError("invalid positive acceptance status")
    _m5_counters(data["counters"])
    candidate = _m5_require_fields(data["authorization_candidate"], frozenset({
        "schema_version", "review_id", "package_id", "package_sha256", "site_contract_id",
        "site_contract_sha256", "exact_origin", "adapter_id", "adapter_contract_version",
        "adapter_schema_sha256", "requested_mode", "requested_at", "candidate_status", "reason_code",
    }), "authorization candidate")
    if type(candidate["schema_version"]) is not int or candidate["schema_version"] != 2:
        raise M5InputError("invalid authorization candidate")
    for key in ("review_id", "package_id", "site_contract_id", "adapter_id"):
        _m5_text(candidate[key], key)
    for key in ("package_sha256", "site_contract_sha256", "adapter_schema_sha256"):
        _m5_sha(candidate[key], key)
    if type(candidate["adapter_contract_version"]) is not int or candidate["adapter_contract_version"] < 1:
        raise M5InputError("invalid adapter contract version")
    _m5_origin(candidate["exact_origin"])
    _m5_timestamp(candidate["requested_at"], "requested_at")
    if (candidate["requested_mode"], candidate["candidate_status"], candidate["reason_code"]) != ("fill_only", "capability_disabled", "FILL_AUTHORITY_DISABLED"):
        raise M5InputError("invalid authorization candidate status")
    if any(candidate[key] != data[key] for key in ("review_id", "package_id", "package_sha256", "site_contract_id", "site_contract_sha256")):
        raise M5InputError("authorization candidate binding mismatch")
    report = readiness_report_from_dict(data["readiness_report"])
    if data["readiness_sha256"] != readiness_report_sha256(report):
        raise M5InputError("readiness digest mismatch")
    return report


def _m5_validate_envelope(value: object) -> object:
    outer = _m5_require_fields(value, _M5_KEYS, "offline acceptance envelope")
    if (
        outer["schema_version"] != "career-pipeline-cli-offline-acceptance-v1"
        or outer["command"] != "offline-acceptance"
        or outer["kind"] != "offline_acceptance"
        or outer["error_code"] is not None
        or outer["message"] is not None
    ):
        raise M5InputError("invalid offline acceptance envelope")
    acceptance = outer["acceptance"]
    if not isinstance(acceptance, dict) or outer["acceptance_sha256"] != _m5_sha256(acceptance):
        raise M5InputError("acceptance digest mismatch")
    _m5_sha(outer["acceptance_sha256"], "acceptance_sha256")
    if set(acceptance) == {"schema_version", "scenario", "block_code", "counters"}:
        if (
            acceptance.get("schema_version") != "career-pipeline-offline-acceptance-v1"
            or acceptance.get("scenario") != "sensitive_fixture"
            or acceptance.get("block_code") != "blocked_sensitive_fixture"
            or (outer["outcome"], outer["local_status"], outer["offline_acceptance_status"], outer["external_inputs_status"], outer["live_execution_status"], outer["submission_status"]) != ("local_unsafe", "unsafe", "failed", "blocked", "disabled", "not_attempted")
            or outer["blocker_codes"] != ["blocked_sensitive_fixture"]
            or any(outer[key] is not None for key in ("readiness_sha256", "artifact_sha256", "package_sha256"))
        ):
            raise M5InputError("invalid blocked offline acceptance envelope")
        _m5_counters(acceptance["counters"])
        return None
    report = _m5_validate_positive_acceptance(acceptance)
    axes = _m5_axis_values(report)
    blockers = sorted({item.code.value for item in report.blockers})
    if (
        (outer["outcome"], outer["local_status"], outer["offline_acceptance_status"], outer["external_inputs_status"], outer["live_execution_status"], outer["submission_status"]) != ("external_only_blocked", "complete", "passed", axes["external_inputs"], axes["live_execution"], axes["submission"])
        or outer["blocker_codes"] != blockers
        or outer["readiness_sha256"] != acceptance["readiness_sha256"]
        or outer["artifact_sha256"] != acceptance["final_manifest_sha256"]
        or outer["package_sha256"] != acceptance["package_sha256"]
    ):
        raise M5InputError("invalid positive offline acceptance envelope")
    for key in ("readiness_sha256", "artifact_sha256", "package_sha256"):
        _m5_sha(outer[key], key)
    if _m5_classify_readiness(report) != ("external_only_blocked", 3):
        raise M5InputError("invalid positive offline acceptance readiness")
    return report


def _m5_read_status_input(raw_path: str) -> object:
    path = Path(raw_path)
    windows = PureWindowsPath(raw_path)
    if (
        not raw_path
        or path.is_absolute()
        or windows.drive
        or windows.root
        or raw_path.startswith(("/", "\\"))
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise M5InputError("invalid status input")
    cwd = Path.cwd().resolve(strict=True)
    candidate = cwd.joinpath(*path.parts)
    try:
        relative = candidate.relative_to(cwd)
    except ValueError as error:
        raise M5InputError("invalid status input") from error
    checked = cwd
    for part in relative.parts:
        checked = checked / part
        if checked.is_symlink():
            raise M5InputError("invalid status input")
    try:
        target_stat = candidate.lstat()
        if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_size > 1_000_000:
            raise M5InputError("invalid status input")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(cwd)
        raw = candidate.read_bytes()
        if len(raw) > 1_000_000:
            raise M5InputError("invalid status input")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, M5InputError):
            raise
        raise M5InputError("invalid status input") from error
    if not isinstance(value, dict):
        raise M5InputError("invalid status input")
    return value


def _m5_error_envelope(command: str) -> dict[str, object]:
    return {
        "acceptance": None, "acceptance_sha256": None, "artifact_sha256": None,
        "blocker_codes": [], "command": command, "error_code": "INVALID_INPUT",
        "external_inputs_status": None,
        "kind": "offline_acceptance" if command == "offline-acceptance" else "status",
        "live_execution_status": None, "local_status": None, "message": f"invalid {command.replace('-', ' ')} input",
        "offline_acceptance_status": None, "outcome": "invalid_input", "package_sha256": None,
        "readiness_sha256": None, "schema_version": "career-pipeline-cli-error-v1", "submission_status": None,
    }


def _m5_render_human(envelope: dict[str, object], exit_code: int) -> str:
    blockers = envelope["blocker_codes"]
    return "\n".join((
        f"command: {envelope['command']}",
        f"local: {envelope['local_status']}",
        f"offline acceptance: {envelope['offline_acceptance_status'] or 'not_assessed'}",
        f"external inputs: {envelope['external_inputs_status'] or 'not_assessed'}",
        f"live execution: {envelope['live_execution_status'] or 'not_assessed'}",
        f"submission: {envelope['submission_status'] or 'not_assessed'}",
        "blockers: " + (",".join(blockers) if blockers else "none"),
        f"readiness sha256: {envelope['readiness_sha256'] or 'none'}",
        f"artifact sha256: {envelope['artifact_sha256'] or 'none'}",
        f"outcome: {envelope['outcome']} (exit {exit_code})",
    )) + "\n"


def _m5_emit(command: str, output_format: str, envelope: dict[str, object], exit_code: int, *, error: bool = False) -> None:
    if output_format == "json":
        sys.stdout.write(_m5_canonical_json(envelope).decode("utf-8") + "\n")
        return
    if error:
        sys.stderr.write("\n".join((
            f"command: {command}",
            "outcome: invalid_input (exit 4)",
            "error: INVALID_INPUT",
            f"message: {envelope['message']}",
        )) + "\n")
        return
    sys.stdout.write(_m5_render_human(envelope, exit_code))


def run_m5_offline_acceptance(args: argparse.Namespace) -> int:
    if args.output and args.format != "json":
        raise M5InputError("output requires json")
    inputs = AcceptanceInputs(
        args.at, args.at, args.at, args.at, args.at, args.at,
        args.site_valid_until, args.at, args.at, args.at,
        _M5_SYNTHETIC_SIGNING_KEY, _M5_SYNTHETIC_KEY_ID,
        args.test_evidence_sha256,
    )
    result = run_offline_acceptance(workspace=Path(args.workspace), inputs=inputs)
    acceptance = offline_acceptance_to_dict(result)
    if isinstance(result, OfflineAcceptanceBlockedResult):
        envelope = {
            "acceptance": acceptance, "acceptance_sha256": _m5_sha256(acceptance), "artifact_sha256": None,
            "blocker_codes": ["blocked_sensitive_fixture"], "command": "offline-acceptance", "error_code": None,
            "external_inputs_status": "blocked", "kind": "offline_acceptance", "live_execution_status": "disabled",
            "local_status": "unsafe", "message": None, "offline_acceptance_status": "failed", "outcome": "local_unsafe",
            "package_sha256": None, "readiness_sha256": None, "schema_version": "career-pipeline-cli-offline-acceptance-v1", "submission_status": "not_attempted",
        }
        exit_code = 2
    else:
        report = result.readiness_report
        axes = _m5_axis_values(report)
        outcome, exit_code = _m5_classify_readiness(report)
        if (outcome, exit_code) != ("external_only_blocked", 3):
            raise M5InputError("invalid offline acceptance readiness")
        envelope = {
            "acceptance": acceptance, "acceptance_sha256": _m5_sha256(acceptance), "artifact_sha256": result.final_manifest_sha256,
            "blocker_codes": sorted({item.code.value for item in report.blockers}), "command": "offline-acceptance", "error_code": None,
            "external_inputs_status": axes["external_inputs"], "kind": "offline_acceptance", "live_execution_status": axes["live_execution"],
            "local_status": "complete", "message": None, "offline_acceptance_status": axes["offline_acceptance"], "outcome": outcome,
            "package_sha256": result.package_sha256, "readiness_sha256": result.readiness_sha256, "schema_version": "career-pipeline-cli-offline-acceptance-v1", "submission_status": axes["submission"],
        }
    if args.output:
        Path(args.output).write_bytes(_m5_canonical_json(envelope) + b"\n")
    _m5_emit("offline-acceptance", args.format, envelope, exit_code)
    return exit_code


def run_m5_status(args: argparse.Namespace) -> int:
    value = _m5_read_status_input(args.input)
    if value.get("schema_version") == "career-pipeline-readiness-v1":
        report = readiness_report_from_dict(value)
    else:
        report = _m5_validate_envelope(value)
        if report is None:
            envelope = {
                "acceptance": None, "acceptance_sha256": None, "artifact_sha256": None,
                "blocker_codes": ["blocked_sensitive_fixture"], "command": "status", "error_code": None,
                "external_inputs_status": "blocked", "kind": "status", "live_execution_status": "disabled",
                "local_status": "unsafe", "message": None, "offline_acceptance_status": "failed", "outcome": "local_unsafe",
                "package_sha256": None, "readiness_sha256": None, "schema_version": "career-pipeline-cli-status-v1", "submission_status": "not_attempted",
            }
            _m5_emit("status", args.format, envelope, 2)
            return 2
    outcome, exit_code = _m5_classify_readiness(report)
    envelope = _m5_status_envelope(report, outcome)
    _m5_emit("status", args.format, envelope, exit_code)
    return exit_code


def run_m5_command(args: argparse.Namespace) -> int:
    command = args.command
    try:
        return run_m5_offline_acceptance(args) if command == "offline-acceptance" else run_m5_status(args)
    except (OSError, ValueError, OfflineAcceptanceError, ReadinessContractError, M5InputError):
        envelope = _m5_error_envelope(command)
        _m5_emit(command, args.format, envelope, 4, error=True)
        return 4


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
    root = Path(getattr(args, "root", ".")).resolve()
    if args.application_command == "site-intake":
        from .site_intake import build_site_intake, load_intake_registry, persist_intake
        if args.intake_command == "platform-status":
            value = {
                "jobkorea_jrs":{"public_service":"known","actual_execution_origin":None,"requires_manual_intake":True},
                "saramin_applyin":{"host_family":"known","company_exact_origin":"required","requires_manual_intake":True},
                "saramin_direct":{"discovery":"known","application_destination":"unresolved","requires_manual_intake":True},
            }
            print(json.dumps(value,ensure_ascii=False,indent=2)); return 0
        if args.intake_command in {"show","list"}:
            registry_path=_phase4_path(root,args.registry,must_exist=True)
            registry=load_intake_registry(registry_path)
            if args.intake_command=="show":
                value=registry.get("records",{}).get(args.intake_id)
                if value is None: raise ApplicationPackageError("site intake record not found")
            else:
                value=[{"intake_id":item.get("intake_id"),"platform_family":item.get("platform_family"),"contract_status":item.get("contract_status"),"manual_review_required":item.get("manual_review_required")} for item in registry.get("records",{}).values()]
            print(json.dumps(value,ensure_ascii=False,indent=2)); return 0
        fixture_root=_phase4_path(root,"tests/fixtures/site_intake",must_exist=True)
        if args.intake_command=="schema":
            result=build_site_intake(posting_url=None,resolved_application_url=args.resolved_application_url,fixture_root=fixture_root,fixture_resource_id=args.fixture_resource_id,discovery_platform_id=None,created_at="1970-01-01T00:00:00+00:00")
            safe={"fixture_resource_id":result.record.fixture_resource_id,"fixture_sha256":result.record.fixture_sha256,"schema_sha256":result.record.schema_sha256,"validation_codes":result.record.validation_codes,"schema":result.schema}
            print(json.dumps(safe,ensure_ascii=False,indent=2)); return 0 if result.schema is not None else 2
        known_structure={name:getattr(args,name) for name in ("login_status","mfa_status","captcha_status","iframe_status","popup_status","redirect_status","attachment_status")}
        result=build_site_intake(posting_url=args.posting_url,resolved_application_url=args.resolved_application_url,fixture_root=fixture_root,fixture_resource_id=args.fixture_resource_id,discovery_platform_id=args.discovery_platform,created_at=args.at,requested_platform_family=args.platform_family,known_structure=known_structure)
        registry_path=_phase4_path(root,args.registry)
        persist_intake(registry_path,result,expected_version=args.expected_version)
        print(json.dumps({"intake_id":result.record.intake_id,"platform_family":result.record.platform_family,"contract_status":result.record.contract_status,"manual_review_required":result.record.manual_review_required,"validation_codes":result.record.validation_codes,"fixture_resource_id":result.record.fixture_resource_id,"fixture_sha256":result.record.fixture_sha256,"schema_sha256":result.record.schema_sha256},ensure_ascii=False,indent=2))
        return 0 if result.record.contract_status=="read_only_contract_ready" else 2
    if args.application_command == "platform":
        from .platform_catalog import classify_application_url, get_platform, list_platforms
        if args.platform_command == "list":
            print(json.dumps([asdict(item) for item in list_platforms(args.role)], ensure_ascii=False, indent=2))
        elif args.platform_command == "show":
            print(json.dumps(asdict(get_platform(args.platform_id)), ensure_ascii=False, indent=2))
        else:
            detection = classify_application_url(args.url, discovery_platform_id=args.discovery_platform,
                detected_at=args.at, original_posting_url=args.posting_url)
            print(json.dumps(asdict(detection), ensure_ascii=False, indent=2))
        return 0
    if args.application_command == "adapter":
        from .platform_catalog import list_fixture_adapters
        fixture_adapters = list_fixture_adapters()
        if args.adapter_command == "list":
            print(json.dumps(list(fixture_adapters), ensure_ascii=False, indent=2))
            return 0
        from .adapters.jobkorea_jrs import adapter_contract as jobkorea_contract, collect_fixture_schema as jobkorea_schema, expected_schema as jobkorea_expected, fixture_schema_sha256 as jobkorea_sha
        from .adapters.saramin_applyin import adapter_contract as saramin_contract, collect_fixture_schema as saramin_schema, expected_schema as saramin_expected, schema_sha256 as saramin_sha
        bindings = {
            "jobkorea_jrs_fixture": (jobkorea_contract, jobkorea_schema, jobkorea_expected, jobkorea_sha, "tests/fixtures/jobkorea_jrs/application_form_v1.html"),
            "saramin_applyin_fixture": (saramin_contract, saramin_schema, saramin_expected, saramin_sha, "tests/fixtures/saramin_applyin/application_form_v1.html"),
        }
        if set(bindings) != set(fixture_adapters):
            raise ApplicationPackageError("fixture adapter dispatch mismatch")
        adapter_contract, collect_fixture_schema, expected_schema, fixture_schema_sha256, fixture_relative = bindings[args.adapter_id]
        if args.adapter_command == "show":
            print(json.dumps(adapter_contract(), ensure_ascii=False, indent=2))
            return 0
        fixture = _phase4_path(root, fixture_relative, must_exist=True)
        schema = collect_fixture_schema(fixture.read_text(encoding="utf-8"))
        if args.adapter_command == "schema":
            print(json.dumps(schema, ensure_ascii=False, indent=2))
            return 0
        if schema != expected_schema():
            raise ApplicationPackageError(f"{args.adapter_id} schema mismatch")
        print(fixture_schema_sha256(schema))
        return 0
    if args.application_command == "fixture-result":
        value = json.loads(_phase4_path(root, args.result, must_exist=True).read_text(encoding="utf-8"))
        safe = {key:value.get(key) for key in ("adapter_id","contract_version","package_id","authorization_id","status","events")}
        safe["field_count"] = len(value.get("fields", [])) if isinstance(value.get("fields"), list) else 0
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        return 0
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
    if args.application_command == "fill-fixture":
        from .platform_catalog import list_fixture_adapters
        from .adapters.jobkorea_jrs import FixtureMockPage as JobkoreaPage, collect_fixture_schema as jobkorea_schema, run_fixture_fill as jobkorea_fill
        from .adapters.saramin_applyin import FixtureMockPage as SaraminPage, collect_fixture_schema as saramin_schema, run_fixture_fill as saramin_fill
        bindings = {
            "jobkorea_jrs_fixture": (JobkoreaPage, jobkorea_schema, jobkorea_fill, "tests/fixtures/jobkorea_jrs/application_form_v1.html"),
            "saramin_applyin_fixture": (SaraminPage, saramin_schema, saramin_fill, "tests/fixtures/saramin_applyin/application_form_v1.html"),
        }
        if set(bindings) != set(list_fixture_adapters()):
            raise ApplicationPackageError("fixture adapter dispatch mismatch")
        FixtureMockPage, collect_fixture_schema, run_fixture_fill, fixture_relative = bindings[args.adapter]
        signing_key = os.environ.get("CAREER_EXECUTION_SIGNING_KEY", "").encode("utf-8")
        result = load_form_result(_phase4_path(root, args.dry_run_result, must_exist=True))
        authorization = load_authorization(_phase4_path(root, args.authorization, must_exist=True), signing_key)
        values = json.loads(_phase4_path(root, args.values, must_exist=True).read_text(encoding="utf-8"))
        fixture = _phase4_path(root, fixture_relative, must_exist=True)
        page = FixtureMockPage(collect_fixture_schema(fixture.read_text(encoding="utf-8")))
        report = run_fixture_fill(page, values, package, result, authorization, executed_at=args.at,
            ledger_path=_phase4_path(root, args.ledger), signing_key=signing_key)
        write_json(_phase4_path(root, args.output), report)
        print(f"{authorization.authorization_id} {report['status']}")
        return 0
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
    if args.command in {"offline-acceptance", "status"}:
        return run_m5_command(args)
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
        print(
            f"내부검증 {audit['internal_validation_score']}/100 "
            f"{audit['recommendation']} · 제출 상태는 portfolio 품질 게이트에서 별도 확인"
        )
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
