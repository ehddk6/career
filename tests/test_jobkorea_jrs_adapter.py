from dataclasses import replace
from pathlib import Path
import secrets

import pytest

from career_pipeline.adapters.jobkorea_jrs import (ADAPTER_ID, LIVE_ENABLED, AdapterBlocked,
    FixtureMockPage, collect_fixture_schema, fixture_schema_sha256, run_fixture_fill)
from career_pipeline.application_execution import approve_application, authorize_execution
from tests.test_application_execution import dry_run
from tests.test_application_package import build_package

FIXTURE=Path("tests/fixtures/jobkorea_jrs/application_form_v1.html"); KEY=secrets.token_bytes(32)
VALUES={"applicant_name":"테스트지원자","email":"person@example.invalid","phone":"010-0000-0000","recruitment_track":"general_admin","work_region":"seoul","motivation":"가"*20,"problem_solving":"나"*20,"teamwork":"다"*20,"career_plan":"라"*20,"privacy_consent":"true"}

def setup(tmp_path):
    schema=collect_fixture_schema(FIXTURE.read_text(encoding="utf-8")); digest=fixture_schema_sha256(schema)
    package=build_package(tmp_path); result=replace(dry_run(package.package_id),form_schema_sha256=digest)
    review=approve_application(package,result,decision="approved",decided_at="2026-07-12T12:00:00+09:00",approver_id="user",signing_key=KEY)
    auth=authorize_execution(package,result,review,allowed_origin="https://jrs.fixture.invalid",mode="fill_only",authorized_at="2026-07-12T12:00:00+09:00",expires_at="2026-07-12T13:00:00+09:00",approver_id="user",signing_key=KEY)
    return schema,package,result,auth,tmp_path/"ledger.json"

def test_contract_and_schema_are_fixed():
    schema=collect_fixture_schema(FIXTURE.read_text(encoding="utf-8"))
    assert ADAPTER_ID=="jobkorea_jrs_fixture" and LIVE_ENABLED is False
    assert len(schema["fields"])==10 and schema["form_action"]=="https://jrs.fixture.invalid/application/submit"
    assert fixture_schema_sha256(schema)=="296a196d9151fe10e988d73e8ca6016bdc01746225e2d96db8550f35dd85dac9"

def test_normal_fill_only_uses_only_allowed_mutations(tmp_path):
    schema,package,result,auth,ledger=setup(tmp_path); page=FixtureMockPage(schema)
    report=run_fixture_fill(page,VALUES,package,result,auth,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    assert report["status"]=="filled" and len(report["fields"])==10
    assert {call[0] for call in page.calls}=={"fill","select_option","check"}
    assert "테스트지원자" not in str(report) and "person@example.invalid" not in str(report)

@pytest.mark.parametrize("mutation",["password","file","unknown","iframe","script","captcha","action","required","readonly","disabled","maxlength","option","selector_zero","selector_duplicate","submit"])
def test_any_schema_risk_blocks_before_mutation(tmp_path,mutation):
    schema,package,result,auth,ledger=setup(tmp_path); changed={**schema,"fields":[dict(x) for x in schema["fields"]],"controls":[dict(x) for x in schema["controls"]]}
    if mutation in {"password","file","unknown"}: changed["fields"].append({"logical_id":"bad","selector":"#bad","type":"text" if mutation=="unknown" else mutation,"required":False,"maxlength":None,"options":[],"readonly":False,"disabled":False})
    elif mutation in {"iframe","script"}: changed[mutation+"_count"]=1
    elif mutation=="captcha": changed["security_markers"]=["captcha"]
    elif mutation=="action": changed["form_action"]="https://evil.invalid/submit"
    elif mutation=="required": changed["fields"][0]["required"]=False
    elif mutation=="readonly": changed["fields"][0]["readonly"]=True
    elif mutation=="disabled": changed["fields"][0]["disabled"]=True
    elif mutation=="maxlength": changed["fields"][0]["maxlength"]=41
    elif mutation=="option": changed["fields"][3]["options"].append("evil")
    elif mutation=="selector_zero": changed["fields"][0]["selector"]="#missing"
    elif mutation=="selector_duplicate": changed["fields"][1]["selector"]=changed["fields"][0]["selector"]
    else: changed["controls"][1]["selector"]="#changed"
    page=FixtureMockPage(changed)
    with pytest.raises(AdapterBlocked): run_fixture_fill(page,VALUES,package,result,auth,executed_at="2026-07-12T12:05:00+09:00",ledger_path=ledger,signing_key=KEY)
    assert page.calls==[]
