from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import secrets

import pytest

from career_pipeline.adapters.saramin_applyin_live import (
    KODIT_ORIGIN, KODIT_PRECONFIRM_ACTION, KODIT_PRECONFIRM_PATH,
    build_preconfirm_plan, normalize_preconfirm_schema, private_value_keys,
    schema_sha256, validate_private_consents,
)
from career_pipeline.live_application import (
    LiveApplicationError, LiveFieldAction, execute_live_application, issue_live_grant,
)
from career_pipeline.__main__ import main
from career_pipeline.application_package import write_application_package
from career_pipeline.state import write_json
from tests.test_application_package import build_package

NOW = "2026-07-13T12:00:00+09:00"
RUN = "2026-07-13T12:01:00+09:00"
EXP = "2026-07-13T12:10:00+09:00"
KEY = secrets.token_bytes(32)
KEY_ID = "live-test-key"


def snapshot():
    fields = []
    for index in range(1, 6):
        fields.append({"tag": "input", "type": "checkbox", "name": None, "id": f"check{index}", "required": False, "maxlength": None, "options": None})
    fields += [
        {"tag":"select","type":"select-one","name":"field1","id":"field1","required":False,"maxlength":None,"options":[{"text":"선택"},{"text":"체험형 청년인턴1(보증)"},{"text":"체험형 청년인턴2(보험)"}]},
        {"tag":"select","type":"select-one","name":"field2","id":"field2","required":False,"maxlength":None,"options":[{"text":"선택"}]},
        {"tag":"select","type":"select-one","name":"field3","id":"field3","required":False,"maxlength":None,"options":[{"text":"선택"}]},
        {"tag":"input","type":"text","name":"kor_name","id":None,"required":False,"maxlength":10,"options":None},
        {"tag":"input","type":"text","name":"hp1","id":None,"required":False,"maxlength":3,"options":None},
        {"tag":"input","type":"text","name":"hp2","id":None,"required":False,"maxlength":4,"options":None},
        {"tag":"input","type":"text","name":"hp3","id":None,"required":False,"maxlength":4,"options":None},
        {"tag":"input","type":"text","name":"email1","id":"email1","required":False,"maxlength":20,"options":None},
        {"tag":"select","type":"select-one","name":"email2_select","id":None,"required":False,"maxlength":None,"options":[{"text":"선택하세요"},{"text":"naver.com"},{"text":"nate.com"},{"text":"gmail.com"},{"text":"직접입력"}]},
        {"tag":"input","type":"text","name":"email2_etc","id":None,"required":False,"maxlength":20,"options":None},
        {"tag":"input","type":"text","name":"email1_check","id":"email1_check","required":False,"maxlength":None,"options":None},
        {"tag":"select","type":"select-one","name":"email2_select_check","id":None,"required":False,"maxlength":None,"options":[{"text":"선택하세요"},{"text":"naver.com"},{"text":"nate.com"},{"text":"gmail.com"},{"text":"직접입력"}]},
        {"tag":"input","type":"text","name":"email2_etc_check","id":None,"required":False,"maxlength":20,"options":None},
    ]
    return {"origin": KODIT_ORIGIN, "path": KODIT_PRECONFIRM_PATH,
        "forms": [{"method":"post","action":KODIT_PRECONFIRM_ACTION}], "fields": fields,
        "iframe_count":0, "captcha":False, "mfa":False}


def values():
    return {
        "privacy_general":"true", "privacy_sensitive":"true", "privacy_processing":"true",
        "privacy_third_party":"true", "privacy_final_confirmation":"true",
        "recruitment_track":"체험형 청년인턴1(보증)", "headquarters":"서울서부영업본부", "branch":"마포지점",
        "applicant_name":"홍길동", "phone_prefix":"010", "phone_middle":"1234", "phone_suffix":"5678",
        "email_local":"person", "email_domain":"gmail.com", "email_domain_custom":"",
        "email_local_confirm":"person", "email_domain_confirm":"gmail.com", "email_domain_custom_confirm":"",
    }


class FakeLiveDriver:
    def __init__(self, plan, *, markers=(), schema=None, receipt="receipt-1", completion=None, fail_submit=False):
        self.plan=plan; self.markers=markers; self.schema=schema or plan.form_schema_sha256
        self.receipt=receipt; self.completion=completion or KODIT_ORIGIN + "/complete"; self.fail_submit=fail_submit
        self.values={}; self.calls=[]
    def current_url(self): return KODIT_ORIGIN + KODIT_PRECONFIRM_PATH
    def form_action_url(self): return KODIT_PRECONFIRM_ACTION
    def current_form_schema_sha256(self): return self.schema
    def security_markers(self): return tuple(self.markers)
    def fill(self,a,v): self.calls.append(("fill",a.logical_id)); self.values[a.logical_id]=v
    def select(self,a,v): self.calls.append(("select",a.logical_id)); self.values[a.logical_id]=v
    def check(self,a,v): self.calls.append(("check",a.logical_id)); self.values[a.logical_id]=v
    def upload(self,a,p): self.calls.append(("upload",a.logical_id)); self.values[a.logical_id]=p.read_bytes()
    def verify(self,a,expected):
        value=self.values[a.logical_id]
        raw=value if isinstance(value,bytes) else str(value).encode()
        return sha256(raw).hexdigest()==expected
    def submit(self,kind,value):
        self.calls.append(("submit",kind,value))
        if self.fail_submit: raise TimeoutError
    def submission_evidence(self): return self.receipt,self.completion


def setup(tmp_path, mode="fill_only"):
    package=build_package(tmp_path); plan=build_preconfirm_plan(snapshot(),created_at=NOW)
    grant=issue_live_grant(package,plan,mode=mode,approval_actor="applicant",issued_at=NOW,
        expires_at=EXP,key_id=KEY_ID,signing_key=KEY,action_time_confirmed=True)
    return package,plan,grant


def test_actual_kodit_schema_builds_exact_origin_action_plan():
    plan=build_preconfirm_plan(snapshot(),created_at=NOW)
    assert plan.exact_origin==KODIT_ORIGIN and plan.exact_path==KODIT_PRECONFIRM_PATH
    assert len(plan.actions)==18 and set(private_value_keys())==set(values())
    assert plan.submit_locator_value=="confirm"


@pytest.mark.parametrize("change", ["origin","path","action","captcha","mfa","field","option"])
def test_kodit_schema_drift_or_security_marker_is_fail_closed(change):
    raw=snapshot()
    if change=="origin": raw["origin"]="https://evil.example:443"
    elif change=="path": raw["path"]="/other"
    elif change=="action": raw["forms"][0]["action"]="https://evil.example/submit"
    elif change in {"captcha","mfa"}: raw[change]=True
    elif change=="field": raw["fields"].pop()
    else: raw["fields"][5]["options"].append({"text":"unexpected"})
    with pytest.raises(LiveApplicationError): build_preconfirm_plan(raw,created_at=NOW)


def test_fill_executes_once_and_ledger_never_contains_private_values(tmp_path):
    package,plan,grant=setup(tmp_path); driver=FakeLiveDriver(plan); ledger=tmp_path/"live-ledger.json"
    result=execute_live_application(package,plan,grant,driver,private_values=values(),executed_at=RUN,
        ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert result.status=="filled_verified" and len(result.verified_fields)==18
    assert not any(call[0]=="submit" for call in driver.calls)
    text=ledger.read_text(encoding="utf-8")
    for secret in ("홍길동","010","person","gmail.com"): assert secret not in text
    with pytest.raises(LiveApplicationError,match="already used"):
        execute_live_application(package,plan,grant,FakeLiveDriver(plan),private_values=values(),executed_at=RUN,
            ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)


@pytest.mark.parametrize("marker", ["captcha","mfa","otp","unknown_field","cross_origin_iframe"])
def test_runtime_security_marker_stops_before_any_mutation(tmp_path, marker):
    package,plan,grant=setup(tmp_path); driver=FakeLiveDriver(plan,markers=(marker,))
    with pytest.raises(LiveApplicationError,match="manual review"):
        execute_live_application(package,plan,grant,driver,private_values=values(),executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[]


def test_changed_schema_and_missing_action_confirmation_stop_before_mutation(tmp_path):
    package,plan,grant=setup(tmp_path); driver=FakeLiveDriver(plan,schema="0"*64)
    with pytest.raises(LiveApplicationError,match="schema changed"):
        execute_live_application(package,plan,grant,driver,private_values=values(),executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[]
    with pytest.raises(LiveApplicationError,match="confirmation"):
        issue_live_grant(package,plan,mode="fill_only",approval_actor="applicant",issued_at=NOW,
            expires_at=EXP,key_id=KEY_ID,signing_key=KEY,action_time_confirmed=False)


def test_required_consent_and_confirmation_mismatch_stop_before_mutation(tmp_path):
    package,plan,grant=setup(tmp_path); driver=FakeLiveDriver(plan)
    bad={**values(),"privacy_sensitive":"false"}
    with pytest.raises(LiveApplicationError,match="consent"):
        execute_live_application(package,plan,grant,driver,private_values=bad,executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[]
    bad={**values(),"email_local_confirm":"different"}
    with pytest.raises(LiveApplicationError,match="differs"):
        execute_live_application(package,plan,grant,driver,private_values=bad,executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[]
    bad={**values(),"email_domain_custom":"unexpected","email_domain_custom_confirm":"unexpected"}
    with pytest.raises(LiveApplicationError,match="must be blank"):
        execute_live_application(package,plan,grant,driver,private_values=bad,executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    bad={**values(),"email_domain":"직접입력","email_domain_confirm":"직접입력"}
    with pytest.raises(LiveApplicationError,match="is required"):
        execute_live_application(package,plan,grant,driver,private_values=bad,executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[]


def test_upload_requires_separate_confirmation_and_verifies_file_hash(tmp_path):
    package,plan,_grant=setup(tmp_path)
    attachment=tmp_path/"resume.pdf"; attachment.write_bytes(b"synthetic-pdf")
    upload=LiveFieldAction("resume","id","resume_file","upload","resume_path","file",True,None,(".pdf",))
    plan=replace(plan,actions=plan.actions+(upload,))
    grant=issue_live_grant(package,plan,mode="fill_only",approval_actor="applicant",issued_at=NOW,
        expires_at=EXP,key_id=KEY_ID,signing_key=KEY,action_time_confirmed=True)
    upload_values={**values(),"resume_path":attachment}
    driver=FakeLiveDriver(plan)
    with pytest.raises(LiveApplicationError,match="upload requires"):
        execute_live_application(package,plan,grant,driver,private_values=upload_values,executed_at=RUN,
            ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[]
    result=execute_live_application(package,plan,grant,driver,private_values=upload_values,executed_at=RUN,
        ledger_path=tmp_path/"ledger.json",key_id=KEY_ID,signing_key=KEY,upload_confirmed=True)
    assert result.status=="filled_verified" and ("upload","resume") in driver.calls


def test_submit_requires_separate_confirmation_and_records_intent_before_driver(tmp_path):
    package,plan,grant=setup(tmp_path,"submit"); driver=FakeLiveDriver(plan); ledger=tmp_path/"ledger.json"
    with pytest.raises(LiveApplicationError,match="immediate confirmation"):
        execute_live_application(package,plan,grant,driver,private_values={},executed_at=RUN,
            ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.calls==[] and not ledger.exists()
    result=execute_live_application(package,plan,grant,driver,private_values={},executed_at=RUN,
        ledger_path=ledger,key_id=KEY_ID,signing_key=KEY,final_submit_confirmed=True)
    assert result.status=="submitted_verified" and driver.calls==[("submit","id","confirm")]
    data=json.loads(ledger.read_text(encoding="utf-8"))
    assert [event["event_type"] for event in data["events"]]==["submit_started","submitted_verified"]


def test_submit_timeout_is_unverified_and_never_retried(tmp_path):
    package,plan,grant=setup(tmp_path,"submit"); driver=FakeLiveDriver(plan,fail_submit=True); ledger=tmp_path/"ledger.json"
    result=execute_live_application(package,plan,grant,driver,private_values={},executed_at=RUN,
        ledger_path=ledger,key_id=KEY_ID,signing_key=KEY,final_submit_confirmed=True)
    assert result.status=="submission_unverified" and result.reason_code=="SUBMIT_RESULT_UNVERIFIED"
    with pytest.raises(LiveApplicationError,match="already used"):
        execute_live_application(package,plan,grant,driver,private_values={},executed_at=RUN,
            ledger_path=ledger,key_id=KEY_ID,signing_key=KEY,final_submit_confirmed=True)


def test_package_must_be_eligible_and_consent_values_are_consistent(tmp_path):
    package,plan,_grant=setup(tmp_path)
    with pytest.raises(LiveApplicationError,match="not eligible"):
        issue_live_grant(replace(package,eligibility_status="manual_review"),plan,mode="fill_only",
            approval_actor="applicant",issued_at=NOW,expires_at=EXP,key_id=KEY_ID,signing_key=KEY,
            action_time_confirmed=True)
    good=values(); validate_private_consents(good)
    bad={**good,"privacy_sensitive":"false"}
    with pytest.raises(LiveApplicationError,match="consents"):
        validate_private_consents(bad)


def test_cli_builds_plan_and_requires_explicit_live_authorization_flag(tmp_path, monkeypatch):
    package=build_package(tmp_path)
    write_application_package(tmp_path/"package.json",package)
    write_json(tmp_path/"snapshot.json",snapshot())
    assert main(["application","live-plan","--root",str(tmp_path),"--adapter","saramin_applyin_kodit_live",
        "--snapshot","snapshot.json","--output","plan.json","--at",NOW])==0
    monkeypatch.setenv("CAREER_APPLICATION_AUTH_HMAC_KEY","k"*32)
    base=["application","live-authorize","--root",str(tmp_path),"--package","package.json","--plan","plan.json",
        "--mode","fill_only","--approver-id","applicant","--at",NOW,"--expires-at",EXP,"--output","grant.json"]
    assert main(base)==4
    assert not (tmp_path/"grant.json").exists()
    assert main(base+["--confirm-live-action"])==0
    grant=json.loads((tmp_path/"grant.json").read_text(encoding="utf-8"))
    assert grant["mode"]=="fill_only" and grant["exact_origin"]==KODIT_ORIGIN
