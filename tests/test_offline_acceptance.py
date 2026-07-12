from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

import career_pipeline.application_execution as execution
from career_pipeline.application_execution import (
    ApplicationExecutionError, approve_application_v2, authorize_execution_v2,
    build_authorization_candidate_v2, revoke_authorization, validate_execution_candidate_v2,
)
from career_pipeline.models import FormAutomationResult
from career_pipeline.offline_acceptance import (
    AcceptanceInputs, OfflineAcceptanceBlockedResult, offline_acceptance_to_dict,
    run_offline_acceptance,
)
from career_pipeline.site_intake import SiteReadOnlyContract, build_site_intake
from tests.test_application_package import build_package
from tests.test_site_intake import SAFE_FORM, SAFE_STRUCTURE


NOW = "2026-07-12T12:00:00+09:00"
MID = "2026-07-12T12:05:00+09:00"
EXP = "2026-07-12T13:00:00+09:00"
KEY = b"m4-deterministic-signing-key-0001"
KEY_ID = "m4-test-key"


def acceptance_inputs():
    return AcceptanceInputs(NOW, NOW, NOW, NOW, NOW, NOW, EXP, NOW, NOW, NOW, KEY, KEY_ID,
        sha256(Path(__file__).read_bytes()).hexdigest())


class ProbeDriver:
    def __init__(self, origin="https://jobs.example.or.kr:443"):
        self.origin = origin
        self.probe_calls = []
        self.mutation_calls = []

    def current_origin(self): self.probe_calls.append("current_origin"); return self.origin
    def form_action_origin(self): self.probe_calls.append("form_action_origin"); return self.origin
    def current_form_schema_sha256(self): self.probe_calls.append("current_form_schema_sha256"); return "a" * 64
    def fill_and_verify(self): self.mutation_calls.append("fill_and_verify"); return True
    def submit(self): self.mutation_calls.append("submit")


def _enabled_fixture(tmp_path, *, expires_at=EXP):
    package = build_package(tmp_path)
    site = SiteReadOnlyContract("site-m4", "fixture", "contract-m4", 2, NOW, EXP,
        "https://jobs.example.or.kr:443", ("/apply",), "a" * 64, "fixture-v1", "a" * 64,
        "fixture-adapter", 1, "a" * 64, (), (), (), (), (), (), (), (), (), (), (), (),
        ("fill_only",), True, True, False, ())
    dry = FormAutomationResult(1, "form-m4", package.package_id, "review_required", NOW, NOW,
        "review_required", None, "https://jobs.example.or.kr/apply", False, False, True, "a" * 64, True, (), (), ())
    review = approve_application_v2(package, dry, site, decision="approved", decided_at=NOW,
        approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)
    authorization = authorize_execution_v2(package, review, site, adapter_id=site.adapter_id,
        adapter_contract_version=site.adapter_contract_version, adapter_schema_sha256=site.adapter_schema_sha256,
        allowed_origin=site.exact_origin, mode="fill_only", authorized_at=NOW, expires_at=expires_at,
        approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)
    return package, review, authorization, site, tmp_path / "ledger.json"


def test_offline_acceptance_reaches_external_live_disabled_boundary(tmp_path):
    result = run_offline_acceptance(workspace=tmp_path, inputs=acceptance_inputs())
    assert (result.local_status, result.live_status, result.submission_status) == ("awaiting_external_live_enablement", "disabled", "not_attempted")
    assert result.authorization_candidate.candidate_status == "capability_disabled"
    assert tuple(result.counters.__dict__.values()) == (0, 0, 0, 0, 0, 0, 0)


def test_offline_acceptance_uses_structured_eligible_posting_and_synthetic_temp_workspace(tmp_path):
    result = run_offline_acceptance(workspace=tmp_path, inputs=acceptance_inputs())
    assert result.posting_id and result.profile_id and result.eligibility_decision_id
    assert (tmp_path / "career_runs" / "offline-acceptance" / "run.json").is_file()
    assert not (tmp_path / "career_runs" / "offline-acceptance" / "draft_humanized.json").exists()


def test_offline_acceptance_builds_valid_readiness_report_and_disabled_candidate(tmp_path):
    result = run_offline_acceptance(workspace=tmp_path, inputs=acceptance_inputs())
    assert result.authorization_candidate.reason_code == "FILL_AUTHORITY_DISABLED"
    assert {axis.axis.value: axis.status.value for axis in result.readiness_report.axes} == {
        "local_foundation": "complete", "offline_acceptance": "passed", "external_inputs": "blocked",
        "live_execution": "disabled", "submission": "not_attempted",
    }
    test_evidence = next(item for item in result.readiness_report.evidence if item.evidence_id == "EVIDENCE-TEST")
    assert test_evidence.source == "tests/test_offline_acceptance.py"
    assert test_evidence.sha256 == sha256(Path(__file__).read_bytes()).hexdigest()


def test_offline_acceptance_is_deterministic_for_identical_inputs_across_roots(tmp_path):
    first = run_offline_acceptance(workspace=tmp_path / "one", inputs=acceptance_inputs())
    second = run_offline_acceptance(workspace=tmp_path / "two", inputs=acceptance_inputs())
    assert offline_acceptance_to_dict(first) == offline_acceptance_to_dict(second)


def test_offline_acceptance_sensitive_fixture_fails_closed(tmp_path):
    sentinel = "test_session_token_sentinel"
    inputs = replace(acceptance_inputs(), fixture_scenario="sensitive_fixture",
        fixture_html=SAFE_FORM + f"<input type='password' value='{sentinel}'>")
    result = run_offline_acceptance(workspace=tmp_path, inputs=inputs)
    assert isinstance(result, OfflineAcceptanceBlockedResult)
    assert result.block_code == "blocked_sensitive_fixture"
    assert sentinel not in str(offline_acceptance_to_dict(result))
    assert tuple(result.counters.__dict__.values()) == (0, 0, 0, 0, 0, 0, 0)


def test_offline_acceptance_stale_digest_fails_before_issuance(tmp_path):
    package, review, _, site, _ = _enabled_fixture(tmp_path)
    stale_package = replace(package, final_manifest_sha256="f" * 64)
    with pytest.raises(ApplicationExecutionError, match="review binding changed"):
        build_authorization_candidate_v2(stale_package, review, site, adapter_id=site.adapter_id,
            adapter_contract_version=site.adapter_contract_version, adapter_schema_sha256=site.adapter_schema_sha256,
            allowed_origin=site.exact_origin, mode="fill_only", requested_at=NOW)
    assert tuple(run_offline_acceptance(workspace=tmp_path / "result", inputs=acceptance_inputs()).counters.__dict__.values()) == (0, 0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("state", ["revoked", "expired", "reused"])
def test_offline_acceptance_static_kernel_negative(tmp_path, state):
    expires_at = "2026-07-12T12:01:00+09:00" if state == "expired" else EXP
    package, review, authorization, site, ledger = _enabled_fixture(tmp_path, expires_at=expires_at)
    if state == "revoked":
        revoke_authorization(ledger, authorization, revoked_at=NOW, signing_key=KEY)
    elif state == "reused":
        execution._write_ledger(ledger, {"schema_version": 1, "authorizations": {authorization.authorization_id: {"used_at": NOW}}, "events": []}, KEY)
    driver = ProbeDriver()
    with pytest.raises(ApplicationExecutionError, match=state if state != "reused" else "already used"):
        validate_execution_candidate_v2(package, review, authorization, site, driver, executed_at=MID,
            ledger_path=ledger, key_id=KEY_ID, signing_key=KEY)
    assert driver.probe_calls == [] and driver.mutation_calls == []


def test_offline_acceptance_origin_mismatch_is_probe_only(tmp_path):
    package, review, authorization, site, ledger = _enabled_fixture(tmp_path)
    driver = ProbeDriver("https://other.example.or.kr:443")
    with pytest.raises(ApplicationExecutionError, match="current origin mismatch"):
        validate_execution_candidate_v2(package, review, authorization, site, driver, executed_at=MID,
            ledger_path=ledger, key_id=KEY_ID, signing_key=KEY)
    assert driver.probe_calls == ["current_origin"] and driver.mutation_calls == []


def test_offline_acceptance_unknown_structure_blocks_contract(tmp_path):
    (tmp_path / "unknown.html").write_text(SAFE_FORM + "<iframe src='https://frame.example.invalid'></iframe>", encoding="utf-8")
    result = build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply",
        fixture_root=tmp_path, fixture_resource_id="unknown.html", discovery_platform_id=None,
        created_at=NOW, known_structure={**SAFE_STRUCTURE, "iframe_status": "unknown"})
    assert result.contract is None and result.record.manual_review_required
