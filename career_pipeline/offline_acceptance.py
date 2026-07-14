"""Deterministic offline acceptance boundary (M4)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Literal

from .application_execution import (
    ApplicationExecutionError, AuthorizationCandidateV2, approve_application_v2,
    authorize_execution_v2, build_authorization_candidate_v2, canonical_site_contract_sha256,
)
from .application_package import build_application_package
from .artifacts import sha256_file
from .eligibility import applicant_profile_from_ledger, evaluate_eligibility, validate_posting_record
from .form_adapter import FixtureFormDriver, ReviewRequiredFormAdapter
from .models import EligibilityRule, FormAutomationResult, PostingRecord
from .profile_schema import EvidenceRef, Experience, ExperienceLedger, ProfileClaim, ledger_to_dict
from .readiness import (
    BlockerCode, BlockerRecord, EvidenceFreshness, EvidenceRecord, EvidenceSourceKind,
    ExternalInputsStatus, LiveExecutionStatus, LocalFoundationStatus, OfflineAcceptanceStatus,
    ProjectReadinessReport, ReadinessAxisName, RequirementClassification, RequirementRecord,
    SubmissionStatus, build_readiness_report, readiness_report_sha256, readiness_report_to_dict,
)
from .site_intake import build_site_intake


class OfflineAcceptanceError(ValueError):
    pass


@dataclass(frozen=True)
class AcceptanceInputs:
    posting_retrieved_at: str
    profile_generated_at: str
    eligibility_evaluated_at: str
    final_artifact_generated_at: str
    package_created_at: str
    site_observed_at: str
    site_valid_until: str
    review_decided_at: str
    candidate_requested_at: str
    report_generated_at: str
    signing_key: bytes
    key_id: str
    test_evidence_sha256: str
    fixture_scenario: Literal["positive", "sensitive_fixture"] = "positive"
    fixture_html: str | None = None


@dataclass(frozen=True)
class OfflineCallCounters:
    network: int
    browser: int
    credential: int
    pii: int
    upload: int
    click: int
    submit: int


@dataclass(frozen=True)
class OfflineAcceptanceResult:
    schema_version: Literal["career-pipeline-offline-acceptance-v1"]
    run_id: str
    posting_id: str
    profile_id: str
    eligibility_decision_id: str
    final_manifest_sha256: str
    package_id: str
    package_sha256: str
    site_contract_id: str
    site_contract_sha256: str
    review_id: str
    authorization_candidate: AuthorizationCandidateV2
    local_status: Literal["awaiting_external_live_enablement"]
    live_status: Literal["disabled"]
    submission_status: Literal["not_attempted"]
    readiness_report: ProjectReadinessReport
    readiness_sha256: str
    counters: OfflineCallCounters


@dataclass(frozen=True)
class OfflineAcceptanceBlockedResult:
    schema_version: Literal["career-pipeline-offline-acceptance-v1"]
    scenario: Literal["sensitive_fixture"]
    block_code: Literal["blocked_sensitive_fixture"]
    counters: OfflineCallCounters


OfflineAcceptanceOutcome = OfflineAcceptanceResult | OfflineAcceptanceBlockedResult


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _timestamp(value: str, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise OfflineAcceptanceError(f"{label} must be timezone-aware ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfflineAcceptanceError(f"{label} must be timezone-aware ISO-8601")


def _validate_inputs(inputs: AcceptanceInputs) -> None:
    if not isinstance(inputs, AcceptanceInputs):
        raise OfflineAcceptanceError("inputs must be AcceptanceInputs")
    for name in (
        "posting_retrieved_at", "profile_generated_at", "eligibility_evaluated_at",
        "final_artifact_generated_at", "package_created_at", "site_observed_at",
        "site_valid_until", "review_decided_at", "candidate_requested_at", "report_generated_at",
    ):
        _timestamp(getattr(inputs, name), name)
    if datetime.fromisoformat(inputs.site_valid_until.replace("Z", "+00:00")) <= datetime.fromisoformat(inputs.site_observed_at.replace("Z", "+00:00")):
        raise OfflineAcceptanceError("site_valid_until must be later than site_observed_at")
    if not isinstance(inputs.signing_key, bytes) or len(inputs.signing_key) < 32:
        raise OfflineAcceptanceError("signing_key must contain at least 32 bytes")
    if not isinstance(inputs.key_id, str) or not inputs.key_id:
        raise OfflineAcceptanceError("key_id must not be empty")
    if not isinstance(inputs.test_evidence_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", inputs.test_evidence_sha256):
        raise OfflineAcceptanceError("test_evidence_sha256 must be lowercase SHA-256")
    if inputs.fixture_scenario not in {"positive", "sensitive_fixture"}:
        raise OfflineAcceptanceError("fixture_scenario is invalid")
    if inputs.fixture_scenario == "positive" and inputs.fixture_html is not None:
        raise OfflineAcceptanceError("positive fixture_scenario must not provide fixture_html")
    if inputs.fixture_scenario == "sensitive_fixture" and (not isinstance(inputs.fixture_html, str) or not inputs.fixture_html):
        raise OfflineAcceptanceError("sensitive_fixture requires explicit fixture_html")


def _synthetic_profile(inputs: AcceptanceInputs):
    evidence = EvidenceRef("synthetic/experience.txt", 0, "1" * 64, "2" * 64)
    claim = ProfileClaim("employment", "synthetic analyst experience", "confirmed", (evidence,))
    experience = Experience("experience-synthetic", "Analyst", "Synthetic Organization",
        {"start": "2024-01-01", "end": "2025-01-01", "employment_type": "contract"}, "Analyst",
        "Synthetic offline fixture", ("Validated records",), ("Completed offline acceptance input",),
        ("analysis",), (claim,), "confirmed", inputs.profile_generated_at)
    ledger = ExperienceLedger(1, inputs.profile_generated_at, "synthetic-offline", (experience,))
    profile = applicant_profile_from_ledger(ledger, profile_id="profile-synthetic", generated_at=inputs.profile_generated_at)
    return ledger, profile


def _synthetic_posting(inputs: AcceptanceInputs) -> PostingRecord:
    rule = EligibilityRule("rule-experience", "experience", "Synthetic analyst experience", True,
        {"minimum_months": 1, "employment_types": ["contract"]}, "parsed")
    posting = PostingRecord(1, "posting-synthetic", "https://jobs.example.invalid/offline", "jobs.example.invalid",
        "2026-07-01", "2026-12-31", "Synthetic offline posting", "Synthetic Organization", "Analyst",
        "3" * 64, inputs.posting_retrieved_at, "verified_domain", ("synthetic",), (rule,), (),
        canonical_url="https://jobs.example.invalid/offline", timezone="+09:00", status="active")
    return validate_posting_record(posting)


def _write_verified_final_artifact_fixture(workspace: Path, inputs: AcceptanceInputs) -> tuple[Path, dict[str, Any]]:
    run_dir = workspace / "career_runs" / "offline-acceptance"
    run_dir.mkdir(parents=True, exist_ok=True)
    answer = run_dir / "draft_final.json"
    markdown = run_dir / "final.md"
    docx = run_dir / "final.docx"
    answer.write_bytes(_canonical([{"question_index": 1, "answer": "Synthetic verified final answer."}]))
    markdown.write_text("# Synthetic final artifact\n", encoding="utf-8")
    docx.write_bytes(b"PK-synthetic-docx")
    artifact = {
        "generated_at": inputs.final_artifact_generated_at,
        "answer_json_path": answer.name,
        "markdown_path": markdown.name,
        "docx_path": docx.name,
        "sha256": {"answer_json": sha256_file(answer), "markdown": sha256_file(markdown), "docx": sha256_file(docx)},
        "validation": {"status": "passed", "issues": []},
    }
    state = {"status": "complete", "questions": [{"index": 1, "prompt": "Synthetic prompt", "character_limit": 500}], "final_artifact": artifact}
    (run_dir / "run.json").write_bytes(_canonical(state))
    return run_dir, state


def _build_readiness(inputs: AcceptanceInputs) -> ProjectReadinessReport:
    code_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    evidence = (
        EvidenceRecord("EVIDENCE-CODE", EvidenceSourceKind.CODE, "career_pipeline/offline_acceptance.py", code_sha, None, inputs.report_generated_at, EvidenceFreshness.CURRENT),
        EvidenceRecord("EVIDENCE-TEST", EvidenceSourceKind.TEST, "tests/test_offline_acceptance.py", inputs.test_evidence_sha256, None, inputs.report_generated_at, EvidenceFreshness.CURRENT),
        EvidenceRecord("EVIDENCE-EXTERNAL", EvidenceSourceKind.EXTERNAL_ATTESTATION, "external-live-enablement", None, "m4-boundary-v1", inputs.report_generated_at, EvidenceFreshness.UNKNOWN),
    )
    requirements = [
        RequirementRecord("REQ-LOCAL-FOUNDATION", ReadinessAxisName.LOCAL_FOUNDATION, "Offline foundation", RequirementClassification.IMPLEMENTED, ("EVIDENCE-CODE", "EVIDENCE-TEST")),
        RequirementRecord("REQ-OFFLINE-ACCEPTANCE", ReadinessAxisName.OFFLINE_ACCEPTANCE, "Deterministic offline acceptance", RequirementClassification.IMPLEMENTED, ("EVIDENCE-CODE", "EVIDENCE-TEST")),
    ]
    boundaries = (
        ("REQ-ORIGIN", ReadinessAxisName.EXTERNAL_INPUTS, BlockerCode.ORIGIN_UNCONFIRMED),
        ("REQ-DOM", ReadinessAxisName.EXTERNAL_INPUTS, BlockerCode.DOM_UNVERIFIED),
        ("REQ-POLICY", ReadinessAxisName.EXTERNAL_INPUTS, BlockerCode.AUTOMATION_POLICY_UNCONFIRMED),
        ("REQ-CREDENTIALS", ReadinessAxisName.EXTERNAL_INPUTS, BlockerCode.CREDENTIALS_UNAVAILABLE),
        ("REQ-PII", ReadinessAxisName.EXTERNAL_INPUTS, BlockerCode.PII_TRANSMISSION_UNAUTHORIZED),
        ("REQ-UPLOAD", ReadinessAxisName.LIVE_EXECUTION, BlockerCode.UPLOAD_NOT_AUTHORIZED),
        ("REQ-CLICK", ReadinessAxisName.LIVE_EXECUTION, BlockerCode.CLICK_NOT_AUTHORIZED),
        ("REQ-SUBMIT", ReadinessAxisName.LIVE_EXECUTION, BlockerCode.SUBMIT_NOT_AUTHORIZED),
        ("REQ-RECEIPT", ReadinessAxisName.SUBMISSION, BlockerCode.RECEIPT_UNVERIFIED),
    )
    requirements.extend(RequirementRecord(requirement_id, axis, code.value, RequirementClassification.EXTERNAL_ONLY, ("EVIDENCE-EXTERNAL",), (code,)) for requirement_id, axis, code in boundaries)
    blockers = tuple(BlockerRecord(code, axis, requirement_id, f"{code.value} remains externally unverified", ("EVIDENCE-EXTERNAL",)) for requirement_id, axis, code in boundaries)
    return build_readiness_report(generated_at=inputs.report_generated_at, axis_statuses={
        ReadinessAxisName.LOCAL_FOUNDATION: LocalFoundationStatus.COMPLETE,
        ReadinessAxisName.OFFLINE_ACCEPTANCE: OfflineAcceptanceStatus.PASSED,
        ReadinessAxisName.EXTERNAL_INPUTS: ExternalInputsStatus.BLOCKED,
        ReadinessAxisName.LIVE_EXECUTION: LiveExecutionStatus.DISABLED,
        ReadinessAxisName.SUBMISSION: SubmissionStatus.NOT_ATTEMPTED,
    }, requirements=requirements, blockers=blockers, evidence=evidence)


def run_offline_acceptance(*, workspace: Path, inputs: AcceptanceInputs) -> OfflineAcceptanceOutcome:
    _validate_inputs(inputs)
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    ledger, profile = _synthetic_profile(inputs)
    posting = _synthetic_posting(inputs)
    decision = evaluate_eligibility(profile, posting, evaluated_at=inputs.eligibility_evaluated_at)
    if decision.status != "eligible" or decision.human_review_required:
        raise OfflineAcceptanceError("synthetic eligibility fixture must be eligible")
    run_dir, run_state = _write_verified_final_artifact_fixture(workspace, inputs)
    private_data = workspace / "private.json"
    private_data.write_bytes(_canonical({"schema_version": 1, "fields": {"full_name": "Synthetic Applicant"}}))
    profile_sha = _digest(ledger_to_dict(ledger))
    package = build_application_package(root=workspace, run_dir=run_dir, run_state=run_state, profile=profile,
        posting=posting, decision=decision, private_data_path=private_data, profile_sha256=profile_sha,
        created_at=inputs.package_created_at)
    if package.validation_status != "ready_for_review":
        raise OfflineAcceptanceError("synthetic package must be ready_for_review")
    html = inputs.fixture_html if inputs.fixture_html is not None else "<form id='application' action='/submit' method='post'><button id='save' type='button' data-role='save'>Save</button><button id='submit' type='submit'>Submit</button></form>"
    fixture = workspace / "offline-safe.html"
    fixture.write_text(html, encoding="utf-8")
    fixture_url = "https://company.applyin.co.kr/apply"
    _, adapter_schema = ReviewRequiredFormAdapter().probe_contract(FixtureFormDriver(html, url=fixture_url))
    intake = build_site_intake(posting_url=None, resolved_application_url=fixture_url, fixture_root=workspace,
        fixture_resource_id=fixture.name, discovery_platform_id=None, created_at=inputs.site_observed_at,
        valid_until=inputs.site_valid_until, known_structure={"login_status": "none", "mfa_status": "none", "captcha_status": "none", "iframe_status": "none", "popup_status": "none", "redirect_status": "none", "attachment_status": "unsupported"},
        adapter_schema_sha256=adapter_schema)
    counters = OfflineCallCounters(0, 0, 0, 0, 0, 0, 0)
    if inputs.fixture_scenario == "sensitive_fixture":
        if intake.record.contract_status != "blocked_sensitive_fixture" or intake.contract is not None:
            raise OfflineAcceptanceError("sensitive fixture must fail closed")
        return OfflineAcceptanceBlockedResult("career-pipeline-offline-acceptance-v1", "sensitive_fixture", "blocked_sensitive_fixture", counters)
    if intake.contract is None:
        raise OfflineAcceptanceError("synthetic site intake must produce a disabled contract")
    contract = intake.contract
    if contract.allowed_capabilities or contract.mutation_enabled or contract.live_enabled:
        raise OfflineAcceptanceError("offline contract must remain disabled")
    dry_result = FormAutomationResult(1, "form-offline", package.package_id, "review_required", inputs.site_observed_at,
        inputs.site_observed_at, "review_required", None, fixture_url, False, False, True, adapter_schema, True, (), (), ())
    review = approve_application_v2(package, dry_result, contract, decision="approved", decided_at=inputs.review_decided_at,
        approver_id="offline-reviewer", key_id=inputs.key_id, signing_key=inputs.signing_key)
    candidate = build_authorization_candidate_v2(package, review, contract, adapter_id=contract.adapter_id,
        adapter_contract_version=contract.adapter_contract_version, adapter_schema_sha256=contract.adapter_schema_sha256,
        allowed_origin=contract.exact_origin, mode="fill_only", requested_at=inputs.candidate_requested_at)
    if candidate.candidate_status != "capability_disabled" or candidate.reason_code != "FILL_AUTHORITY_DISABLED":
        raise OfflineAcceptanceError("offline authorization candidate must remain disabled")
    try:
        authorize_execution_v2(package, review, contract, adapter_id=contract.adapter_id,
            adapter_contract_version=contract.adapter_contract_version, adapter_schema_sha256=contract.adapter_schema_sha256,
            allowed_origin=contract.exact_origin, mode="fill_only", authorized_at=inputs.candidate_requested_at,
            expires_at=inputs.site_valid_until, approver_id="offline-reviewer", key_id=inputs.key_id, signing_key=inputs.signing_key)
    except ApplicationExecutionError as error:
        if str(error) != "FILL_AUTHORITY_DISABLED":
            raise
    else:
        raise OfflineAcceptanceError("offline acceptance must not issue execution authorization")
    readiness = _build_readiness(inputs)
    return OfflineAcceptanceResult("career-pipeline-offline-acceptance-v1", "offline-acceptance-" + _digest({"posting": posting.posting_id, "profile": profile.profile_id})[:24],
        posting.posting_id, profile.profile_id, decision.decision_id, package.final_manifest_sha256, package.package_id,
        _digest(asdict(package)), contract.contract_id, canonical_site_contract_sha256(contract), review.review_id, candidate,
        "awaiting_external_live_enablement", "disabled", "not_attempted", readiness, readiness_report_sha256(readiness), counters)


def offline_acceptance_to_dict(result: OfflineAcceptanceOutcome) -> dict[str, Any]:
    if isinstance(result, OfflineAcceptanceBlockedResult):
        return {"schema_version": result.schema_version, "scenario": result.scenario, "block_code": result.block_code, "counters": asdict(result.counters)}
    if not isinstance(result, OfflineAcceptanceResult):
        raise OfflineAcceptanceError("result must be an offline acceptance outcome")
    return {
        "schema_version": result.schema_version,
        "run_id": result.run_id,
        "posting_id": result.posting_id,
        "profile_id": result.profile_id,
        "eligibility_decision_id": result.eligibility_decision_id,
        "final_manifest_sha256": result.final_manifest_sha256,
        "package_id": result.package_id,
        "package_sha256": result.package_sha256,
        "site_contract_id": result.site_contract_id,
        "site_contract_sha256": result.site_contract_sha256,
        "review_id": result.review_id,
        "authorization_candidate": asdict(result.authorization_candidate),
        "local_status": result.local_status,
        "live_status": result.live_status,
        "submission_status": result.submission_status,
        "readiness_sha256": result.readiness_sha256,
        "readiness_report": readiness_report_to_dict(result.readiness_report),
        "counters": asdict(result.counters),
    }
