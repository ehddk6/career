from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from career_pipeline.readiness import (
    READINESS_SCHEMA_VERSION,
    REQUIREMENTS_TRACE_VERSION,
    AxisReadiness,
    BlockerCode,
    BlockerRecord,
    EvidenceFreshness,
    EvidenceRecord,
    EvidenceSourceKind,
    ExternalInputsStatus,
    LiveExecutionStatus,
    LocalFoundationStatus,
    OfflineAcceptanceStatus,
    ProjectReadinessReport,
    ReadinessAxisName,
    ReadinessContractError,
    RequirementClassification,
    RequirementRecord,
    SubmissionStatus,
    build_readiness_report,
    canonical_readiness_json,
    readiness_report_from_dict,
    readiness_report_sha256,
    readiness_report_to_dict,
    validate_readiness_report,
)


GENERATED_AT = "2026-07-12T18:00:00+09:00"
FIXTURE_SHA256 = "a" * 64


def make_report() -> ProjectReadinessReport:
    evidence = (
        EvidenceRecord(
            evidence_id="EVIDENCE-EXTERNAL",
            source_kind=EvidenceSourceKind.EXTERNAL_ATTESTATION,
            source="external-attestation",
            sha256=None,
            version="attestation-v1",
            observed_at=GENERATED_AT,
            freshness=EvidenceFreshness.UNKNOWN,
        ),
        EvidenceRecord(
            evidence_id="EVIDENCE-DOC",
            source_kind=EvidenceSourceKind.DOCUMENT,
            source="docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md",
            sha256=FIXTURE_SHA256,
            version="career-pipeline-requirements-trace-v1",
            observed_at=GENERATED_AT,
            freshness=EvidenceFreshness.CURRENT,
        ),
        EvidenceRecord(
            evidence_id="EVIDENCE-TEST",
            source_kind=EvidenceSourceKind.TEST,
            source="tests/test_readiness.py",
            sha256=FIXTURE_SHA256,
            version=None,
            observed_at=GENERATED_AT,
            freshness=EvidenceFreshness.CURRENT,
        ),
        EvidenceRecord(
            evidence_id="EVIDENCE-CODE",
            source_kind=EvidenceSourceKind.CODE,
            source="career_pipeline/readiness.py",
            sha256=FIXTURE_SHA256,
            version=None,
            observed_at=GENERATED_AT,
            freshness=EvidenceFreshness.CURRENT,
        ),
    )

    requirements = (
        RequirementRecord(
            requirement_id="REQ-READINESS-CONTRACT",
            axis=ReadinessAxisName.LOCAL_FOUNDATION,
            title="Versioned readiness contract",
            classification=RequirementClassification.IMPLEMENTED,
            evidence_ids=("EVIDENCE-TEST", "EVIDENCE-CODE"),
        ),
        RequirementRecord(
            requirement_id="REQ-OFFLINE-ACCEPTANCE",
            axis=ReadinessAxisName.OFFLINE_ACCEPTANCE,
            title="Offline acceptance runner",
            classification=RequirementClassification.LOCALLY_MISSING,
            evidence_ids=("EVIDENCE-DOC",),
        ),
        RequirementRecord(
            requirement_id="REQ-CAPTCHA",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="CAPTCHA state",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.CAPTCHA_PRESENT,),
        ),
        RequirementRecord(
            requirement_id="REQ-CLICK",
            axis=ReadinessAxisName.LIVE_EXECUTION,
            title="Click authorization",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.CLICK_NOT_AUTHORIZED,),
        ),
        RequirementRecord(
            requirement_id="REQ-CREDENTIALS",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="Credentials availability",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.CREDENTIALS_UNAVAILABLE,),
        ),
        RequirementRecord(
            requirement_id="REQ-DOM",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="DOM verification",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.DOM_UNVERIFIED,),
        ),
        RequirementRecord(
            requirement_id="REQ-LIVE-EXECUTION",
            axis=ReadinessAxisName.LIVE_EXECUTION,
            title="Live execution boundary",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(
                BlockerCode.ORIGIN_UNCONFIRMED,
                BlockerCode.DOM_UNVERIFIED,
                BlockerCode.AUTOMATION_POLICY_UNCONFIRMED,
                BlockerCode.CREDENTIALS_UNAVAILABLE,
                BlockerCode.PII_TRANSMISSION_UNAUTHORIZED,
            ),
        ),
        RequirementRecord(
            requirement_id="REQ-MFA",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="MFA state",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.MFA_REQUIRED,),
        ),
        RequirementRecord(
            requirement_id="REQ-ORIGIN",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="Origin verification",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.ORIGIN_UNCONFIRMED,),
        ),
        RequirementRecord(
            requirement_id="REQ-PII-AUTHORITY",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="PII transmission authority",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.PII_TRANSMISSION_UNAUTHORIZED,),
        ),
        RequirementRecord(
            requirement_id="REQ-POLICY",
            axis=ReadinessAxisName.EXTERNAL_INPUTS,
            title="Automation policy confirmation",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.AUTOMATION_POLICY_UNCONFIRMED,),
        ),
        RequirementRecord(
            requirement_id="REQ-RECEIPT",
            axis=ReadinessAxisName.SUBMISSION,
            title="Submission receipt",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.RECEIPT_UNVERIFIED,),
        ),
        RequirementRecord(
            requirement_id="REQ-SUBMIT",
            axis=ReadinessAxisName.LIVE_EXECUTION,
            title="Submit authorization",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.SUBMIT_NOT_AUTHORIZED,),
        ),
        RequirementRecord(
            requirement_id="REQ-UPLOAD",
            axis=ReadinessAxisName.LIVE_EXECUTION,
            title="Upload authorization",
            classification=RequirementClassification.EXTERNAL_ONLY,
            evidence_ids=("EVIDENCE-EXTERNAL",),
            blocker_codes=(BlockerCode.UPLOAD_NOT_AUTHORIZED,),
        ),
    )

    blocker_specs = (
        ("REQ-UPLOAD", BlockerCode.UPLOAD_NOT_AUTHORIZED),
        ("REQ-LIVE-EXECUTION", BlockerCode.PII_TRANSMISSION_UNAUTHORIZED),
        ("REQ-CREDENTIALS", BlockerCode.CREDENTIALS_UNAVAILABLE),
        ("REQ-RECEIPT", BlockerCode.RECEIPT_UNVERIFIED),
        ("REQ-DOM", BlockerCode.DOM_UNVERIFIED),
        ("REQ-LIVE-EXECUTION", BlockerCode.DOM_UNVERIFIED),
        ("REQ-POLICY", BlockerCode.AUTOMATION_POLICY_UNCONFIRMED),
        ("REQ-MFA", BlockerCode.MFA_REQUIRED),
        ("REQ-CLICK", BlockerCode.CLICK_NOT_AUTHORIZED),
        ("REQ-ORIGIN", BlockerCode.ORIGIN_UNCONFIRMED),
        ("REQ-LIVE-EXECUTION", BlockerCode.ORIGIN_UNCONFIRMED),
        ("REQ-CAPTCHA", BlockerCode.CAPTCHA_PRESENT),
        ("REQ-PII-AUTHORITY", BlockerCode.PII_TRANSMISSION_UNAUTHORIZED),
        ("REQ-LIVE-EXECUTION", BlockerCode.AUTOMATION_POLICY_UNCONFIRMED),
        ("REQ-SUBMIT", BlockerCode.SUBMIT_NOT_AUTHORIZED),
        ("REQ-LIVE-EXECUTION", BlockerCode.CREDENTIALS_UNAVAILABLE),
    )
    blockers = tuple(
        BlockerRecord(
            code=code,
            axis=next(item.axis for item in requirements if item.requirement_id == requirement_id),
            requirement_id=requirement_id,
            message=f"{code.value} is not confirmed",
            evidence_ids=("EVIDENCE-EXTERNAL",),
        )
        for requirement_id, code in blocker_specs
    )

    return build_readiness_report(
        generated_at=GENERATED_AT,
        axis_statuses={
            ReadinessAxisName.LOCAL_FOUNDATION: LocalFoundationStatus.COMPLETE,
            ReadinessAxisName.OFFLINE_ACCEPTANCE: OfflineAcceptanceStatus.NOT_RUN,
            ReadinessAxisName.EXTERNAL_INPUTS: ExternalInputsStatus.BLOCKED,
            ReadinessAxisName.LIVE_EXECUTION: LiveExecutionStatus.DISABLED,
            ReadinessAxisName.SUBMISSION: SubmissionStatus.NOT_ATTEMPTED,
        },
        requirements=requirements,
        blockers=blockers,
        evidence=evidence,
    )


def test_contract_enums_are_stable():
    assert READINESS_SCHEMA_VERSION == "career-pipeline-readiness-v1"
    assert REQUIREMENTS_TRACE_VERSION == "career-pipeline-requirements-trace-v1"
    assert [item.value for item in RequirementClassification] == [
        "implemented", "locally_missing", "external_only"
    ]
    assert [item.value for item in ReadinessAxisName] == [
        "local_foundation", "offline_acceptance", "external_inputs", "live_execution", "submission"
    ]
    assert [item.value for item in BlockerCode] == [
        "ORIGIN_UNCONFIRMED", "DOM_UNVERIFIED", "AUTOMATION_POLICY_UNCONFIRMED",
        "CREDENTIALS_UNAVAILABLE", "MFA_REQUIRED", "CAPTCHA_PRESENT",
        "PII_TRANSMISSION_UNAUTHORIZED", "UPLOAD_NOT_AUTHORIZED", "CLICK_NOT_AUTHORIZED",
        "SUBMIT_NOT_AUTHORIZED", "RECEIPT_UNVERIFIED",
    ]


def test_report_serialization_is_versioned_canonical_and_has_no_ready_boolean():
    report = make_report()
    payload = readiness_report_to_dict(report)

    assert set(payload) == {"schema_version", "requirements_trace_version", "generated_at", "axes", "requirements", "blockers", "evidence"}
    assert payload["schema_version"] == READINESS_SCHEMA_VERSION
    assert "ready" not in payload
    assert isinstance(payload["axes"], list)
    assert payload["axes"][0]["axis"] == "local_foundation"
    assert canonical_readiness_json(report) == json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert b"\n" not in canonical_readiness_json(report)


def test_report_round_trip_preserves_enum_and_tuple_types():
    restored = readiness_report_from_dict(readiness_report_to_dict(make_report()))

    assert restored == make_report()
    assert isinstance(restored.axes, tuple)
    assert isinstance(restored.axes[0], AxisReadiness)
    assert isinstance(restored.axes[0].axis, ReadinessAxisName)
    assert isinstance(restored.axes[0].requirement_ids, tuple)
    assert isinstance(restored.requirements[0].classification, RequirementClassification)
    assert isinstance(restored.blockers[0].code, BlockerCode)
    assert isinstance(restored.evidence[0].freshness, EvidenceFreshness)


def test_report_sha256_matches_canonical_bytes():
    report = make_report()

    assert readiness_report_sha256(report) == sha256(canonical_readiness_json(report)).hexdigest()


def test_report_rejects_missing_duplicate_or_misordered_axes():
    report = make_report()
    with pytest.raises(ReadinessContractError, match="exactly five axes"):
        validate_readiness_report(replace(report, axes=report.axes[:-1]))
    with pytest.raises(ReadinessContractError, match="exactly five axes"):
        validate_readiness_report(replace(report, axes=report.axes[:-1] + (report.axes[0],)))
    with pytest.raises(ReadinessContractError, match="axis order"):
        validate_readiness_report(replace(report, axes=(report.axes[1], report.axes[0], *report.axes[2:])))


def test_report_rejects_status_from_another_axis():
    report = make_report()
    invalid_axis = replace(report.axes[0], status=OfflineAcceptanceStatus.PASSED)

    with pytest.raises(ReadinessContractError, match="axis/status"):
        validate_readiness_report(replace(report, axes=(invalid_axis, *report.axes[1:])))


def test_deserializer_rejects_unknown_and_missing_keys():
    payload = readiness_report_to_dict(make_report())
    unknown = dict(payload)
    unknown["ready"] = True
    with pytest.raises(ReadinessContractError, match="unknown keys"):
        readiness_report_from_dict(unknown)

    missing = dict(payload)
    del missing["axes"]
    with pytest.raises(ReadinessContractError, match="missing keys"):
        readiness_report_from_dict(missing)


def test_builder_sorts_records_and_derives_axis_references():
    report = make_report()

    assert tuple(item.requirement_id for item in report.requirements) == tuple(
        sorted(item.requirement_id for item in report.requirements)
    )
    assert tuple(item.evidence_id for item in report.evidence) == (
        "EVIDENCE-CODE", "EVIDENCE-DOC", "EVIDENCE-EXTERNAL", "EVIDENCE-TEST"
    )
    blocker_pairs = tuple((item.requirement_id, item.code.value) for item in report.blockers)
    assert blocker_pairs == tuple(sorted(blocker_pairs, key=lambda item: (item[1], item[0])))
    assert report.axes[0].requirement_ids == ("REQ-READINESS-CONTRACT",)
    assert report.axes[1].requirement_ids == ("REQ-OFFLINE-ACCEPTANCE",)
    assert report.axes[2].requirement_ids == (
        "REQ-CAPTCHA", "REQ-CREDENTIALS", "REQ-DOM", "REQ-MFA", "REQ-ORIGIN", "REQ-PII-AUTHORITY", "REQ-POLICY"
    )
    assert report.axes[3].requirement_ids == ("REQ-CLICK", "REQ-LIVE-EXECUTION", "REQ-SUBMIT", "REQ-UPLOAD")
    assert report.axes[4].requirement_ids == ("REQ-RECEIPT",)
    assert report.axes[3].blocker_codes == (
        BlockerCode.AUTOMATION_POLICY_UNCONFIRMED,
        BlockerCode.CLICK_NOT_AUTHORIZED,
        BlockerCode.CREDENTIALS_UNAVAILABLE,
        BlockerCode.DOM_UNVERIFIED,
        BlockerCode.ORIGIN_UNCONFIRMED,
        BlockerCode.PII_TRANSMISSION_UNAUTHORIZED,
        BlockerCode.SUBMIT_NOT_AUTHORIZED,
        BlockerCode.UPLOAD_NOT_AUTHORIZED,
    )


def test_implemented_requires_code_and_test_evidence_and_no_blocker():
    report = make_report()
    requirements = tuple(
        replace(item, evidence_ids=("EVIDENCE-CODE",))
        if item.requirement_id == "REQ-READINESS-CONTRACT" else item
        for item in report.requirements
    )
    axes = tuple(
        replace(item, evidence_ids=("EVIDENCE-CODE",))
        if item.axis is ReadinessAxisName.LOCAL_FOUNDATION else item
        for item in report.axes
    )

    with pytest.raises(ReadinessContractError, match="implemented evidence"):
        validate_readiness_report(replace(report, requirements=requirements, axes=axes))


def test_locally_missing_cannot_use_external_blockers():
    report = make_report()
    requirements = tuple(
        replace(item, blocker_codes=(BlockerCode.CAPTCHA_PRESENT,))
        if item.requirement_id == "REQ-OFFLINE-ACCEPTANCE" else item
        for item in report.requirements
    )
    blockers = tuple(sorted(report.blockers + (
        BlockerRecord(
            code=BlockerCode.CAPTCHA_PRESENT,
            axis=ReadinessAxisName.OFFLINE_ACCEPTANCE,
            requirement_id="REQ-OFFLINE-ACCEPTANCE",
            message="external blocker",
            evidence_ids=("EVIDENCE-EXTERNAL",),
        ),
    ), key=lambda item: (item.code.value, item.requirement_id)))
    axes = tuple(
        replace(item, blocker_codes=(BlockerCode.CAPTCHA_PRESENT,), evidence_ids=("EVIDENCE-DOC", "EVIDENCE-EXTERNAL"))
        if item.axis is ReadinessAxisName.OFFLINE_ACCEPTANCE else item
        for item in report.axes
    )

    with pytest.raises(ReadinessContractError, match="locally_missing blocker"):
        validate_readiness_report(replace(report, requirements=requirements, blockers=blockers, axes=axes))


def test_external_only_requires_matching_stable_blocker_records():
    report = make_report()
    blockers = tuple(
        item for item in report.blockers
        if not (item.requirement_id == "REQ-CAPTCHA" and item.code is BlockerCode.CAPTCHA_PRESENT)
    )
    axes = tuple(
        replace(item, blocker_codes=tuple(code for code in item.blocker_codes if code is not BlockerCode.CAPTCHA_PRESENT))
        if item.axis is ReadinessAxisName.EXTERNAL_INPUTS else item
        for item in report.axes
    )

    with pytest.raises(ReadinessContractError, match="external_only blocker"):
        validate_readiness_report(replace(report, blockers=blockers, axes=axes))


def test_evidence_requires_source_sha_or_version_and_valid_freshness():
    report = make_report()
    evidence = tuple(
        replace(item, observed_at=None)
        if item.evidence_id == "EVIDENCE-CODE" else item
        for item in report.evidence
    )

    with pytest.raises(ReadinessContractError, match="evidence freshness"):
        validate_readiness_report(replace(report, evidence=evidence))


def test_aggregate_test_counts_are_rejected_as_readiness_inputs():
    payload = readiness_report_to_dict(make_report())
    payload["test_count"] = 425
    with pytest.raises(ReadinessContractError):
        readiness_report_from_dict(payload)


def test_requirements_trace_matches_contract_and_defers_cli_to_m5():
    path = Path(__file__).parents[1] / "docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md"
    text = path.read_text(encoding="utf-8")
    expected_ids = [
        "REQ-CAPTCHA", "REQ-CLICK", "REQ-CREDENTIALS", "REQ-DOM", "REQ-LIVE-EXECUTION",
        "REQ-MFA", "REQ-OFFLINE-ACCEPTANCE", "REQ-ORIGIN", "REQ-PII-AUTHORITY", "REQ-POLICY",
        "REQ-READINESS-CONTRACT", "REQ-RECEIPT", "REQ-SUBMIT", "REQ-UPLOAD",
    ]
    blocker_codes = [item.value for item in BlockerCode]

    assert "Schema: career-pipeline-readiness-v1" in text
    assert "Trace version: career-pipeline-requirements-trace-v1" in text
    assert "CLI exposure: deferred_to_m5" in text
    assert "Live boundary: disabled; no network, browser, credentials, real PII, upload, click, or submit" in text
    assert "| requirement_id | axis | classification | implementation_paths | test_ids | artifact_sources | cli_exposure | blocker_codes | rationale |" in text
    rows = [line for line in text.splitlines() if line.startswith("| REQ-")]
    assert [line.split("|")[1].strip() for line in rows] == expected_ids
    assert all(text.count(requirement_id) >= 1 for requirement_id in expected_ids)
    assert all(code in text for code in blocker_codes)
    assert text.count("deferred_to_m5") >= len(expected_ids)
    assert "local_foundation=complete" in text
    assert "offline_acceptance=not_run" in text
    assert "external_inputs=blocked" in text
    assert "live_execution=disabled" in text
    assert "submission=not_attempted" in text
    assert "python -m career_pipeline" not in text

    payload = readiness_report_to_dict(make_report())
    payload["evidence"][0]["passed_count"] = 425
    with pytest.raises(ReadinessContractError):
        readiness_report_from_dict(payload)
