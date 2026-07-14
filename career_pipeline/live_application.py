"""Fail-closed contracts for user-confirmed live application browser actions.

This module deliberately has no browser dependency.  A browser bridge implements
``LiveBrowserDriver`` and receives private values only in memory.  Plans and
ledgers contain hashes and lengths, never the values themselves.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
from pathlib import Path
import re
from typing import Literal, Mapping, Protocol
from urllib.parse import urlsplit

from .models import ApplicationPackage
from .origin_policy import normalize_origin, origin_from_url
from .path_policy import LockAcquisitionError, exclusive_lock
from .state import write_json

LIVE_CONTRACT_VERSION = "live-application-v1"
LIVE_SIGNATURE_VERSION = "hmac-sha256-live-v1"


class LiveApplicationError(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise LiveApplicationError("timestamp must be timezone-aware") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise LiveApplicationError("timestamp must be timezone-aware")
    return result


def _sign(value: object, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise LiveApplicationError("signing key must be at least 32 bytes")
    return hmac.new(key, _canonical(value), sha256).hexdigest()


def _package_sha256(package: ApplicationPackage) -> str:
    return _digest(asdict(package))


def _attachment_manifest_sha256(package: ApplicationPackage) -> str:
    return _digest([asdict(item) for item in package.attachments])


@dataclass(frozen=True)
class LiveFieldAction:
    logical_id: str
    locator_kind: Literal["id", "name", "label", "role"]
    locator_value: str
    action: Literal["fill", "select", "check", "upload"]
    private_value_key: str
    expected_type: str
    required: bool = True
    max_length: int | None = None
    allowed_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class LiveConditionalValue:
    private_value_key: str
    controller_key: str
    trigger_value: str
    required_when_triggered: bool
    empty_otherwise: bool


@dataclass(frozen=True)
class LiveActionPlan:
    schema_version: Literal[1]
    plan_id: str
    adapter_id: str
    adapter_version: int
    exact_origin: str
    exact_path: str
    form_action_origin: str
    form_schema_sha256: str
    actions: tuple[LiveFieldAction, ...]
    matching_value_pairs: tuple[tuple[str, str], ...]
    conditional_values: tuple[LiveConditionalValue, ...]
    submit_locator_kind: Literal["id", "name", "label", "role"]
    submit_locator_value: str
    created_at: str


@dataclass(frozen=True)
class LiveExecutionGrant:
    schema_version: Literal[1]
    grant_id: str
    package_id: str
    package_sha256: str
    posting_sha256: str
    profile_sha256: str
    final_manifest_sha256: str
    attachment_manifest_sha256: str
    plan_sha256: str
    exact_origin: str
    mode: Literal["fill_only", "submit"]
    approval_actor: str
    issued_at: str
    expires_at: str
    nonce: str
    contract_version: Literal["live-application-v1"]
    key_id: str
    signature_version: Literal["hmac-sha256-live-v1"]
    integrity_sha256: str


@dataclass(frozen=True)
class LiveExecutionResult:
    schema_version: Literal[1]
    execution_id: str
    grant_id: str
    package_id: str
    mode: Literal["fill_only", "submit"]
    status: Literal["filled_verified", "fill_unverified", "awaiting_final_confirmation", "submitted_verified", "submission_unverified"]
    executed_at: str
    verified_fields: tuple[str, ...]
    receipt_fingerprint: str | None = None
    completion_origin: str | None = None
    reason_code: str | None = None


class LiveBrowserDriver(Protocol):
    def current_url(self) -> str: ...
    def form_action_url(self) -> str: ...
    def current_form_schema_sha256(self) -> str: ...
    def security_markers(self) -> tuple[str, ...]: ...
    def fill(self, action: LiveFieldAction, value: str) -> None: ...
    def select(self, action: LiveFieldAction, value: str) -> None: ...
    def check(self, action: LiveFieldAction, value: str) -> None: ...
    def upload(self, action: LiveFieldAction, path: Path) -> None: ...
    def verify(self, action: LiveFieldAction, expected_sha256: str) -> bool: ...
    def submit(self, locator_kind: str, locator_value: str) -> None: ...
    def submission_evidence(self) -> tuple[str | None, str | None]: ...


def plan_sha256(plan: LiveActionPlan) -> str:
    _validate_plan(plan)
    return _digest(asdict(plan))


def live_plan_from_dict(value: Mapping) -> LiveActionPlan:
    try:
        actions = tuple(LiveFieldAction(**item) for item in value["actions"])
        conditions = tuple(LiveConditionalValue(**item) for item in value["conditional_values"])
        plan = LiveActionPlan(**{**value, "actions": actions, "conditional_values": conditions})
    except (KeyError, TypeError, ValueError) as error:
        raise LiveApplicationError("invalid live action plan document") from error
    _validate_plan(plan)
    return plan


def live_grant_from_dict(value: Mapping, *, signing_key: bytes) -> LiveExecutionGrant:
    try:
        grant = LiveExecutionGrant(**value)
    except (TypeError, ValueError) as error:
        raise LiveApplicationError("invalid live grant document") from error
    if not hmac.compare_digest(grant.integrity_sha256, _sign(grant_payload(grant), signing_key)):
        raise LiveApplicationError("live grant integrity check failed")
    return grant


def _validate_plan(plan: LiveActionPlan) -> None:
    if not isinstance(plan, LiveActionPlan) or plan.schema_version != 1 or plan.adapter_version < 1:
        raise LiveApplicationError("invalid live action plan")
    if normalize_origin(plan.exact_origin) != plan.exact_origin:
        raise LiveApplicationError("plan origin must be canonical HTTPS")
    if origin_from_url(plan.form_action_origin) != plan.exact_origin:
        raise LiveApplicationError("cross-origin form action is forbidden")
    if not plan.exact_path.startswith("/") or "?" in plan.exact_path or "#" in plan.exact_path:
        raise LiveApplicationError("invalid exact path")
    if not re.fullmatch(r"[0-9a-f]{64}", plan.form_schema_sha256):
        raise LiveApplicationError("invalid form schema SHA")
    _timestamp(plan.created_at)
    identifiers = [action.logical_id for action in plan.actions]
    if len(identifiers) != len(set(identifiers)):
        raise LiveApplicationError("duplicate logical field")
    private_keys = {action.private_value_key for action in plan.actions}
    if any(left not in private_keys or right not in private_keys or left == right for left, right in plan.matching_value_pairs):
        raise LiveApplicationError("invalid matching value pair")
    if any(item.private_value_key not in private_keys or item.controller_key not in private_keys for item in plan.conditional_values):
        raise LiveApplicationError("invalid conditional value")


def grant_payload(grant: LiveExecutionGrant) -> dict:
    value = asdict(grant)
    value.pop("integrity_sha256", None)
    return value


def issue_live_grant(
    package: ApplicationPackage,
    plan: LiveActionPlan,
    *,
    mode: Literal["fill_only", "submit"],
    approval_actor: str,
    issued_at: str,
    expires_at: str,
    key_id: str,
    signing_key: bytes,
    action_time_confirmed: bool,
) -> LiveExecutionGrant:
    """Issue short-lived authority after an explicit action-time confirmation."""
    _validate_plan(plan)
    start, end = _timestamp(issued_at), _timestamp(expires_at)
    if end <= start or not action_time_confirmed:
        raise LiveApplicationError("action-time confirmation and a valid expiry are required")
    if mode not in {"fill_only", "submit"}:
        raise LiveApplicationError("invalid live execution mode")
    if package.mode != "review_required" or package.validation_status != "ready_for_review" or package.eligibility_status != "eligible":
        raise LiveApplicationError("package is not eligible for live execution")
    if not approval_actor.strip() or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", key_id):
        raise LiveApplicationError("invalid approval actor or key_id")
    package_sha = _package_sha256(package)
    plan_sha = plan_sha256(plan)
    nonce = sha256(f"{package.package_id}|{plan_sha}|{mode}|{issued_at}|{expires_at}".encode()).hexdigest()
    raw = LiveExecutionGrant(1, "live-grant-" + nonce[:24], package.package_id, package_sha,
        package.posting_sha256, package.profile_sha256, package.final_manifest_sha256,
        _attachment_manifest_sha256(package), plan_sha, plan.exact_origin, mode,
        approval_actor, issued_at, expires_at, nonce, LIVE_CONTRACT_VERSION, key_id,
        LIVE_SIGNATURE_VERSION, "")
    return LiveExecutionGrant(**{**asdict(raw), "integrity_sha256": _sign(grant_payload(raw), signing_key)})


def _validate_grant(package: ApplicationPackage, plan: LiveActionPlan, grant: LiveExecutionGrant, *, at: str, key_id: str, signing_key: bytes) -> None:
    _validate_plan(plan)
    now = _timestamp(at)
    if grant.contract_version != LIVE_CONTRACT_VERSION or grant.signature_version != LIVE_SIGNATURE_VERSION or grant.key_id != key_id:
        raise LiveApplicationError("live grant contract mismatch")
    if not hmac.compare_digest(grant.integrity_sha256, _sign(grant_payload(grant), signing_key)):
        raise LiveApplicationError("live grant integrity check failed")
    expected = (_package_sha256(package), package.posting_sha256, package.profile_sha256,
        package.final_manifest_sha256, _attachment_manifest_sha256(package), plan_sha256(plan), plan.exact_origin)
    actual = (grant.package_sha256, grant.posting_sha256, grant.profile_sha256,
        grant.final_manifest_sha256, grant.attachment_manifest_sha256, grant.plan_sha256, grant.exact_origin)
    if grant.package_id != package.package_id or expected != actual:
        raise LiveApplicationError("live execution binding changed")
    if now < _timestamp(grant.issued_at) or now > _timestamp(grant.expires_at):
        raise LiveApplicationError("live grant is not currently valid")


def _read_ledger(path: Path, signing_key: bytes) -> dict:
    if path.is_symlink():
        raise LiveApplicationError("live ledger must not be a symlink")
    if not path.exists():
        return {"schema_version": 1, "grants": {}, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LiveApplicationError("invalid live ledger") from error
    seal = value.pop("integrity_sha256", None)
    if not seal or not hmac.compare_digest(seal, _sign(value, signing_key)):
        raise LiveApplicationError("live ledger integrity check failed")
    return value


def _write_ledger(path: Path, value: dict, signing_key: bytes) -> None:
    write_json(path, {**value, "integrity_sha256": _sign(value, signing_key)})


def _event(data: dict, event_type: str, grant: LiveExecutionGrant, at: str, **metadata: object) -> None:
    data["events"].append({"event_type": event_type, "grant_id": grant.grant_id,
        "occurred_at": at, "metadata": metadata})


def execute_live_application(
    package: ApplicationPackage,
    plan: LiveActionPlan,
    grant: LiveExecutionGrant,
    driver: LiveBrowserDriver,
    *,
    private_values: Mapping[str, str | Path],
    executed_at: str,
    ledger_path: Path,
    key_id: str,
    signing_key: bytes,
    upload_confirmed: bool = False,
    final_submit_confirmed: bool = False,
    duplicate_detected: bool = False,
) -> LiveExecutionResult:
    """Execute one signed browser phase; every grant is consumed exactly once."""
    _validate_grant(package, plan, grant, at=executed_at, key_id=key_id, signing_key=signing_key)
    if duplicate_detected:
        raise LiveApplicationError("duplicate application detected")
    parsed = urlsplit(driver.current_url())
    if origin_from_url(driver.current_url()) != plan.exact_origin or parsed.path != plan.exact_path:
        raise LiveApplicationError("live page origin or path changed")
    if origin_from_url(driver.form_action_url()) != plan.exact_origin:
        raise LiveApplicationError("live form action origin changed")
    if driver.current_form_schema_sha256() != plan.form_schema_sha256:
        raise LiveApplicationError("live form schema changed")
    markers = set(driver.security_markers())
    if markers & {"captcha", "mfa", "otp", "unknown_field", "cross_origin_iframe"}:
        raise LiveApplicationError("live security or schema marker requires manual review")
    if grant.mode == "submit" and not final_submit_confirmed:
        raise LiveApplicationError("final submit requires immediate confirmation")
    required_keys = {action.private_value_key for action in plan.actions}
    if grant.mode == "fill_only" and set(private_values) != required_keys:
        raise LiveApplicationError("private value set does not match action plan")
    if grant.mode == "fill_only":
        for action in plan.actions:
            value = private_values.get(action.private_value_key)
            if not isinstance(value, (str, Path)) or (action.required and not str(value)):
                raise LiveApplicationError("required private value missing")
            if action.max_length is not None and isinstance(value, str) and len(value) > action.max_length:
                raise LiveApplicationError("private value exceeds field length")
            if action.allowed_options and isinstance(value, str) and value not in action.allowed_options:
                raise LiveApplicationError("private option is not allowed")
            if action.action == "check" and action.required and str(value).casefold() not in {"true", "yes", "1"}:
                raise LiveApplicationError("required consent is not affirmative")
            if action.action == "upload" and not upload_confirmed:
                raise LiveApplicationError("file upload requires immediate confirmation")
        for left, right in plan.matching_value_pairs:
            if private_values[left] != private_values[right]:
                raise LiveApplicationError("confirmation value differs")
        for condition in plan.conditional_values:
            value = str(private_values[condition.private_value_key])
            triggered = str(private_values[condition.controller_key]) == condition.trigger_value
            if triggered and condition.required_when_triggered and not value:
                raise LiveApplicationError("conditional private value is required")
            if not triggered and condition.empty_otherwise and value:
                raise LiveApplicationError("conditional private value must be blank")

    ledger_path = Path(ledger_path)
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    try:
        with exclusive_lock(lock_path):
            data = _read_ledger(ledger_path, signing_key)
            state = data["grants"].setdefault(grant.grant_id, {})
            if state.get("used_at"):
                raise LiveApplicationError("live grant already used")
            state.update({"used_at": executed_at, "status": "submit_started" if grant.mode == "submit" else "fill_started"})
            _event(data, state["status"], grant, executed_at, plan_id=plan.plan_id)
            _write_ledger(ledger_path, data, signing_key)
    except LockAcquisitionError as error:
        raise LiveApplicationError("live ledger lock failed") from error

    verified: list[str] = []
    if grant.mode == "fill_only":
        try:
            for action in plan.actions:
                value = private_values[action.private_value_key]
                if action.action == "fill": driver.fill(action, str(value))
                elif action.action == "select": driver.select(action, str(value))
                elif action.action == "check": driver.check(action, str(value))
                else: driver.upload(action, Path(value))
                value_hash = sha256((Path(value).read_bytes() if action.action == "upload" else str(value).encode("utf-8"))).hexdigest()
                if not driver.verify(action, value_hash):
                    raise LiveApplicationError("field verification failed")
                verified.append(action.logical_id)
            status, reason = "filled_verified", None
        except Exception:
            status, reason = "fill_unverified", "FILL_RESULT_UNVERIFIED"
    else:
        try:
            driver.submit(plan.submit_locator_kind, plan.submit_locator_value)
            receipt, completion = driver.submission_evidence()
            completion_origin = origin_from_url(completion) if completion else None
            if not receipt or completion_origin != plan.exact_origin:
                status, reason = "submission_unverified", "RECEIPT_NOT_VERIFIED"
            else:
                status, reason = "submitted_verified", None
        except Exception:
            receipt, completion_origin = None, None
            status, reason = "submission_unverified", "SUBMIT_RESULT_UNVERIFIED"

    with exclusive_lock(lock_path):
        data = _read_ledger(ledger_path, signing_key)
        data["grants"][grant.grant_id]["status"] = status
        _event(data, status, grant, executed_at, verified_fields=verified, reason_code=reason)
        _write_ledger(ledger_path, data, signing_key)
    execution_id = "live-execution-" + sha256(f"{grant.grant_id}|{executed_at}".encode()).hexdigest()[:24]
    return LiveExecutionResult(1, execution_id, grant.grant_id, package.package_id, grant.mode,
        status, executed_at, tuple(verified), receipt if grant.mode == "submit" else None,
        completion_origin if grant.mode == "submit" else None, reason)
