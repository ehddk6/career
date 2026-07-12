"""Fail-closed approval, authorization, and durable execution state."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
from pathlib import Path
import time
from typing import Literal, Protocol

from .models import ApplicationPackage, FormAutomationResult
from .origin_policy import OriginPolicyError, normalize_origin as _normalize_origin, origin_from_url as _origin_from_url_policy
from .path_policy import LockAcquisitionError, exclusive_lock
from .state import write_json

CONTRACT_VERSION="controlled-execution-v1"
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
    start,end=_dt(authorized_at),_dt(expires_at)
    if end<=start: raise ApplicationExecutionError("authorization expiry must be later")
    _validate_review(review,signing_key)
    if review.decision!="approved": raise ApplicationExecutionError("execution requires an approved review")
    if mode not in {"fill_only","submit"} or approver_id!=review.approver_id: raise ApplicationExecutionError("invalid execution authorization")
    _dry(p,r); origin=normalize_origin(allowed_origin)
    expected=(_package_sha(p),p.posting_id,p.posting_sha256,p.profile_sha256,p.final_manifest_sha256,_attachments_sha(p),r.form_schema_sha256)
    actual=(review.package_sha256,review.posting_id,review.posting_sha256,review.profile_sha256,review.final_manifest_sha256,review.attachment_manifest_sha256,review.form_schema_sha256)
    if expected!=actual or review.package_id!=p.package_id or review.contract_version!=CONTRACT_VERSION: raise ApplicationExecutionError("review binding changed")
    nonce=_id("nonce",review.review_id,origin,mode,authorized_at,expires_at)
    aid=_id("authorization",nonce,review.review_id)
    partial=ExecutionAuthorization(1,aid,review.review_id,p.package_id,*expected,origin,mode,approver_id,authorized_at,expires_at,nonce,CONTRACT_VERSION,"")
    return ExecutionAuthorization(**{**asdict(partial),"integrity_sha256":_sign(_auth_payload(partial),signing_key)})

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
    _validate_auth(a,signing_key); _dt(revoked_at); path=Path(path)
    with _lock(path.with_suffix(path.suffix+".lock")):
        data=_ledger(path,signing_key); state=data["authorizations"].setdefault(a.authorization_id,{})
        state["revoked_at"]=revoked_at; _event(data,"authorization_revoked",a,revoked_at); _write_ledger(path,data,signing_key)

def _bindings(p,r,review,a):
    expected=(_package_sha(p),p.posting_id,p.posting_sha256,p.profile_sha256,p.final_manifest_sha256,_attachments_sha(p),r.form_schema_sha256)
    actual=(a.package_sha256,a.posting_id,a.posting_sha256,a.profile_sha256,a.final_manifest_sha256,a.attachment_manifest_sha256,a.form_schema_sha256)
    if expected!=actual or a.package_id!=p.package_id or a.review_id!=review.review_id: raise ApplicationExecutionError("execution binding changed")

def claim_fixture_fill_authorization(p,r,a,*,executed_at,ledger_path,signing_key,adapter_id,validation_event="fill_fixture_validation_started"):
    """Atomically claim a signed fill-only authorization for an offline fixture adapter."""
    now=_dt(executed_at); _validate_auth(a,signing_key); _dry(p,r)
    expected=(_package_sha(p),p.posting_id,p.posting_sha256,p.profile_sha256,p.final_manifest_sha256,_attachments_sha(p),r.form_schema_sha256)
    actual=(a.package_sha256,a.posting_id,a.posting_sha256,a.profile_sha256,a.final_manifest_sha256,a.attachment_manifest_sha256,a.form_schema_sha256)
    if expected!=actual or a.package_id!=p.package_id: raise ApplicationExecutionError("fixture execution binding changed")
    if a.mode!="fill_only": raise ApplicationExecutionError("fixture adapter requires fill_only authorization")
    if now>_dt(a.expires_at): raise ApplicationExecutionError("authorization expired")
    path=Path(ledger_path)
    with _lock(path.with_suffix(path.suffix+".lock")):
        data=_ledger(path,signing_key); state=data["authorizations"].setdefault(a.authorization_id,{})
        if state.get("revoked_at"): raise ApplicationExecutionError("authorization revoked")
        if state.get("used_at"): raise ApplicationExecutionError("authorization already used")
        state.update({"used_at":executed_at,"status":"fixture_fill_started","adapter_id":adapter_id})
        if validation_event not in {"fill_fixture_validation_started","applyin_fixture_validation_started"}: raise ApplicationExecutionError("invalid fixture validation event")
        _event(data,validation_event,a,executed_at,adapter_id=adapter_id)
        _write_ledger(path,data,signing_key)

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
    now=_dt(executed_at); _validate_review(review,signing_key); _validate_auth(a,signing_key); _dry(p,r); _bindings(p,r,review,a)
    if now>_dt(a.expires_at): raise ApplicationExecutionError("authorization expired")
    if duplicate_detected: raise ApplicationExecutionError("duplicate application detected")
    if _origin_from_url(driver.current_origin(),bare=False)!=a.allowed_origin or _origin_from_url(driver.form_action_origin(),bare=False)!=a.allowed_origin: raise ApplicationExecutionError("live origin or form action origin changed")
    if driver.current_form_schema_sha256()!=r.form_schema_sha256: raise ApplicationExecutionError("live form schema changed")
    path=Path(ledger_path)
    with _lock(path.with_suffix(path.suffix+".lock")):
        data=_ledger(path,signing_key); state=data["authorizations"].setdefault(a.authorization_id,{})
        if state.get("revoked_at"): raise ApplicationExecutionError("authorization revoked")
        if state.get("used_at"): raise ApplicationExecutionError("authorization already used")
        state["used_at"]=executed_at; state["status"]="executing"; _event(data,"execution_started",a,executed_at); _write_ledger(path,data,signing_key)
    try:
        if not driver.fill_and_verify(): raise ApplicationExecutionError("field verification failed")
        if _origin_from_url(driver.current_origin(),bare=False)!=a.allowed_origin or _origin_from_url(driver.form_action_origin(),bare=False)!=a.allowed_origin: raise ApplicationExecutionError("origin changed after fill")
        if driver.current_form_schema_sha256()!=r.form_schema_sha256: raise ApplicationExecutionError("live form schema changed after fill")
        eid=_id("execution",a.authorization_id,executed_at)
        if a.mode=="fill_only": evidence=SubmissionEvidence(1,eid,p.package_id,a.authorization_id,"fill_only","awaiting_final_confirmation",executed_at,None,None)
        else:
            with _lock(path.with_suffix(path.suffix+".lock")):
                data=_ledger(path,signing_key); data["authorizations"][a.authorization_id]["status"]="submit_started"; _event(data,"submit_started",a,executed_at); _write_ledger(path,data,signing_key)
            try: driver.submit(); receipt,url=driver.submission_evidence()
            except Exception: receipt=url=None
            completion=None
            if url:
                try: completion=_origin_from_url(url,bare=False)
                except ApplicationExecutionError: completion=None
            status="submitted_verified" if receipt and completion==a.allowed_origin else "submission_unverified"
            evidence=SubmissionEvidence(1,eid,p.package_id,a.authorization_id,"submit",status,executed_at,sha256(receipt.encode()).hexdigest() if receipt else None,completion)
        with _lock(path.with_suffix(path.suffix+".lock")):
            data=_ledger(path,signing_key); data["authorizations"][a.authorization_id]["status"]=evidence.status; _event(data,evidence.status,a,executed_at); _write_ledger(path,data,signing_key)
        return evidence
    except Exception:
        with _lock(path.with_suffix(path.suffix+".lock")):
            data=_ledger(path,signing_key); data["authorizations"][a.authorization_id]["status"]="failed"; _event(data,"execution_failed",a,executed_at); _write_ledger(path,data,signing_key)
        raise

def write_workflow_artifact(path,value): write_json(path,asdict(value))
def load_review(path,signing_key):
    value=ReviewDecision(**json.loads(Path(path).read_text(encoding="utf-8"))); _validate_review(value,signing_key); return value
def load_authorization(path,signing_key):
    value=ExecutionAuthorization(**json.loads(Path(path).read_text(encoding="utf-8"))); _validate_auth(value,signing_key); return value
