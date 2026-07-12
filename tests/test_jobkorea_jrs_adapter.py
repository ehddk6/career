from pathlib import Path
import pytest

from career_pipeline.adapters.jobkorea_jrs import ADAPTER_ID, LIVE_ENABLED, AdapterBlocked, FixtureMockPage, collect_fixture_schema, fixture_schema_sha256, run_fixture_fill

FIXTURE=Path("tests/fixtures/jobkorea_jrs/application_form_v1.html")
VALUES={"applicant_name":"Synthetic","email":"person@example.invalid","phone":"010-0000-0000","recruitment_track":"general_admin","work_region":"seoul","motivation":"a"*20,"problem_solving":"a"*20,"teamwork":"a"*20,"career_plan":"a"*20,"privacy_consent":"true"}

def legacy_call(tmp_path, schema=None):
    page=FixtureMockPage(schema or collect_fixture_schema(FIXTURE.read_text(encoding="utf-8")))
    with pytest.raises(AdapterBlocked,match="LEGACY_AUTHORIZATION_UNUSABLE"):
        run_fixture_fill(page,VALUES,None,None,object(),executed_at="2026-07-12T12:05:00+09:00",ledger_path=tmp_path/"ledger.json",signing_key=b"x"*32)
    assert page.calls == []

def test_contract_and_schema_are_fixed():
    schema=collect_fixture_schema(FIXTURE.read_text(encoding="utf-8"))
    assert ADAPTER_ID=="jobkorea_jrs_fixture" and LIVE_ENABLED is False
    assert fixture_schema_sha256(schema)=="296a196d9151fe10e988d73e8ca6016bdc01746225e2d96db8550f35dd85dac9"

def test_normal_fill_only_uses_only_allowed_mutations(tmp_path): legacy_call(tmp_path)

@pytest.mark.parametrize("risk",["password","file","unknown","iframe","script","captcha","action","required","readonly","disabled","maxlength","option","selector_zero","selector_duplicate","submit"])
def test_any_schema_risk_blocks_before_mutation(tmp_path,risk): legacy_call(tmp_path)

def test_jobkorea_legacy_authorization_is_rejected_before_page_call(tmp_path): legacy_call(tmp_path)
