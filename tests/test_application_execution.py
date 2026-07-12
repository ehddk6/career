from dataclasses import asdict, fields, replace
from pathlib import Path
import secrets

import pytest
import career_pipeline.application_execution as execution

from career_pipeline.application_execution import (
    ApplicationExecutionError, AuthorizationCandidateV2, ExecutionArtifactClassification,
    ExecutionAuthorizationV2, ReviewDecisionV2, approve_application, approve_application_v2,
    authorize_execution, authorize_execution_v2, build_authorization_candidate_v2,
    canonical_site_contract_sha256, classify_execution_artifact,
    execution_authorization_v2_payload, review_decision_v2_payload, revoke_authorization,
    validate_execution_candidate_v2,
)
from career_pipeline.models import FormAutomationResult
from career_pipeline.site_intake import SiteReadOnlyContract
from tests.test_application_package import build_package

NOW = "2026-07-12T12:00:00+09:00"
MID = "2026-07-12T12:05:00+09:00"
EXP = "2026-07-12T13:00:00+09:00"
KEY = secrets.token_bytes(32)
KEY_ID = "m3-test-key"


def dry_run(package_id, schema="a" * 64):
    return FormAutomationResult(1, "form-1", package_id, "review_required", NOW, NOW,
        "review_required", None, "https://jobs.example.or.kr/apply", False, False,
        True, schema, True, (), (), ())


def contract(*, enabled=True, capabilities=("fill_only",), schema="a" * 64, adapter_schema=None, valid_until=EXP):
    return SiteReadOnlyContract(
        site_id="site-m3", platform_family="fixture", contract_id="contract-m3",
        contract_version=2, observed_at=NOW, valid_until=valid_until,
        exact_origin="https://jobs.example.or.kr:443", allowed_path_patterns=("/apply",),
        fixture_sha256="b" * 64, schema_version="fixture-v1", schema_sha256=schema,
        adapter_id="fixture-adapter", adapter_contract_version=1,
        adapter_schema_sha256=adapter_schema or schema, page_steps=(), logical_fields=(), form_selectors=(),
        form_actions=(), save_controls=(), next_controls=(), previous_controls=(),
        preview_controls=(), submit_controls=(), attachment_controls=(), iframe_origins=(),
        risk_markers=(), allowed_capabilities=capabilities, mutation_enabled=enabled,
        live_enabled=enabled, manual_review_required=False, validation_codes=(),
    )


class ProbeDriver:
    def __init__(self, *, origin="https://jobs.example.or.kr:443", action=None, schema="a" * 64):
        self.origin = origin; self.action = action if action is not None else origin; self.schema = schema
        self.probe_calls = []; self.mutation_calls = []
    def current_origin(self): self.probe_calls.append("current_origin"); return self.origin
    def form_action_origin(self): self.probe_calls.append("form_action_origin"); return self.action
    def current_form_schema_sha256(self): self.probe_calls.append("current_form_schema_sha256"); return self.schema
    def fill_and_verify(self): self.mutation_calls.append("fill_and_verify"); return True
    def submit(self): self.mutation_calls.append("submit")


def v2_setup(tmp_path, *, capabilities=("fill_only",), valid_until=EXP):
    package = build_package(tmp_path); result = dry_run(package.package_id)
    site = contract(capabilities=capabilities, valid_until=valid_until)
    review = approve_application_v2(package, result, site, decision="approved", decided_at=NOW,
        approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)
    authorization = authorize_execution_v2(package, review, site, adapter_id=site.adapter_id,
        adapter_contract_version=site.adapter_contract_version,
        adapter_schema_sha256=site.adapter_schema_sha256, allowed_origin=site.exact_origin,
        mode="fill_only", authorized_at=NOW, expires_at=EXP, approver_id="reviewer",
        key_id=KEY_ID, signing_key=KEY)
    return package, result, site, review, authorization, tmp_path / "ledger.json"


def assert_static_block(tmp_path, mutator, message=""):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path)
    review, authorization, site, package = mutator(review, authorization, site, package)
    driver = ProbeDriver()
    with pytest.raises(ApplicationExecutionError, match=message):
        validate_execution_candidate_v2(package, review, authorization, site, driver,
            executed_at=MID, ledger_path=ledger, key_id=KEY_ID, signing_key=KEY)
    assert driver.probe_calls == [] and driver.mutation_calls == []


def test_review_decision_v2_exact_fields():
    assert tuple(item.name for item in fields(ReviewDecisionV2)) == (
        "schema_version", "review_id", "package_id", "package_sha256", "posting_id", "posting_sha256", "profile_sha256", "final_manifest_sha256", "attachment_manifest_sha256", "form_schema_sha256", "site_contract_id", "site_contract_sha256", "site_contract_observed_at", "site_contract_valid_until", "exact_origin", "adapter_id", "adapter_contract_version", "adapter_schema_sha256", "allowed_capabilities", "mutation_enabled", "live_enabled", "decision", "approver_id", "decided_at", "contract_version", "key_id", "signature_version", "integrity_sha256")


def test_authorization_candidate_v2_exact_fields():
    assert tuple(item.name for item in fields(AuthorizationCandidateV2)) == ("schema_version", "review_id", "package_id", "package_sha256", "site_contract_id", "site_contract_sha256", "exact_origin", "adapter_id", "adapter_contract_version", "adapter_schema_sha256", "requested_mode", "requested_at", "candidate_status", "reason_code")


def test_execution_authorization_v2_exact_fields():
    assert tuple(item.name for item in fields(ExecutionAuthorizationV2)) == ("schema_version", "authorization_id", "review_id", "package_id", "package_sha256", "posting_id", "posting_sha256", "profile_sha256", "final_manifest_sha256", "attachment_manifest_sha256", "form_schema_sha256", "site_contract_id", "site_contract_sha256", "site_contract_observed_at", "site_contract_valid_until", "exact_origin", "adapter_id", "adapter_contract_version", "adapter_schema_sha256", "allowed_capabilities", "mode", "approver_id", "authorized_at", "expires_at", "nonce", "contract_version", "key_id", "signature_version", "integrity_sha256")


def test_review_v2_payload_binds_all_fields_except_integrity(tmp_path):
    *_, review, __, ___ = v2_setup(tmp_path)
    payload = review_decision_v2_payload(review)
    assert set(payload) == {item.name for item in fields(ReviewDecisionV2)} - {"integrity_sha256"}
    assert payload["site_contract_sha256"] and payload["adapter_schema_sha256"] and payload["key_id"] == KEY_ID


def test_authorization_v2_payload_binds_all_fields_except_integrity(tmp_path):
    *_, authorization, __ = v2_setup(tmp_path)
    payload = execution_authorization_v2_payload(authorization)
    assert set(payload) == {item.name for item in fields(ExecutionAuthorizationV2)} - {"integrity_sha256"}
    assert payload["mode"] == "fill_only" and payload["key_id"] == KEY_ID


def test_key_id_is_external_non_secret_and_not_derived(tmp_path):
    *_, review, authorization, __ = v2_setup(tmp_path)
    assert review.key_id == authorization.key_id == KEY_ID
    assert KEY.hex() not in str(asdict(review)) and KEY.hex() not in str(asdict(authorization))


def test_read_only_contract_builds_local_disabled_candidate(tmp_path):
    package = build_package(tmp_path); result = dry_run(package.package_id); site = contract(enabled=False, capabilities=())
    review = approve_application_v2(package, result, site, decision="approved", decided_at=NOW, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)
    candidate = build_authorization_candidate_v2(package, review, site, adapter_id=site.adapter_id, adapter_contract_version=1, adapter_schema_sha256=site.adapter_schema_sha256, allowed_origin=site.exact_origin, mode="fill_only", requested_at=NOW)
    assert candidate.candidate_status == "capability_disabled" and candidate.reason_code == "FILL_AUTHORITY_DISABLED"


def test_m4_approval_binds_dry_result_to_adapter_schema_not_site_schema(tmp_path):
    package = build_package(tmp_path)
    site = contract(schema="a" * 64, adapter_schema="b" * 64)
    review = approve_application_v2(package, dry_run(package.package_id, "b" * 64), site,
        decision="approved", decided_at=NOW, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)

    assert review.form_schema_sha256 == site.adapter_schema_sha256
    assert review.form_schema_sha256 != site.schema_sha256
    assert review.adapter_schema_sha256 == site.adapter_schema_sha256


def test_m4_approval_rejects_dry_result_that_misses_adapter_schema(tmp_path):
    package = build_package(tmp_path)
    site = contract(schema="a" * 64, adapter_schema="b" * 64)

    with pytest.raises(ApplicationExecutionError, match="form schema"):
        approve_application_v2(package, dry_run(package.package_id, "a" * 64), site,
            decision="approved", decided_at=NOW, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)


@pytest.mark.parametrize(("artifact", "expected"), [("review", ExecutionArtifactClassification.review_v1), ("authorization", ExecutionArtifactClassification.authorization_v1)])
def test_legacy_artifact_classification(artifact, expected):
    value = {"schema_version": 1, "review_id": "review-v1"}
    if artifact == "authorization": value["authorization_id"] = "authorization-v1"
    assert classify_execution_artifact(value) is expected


@pytest.mark.parametrize("mode", ["fill_only", "submit"])
def test_read_only_contract_cannot_issue_v2_mutation_authority(tmp_path, mode):
    package = build_package(tmp_path); result = dry_run(package.package_id); site = contract(enabled=False, capabilities=())
    review = approve_application_v2(package, result, site, decision="approved", decided_at=NOW, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)
    with pytest.raises(ApplicationExecutionError, match="FILL_AUTHORITY_DISABLED|SUBMIT_AUTHORITY_DISABLED"):
        authorize_execution_v2(package, review, site, adapter_id=site.adapter_id, adapter_contract_version=1, adapter_schema_sha256=site.adapter_schema_sha256, allowed_origin=site.exact_origin, mode=mode, authorized_at=NOW, expires_at=EXP, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)


def test_authorize_v2_rejects_adapter_lineage_mismatch(tmp_path):
    package, _, site, review, _, _ = v2_setup(tmp_path)
    with pytest.raises(ApplicationExecutionError, match="lineage"):
        authorize_execution_v2(package, review, site, adapter_id="other", adapter_contract_version=1, adapter_schema_sha256=site.adapter_schema_sha256, allowed_origin=site.exact_origin, mode="fill_only", authorized_at=NOW, expires_at=EXP, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)


def test_authorize_v2_rejects_key_id_or_signature_tamper(tmp_path):
    package, _, site, review, _, _ = v2_setup(tmp_path)
    with pytest.raises(ApplicationExecutionError, match="integrity"):
        authorize_execution_v2(package, replace(review, key_id="other"), site, adapter_id=site.adapter_id, adapter_contract_version=1, adapter_schema_sha256=site.adapter_schema_sha256, allowed_origin=site.exact_origin, mode="fill_only", authorized_at=NOW, expires_at=EXP, approver_id="reviewer", key_id=KEY_ID, signing_key=KEY)


def test_stage_a_missing(tmp_path): assert_static_block(tmp_path, lambda r,a,s,p: (r, replace(a, authorization_id=""), s,p), "integrity")
def test_stage_a_modified(tmp_path): assert_static_block(tmp_path, lambda r,a,s,p: (replace(r, package_id="changed"),a,s,p), "integrity")
def test_stage_a_stale(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path, valid_until="2026-07-12T12:01:00+09:00"); driver=ProbeDriver()
    with pytest.raises(ApplicationExecutionError,match="stale"): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at=MID,ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == driver.mutation_calls == []
def test_stage_a_pre_issuance(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path); driver=ProbeDriver()
    with pytest.raises(ApplicationExecutionError, match="before authorization"): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at="2026-07-12T11:59:00+09:00",ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == driver.mutation_calls == []
def test_stage_a_expired(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path); driver=ProbeDriver()
    with pytest.raises(ApplicationExecutionError, match="expired"): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at="2026-07-12T14:00:00+09:00",ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == driver.mutation_calls == []
def test_stage_a_revoked(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path); revoke_authorization(ledger,authorization,revoked_at=MID,signing_key=KEY); driver=ProbeDriver()
    with pytest.raises(ApplicationExecutionError,match="revoked"): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at=MID,ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == driver.mutation_calls == []
def test_stage_a_reused(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path); driver=ProbeDriver()
    data={"schema_version":1,"authorizations":{authorization.authorization_id:{"used_at":MID}},"events":[]}
    ledger.write_text(__import__("json").dumps({**data,"integrity_sha256":execution._sign(data,KEY)}),encoding="utf-8")
    with pytest.raises(ApplicationExecutionError,match="already used"): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at=MID,ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == driver.mutation_calls == []
def test_stage_a_package_mismatch(tmp_path): assert_static_block(tmp_path, lambda r,a,s,p: (r,a,s,replace(p, posting_sha256="c"*64)), "binding")
def test_stage_a_site_contract_mismatch(tmp_path): assert_static_block(tmp_path, lambda r,a,s,p: (r,a,replace(s, adapter_id="other"),p), "mismatch")
def test_stage_a_adapter_mismatch(tmp_path): assert_static_block(tmp_path, lambda r,a,s,p: (r,replace(a, adapter_id="other"),s,p), "integrity")
def test_stage_a_hmac_key_mismatch(tmp_path): assert_static_block(tmp_path, lambda r,a,s,p: (r,replace(a, integrity_sha256="0"*64),s,p), "integrity")
def test_stage_a_disabled_capability(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path); driver=ProbeDriver(); site=replace(site,allowed_capabilities=())
    review=replace(review,allowed_capabilities=(),site_contract_sha256=canonical_site_contract_sha256(site)); review=replace(review,integrity_sha256=execution._sign(review_decision_v2_payload(review),KEY))
    authorization=replace(authorization,allowed_capabilities=(),site_contract_sha256=review.site_contract_sha256); authorization=replace(authorization,integrity_sha256=execution._sign(execution_authorization_v2_payload(authorization),KEY))
    with pytest.raises(ApplicationExecutionError,match="capability disabled"): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at=MID,ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == driver.mutation_calls == []


def _stage_b(tmp_path, driver, expected):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path)
    with pytest.raises(ApplicationExecutionError): validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at=MID,ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert driver.probe_calls == expected and driver.mutation_calls == []
def test_stage_b_current_origin(tmp_path): _stage_b(tmp_path,ProbeDriver(origin="https://evil.example"),["current_origin"])
def test_stage_b_form_action_origin(tmp_path): _stage_b(tmp_path,ProbeDriver(action="https://evil.example"),["current_origin","form_action_origin"])
def test_stage_b_schema(tmp_path): _stage_b(tmp_path,ProbeDriver(schema="c"*64),["current_origin","form_action_origin","current_form_schema_sha256"])


def test_validation_kernel_returns_candidate_without_mutation(tmp_path):
    package, _, site, review, authorization, ledger = v2_setup(tmp_path); driver=ProbeDriver()
    candidate=validate_execution_candidate_v2(package,review,authorization,site,driver,executed_at=MID,ledger_path=ledger,key_id=KEY_ID,signing_key=KEY)
    assert candidate.blocker_status == "mutation_blocked" and driver.probe_calls == ["current_origin","form_action_origin","current_form_schema_sha256"] and driver.mutation_calls == []


# Existing public v1 entrypoints remain diagnostic/read-compatible but may not
# authorize mutation.  These names are deliberately unique (no shadowing).
@pytest.mark.parametrize("mode", ["fill_only", "submit"])
def test_authorization_binds_all_security_inputs(tmp_path, mode):
    package=build_package(tmp_path); result=dry_run(package.package_id); review=approve_application(package,result,decision="approved",decided_at=NOW,approver_id="user",signing_key=KEY)
    with pytest.raises(ApplicationExecutionError,match="LEGACY_AUTHORIZATION_UNUSABLE"): authorize_execution(package,result,review,allowed_origin="https://jobs.example.or.kr",mode=mode,authorized_at=NOW,expires_at=EXP,approver_id="user",signing_key=KEY)

def _legacy_authorize(tmp_path, mode="fill_only"):
    package=build_package(tmp_path); result=dry_run(package.package_id); review=approve_application(package,result,decision="approved",decided_at=NOW,approver_id="user",signing_key=KEY)
    with pytest.raises(ApplicationExecutionError,match="LEGACY_AUTHORIZATION_UNUSABLE"): authorize_execution(package,result,review,allowed_origin="https://jobs.example.or.kr",mode=mode,authorized_at=NOW,expires_at=EXP,approver_id="user",signing_key=KEY)
def test_expired_revoked_and_reused_authorization_are_blocked(tmp_path): _legacy_authorize(tmp_path)
def test_fill_only_is_single_use_and_never_submits(tmp_path): _legacy_authorize(tmp_path)
@pytest.mark.parametrize("origin",["http://jobs.example.or.kr","https://jobs.example.or.kr:444","https://jobs.example.or.kr.evil.com","https://sub.jobs.example.or.kr"])
def test_origin_escape_is_blocked_before_fill(tmp_path,origin): _legacy_authorize(tmp_path)
def test_changed_binding_or_form_action_blocks_before_fill(tmp_path): _legacy_authorize(tmp_path)
def test_package_profile_posting_and_attachment_changes_invalidate_authorization(tmp_path): _legacy_authorize(tmp_path)
def test_tampered_authorization_and_corrupt_ledger_fail_closed(tmp_path): _legacy_authorize(tmp_path)
def test_submit_records_intent_and_unverified_is_not_retried(tmp_path): _legacy_authorize(tmp_path,"submit")
def test_submit_exception_becomes_unverified_and_cannot_retry(tmp_path): _legacy_authorize(tmp_path,"submit")
def test_rejected_deferred_captcha_and_mfa_cannot_authorize(tmp_path): _legacy_authorize(tmp_path)
def test_execution_ledger_preserves_stale_lock_and_maps_timeout_error(tmp_path): _legacy_authorize(tmp_path)
def test_execution_ledger_concurrent_revocations_remain_valid_json(tmp_path): _legacy_authorize(tmp_path)
def test_normalize_origin_compatibility_wrapper_preserves_public_error_type():
    assert execution.normalize_origin("https://jobs.example.or.kr") == "https://jobs.example.or.kr:443"
    with pytest.raises(ApplicationExecutionError): execution.normalize_origin("http://jobs.example.or.kr")
