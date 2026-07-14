from pathlib import Path
from dataclasses import replace
from dataclasses import asdict
import json
import pytest

from career_pipeline.application_execution import ApplicationExecutionError, ExecutionArtifactClassification, classify_execution_artifact, issue_fixture_fill_authorization, revoke_authorization
from career_pipeline.models import FormAutomationResult
from career_pipeline.application_package import write_application_package
from career_pipeline.__main__ import main
from career_pipeline.adapters.saramin_applyin import ADAPTER_ID, CONTRACT_VERSION, FIXTURE_ORIGIN, LIVE_ENABLED, AdapterBlocked, FixtureMockPage, collect_fixture_schema, run_fixture_fill, schema_sha256
from tests.test_application_package import build_package

FIXTURE=Path("tests/fixtures/saramin_applyin/application_form_v1.html")
VALUES={"applicant_name":"Synthetic","email":"person@example.invalid","phone":"010-0000-0000","recruitment_track":"general_admin","preferred_region":"seoul","education_summary":"Synthetic","experience_summary":"Synthetic","motivation":"a"*20,"competency":"a"*20,"teamwork":"a"*20,"career_plan":"a"*20,"privacy_consent":"true"}

def legacy_call(tmp_path, schema=None):
    page=FixtureMockPage(schema or collect_fixture_schema(FIXTURE.read_text(encoding="utf-8")))
    with pytest.raises(AdapterBlocked,match="LEGACY_AUTHORIZATION_UNUSABLE"):
        run_fixture_fill(page,VALUES,None,None,object(),executed_at="2026-07-12T12:05:00+09:00",ledger_path=tmp_path/"ledger.json",signing_key=b"x"*32)
    assert page.calls == []


def fixture_setup(tmp_path):
    package = build_package(tmp_path)
    schema = collect_fixture_schema(FIXTURE.read_text(encoding="utf-8"))
    digest = schema_sha256(schema)
    result = FormAutomationResult(
        1, "form-saramin", package.package_id, "review_required",
        "2026-07-12T12:00:00+09:00", "2026-07-12T12:00:00+09:00",
        "review_required", None, FIXTURE_ORIGIN + "/application",
        False, False, True, digest, True, (), (), (),
    )
    authorization = issue_fixture_fill_authorization(
        package, result, adapter_id=ADAPTER_ID,
        adapter_contract_version=CONTRACT_VERSION, form_schema_sha256=digest,
        allowed_origin=FIXTURE_ORIGIN, authorized_at="2026-07-12T12:01:00+09:00",
        expires_at="2026-07-12T13:00:00+09:00", key_id="saramin-fixture-test",
        signing_key=b"s" * 32,
    )
    return package, result, authorization, schema


def test_valid_fixture_fill_is_single_batch_and_verifies_every_field(tmp_path):
    package, result, authorization, schema = fixture_setup(tmp_path)
    page = FixtureMockPage(schema)
    report = run_fixture_fill(
        page, VALUES, package, result, authorization,
        executed_at="2026-07-12T12:05:00+09:00", ledger_path=tmp_path / "ledger.json",
        signing_key=b"s" * 32,
    )
    assert report["status"] == "filled"
    assert len(report["fields"]) == 12
    assert [call[0] for call in page.calls].count("fill") == 9
    assert [call[0] for call in page.calls].count("select_option") == 2
    assert [call[0] for call in page.calls].count("check") == 1
    assert all(call[0] not in {"click", "submit", "upload"} for call in page.calls)

    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["authorizations"][authorization.authorization_id]["status"] == "applyin_fixture_completed"
    assert all("value" not in event.get("metadata", {}) for event in ledger["events"])
    assert "person@example.invalid" not in json.dumps(ledger, ensure_ascii=False)


def test_valid_fixture_authorization_is_single_use(tmp_path):
    package, result, authorization, schema = fixture_setup(tmp_path)
    ledger = tmp_path / "ledger.json"
    page = FixtureMockPage(schema)
    run_fixture_fill(page, VALUES, package, result, authorization,
        executed_at="2026-07-12T12:05:00+09:00", ledger_path=ledger, signing_key=b"s" * 32)
    second_page = FixtureMockPage(schema)
    with pytest.raises(ApplicationExecutionError, match="already used"):
        run_fixture_fill(second_page, VALUES, package, result, authorization,
            executed_at="2026-07-12T12:06:00+09:00", ledger_path=ledger, signing_key=b"s" * 32)
    assert second_page.calls == []


def test_fixture_page_must_be_the_local_mock_type(tmp_path):
    package, result, authorization, schema = fixture_setup(tmp_path)

    class DuckPage:
        def snapshot(self): return schema
        def fill(self, selector, value): raise AssertionError("must not mutate")
        def select_option(self, selector, value): raise AssertionError("must not mutate")
        def check(self, selector): raise AssertionError("must not mutate")
        def read_value(self, selector): return ""

    with pytest.raises(AdapterBlocked, match="fixture_page_required"):
        run_fixture_fill(DuckPage(), VALUES, package, result, authorization,
            executed_at="2026-07-12T12:05:00+09:00", ledger_path=tmp_path / "ledger.json",
            signing_key=b"s" * 32)


def test_schema_and_origin_tamper_block_before_mutation(tmp_path):
    package, result, authorization, schema = fixture_setup(tmp_path)
    page = FixtureMockPage(schema)
    with pytest.raises(AdapterBlocked, match="applyin_authorization_mismatch"):
        run_fixture_fill(page, VALUES, package, result,
            replace(authorization, exact_origin="https://evil.invalid:443"),
            executed_at="2026-07-12T12:05:00+09:00", ledger_path=tmp_path / "ledger.json",
            signing_key=b"s" * 32)
    assert page.calls == []


def test_fixture_authorization_revoke_blocks_before_mutation(tmp_path):
    package, result, authorization, schema = fixture_setup(tmp_path)
    ledger = tmp_path / "ledger.json"
    revoke_authorization(ledger, authorization, revoked_at="2026-07-12T12:02:00+09:00", signing_key=b"s" * 32)
    with pytest.raises(ApplicationExecutionError, match="revoked"):
        run_fixture_fill(FixtureMockPage(schema), VALUES, package, result, authorization,
            executed_at="2026-07-12T12:05:00+09:00", ledger_path=ledger, signing_key=b"s" * 32)


def test_cli_issues_fixture_authorization_without_external_model_or_site(tmp_path, monkeypatch):
    package, result, _authorization, _schema = fixture_setup(tmp_path)
    package_path = tmp_path / "package.json"
    result_path = tmp_path / "form_result.json"
    output_path = tmp_path / "fixture_authorization.json"
    write_application_package(package_path, package)
    result_path.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CAREER_EXECUTION_SIGNING_KEY", "s" * 32)
    assert main([
        "application", "fixture-authorize", "--root", str(tmp_path),
        "--adapter", ADAPTER_ID, "--package", "package.json",
        "--dry-run-result", "form_result.json", "--allowed-origin", FIXTURE_ORIGIN,
        "--at", "2026-07-12T12:01:00+09:00", "--expires-at", "2026-07-12T13:00:00+09:00",
        "--output", "fixture_authorization.json",
    ]) == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["fixture_only"] is True and payload["mode"] == "fill_only"
    assert classify_execution_artifact(payload) is ExecutionArtifactClassification.fixture_authorization

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
