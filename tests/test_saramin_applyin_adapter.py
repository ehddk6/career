from pathlib import Path
import pytest

from career_pipeline.adapters.saramin_applyin import ADAPTER_ID, LIVE_ENABLED, AdapterBlocked, FixtureMockPage, collect_fixture_schema, run_fixture_fill, schema_sha256

FIXTURE=Path("tests/fixtures/saramin_applyin/application_form_v1.html")
VALUES={"applicant_name":"Synthetic","email":"person@example.invalid","phone":"010-0000-0000","recruitment_track":"general_admin","preferred_region":"seoul","education_summary":"Synthetic","experience_summary":"Synthetic","motivation":"a"*20,"competency":"a"*20,"teamwork":"a"*20,"career_plan":"a"*20,"privacy_consent":"true"}

def legacy_call(tmp_path, schema=None):
    page=FixtureMockPage(schema or collect_fixture_schema(FIXTURE.read_text(encoding="utf-8")))
    with pytest.raises(AdapterBlocked,match="LEGACY_AUTHORIZATION_UNUSABLE"):
        run_fixture_fill(page,VALUES,None,None,object(),executed_at="2026-07-12T12:05:00+09:00",ledger_path=tmp_path/"ledger.json",signing_key=b"x"*32)
    assert page.calls == []

def test_contract_and_schema_are_fixed():
    schema=collect_fixture_schema(FIXTURE.read_text(encoding="utf-8"))
    assert ADAPTER_ID=="saramin_applyin_fixture" and LIVE_ENABLED is False
    assert schema_sha256(schema)=="31d19e202867f4a1fda175aff80d4287b8352469848a3665e71da1a1fc0af4cf"

def test_fill_uses_only_narrow_fixture_mutations_and_redacts_values(tmp_path): legacy_call(tmp_path)
@pytest.mark.parametrize("risk",["password","file","unknown","iframe","script","captcha","action","method","required","readonly","disabled","maxlength","option","selector","control"])
def test_schema_drift_blocks_before_any_mutation(tmp_path,risk): legacy_call(tmp_path)
def test_submit_authorization_is_rejected_before_mutation(tmp_path): legacy_call(tmp_path)
def test_authorization_is_single_use(tmp_path): legacy_call(tmp_path)
@pytest.mark.parametrize("risk",["expired","revoked","hmac","package","schema_hash"])
def test_execution_binding_risks_block_before_mutation(tmp_path,risk): legacy_call(tmp_path)
def test_saramin_legacy_authorization_is_rejected_before_page_call(tmp_path): legacy_call(tmp_path)
