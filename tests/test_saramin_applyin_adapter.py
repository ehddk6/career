from dataclasses import replace
from pathlib import Path
import secrets

import pytest

from career_pipeline.adapters.saramin_applyin import (
    ADAPTER_ID, LIVE_ENABLED, AdapterBlocked, FixtureMockPage,
    collect_fixture_schema, run_fixture_fill, schema_sha256,
)
from career_pipeline.application_execution import approve_application, authorize_execution, revoke_authorization
from tests.test_application_execution import dry_run
from tests.test_application_package import build_package

FIXTURE = Path("tests/fixtures/saramin_applyin/application_form_v1.html")
KEY = secrets.token_bytes(32)
NOW = "2026-07-12T12:05:00+09:00"
VALUES = {
    "applicant_name": "Synthetic Applicant", "email": "person@example.invalid",
    "phone": "010-0000-0000", "recruitment_track": "general_admin",
    "preferred_region": "seoul", "education_summary": "Synthetic education",
    "experience_summary": "Synthetic experience", "motivation": "A" * 20,
    "competency": "B" * 20, "teamwork": "C" * 20,
    "career_plan": "D" * 20, "privacy_consent": "true",
}

def setup_case(tmp_path):
    schema = collect_fixture_schema(FIXTURE.read_text(encoding="utf-8"))
    digest = schema_sha256(schema)
    package = build_package(tmp_path)
    result = replace(dry_run(package.package_id), form_schema_sha256=digest)
    review = approve_application(package, result, decision="approved", decided_at="2026-07-12T12:00:00+09:00", approver_id="user", signing_key=KEY)
    auth = authorize_execution(package, result, review, allowed_origin="https://sample-company.applyin.invalid", mode="fill_only", authorized_at="2026-07-12T12:00:00+09:00", expires_at="2026-07-12T13:00:00+09:00", approver_id="user", signing_key=KEY)
    return schema, package, result, auth, tmp_path / "ledger.json"

def test_contract_and_schema_are_fixed():
    schema = collect_fixture_schema(FIXTURE.read_text(encoding="utf-8"))
    assert ADAPTER_ID == "saramin_applyin_fixture" and LIVE_ENABLED is False
    assert len(schema["fields"]) == 12
    assert schema["form_action"] == "https://sample-company.applyin.invalid/application/submit"
    assert schema_sha256(schema) == "31d19e202867f4a1fda175aff80d4287b8352469848a3665e71da1a1fc0af4cf"

def test_fill_uses_only_narrow_fixture_mutations_and_redacts_values(tmp_path):
    schema, package, result, auth, ledger = setup_case(tmp_path)
    page = FixtureMockPage(schema)
    report = run_fixture_fill(page, VALUES, package, result, auth, executed_at=NOW, ledger_path=ledger, signing_key=KEY)
    assert report["status"] == "filled" and len(report["fields"]) == 12
    assert {call[0] for call in page.calls} == {"fill", "select_option", "check"}
    assert "Synthetic Applicant" not in str(report) and "person@example.invalid" not in str(report)

@pytest.mark.parametrize("mutation", ["password", "file", "unknown", "iframe", "script", "captcha", "action", "method", "required", "readonly", "disabled", "maxlength", "option", "selector", "control"])
def test_schema_drift_blocks_before_any_mutation(tmp_path, mutation):
    schema, package, result, auth, ledger = setup_case(tmp_path)
    changed = {**schema, "fields": [dict(x) for x in schema["fields"]], "controls": [dict(x) for x in schema["controls"]]}
    if mutation in {"password", "file", "unknown"}:
        changed["fields"].append({"logical_id": "bad", "selector": "#bad", "type": "text" if mutation == "unknown" else mutation, "required": False, "maxlength": None, "options": [], "readonly": False, "disabled": False})
    elif mutation in {"iframe", "script"}: changed[mutation + "_count"] = 1
    elif mutation == "captcha": changed["security_markers"] = ["captcha"]
    elif mutation == "action": changed["form_action"] = "https://evil.invalid/submit"
    elif mutation == "method": changed["form_method"] = "get"
    elif mutation == "required": changed["fields"][0]["required"] = False
    elif mutation == "readonly": changed["fields"][0]["readonly"] = True
    elif mutation == "disabled": changed["fields"][0]["disabled"] = True
    elif mutation == "maxlength": changed["fields"][0]["maxlength"] = 41
    elif mutation == "option": changed["fields"][3]["options"].append("unexpected")
    elif mutation == "selector": changed["fields"][0]["selector"] = "#missing"
    else: changed["controls"][1]["selector"] = "#changed"
    page = FixtureMockPage(changed)
    with pytest.raises(AdapterBlocked):
        run_fixture_fill(page, VALUES, package, result, auth, executed_at=NOW, ledger_path=ledger, signing_key=KEY)
    assert page.calls == []

def test_submit_authorization_is_rejected_before_mutation(tmp_path):
    schema, package, result, auth, ledger = setup_case(tmp_path)
    page = FixtureMockPage(schema)
    with pytest.raises(AdapterBlocked):
        run_fixture_fill(page, VALUES, package, result, replace(auth, mode="submit"), executed_at=NOW, ledger_path=ledger, signing_key=KEY)
    assert page.calls == []

def test_authorization_is_single_use(tmp_path):
    schema, package, result, auth, ledger = setup_case(tmp_path)
    run_fixture_fill(FixtureMockPage(schema), VALUES, package, result, auth, executed_at=NOW, ledger_path=ledger, signing_key=KEY)
    with pytest.raises(Exception, match="already used"):
        run_fixture_fill(FixtureMockPage(schema), VALUES, package, result, auth, executed_at=NOW, ledger_path=ledger, signing_key=KEY)

@pytest.mark.parametrize("risk", ["expired", "revoked", "hmac", "package", "schema_hash"])
def test_execution_binding_risks_block_before_mutation(tmp_path, risk):
    schema, package, result, auth, ledger = setup_case(tmp_path)
    page = FixtureMockPage(schema)
    executed_at = NOW
    if risk == "expired": executed_at = "2026-07-12T14:00:00+09:00"
    elif risk == "revoked": revoke_authorization(ledger, auth, revoked_at="2026-07-12T12:03:00+09:00", signing_key=KEY)
    elif risk == "hmac": auth = replace(auth, integrity_sha256="0" * 64)
    elif risk == "package": package = replace(package, posting_sha256="0" * 64)
    else:
        result = replace(result, form_schema_sha256="0" * 64)
    with pytest.raises(Exception):
        run_fixture_fill(page, VALUES, package, result, auth, executed_at=executed_at, ledger_path=ledger, signing_key=KEY)
    assert page.calls == []
