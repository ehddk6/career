from dataclasses import replace
from pathlib import Path
import secrets

import pytest

from career_pipeline.application_execution import (ApplicationExecutionError, ReviewDecision, SubmissionEvidence,
    approve_application, authorize_execution, execute_application, load_authorization, revoke_authorization,
    write_workflow_artifact)
from career_pipeline.models import FormAutomationResult
from tests.test_application_package import build_package

NOW="2026-07-12T12:00:00+09:00"; EXP="2026-07-12T13:00:00+09:00"
KEY=secrets.token_bytes(32)

def dry_run(pid): return FormAutomationResult(1,"form-1",pid,"review_required",NOW,NOW,"review_required",None,
    "https://jobs.example.or.kr/apply",False,False,True,"a"*64,True,(),(),())

class FakeExecutor:
    def __init__(self,receipt="R-100",schema="a"*64,origin="https://jobs.example.or.kr"):
        self.filled=False; self.submitted=False; self.receipt=receipt; self.schema=schema; self.origin=origin
    def current_form_schema_sha256(self): return self.schema
    def current_origin(self): return self.origin
    def form_action_origin(self): return self.origin
    def fill_and_verify(self): self.filled=True; return True
    def submit(self): self.submitted=True
    def submission_evidence(self): return self.receipt,"https://jobs.example.or.kr/complete?token=secret"

def setup(tmp_path,mode="fill_only"):
    package=build_package(tmp_path); result=dry_run(package.package_id)
    review=approve_application(package,result,decision="approved",decided_at=NOW,approver_id="user",signing_key=KEY)
    auth=authorize_execution(package,result,review,allowed_origin="https://jobs.example.or.kr",mode=mode,
        authorized_at=NOW,expires_at=EXP,approver_id="user",signing_key=KEY)
    return package,result,review,auth,tmp_path/".career_profile"/"execution-ledger.json"

def test_authorization_binds_all_security_inputs(tmp_path):
    package,result,review,auth,_=setup(tmp_path)
    assert isinstance(review,ReviewDecision)
    assert auth.package_sha256 and auth.posting_id==package.posting_id and auth.profile_sha256==package.profile_sha256
    assert auth.attachment_manifest_sha256 and auth.allowed_origin=="https://jobs.example.or.kr:443"
    assert auth.expires_at==EXP and auth.approver_id=="user" and auth.contract_version

def test_expired_revoked_and_reused_authorization_are_blocked(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path)
    with pytest.raises(ApplicationExecutionError,match="expired"):
        execute_application(package,result,review,auth,FakeExecutor(),executed_at="2026-07-12T14:00:00+09:00",ledger_path=ledger,signing_key=KEY)
    revoke_authorization(ledger,auth,revoked_at="2026-07-12T12:10:00+09:00",signing_key=KEY)
    with pytest.raises(ApplicationExecutionError,match="revoked"):
        execute_application(package,result,review,auth,FakeExecutor(),executed_at="2026-07-12T12:20:00+09:00",ledger_path=ledger,signing_key=KEY)

def test_fill_only_is_single_use_and_never_submits(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path); driver=FakeExecutor()
    evidence=execute_application(package,result,review,auth,driver,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    assert driver.filled and not driver.submitted and evidence.status=="awaiting_final_confirmation"
    with pytest.raises(ApplicationExecutionError,match="already used"):
        execute_application(package,result,review,auth,FakeExecutor(),executed_at="2026-07-12T12:06:00+09:00",ledger_path=ledger,signing_key=KEY)

@pytest.mark.parametrize("origin",["http://jobs.example.or.kr","https://jobs.example.or.kr:444","https://jobs.example.or.kr.evil.com","https://sub.jobs.example.or.kr"])
def test_origin_escape_is_blocked_before_fill(tmp_path,origin):
    package,result,review,auth,ledger=setup(tmp_path); driver=FakeExecutor(origin=origin)
    with pytest.raises(ApplicationExecutionError,match="origin"):
        execute_application(package,result,review,auth,driver,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    assert not driver.filled

def test_changed_binding_or_form_action_blocks_before_fill(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path); driver=FakeExecutor(); driver.form_action_origin=lambda:"https://evil.example"
    with pytest.raises(ApplicationExecutionError):
        execute_application(package,result,review,auth,driver,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    with pytest.raises(ApplicationExecutionError,match="changed"):
        execute_application(package,replace(result,form_schema_sha256="b"*64),review,auth,FakeExecutor(),executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)

def test_package_profile_posting_and_attachment_changes_invalidate_authorization(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path)
    variants=(replace(package,profile_sha256="9"*64),replace(package,posting_sha256="8"*64),
        replace(package,attachments=()))
    for changed in variants:
        with pytest.raises(ApplicationExecutionError,match="changed"):
            execute_application(changed,result,review,auth,FakeExecutor(),executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)

def test_tampered_authorization_and_corrupt_ledger_fail_closed(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path); path=tmp_path/"auth.json"; write_workflow_artifact(path,auth)
    text=path.read_text(encoding="utf-8").replace('"fill_only"','"submit"'); path.write_text(text,encoding="utf-8")
    with pytest.raises(ApplicationExecutionError,match="integrity"): load_authorization(path,KEY)
    ledger.parent.mkdir(exist_ok=True); ledger.write_text("{",encoding="utf-8")
    with pytest.raises(ApplicationExecutionError,match="corrupt"):
        execute_application(package,result,review,auth,FakeExecutor(),executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)

def test_submit_records_intent_and_unverified_is_not_retried(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path,"submit"); driver=FakeExecutor(receipt=None)
    evidence=execute_application(package,result,review,auth,driver,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    assert driver.submitted and isinstance(evidence,SubmissionEvidence) and evidence.status=="submission_unverified"
    assert "secret" not in str(evidence)
    with pytest.raises(ApplicationExecutionError,match="already used"):
        execute_application(package,result,review,auth,FakeExecutor(),executed_at="2026-07-12T12:06:00+09:00",ledger_path=ledger,signing_key=KEY)

def test_submit_exception_becomes_unverified_and_cannot_retry(tmp_path):
    package,result,review,auth,ledger=setup(tmp_path,"submit")
    driver=FakeExecutor()
    def fail(): raise TimeoutError("network timeout token=private")
    driver.submit=fail
    evidence=execute_application(package,result,review,auth,driver,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    assert evidence.status=="submission_unverified" and "private" not in str(evidence)

def test_rejected_deferred_captcha_and_mfa_cannot_authorize(tmp_path):
    package=build_package(tmp_path); result=dry_run(package.package_id)
    for decision in ("rejected","deferred"):
        review=approve_application(package,result,decision=decision,decided_at=NOW,approver_id="user",signing_key=KEY)
        with pytest.raises(ApplicationExecutionError,match="approved review"):
            authorize_execution(package,result,review,allowed_origin="https://jobs.example.or.kr",mode="fill_only",authorized_at=NOW,expires_at=EXP,approver_id="user",signing_key=KEY)
    for unsafe in (replace(result,captcha_detected=True),replace(result,mfa_detected=True)):
        with pytest.raises(ApplicationExecutionError): approve_application(package,unsafe,decision="approved",decided_at=NOW,approver_id="user",signing_key=KEY)
