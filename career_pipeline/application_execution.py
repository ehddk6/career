"""Fail-closed approval, authorization, and durable execution state."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
import re
from enum import Enum
from pathlib import Path
import time
from typing import Any, Literal, Mapping, Protocol

from .models import ApplicationPackage, FormAutomationResult
from .site_intake import SiteReadOnlyContract
from .origin_policy import OriginPolicyError, normalize_origin as _normalize_origin, origin_from_url as _origin_from_url_policy
from .path_policy import LockAcquisitionError, exclusive_lock
from .state import write_json

CONTRACT_VERSION="controlled-execution-v1"
V2_CONTRACT_VERSION="controlled-execution-v2"
LEGACY_AUTHORIZATION_UNUSABLE="LEGACY_AUTHORIZATION_UNUSABLE"
class ApplicationExecutionError(ValueError): pass
def _key(value:bytes)->bytes:
    if not isinstance(value,bytes) or len(value)<32: raise ApplicationExecutionError("execution signing key must be at least 32 bytes")
    return value
def _sign(value,key): return hmac.new(_key(key),_json(value),sha256).hexdigest()

def _dt(value:str)->datetime:
    try: parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as e: raise ApplicationExecutionError("timestamp must be timezone-aware") from e
    if parsed.tzinfo is None or parsed.utcoffset() is None: raise ApplicationExecutionError("timestamp must be timezone-aware")
    return parsed
def _json(value)->bytes: return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def _digest(value)->str: return sha256(_json(value)).hexdigest()
def _id(prefix,*values): return prefix+"-"+sha256("|".join(values).encode()).hexdigest()[:24]
def _package_sha(p): return _digest(asdict(p))
def _attachments_sha(p): return _digest([asdict(a) for a in p.attachments])

def _origin_from_url(value:str, *, bare:bool)->str:
    try: return _normalize_origin(value) if bare else _origin_from_url_policy(value)
    except OriginPolicyError as e: raise ApplicationExecutionError(str(e)) from e
def normalize_origin(value:str)->str: return _origin_from_url(value,bare=True)

_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

def _sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ApplicationExecutionError(f"invalid {label}")

def _key_id(value: str) -> None:
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ApplicationExecutionError("invalid key_id")

def _contract(contract: SiteReadOnlyContract) -> None:
    if not isinstance(contract, SiteReadOnlyContract) or contract.contract_version != 2:
        raise ApplicationExecutionError("site contract is not v2")
    _dt(contract.observed_at); _dt(contract.valid_until)
    if _dt(contract.valid_until) <= _dt(contract.observed_at): raise ApplicationExecutionError("site contract expiry invalid")
    normalize_origin(contract.exact_origin)
    for value, label in ((contract.fixture_sha256,"fixture SHA"),(contract.schema_sha256,"schema SHA"),(contract.adapter_schema_sha256,"adapter schema SHA")):
        _sha(value,label)
    if set(contract.allowed_capabilities) - {"fill_only","submit"}: raise ApplicationExecutionError("invalid site capabilities")
    if not contract.adapter_id or contract.adapter_contract_version < 1 or not contract.schema_version: raise ApplicationExecutionError("invalid adapter lineage")

def canonical_site_contract_sha256(contract: SiteReadOnlyContract) -> str:
    _contract(contract)
    return sha256(json.dumps(asdict(contract),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()

def review_decision_v2_payload(review: ReviewDecisionV2) -> dict[str, Any]:
    value=asdict(review); value.pop("integrity_sha256",None); return value

def execution_authorization_v2_payload(authorization: ExecutionAuthorizationV2) -> dict[str, Any]:
    value=asdict(authorization); value.pop("integrity_sha256",None); return value

def _v2_review(review: ReviewDecisionV2, key_id: str, signing_key: bytes) -> None:
    _key_id(key_id)
    if not isinstance(review,ReviewDecisionV2) or review.schema_version != 2 or review.contract_version != V2_CONTRACT_VERSION or review.signature_version != "hmac-sha256-v2" or review.key_id != key_id:
        raise ApplicationExecutionError("review v2 integrity check failed")
    if not hmac.compare_digest(review.integrity_sha256,_sign(review_decision_v2_payload(review),signing_key)): raise ApplicationExecutionError("review v2 integrity check failed")

def _v2_authorization(authorization: ExecutionAuthorizationV2, key_id: str, signing_key: bytes) -> None:
    _key_id(key_id)
    if not isinstance(authorization,ExecutionAuthorizationV2) or authorization.schema_version != 2 or authorization.contract_version != V2_CONTRACT_VERSION or authorization.signature_version != "hmac-sha256-v2" or authorization.key_id != key_id:
        raise ApplicationExecutionError("authorization v2 integrity check failed")
    if not hmac.compare_digest(authorization.integrity_sha256,_sign(execution_authorization_v2_payload(authorization),signing_key)): raise ApplicationExecutionError("authorization v2 integrity check failed")

def _v2_bindings(package, review, contract, adapter_id, adapter_contract_version, adapter_schema_sha256, allowed_origin):
    _contract(contract); contract_sha=canonical_site_contract_sha256(contract); origin=normalize_origin(allowed_origin)
    if origin != contract.exact_origin or adapter_id != contract.adapter_id or adapter_contract_version != contract.adapter_contract_version or adapter_schema_sha256 != contract.adapter_schema_sha256:
        raise ApplicationExecutionError("adapter lineage or origin mismatch")
    expected=(_package_sha(package),package.posting_id,package.posting_sha256,package.profile_sha256,package.final_manifest_sha256,_attachments_sha(package),contract.schema_sha256,contract.contract_id,contract_sha,contract.observed_at,contract.valid_until,contract.exact_origin,contract.adapter_id,contract.adapter_contract_version,contract.adapter_schema_sha256,contract.allowed_capabilities,contract.mutation_enabled,contract.live_enabled)
    actual=(review.package_sha256,review.posting_id,review.posting_sha256,review.profile_sha256,review.final_manifest_sha256,review.attachment_manifest_sha256,review.form_schema_sha256,review.site_contract_id,review.site_contract_sha256,review.site_contract_observed_at,review.site_contract_valid_until,review.exact_origin,review.adapter_id,review.adapter_contract_version,review.adapter_schema_sha256,review.allowed_capabilities,review.mutation_enabled,review.live_enabled)
    if review.package_id != package.package_id or expected != actual: raise ApplicationExecutionError("review binding changed")

def approve_application_v2(package, dry_run_result, site_contract: SiteReadOnlyContract, *, decision, decided_at, approver_id, key_id, signing_key) -> ReviewDecisionV2:
    _contract(site_contract); _dt(decided_at); _key_id(key_id)
    if decision not in {"approved","rejected","deferred"} or not approver_id.strip(): raise ApplicationExecutionError("invalid review")
    if decision == "approved":
        _dry(package,dry_run_result)
        if dry_run_result.form_schema_sha256 != site_contract.schema_sha256: raise ApplicationExecutionError("form schema does not match site contract")
    contract_sha=canonical_site_contract_sha256(site_contract)
    values=(_package_sha(package),package.posting_id,package.posting_sha256,package.profile_sha256,package.final_manifest_sha256,_attachments_sha(package),site_contract.schema_sha256,site_contract.contract_id,contract_sha,site_contract.exact_origin,site_contract.adapter_id)
    raw=ReviewDecisionV2(2,_id("review-v2",*values,decision,approver_id,decided_at),package.package_id,*values[:7],site_contract.contract_id,contract_sha,site_contract.observed_at,site_contract.valid_until,site_contract.exact_origin,site_contract.adapter_id,site_contract.adapter_contract_version,site_contract.adapter_schema_sha256,site_contract.allowed_capabilities,site_contract.mutation_enabled,site_contract.live_enabled,decision,approver_id,decided_at,V2_CONTRACT_VERSION,key_id,"hmac-sha256-v2","")
    return ReviewDecisionV2(**{**asdict(raw),"integrity_sha256":_sign(review_decision_v2_payload(raw),signing_key)})

def build_authorization_candidate_v2(package, review: ReviewDecisionV2, site_contract: SiteReadOnlyContract, *, adapter_id, adapter_contract_version, adapter_schema_sha256, allowed_origin, mode, requested_at) -> AuthorizationCandidateV2:
    _dt(requested_at); _v2_bindings(package,review,site_contract,adapter_id,adapter_contract_version,adapter_schema_sha256,allowed_origin)
    if mode not in {"fill_only","submit"}: raise ApplicationExecutionError("invalid requested mode")
    enabled = site_contract.mutation_enabled and site_contract.live_enabled and mode in site_contract.allowed_capabilities
    status = "eligible_for_external_review" if enabled else "capability_disabled"
    code = "CAPABILITY_ENABLED_REQUIRES_EXTERNAL_REVIEW" if enabled else ("FILL_AUTHORITY_DISABLED" if mode == "fill_only" else "SUBMIT_AUTHORITY_DISABLED")
    return AuthorizationCandidateV2(2,review.review_id,package.package_id,_package_sha(package),site_contract.contract_id,canonical_site_contract_sha256(site_contract),site_contract.exact_origin,adapter_id,adapter_contract_version,adapter_schema_sha256,mode,requested_at,status,code)

def authorize_execution_v2(package, review: ReviewDecisionV2, site_contract: SiteReadOnlyContract, *, adapter_id, adapter_contract_version, adapter_schema_sha256, allowed_origin, mode, authorized_at, expires_at, approver_id, key_id, signing_key) -> ExecutionAuthorizationV2:
    start,end=_dt(authorized_at),_dt(expires_at); _key_id(key_id)
    if end <= start: raise ApplicationExecutionError("authorization expiry must be later")
    _v2_review(review,key_id,signing_key); _v2_bindings(package,review,site_contract,adapter_id,adapter_contract_version,adapter_schema_sha256,allowed_origin)
    if review.decision != "approved" or approver_id != review.approver_id: raise ApplicationExecutionError("execution requires an approved review")
    if mode not in {"fill_only","submit"}: raise ApplicationExecutionError("invalid execution mode")
    if not site_contract.mutation_enabled or not site_contract.live_enabled or mode not in site_contract.allowed_capabilities:
        raise ApplicationExecutionError("FILL_AUTHORITY_DISABLED" if mode == "fill_only" else "SUBMIT_AUTHORITY_DISABLED")
    nonce=_id("nonce-v2",review.review_id,mode,authorized_at,expires_at); raw=ExecutionAuthorizationV2(2,_id("authorization-v2",nonce,review.review_id),review.review_id,package.package_id,review.package_sha256,review.posting_id,review.posting_sha256,review.profile_sha256,review.final_manifest_sha256,review.attachment_manifest_sha256,review.form_schema_sha256,review.site_contract_id,review.site_contract_sha256,review.site_contract_observed_at,review.site_contract_valid_until,review.exact_origin,review.adapter_id,review.adapter_contract_version,review.adapter_schema_sha256,review.allowed_capabilities,mode,approver_id,authorized_at,expires_at,nonce,V2_CONTRACT_VERSION,key_id,"hmac-sha256-v2","")
    return ExecutionAuthorizationV2(**{**asdict(raw),"integrity_sha256":_sign(execution_authorization_v2_payload(raw),signing_key)})

def classify_execution_artifact(value: Mapping[str, Any]) -> ExecutionArtifactClassification:
    if not isinstance(value,Mapping): return ExecutionArtifactClassification.unsupported
    if value.get("schema_version") == 1 and "authorization_id" in value: return ExecutionArtifactClassification.authorization_v1
    if value.get("schema_version") == 1 and "review_id" in value: return ExecutionArtifactClassification.review_v1
    if value.get("schema_version") == 2 and "review_id" in value and "site_contract_id" in value:
        return ExecutionArtifactClassification.authorization_v2 if "authorization_id" in value else ExecutionArtifactClassification.review_v2
    return ExecutionArtifactClassification.unsupported

@dataclass(frozen=True)
class ReviewDecision:
    schema_version:int; review_id:str; package_id:str; package_sha256:str; posting_id:str; posting_sha256:str
    profile_sha256:str; final_manifest_sha256:str; attachment_manifest_sha256:str; form_schema_sha256:str
    decision:Literal["approved","rejected","deferred"]; approver_id:str; decided_at:str; contract_version:str; integrity_sha256:str

@dataclass(frozen=True)
class ExecutionAuthorization:
    schema_version:int; authorization_id:str; review_id:str; package_id:str; package_sha256:str; posting_id:str
    posting_sha256:str; profile_sha256:str; final_manifest_sha256:str; attachment_manifest_sha256:str
    form_schema_sha256:str; allowed_origin:str; mode:Literal["fill_only","submit"]; approver_id:str
    authorized_at:str; expires_at:str; nonce:str; contract_version:str; integrity_sha256:str

@dataclass(frozen=True)
class ReviewDecisionV2:
    schema_version: Literal[2]; review_id: str; package_id: str; package_sha256: str; posting_id: str; posting_sha256: str; profile_sha256: str; final_manifest_sha256: str; attachment_manifest_sha256: str; form_schema_sha256: str; site_contract_id: str; site_contract_sha256: str; site_contract_observed_at: str; site_contract_valid_until: str; exact_origin: str; adapter_id: str; adapter_contract_version: int; adapter_schema_sha256: str; allowed_capabilities: tuple[Literal["fill_only", "submit"], ...]; mutation_enabled: bool; live_enabled: bool; decision: Literal["approved", "rejected", "deferred"]; approver_id: str; decided_at: str; contract_version: Literal["controlled-execution-v2"]; key_id: str; signature_version: Literal["hmac-sha256-v2"]; integrity_sha256: str

@dataclass(frozen=True)
class AuthorizationCandidateV2:
    schema_version: Literal[2]; review_id: str; package_id: str; package_sha256: str; site_contract_id: str; site_contract_sha256: str; exact_origin: str; adapter_id: str; adapter_contract_version: int; adapter_schema_sha256: str; requested_mode: Literal["fill_only", "submit"]; requested_at: str; candidate_status: Literal["capability_disabled", "legacy_unusable", "eligible_for_external_review"]; reason_code: str

@dataclass(frozen=True)
class ExecutionAuthorizationV2:
    schema_version: Literal[2]; authorization_id: str; review_id: str; package_id: str; package_sha256: str; posting_id: str; posting_sha256: str; profile_sha256: str; final_manifest_sha256: str; attachment_manifest_sha256: str; form_schema_sha256: str; site_contract_id: str; site_contract_sha256: str; site_contract_observed_at: str; site_contract_valid_until: str; exact_origin: str; adapter_id: str; adapter_contract_version: int; adapter_schema_sha256: str; allowed_capabilities: tuple[Literal["fill_only", "submit"], ...]; mode: Literal["fill_only", "submit"]; approver_id: str; authorized_at: str; expires_at: str; nonce: str; contract_version: Literal["controlled-execution-v2"]; key_id: str; signature_version: Literal["hmac-sha256-v2"]; integrity_sha256: str

@dataclass(frozen=True)
class ValidatedExecutionCandidateV2:
    schema_version: Literal[2]; authorization_id: str; review_id: str; package_id: str; site_contract_id: str; mode: Literal["fill_only", "submit"]; validated_at: str; blocker_status: Literal["mutation_blocked"]

class ExecutionArtifactClassification(str, Enum):
    review_v1="review_v1"; authorization_v1="authorization_v1"; review_v2="review_v2"; authorization_v2="authorization_v2"; unsupported="unsupported"

@dataclass(frozen=True)
class SubmissionEvidence:
    schema_version:int; execution_id:str; package_id:str; authorization_id:str; mode:Literal["fill_only","submit"]
    status:Literal["awaiting_final_confirmation","submitted_verified","submission_unverified"]
    executed_at:str; receipt_fingerprint:str|None; completion_origin:str|None

class ApplicationExecutor(Protocol):
    def current_form_schema_sha256(self)->str: ...
    def current_origin(self)->str: ...
    def form_action_origin(self)->str: ...
    def fill_and_verify(self)->bool: ...
    def submit(self)->None: ...
    def submission_evidence(self)->tuple[str|None,str|None]: ...

def _dry(p,r):
    if r.package_id!=p.package_id: raise ApplicationExecutionError("package binding changed")
    if r.status!="review_required" or r.stop_reason or not r.dom_unchanged: raise ApplicationExecutionError("dry-run is not eligible")
    if r.captcha_detected or r.mfa_detected: raise ApplicationExecutionError("CAPTCHA or MFA blocks execution")

def approve_application(p,r,*,decision,decided_at,approver_id,signing_key):
    _dt(decided_at)
    if decision not in {"approved","rejected","deferred"} or not approver_id.strip(): raise ApplicationExecutionError("invalid review")
    if decision=="approved":
        _dry(p,r)
        if p.validation_status!="ready_for_review" or p.eligibility_status!="eligible": raise ApplicationExecutionError("package is not eligible")
    values=(_package_sha(p),p.posting_id,p.posting_sha256,p.profile_sha256,p.final_manifest_sha256,_attachments_sha(p),r.form_schema_sha256)
    partial=ReviewDecision(1,_id("review",*values,decision,approver_id,decided_at),p.package_id,*values,decision,approver_id,decided_at,CONTRACT_VERSION,"")
    return ReviewDecision(**{**asdict(partial),"integrity_sha256":_sign({k:v for k,v in asdict(partial).items() if k!="integrity_sha256"},signing_key)})

def _auth_payload(a):
    d=asdict(a); d.pop("integrity_sha256",None); return d
def _validate_review(review,key):
    payload=asdict(review); seal=payload.pop("integrity_sha256",None)
    if review.contract_version!=CONTRACT_VERSION or not hmac.compare_digest(seal or "",_sign(payload,key)): raise ApplicationExecutionError("review integrity check failed")
def _validate_auth(a,key):
    if a.contract_version!=CONTRACT_VERSION or not hmac.compare_digest(a.integrity_sha256,_sign(_auth_payload(a),key)): raise ApplicationExecutionError("authorization integrity check failed")

def authorize_execution(p,r,review,*,allowed_origin,mode,authorized_at,expires_at,approver_id,signing_key):
    raise ApplicationExecutionError(LEGACY_AUTHORIZATION_UNUSABLE)

@contextmanager
def _lock(path):
    try:
        with exclusive_lock(path):
            yield
    except LockAcquisitionError as error:
        status = str(error).rsplit(":", 1)[-1].strip()
        raise ApplicationExecutionError(f"execution ledger lock timeout: {status}") from error
def _ledger(path,key):
    if path.is_symlink(): raise ApplicationExecutionError("execution ledger must not be symlink")
    if not path.exists(): return {"schema_version":1,"authorizations":{},"events":[]}
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e: raise ApplicationExecutionError("corrupt execution ledger") from e
    seal=value.pop("integrity_sha256",None)
    if not seal or not hmac.compare_digest(seal,_sign(value,key)): raise ApplicationExecutionError("execution ledger integrity check failed")
    if value.get("schema_version")!=1 or not isinstance(value.get("authorizations"),dict) or not isinstance(value.get("events"),list): raise ApplicationExecutionError("invalid execution ledger")
    return value
def _write_ledger(path,value,key): write_json(path,{**value,"integrity_sha256":_sign(value,key)})
def _event(ledger,kind,a,at,**metadata): ledger["events"].append({"event_id":_id("event",kind,a.authorization_id,at,_digest(metadata)),"event_type":kind,"authorization_id":a.authorization_id,"occurred_at":at,"metadata":metadata})

def revoke_authorization(path,a,*,revoked_at,signing_key):
    if isinstance(a, ExecutionAuthorizationV2): _v2_authorization(a,a.key_id,signing_key)
    else: _validate_auth(a,signing_key)
    _dt(revoked_at); path=Path(path)
    with _lock(path.with_suffix(path.suffix+".lock")):
        data=_ledger(path,signing_key); state=data["authorizations"].setdefault(a.authorization_id,{})
        state["revoked_at"]=revoked_at; _event(data,"authorization_revoked",a,revoked_at); _write_ledger(path,data,signing_key)

def _bindings(p,r,review,a):
    expected=(_package_sha(p),p.posting_id,p.posting_sha256,p.profile_sha256,p.final_manifest_sha256,_attachments_sha(p),r.form_schema_sha256)
    actual=(a.package_sha256,a.posting_id,a.posting_sha256,a.profile_sha256,a.final_manifest_sha256,a.attachment_manifest_sha256,a.form_schema_sha256)
    if expected!=actual or a.package_id!=p.package_id or a.review_id!=review.review_id: raise ApplicationExecutionError("execution binding changed")

def validate_execution_candidate_v2(package, review: ReviewDecisionV2, authorization: ExecutionAuthorizationV2, site_contract: SiteReadOnlyContract, driver, *, executed_at, ledger_path, key_id, signing_key) -> ValidatedExecutionCandidateV2:
    """Validate bindings and read-only probes only; this never mutates a driver or ledger."""
    now=_dt(executed_at); _v2_review(review,key_id,signing_key); _v2_authorization(authorization,key_id,signing_key)
    _v2_bindings(package,review,site_contract,authorization.adapter_id,authorization.adapter_contract_version,authorization.adapter_schema_sha256,authorization.exact_origin)
    review_values=(review.review_id,review.package_id,review.package_sha256,review.posting_id,review.posting_sha256,review.profile_sha256,review.final_manifest_sha256,review.attachment_manifest_sha256,review.form_schema_sha256,review.site_contract_id,review.site_contract_sha256,review.site_contract_observed_at,review.site_contract_valid_until,review.exact_origin,review.adapter_id,review.adapter_contract_version,review.adapter_schema_sha256,review.allowed_capabilities)
    authorization_values=(authorization.review_id,authorization.package_id,authorization.package_sha256,authorization.posting_id,authorization.posting_sha256,authorization.profile_sha256,authorization.final_manifest_sha256,authorization.attachment_manifest_sha256,authorization.form_schema_sha256,authorization.site_contract_id,authorization.site_contract_sha256,authorization.site_contract_observed_at,authorization.site_contract_valid_until,authorization.exact_origin,authorization.adapter_id,authorization.adapter_contract_version,authorization.adapter_schema_sha256,authorization.allowed_capabilities)
    if authorization_values != review_values: raise ApplicationExecutionError("execution binding changed")
    if authorization.mode not in authorization.allowed_capabilities or not site_contract.mutation_enabled or not site_contract.live_enabled: raise ApplicationExecutionError("execution capability disabled")
    if now < _dt(authorization.authorized_at): raise ApplicationExecutionError("execution before authorization")
    if now > _dt(authorization.expires_at): raise ApplicationExecutionError("authorization expired")
    if now > _dt(site_contract.valid_until): raise ApplicationExecutionError("site contract stale")
    data=_ledger(Path(ledger_path),signing_key); state=data["authorizations"].get(authorization.authorization_id,{})
    if state.get("revoked_at"): raise ApplicationExecutionError("authorization revoked")
    if state.get("used_at"): raise ApplicationExecutionError("authorization already used")
    if _origin_from_url(driver.current_origin(),bare=False) != authorization.exact_origin: raise ApplicationExecutionError("current origin mismatch")
    if _origin_from_url(driver.form_action_origin(),bare=False) != authorization.exact_origin: raise ApplicationExecutionError("form action origin mismatch")
    if driver.current_form_schema_sha256() != authorization.form_schema_sha256: raise ApplicationExecutionError("live form schema changed")
    return ValidatedExecutionCandidateV2(2,authorization.authorization_id,review.review_id,package.package_id,site_contract.contract_id,authorization.mode,executed_at,"mutation_blocked")

def claim_fixture_fill_authorization(p,r,a,*,executed_at,ledger_path,signing_key,adapter_id,validation_event="fill_fixture_validation_started"):
    raise ApplicationExecutionError(LEGACY_AUTHORIZATION_UNUSABLE)

def record_fixture_event(ledger_path,a,*,event_type,occurred_at,signing_key,adapter_id,logical_field_id=None):
    allowed={"fill_fixture_blocked","field_fill_started","field_fill_verified","fill_fixture_completed","fill_fixture_failed","applyin_fixture_blocked","applyin_fixture_completed","applyin_fixture_failed"}
    if event_type not in allowed: raise ApplicationExecutionError("invalid fixture event")
    _validate_auth(a,signing_key); _dt(occurred_at); path=Path(ledger_path)
    metadata={"adapter_id":adapter_id}
    if logical_field_id is not None: metadata["logical_field_id"]=logical_field_id
    with _lock(path.with_suffix(path.suffix+".lock")):
        data=_ledger(path,signing_key); state=data["authorizations"].get(a.authorization_id)
        if not state or not state.get("used_at"): raise ApplicationExecutionError("fixture authorization was not claimed")
        state["status"]=event_type; _event(data,event_type,a,occurred_at,**metadata); _write_ledger(path,data,signing_key)

def execute_application(p,r,review,a,driver,*,executed_at,ledger_path,signing_key,duplicate_detected=False):
    raise ApplicationExecutionError(LEGACY_AUTHORIZATION_UNUSABLE)

def write_workflow_artifact(path,value): write_json(path,asdict(value))
def load_review(path,signing_key):
    value=ReviewDecision(**json.loads(Path(path).read_text(encoding="utf-8"))); _validate_review(value,signing_key); return value
def load_authorization(path,signing_key):
    value=ExecutionAuthorization(**json.loads(Path(path).read_text(encoding="utf-8"))); _validate_auth(value,signing_key); return value
