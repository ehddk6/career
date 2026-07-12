"""Pure, versioned readiness contract for the career pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping, TypeAlias


READINESS_SCHEMA_VERSION = "career-pipeline-readiness-v1"
REQUIREMENTS_TRACE_VERSION = "career-pipeline-requirements-trace-v1"


class RequirementClassification(str, Enum):
    IMPLEMENTED = "implemented"
    LOCALLY_MISSING = "locally_missing"
    EXTERNAL_ONLY = "external_only"


class ReadinessAxisName(str, Enum):
    LOCAL_FOUNDATION = "local_foundation"
    OFFLINE_ACCEPTANCE = "offline_acceptance"
    EXTERNAL_INPUTS = "external_inputs"
    LIVE_EXECUTION = "live_execution"
    SUBMISSION = "submission"


class LocalFoundationStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class OfflineAcceptanceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class ExternalInputsStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


class LiveExecutionStatus(str, Enum):
    DISABLED = "disabled"
    REVIEW_REQUIRED = "review_required"
    AUTHORIZED = "authorized"


class SubmissionStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class EvidenceSourceKind(str, Enum):
    CODE = "code"
    TEST = "test"
    ARTIFACT = "artifact"
    DOCUMENT = "document"
    EXTERNAL_ATTESTATION = "external_attestation"


class EvidenceFreshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class BlockerCode(str, Enum):
    ORIGIN_UNCONFIRMED = "ORIGIN_UNCONFIRMED"
    DOM_UNVERIFIED = "DOM_UNVERIFIED"
    AUTOMATION_POLICY_UNCONFIRMED = "AUTOMATION_POLICY_UNCONFIRMED"
    CREDENTIALS_UNAVAILABLE = "CREDENTIALS_UNAVAILABLE"
    MFA_REQUIRED = "MFA_REQUIRED"
    CAPTCHA_PRESENT = "CAPTCHA_PRESENT"
    PII_TRANSMISSION_UNAUTHORIZED = "PII_TRANSMISSION_UNAUTHORIZED"
    UPLOAD_NOT_AUTHORIZED = "UPLOAD_NOT_AUTHORIZED"
    CLICK_NOT_AUTHORIZED = "CLICK_NOT_AUTHORIZED"
    SUBMIT_NOT_AUTHORIZED = "SUBMIT_NOT_AUTHORIZED"
    RECEIPT_UNVERIFIED = "RECEIPT_UNVERIFIED"


AxisStatus: TypeAlias = (
    LocalFoundationStatus
    | OfflineAcceptanceStatus
    | ExternalInputsStatus
    | LiveExecutionStatus
    | SubmissionStatus
)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_kind: EvidenceSourceKind
    source: str
    sha256: str | None
    version: str | None
    observed_at: str | None
    freshness: EvidenceFreshness


@dataclass(frozen=True)
class RequirementRecord:
    requirement_id: str
    axis: ReadinessAxisName
    title: str
    classification: RequirementClassification
    evidence_ids: tuple[str, ...]
    blocker_codes: tuple[BlockerCode, ...] = ()
    cli_exposure: str = "deferred_to_m5"


@dataclass(frozen=True)
class BlockerRecord:
    code: BlockerCode
    axis: ReadinessAxisName
    requirement_id: str
    message: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AxisReadiness:
    axis: ReadinessAxisName
    status: AxisStatus
    requirement_ids: tuple[str, ...]
    blocker_codes: tuple[BlockerCode, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectReadinessReport:
    schema_version: str
    requirements_trace_version: str
    generated_at: str
    axes: tuple[AxisReadiness, ...]
    requirements: tuple[RequirementRecord, ...]
    blockers: tuple[BlockerRecord, ...]
    evidence: tuple[EvidenceRecord, ...]


class ReadinessContractError(ValueError):
    """Raised when a readiness report violates the versioned contract."""


_ID = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{2,79}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AXIS_ORDER = (
    ReadinessAxisName.LOCAL_FOUNDATION,
    ReadinessAxisName.OFFLINE_ACCEPTANCE,
    ReadinessAxisName.EXTERNAL_INPUTS,
    ReadinessAxisName.LIVE_EXECUTION,
    ReadinessAxisName.SUBMISSION,
)
_AXIS_STATUS_TYPES: dict[ReadinessAxisName, type[Enum]] = {
    ReadinessAxisName.LOCAL_FOUNDATION: LocalFoundationStatus,
    ReadinessAxisName.OFFLINE_ACCEPTANCE: OfflineAcceptanceStatus,
    ReadinessAxisName.EXTERNAL_INPUTS: ExternalInputsStatus,
    ReadinessAxisName.LIVE_EXECUTION: LiveExecutionStatus,
    ReadinessAxisName.SUBMISSION: SubmissionStatus,
}


def _fail(message: str) -> None:
    raise ReadinessContractError(message)


def _require_type(value: Any, expected: type, label: str) -> None:
    if not isinstance(value, expected):
        _fail(f"{label} must be {expected.__name__}")


def _validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        _fail(f"{label} must match the readiness ID pattern")
    return value


def _validate_optional_text(value: Any, label: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        _fail(f"{label} must not be empty when present")


def _validate_sha(value: Any, label: str) -> None:
    if value is not None and (not isinstance(value, str) or _SHA256.fullmatch(value) is None):
        _fail(f"{label} must be lowercase SHA-256")


def _validate_timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str):
        _fail(f"{label} must be timezone-aware ISO-8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReadinessContractError(f"{label} must be timezone-aware ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{label} must be timezone-aware ISO-8601")


def _validate_sorted_unique_ids(values: Any, label: str, known: set[str]) -> None:
    if not isinstance(values, tuple):
        _fail(f"{label} must be a tuple")
    for value in values:
        _validate_id(value, f"{label} entry")
        if value not in known:
            _fail(f"{label} references unknown ID: {value}")
    if len(values) != len(set(values)):
        _fail(f"{label} must not contain duplicates")
    if values != tuple(sorted(values)):
        _fail(f"{label} must be sorted")


def _validate_enum(value: Any, enum_type: type[Enum], label: str) -> None:
    if type(value) is not enum_type:
        _fail(f"{label} must use {enum_type.__name__}")


def _normalize_requirement(value: RequirementRecord) -> RequirementRecord:
    if not isinstance(value, RequirementRecord):
        _fail("requirements must contain RequirementRecord values")
    if not isinstance(value.evidence_ids, tuple) or not isinstance(value.blocker_codes, tuple):
        _fail("requirement reference fields must be tuples")
    return RequirementRecord(
        requirement_id=value.requirement_id,
        axis=value.axis,
        title=value.title,
        classification=value.classification,
        evidence_ids=tuple(sorted(value.evidence_ids)),
        blocker_codes=tuple(sorted(value.blocker_codes, key=lambda item: item.value if isinstance(item, BlockerCode) else str(item))),
        cli_exposure=value.cli_exposure,
    )


def _normalize_blocker(value: BlockerRecord) -> BlockerRecord:
    if not isinstance(value, BlockerRecord):
        _fail("blockers must contain BlockerRecord values")
    if not isinstance(value.evidence_ids, tuple):
        _fail("blocker evidence_ids must be a tuple")
    return BlockerRecord(
        code=value.code,
        axis=value.axis,
        requirement_id=value.requirement_id,
        message=value.message,
        evidence_ids=tuple(sorted(value.evidence_ids)),
    )


def _normalize_evidence(value: EvidenceRecord) -> EvidenceRecord:
    if not isinstance(value, EvidenceRecord):
        _fail("evidence must contain EvidenceRecord values")
    return value


def _validate_axis_status(axis: ReadinessAxisName, status: Any) -> None:
    expected = _AXIS_STATUS_TYPES[axis]
    _validate_enum(status, expected, f"{axis.value} axis/status")


def validate_readiness_report(report: ProjectReadinessReport) -> ProjectReadinessReport:
    if not isinstance(report, ProjectReadinessReport):
        _fail("report must be ProjectReadinessReport")
    if report.schema_version != READINESS_SCHEMA_VERSION:
        _fail("unsupported readiness schema version")
    if report.requirements_trace_version != REQUIREMENTS_TRACE_VERSION:
        _fail("unsupported requirements trace version")
    _validate_timestamp(report.generated_at, "generated_at")
    if not isinstance(report.axes, tuple) or not isinstance(report.requirements, tuple) or not isinstance(report.blockers, tuple) or not isinstance(report.evidence, tuple):
        _fail("report collections must be tuples")

    if len(report.axes) != len(_AXIS_ORDER):
        _fail("report must contain exactly five axes")
    axes_by_name: dict[ReadinessAxisName, AxisReadiness] = {}
    for index, axis_record in enumerate(report.axes):
        if not isinstance(axis_record, AxisReadiness):
            _fail("axes must contain AxisReadiness values")
        _validate_enum(axis_record.axis, ReadinessAxisName, "axis")
        if axis_record.axis in axes_by_name:
            _fail("report must contain exactly five axes without duplicates")
        if axis_record.axis != _AXIS_ORDER[index]:
            _fail("axis order must match the readiness contract")
        _validate_axis_status(axis_record.axis, axis_record.status)
        axes_by_name[axis_record.axis] = axis_record

    evidence = {item.evidence_id: item for item in report.evidence}
    if len(evidence) != len(report.evidence):
        _fail("evidence IDs must be unique")
    for item in report.evidence:
        _validate_enum(item.source_kind, EvidenceSourceKind, "evidence source_kind")
        _validate_enum(item.freshness, EvidenceFreshness, "evidence freshness")
        _validate_id(item.evidence_id, "evidence_id")
        _validate_optional_text(item.source, "evidence source")
        _validate_optional_text(item.version, "evidence version")
        _validate_sha(item.sha256, "evidence sha256")
        if item.sha256 is None and item.version is None:
            _fail("evidence must provide sha256 or version")
        if item.freshness in {EvidenceFreshness.CURRENT, EvidenceFreshness.STALE} and item.observed_at is None:
            _fail("evidence freshness requires observed_at")
        if item.freshness is EvidenceFreshness.NOT_APPLICABLE and item.observed_at is not None:
            _fail("not_applicable evidence freshness requires observed_at=None")
        if item.observed_at is not None:
            _validate_timestamp(item.observed_at, "observed_at")
        if item.source_kind is EvidenceSourceKind.ARTIFACT and item.sha256 is None:
            _fail("artifact evidence must provide sha256")
    if tuple(sorted(evidence)) != tuple(item.evidence_id for item in report.evidence):
        _fail("evidence records must be sorted")

    requirements = {item.requirement_id: item for item in report.requirements}
    if len(requirements) != len(report.requirements):
        _fail("requirement IDs must be unique")
    for item in report.requirements:
        _validate_id(item.requirement_id, "requirement_id")
        _validate_enum(item.axis, ReadinessAxisName, "requirement axis")
        _validate_optional_text(item.title, "requirement title")
        _validate_enum(item.classification, RequirementClassification, "requirement classification")
        _validate_optional_text(item.cli_exposure, "requirement cli_exposure")
        _validate_sorted_unique_ids(item.evidence_ids, "requirement evidence_ids", set(evidence))
        if not isinstance(item.blocker_codes, tuple):
            _fail("requirement blocker_codes must be a tuple")
        for code in item.blocker_codes:
            _validate_enum(code, BlockerCode, "requirement blocker code")
        if len(item.blocker_codes) != len(set(item.blocker_codes)):
            _fail("requirement blocker_codes must not contain duplicates")
        if item.blocker_codes != tuple(sorted(item.blocker_codes, key=lambda code: code.value)):
            _fail("requirement blocker_codes must be sorted")
    if tuple(sorted(requirements)) != tuple(item.requirement_id for item in report.requirements):
        _fail("requirement records must be sorted")

    blockers: dict[tuple[str, BlockerCode], BlockerRecord] = {}
    for item in report.blockers:
        _validate_enum(item.code, BlockerCode, "blocker code")
        _validate_enum(item.axis, ReadinessAxisName, "blocker axis")
        _validate_id(item.requirement_id, "blocker requirement_id")
        _validate_optional_text(item.message, "blocker message")
        _validate_sorted_unique_ids(item.evidence_ids, "blocker evidence_ids", set(evidence))
        key = (item.requirement_id, item.code)
        if key in blockers:
            _fail("blocker records must be unique")
        blockers[key] = item
    blocker_sort = tuple((item.code.value, item.requirement_id) for item in report.blockers)
    if blocker_sort != tuple(sorted(blocker_sort)):
        _fail("blocker records must be sorted")

    expected_blockers_by_requirement: dict[str, set[BlockerCode]] = {key: set() for key in requirements}
    for item in report.blockers:
        requirement = requirements.get(item.requirement_id)
        if requirement is None:
            _fail(f"blocker references unknown requirement: {item.requirement_id}")
        if item.axis is not requirement.axis:
            _fail("blocker axis must match requirement axis")
        expected_blockers_by_requirement[item.requirement_id].add(item.code)

    for item in report.requirements:
        record_codes = set(item.blocker_codes)
        blocker_codes = expected_blockers_by_requirement[item.requirement_id]
        if item.classification is RequirementClassification.IMPLEMENTED:
            if record_codes or blocker_codes:
                _fail("implemented requirement must not have blocker")
            evidence_kinds = {evidence[evidence_id].source_kind for evidence_id in item.evidence_ids}
            if not {EvidenceSourceKind.CODE, EvidenceSourceKind.TEST}.issubset(evidence_kinds):
                _fail("implemented evidence must include CODE and TEST")
        elif item.classification is RequirementClassification.LOCALLY_MISSING:
            if record_codes or blocker_codes:
                _fail("locally_missing blocker is not allowed")
        elif item.classification is RequirementClassification.EXTERNAL_ONLY:
            if not record_codes:
                _fail("external_only blocker is required")
            if record_codes != blocker_codes:
                _fail("external_only blocker records must match blocker_codes")
            if any(sum(1 for key in blockers if key == (item.requirement_id, code)) != 1 for code in record_codes):
                _fail("external_only blocker records must contain exactly one record per code")

    expected_axes: dict[ReadinessAxisName, tuple[tuple[str, ...], tuple[BlockerCode, ...], tuple[str, ...]]] = {}
    for axis in _AXIS_ORDER:
        axis_requirements = [item for item in report.requirements if item.axis is axis]
        axis_blockers = [item for item in report.blockers if item.axis is axis]
        requirement_ids = tuple(item.requirement_id for item in axis_requirements)
        blocker_codes = tuple(sorted({item.code for item in axis_blockers}, key=lambda code: code.value))
        evidence_ids = tuple(sorted({evidence_id for item in axis_requirements for evidence_id in item.evidence_ids} | {evidence_id for item in axis_blockers for evidence_id in item.evidence_ids}))
        expected_axes[axis] = (requirement_ids, blocker_codes, evidence_ids)
        actual = axes_by_name[axis]
        if actual.requirement_ids != requirement_ids:
            _fail("axis requirement references do not match requirement records")
        if actual.blocker_codes != blocker_codes:
            _fail("axis blocker references do not match blocker records")
        if actual.evidence_ids != evidence_ids:
            _fail("axis evidence references do not match evidence records")

    local_missing = any(item.classification is RequirementClassification.LOCALLY_MISSING for item in report.requirements if item.axis is ReadinessAxisName.LOCAL_FOUNDATION)
    if axes_by_name[ReadinessAxisName.LOCAL_FOUNDATION].status is LocalFoundationStatus.COMPLETE and local_missing:
        _fail("local_foundation complete requires no locally_missing requirement")

    offline_missing = any(item.classification is RequirementClassification.LOCALLY_MISSING for item in report.requirements if item.axis is ReadinessAxisName.OFFLINE_ACCEPTANCE)
    offline_status = axes_by_name[ReadinessAxisName.OFFLINE_ACCEPTANCE].status
    if offline_status is OfflineAcceptanceStatus.PASSED and any(item.classification is not RequirementClassification.IMPLEMENTED for item in report.requirements if item.axis is ReadinessAxisName.OFFLINE_ACCEPTANCE):
        _fail("offline_acceptance passed requires implemented requirements")
    if offline_missing and offline_status not in {OfflineAcceptanceStatus.NOT_RUN, OfflineAcceptanceStatus.FAILED}:
        _fail("offline_acceptance with locally_missing requirement must be not_run or failed")

    external_blocked = any(item.axis is ReadinessAxisName.EXTERNAL_INPUTS for item in report.blockers)
    external_status = axes_by_name[ReadinessAxisName.EXTERNAL_INPUTS].status
    if external_status is ExternalInputsStatus.READY and external_blocked:
        _fail("external_inputs ready requires no blockers")
    if external_blocked and external_status is not ExternalInputsStatus.BLOCKED:
        _fail("external_inputs with blockers must be blocked")

    live_requirements = [item for item in report.requirements if item.axis is ReadinessAxisName.LIVE_EXECUTION]
    live_blocked = any(item.axis is ReadinessAxisName.LIVE_EXECUTION for item in report.blockers)
    live_status = axes_by_name[ReadinessAxisName.LIVE_EXECUTION].status
    if live_status is LiveExecutionStatus.AUTHORIZED and (live_blocked or any(item.classification is not RequirementClassification.IMPLEMENTED for item in live_requirements)):
        _fail("live_execution authorized requires implemented requirements and no blockers")

    submission_requirements = [item for item in report.requirements if item.axis is ReadinessAxisName.SUBMISSION]
    receipt_blocked = any(item.code is BlockerCode.RECEIPT_UNVERIFIED for item in report.blockers)
    if axes_by_name[ReadinessAxisName.SUBMISSION].status is SubmissionStatus.VERIFIED and (receipt_blocked or any(item.classification is not RequirementClassification.IMPLEMENTED for item in submission_requirements)):
        _fail("submission verified requires implemented requirements and no unverified receipt")
    return report


def build_readiness_report(
    *,
    generated_at: str,
    axis_statuses: Mapping[ReadinessAxisName, AxisStatus],
    requirements: Iterable[RequirementRecord],
    blockers: Iterable[BlockerRecord],
    evidence: Iterable[EvidenceRecord],
) -> ProjectReadinessReport:
    requirement_records = tuple(sorted((_normalize_requirement(item) for item in requirements), key=lambda item: item.requirement_id))
    blocker_records = tuple(sorted((_normalize_blocker(item) for item in blockers), key=lambda item: (item.code.value, item.requirement_id)))
    evidence_records = tuple(sorted((_normalize_evidence(item) for item in evidence), key=lambda item: item.evidence_id))
    if not isinstance(axis_statuses, Mapping):
        _fail("axis_statuses must be a mapping")
    normalized_statuses = dict(axis_statuses)
    if any(type(axis) is not ReadinessAxisName for axis in normalized_statuses):
        _fail("axis_statuses keys must use ReadinessAxisName")
    if set(normalized_statuses) != set(_AXIS_ORDER):
        _fail("axis_statuses must provide exactly the five readiness axes")
    axes = []
    for axis in _AXIS_ORDER:
        axis_requirements = [item for item in requirement_records if item.axis is axis]
        axis_blockers = [item for item in blocker_records if item.axis is axis]
        evidence_ids = sorted({evidence_id for item in axis_requirements for evidence_id in item.evidence_ids} | {evidence_id for item in axis_blockers for evidence_id in item.evidence_ids})
        axes.append(
            AxisReadiness(
                axis=axis,
                status=normalized_statuses[axis],
                requirement_ids=tuple(item.requirement_id for item in axis_requirements),
                blocker_codes=tuple(sorted({item.code for item in axis_blockers}, key=lambda code: code.value)),
                evidence_ids=tuple(evidence_ids),
            )
        )
    return validate_readiness_report(
        ProjectReadinessReport(
            schema_version=READINESS_SCHEMA_VERSION,
            requirements_trace_version=REQUIREMENTS_TRACE_VERSION,
            generated_at=generated_at,
            axes=tuple(axes),
            requirements=requirement_records,
            blockers=blocker_records,
            evidence=evidence_records,
        )
    )


def _record_to_dict(record: EvidenceRecord | RequirementRecord | BlockerRecord | AxisReadiness) -> dict[str, Any]:
    if isinstance(record, EvidenceRecord):
        return {
            "evidence_id": record.evidence_id,
            "source_kind": record.source_kind.value,
            "source": record.source,
            "sha256": record.sha256,
            "version": record.version,
            "observed_at": record.observed_at,
            "freshness": record.freshness.value,
        }
    if isinstance(record, RequirementRecord):
        return {
            "requirement_id": record.requirement_id,
            "axis": record.axis.value,
            "title": record.title,
            "classification": record.classification.value,
            "evidence_ids": list(record.evidence_ids),
            "blocker_codes": [code.value for code in record.blocker_codes],
            "cli_exposure": record.cli_exposure,
        }
    if isinstance(record, BlockerRecord):
        return {
            "code": record.code.value,
            "axis": record.axis.value,
            "requirement_id": record.requirement_id,
            "message": record.message,
            "evidence_ids": list(record.evidence_ids),
        }
    if isinstance(record, AxisReadiness):
        return {
            "axis": record.axis.value,
            "status": record.status.value,
            "requirement_ids": list(record.requirement_ids),
            "blocker_codes": [code.value for code in record.blocker_codes],
            "evidence_ids": list(record.evidence_ids),
        }
    _fail("unsupported readiness record")


def readiness_report_to_dict(report: ProjectReadinessReport) -> dict[str, Any]:
    validate_readiness_report(report)
    return {
        "schema_version": report.schema_version,
        "requirements_trace_version": report.requirements_trace_version,
        "generated_at": report.generated_at,
        "axes": [_record_to_dict(item) for item in report.axes],
        "requirements": [_record_to_dict(item) for item in report.requirements],
        "blockers": [_record_to_dict(item) for item in report.blockers],
        "evidence": [_record_to_dict(item) for item in report.evidence],
    }


def _strict_dict(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    actual = set(value)
    if any(not isinstance(key, str) for key in actual):
        _fail(f"{label} has unknown keys")
    missing = expected - actual
    unknown = actual - expected
    if missing:
        _fail(f"{label} has missing keys: {', '.join(sorted(missing))}")
    if unknown:
        _fail(f"{label} has unknown keys: {', '.join(sorted(unknown))}")
    return value


def _enum_from(enum_type: type[Enum], value: Any, label: str) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ReadinessContractError(f"invalid {label}") from error


def _tuple_from(value: Any, label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        _fail(f"{label} must be a JSON list")
    return tuple(value)


def readiness_report_from_dict(value: Any) -> ProjectReadinessReport:
    top = _strict_dict(value, {"schema_version", "requirements_trace_version", "generated_at", "axes", "requirements", "blockers", "evidence"}, "report")
    try:
        axes = []
        for item in _tuple_from(top["axes"], "axes"):
            data = _strict_dict(item, {"axis", "status", "requirement_ids", "blocker_codes", "evidence_ids"}, "axis")
            axis = _enum_from(ReadinessAxisName, data["axis"], "axis")
            status_type = _AXIS_STATUS_TYPES[axis]
            axes.append(AxisReadiness(axis, _enum_from(status_type, data["status"], "axis status"), tuple(_tuple_from(data["requirement_ids"], "requirement_ids")), tuple(_enum_from(BlockerCode, code, "blocker code") for code in _tuple_from(data["blocker_codes"], "blocker_codes")), tuple(_tuple_from(data["evidence_ids"], "evidence_ids"))))

        requirements = []
        for item in _tuple_from(top["requirements"], "requirements"):
            data = _strict_dict(item, {"requirement_id", "axis", "title", "classification", "evidence_ids", "blocker_codes", "cli_exposure"}, "requirement")
            requirements.append(RequirementRecord(data["requirement_id"], _enum_from(ReadinessAxisName, data["axis"], "requirement axis"), data["title"], _enum_from(RequirementClassification, data["classification"], "requirement classification"), tuple(_tuple_from(data["evidence_ids"], "requirement evidence_ids")), tuple(_enum_from(BlockerCode, code, "requirement blocker code") for code in _tuple_from(data["blocker_codes"], "requirement blocker_codes")), data["cli_exposure"]))

        blockers = []
        for item in _tuple_from(top["blockers"], "blockers"):
            data = _strict_dict(item, {"code", "axis", "requirement_id", "message", "evidence_ids"}, "blocker")
            blockers.append(BlockerRecord(_enum_from(BlockerCode, data["code"], "blocker code"), _enum_from(ReadinessAxisName, data["axis"], "blocker axis"), data["requirement_id"], data["message"], tuple(_tuple_from(data["evidence_ids"], "blocker evidence_ids"))))

        evidence = []
        for item in _tuple_from(top["evidence"], "evidence"):
            data = _strict_dict(item, {"evidence_id", "source_kind", "source", "sha256", "version", "observed_at", "freshness"}, "evidence")
            evidence.append(EvidenceRecord(data["evidence_id"], _enum_from(EvidenceSourceKind, data["source_kind"], "evidence source_kind"), data["source"], data["sha256"], data["version"], data["observed_at"], _enum_from(EvidenceFreshness, data["freshness"], "evidence freshness")))
        return validate_readiness_report(ProjectReadinessReport(top["schema_version"], top["requirements_trace_version"], top["generated_at"], tuple(axes), tuple(requirements), tuple(blockers), tuple(evidence)))
    except ReadinessContractError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ReadinessContractError("invalid readiness report") from error


def canonical_readiness_json(report: ProjectReadinessReport) -> bytes:
    return json.dumps(readiness_report_to_dict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def readiness_report_sha256(report: ProjectReadinessReport) -> str:
    return sha256(canonical_readiness_json(report)).hexdigest()


__all__ = [
    "READINESS_SCHEMA_VERSION", "REQUIREMENTS_TRACE_VERSION", "AxisStatus",
    "RequirementClassification", "ReadinessAxisName", "LocalFoundationStatus",
    "OfflineAcceptanceStatus", "ExternalInputsStatus", "LiveExecutionStatus",
    "SubmissionStatus", "EvidenceSourceKind", "EvidenceFreshness", "BlockerCode",
    "EvidenceRecord", "RequirementRecord", "BlockerRecord", "AxisReadiness",
    "ProjectReadinessReport", "ReadinessContractError", "validate_readiness_report",
    "build_readiness_report", "readiness_report_to_dict", "readiness_report_from_dict",
    "canonical_readiness_json", "readiness_report_sha256",
]
