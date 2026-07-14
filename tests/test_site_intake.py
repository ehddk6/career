from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

import pytest

from career_pipeline.site_intake import (
    SiteIntakeError, build_site_intake, canonical_schema_sha256,
    load_fixture_resource, parse_read_only_schema, persist_intake,
    validate_url_metadata,
)
import career_pipeline.application_execution as execution
import career_pipeline.site_intake as intake

ROOT = Path("tests/fixtures/site_intake")


def _m3_contract():
    return build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=ROOT,fixture_resource_id="safe_single_page.html",discovery_platform_id=None,created_at="2026-07-12T12:00:00+09:00",valid_until="2026-07-12T13:00:00+09:00",known_structure=SAFE_STRUCTURE,adapter_schema_sha256="a" * 64).contract

def test_site_contract_v2_has_exact_lineage_capability_and_freshness_fields():
    value=_m3_contract(); assert value is not None
    assert value.contract_version == 2 and value.observed_at == "2026-07-12T12:00:00+09:00" and value.valid_until == "2026-07-12T13:00:00+09:00"
    assert value.adapter_id and value.adapter_contract_version == 1 and value.adapter_schema_sha256 == "a" * 64
    assert value.allowed_capabilities == () and value.mutation_enabled is False and value.live_enabled is False

def test_site_intake_can_only_build_disabled_capability_contracts():
    value=_m3_contract(); assert value is not None
    assert value.allowed_capabilities == () and not value.mutation_enabled and not value.live_enabled

def test_canonical_site_contract_sha256_is_stable():
    value=_m3_contract(); assert value is not None
    assert execution.canonical_site_contract_sha256(value) == execution.canonical_site_contract_sha256(value)

def test_canonical_site_contract_sha256_changes_for_each_security_binding():
    value=_m3_contract(); assert value is not None
    changes={"fixture_sha256":"c"*64,"schema_sha256":"c"*64,"adapter_schema_sha256":"c"*64,"exact_origin":"https://other.applyin.co.kr:443","valid_until":"2026-07-12T14:00:00+09:00"}
    assert all(execution.canonical_site_contract_sha256(value) != execution.canonical_site_contract_sha256(replace(value,**{field:changed})) for field,changed in changes.items())

def test_legacy_registry_contract_is_readable_but_not_v2_issuable(tmp_path):
    path=tmp_path/"registry.json"; path.write_text(json.dumps({"schema_version":1,"version":0,"records":{},"contracts":{"legacy":{"contract_version":1}},"events":[]}),encoding="utf-8")
    assert intake.load_intake_registry(path)["contracts"]["legacy"]["contract_version"] == 1

UNSAFE_STRUCTURE_CASES = (
    ({}, "LOGIN_STATUS_UNVERIFIED"),
    ({"login_status": "unknown"}, "LOGIN_STATUS_UNVERIFIED"),
    ({"login_status": "required"}, "LOGIN_REQUIRED"),
    ({"mfa_status": "unknown"}, "MFA_STATUS_UNVERIFIED"),
    ({"mfa_status": "present"}, "MFA_DETECTED"),
    ({"captcha_status": "unknown"}, "CAPTCHA_STATUS_UNVERIFIED"),
    ({"captcha_status": "present"}, "CAPTCHA_DETECTED"),
    ({"iframe_status": "unknown"}, "IFRAME_STATUS_UNVERIFIED"),
    ({"iframe_status": "present"}, "EXTERNAL_IFRAME"),
    ({"popup_status": "unknown"}, "POPUP_STRUCTURE_UNKNOWN"),
    ({"popup_status": "present"}, "POPUP_STRUCTURE_UNKNOWN"),
    ({"redirect_status": "unknown"}, "REDIRECT_STRUCTURE_UNKNOWN"),
    ({"redirect_status": "present"}, "REDIRECT_STRUCTURE_UNKNOWN"),
    ({"attachment_status": "unknown"}, "ATTACHMENT_POLICY_UNKNOWN"),
    ({"attachment_status": "required"}, "ATTACHMENT_REQUIRED"),
)

SAFE_STRUCTURE = {
    "login_status": "none", "mfa_status": "none", "captcha_status": "none",
    "iframe_status": "none", "popup_status": "none", "redirect_status": "none",
    "attachment_status": "unsupported",
}

SAFE_FORM = """<form id="application" action="https://company.applyin.co.kr/submit" method="post"><button id="save" type="button" data-role="save">Save</button><button id="submit" type="submit">Submit</button></form>"""

STRUCTURE_CASES = (
    ("<base href='https://other.invalid/'>" + SAFE_FORM, "BASE_ELEMENT_REVIEW_REQUIRED"),
    (SAFE_FORM.replace('id="submit"', 'id="submit" formaction="/other"'), "FORMACTION_REVIEW_REQUIRED"),
    ("<form action='https://company.applyin.co.kr/submit'><form></form></form>", "NESTED_FORM_DETECTED"),
    ("<form action='https://company.applyin.co.kr/one'></form><form action='https://company.applyin.co.kr/two'></form>", "MULTIPLE_FORMS_DETECTED"),
    ("<form action='https://company.applyin.co.kr/submit'>", "MALFORMED_FORM_STRUCTURE"),
    ("<form action='https://company.applyin.co.kr/submit'/><button id='save' type='button' data-role='save'>Save</button><button id='submit' type='submit'>Submit</button>", "MALFORMED_FORM_STRUCTURE"),
)

def test_applyin_url_is_classified_without_network_and_query_is_removed():
    result = validate_url_metadata("https://company.applyin.co.kr/apply?view=1#top")
    assert result.platform_family == "saramin_applyin"
    assert result.exact_origin == "https://company.applyin.co.kr:443"
    assert result.normalized_url == "https://company.applyin.co.kr/apply"

@pytest.mark.parametrize("url", [
    "http://company.applyin.co.kr", "ftp://example.com/a", "file:///tmp/a",
    "javascript:alert(1)", "data:text/plain,x", "https://user:pw@example.com/a",
    "https://*.applyin.co.kr/a", "https://example.com:bad/a", "https://127.0.0.1/a",
    "https://bad_host.example/a", "https://-bad.example/a", "https://bad-.example/a",
    "https://example.com/a\r\nX-Test: bad",
])
def test_unsafe_urls_are_blocked(url):
    with pytest.raises(SiteIntakeError): validate_url_metadata(url)

def test_sensitive_query_is_blocked_without_echoing_value():
    with pytest.raises(SiteIntakeError) as error:
        validate_url_metadata("https://example.com/apply?access_token=TOP_SECRET_SENTINEL")
    assert "TOP_SECRET_SENTINEL" not in str(error.value)

def test_sensitive_fragment_is_blocked_and_idn_is_canonicalized():
    with pytest.raises(SiteIntakeError):
        validate_url_metadata("https://example.com/apply#session=secret")
    result=validate_url_metadata("https://예시.한국/apply")
    assert result.normalized_host.startswith("xn--") and result.platform_family=="unknown"

@pytest.mark.parametrize("url", ["https://applyin.co.kr.evil.example/a","https://evilapplyin.co.kr/a","https://applyin.co.kr.example/a"])
def test_applyin_lookalikes_are_not_classified(url):
    assert validate_url_metadata(url).platform_family=="unknown"

def test_jrs_public_origin_is_not_promoted_to_execution_origin():
    result = validate_url_metadata("https://jrs.jobkorea.co.kr/")
    assert result.platform_family == "jobkorea_jrs"
    assert result.exact_origin is None
    assert "JRS_APPLICATION_ORIGIN_UNRESOLVED" in result.validation_codes

def test_unknown_family_and_saramin_destination_require_review():
    unknown = validate_url_metadata("https://jobs.example.invalid/apply")
    assert unknown.platform_family == "unknown" and unknown.manual_review_required
    saramin = build_site_intake(posting_url="https://www.saramin.co.kr/zf_user/jobs/relay/view", resolved_application_url=None, fixture_root=ROOT, fixture_resource_id=None, discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00")
    assert "APPLICATION_DESTINATION_UNRESOLVED" in saramin.record.validation_codes

@pytest.mark.parametrize("kwargs",[
    {"created_at":"not-a-time"},
    {"created_at":"2026-07-12T12:00:00"},
    {"discovery_platform_id":"unknown"},
    {"discovery_platform_id":"saramin_applyin"},
    {"known_structure":{"mfa_status":"maybe"}},
])
def test_direct_api_rejects_invalid_metadata(kwargs):
    base={"posting_url":None,"resolved_application_url":"https://company.applyin.co.kr/apply","fixture_root":ROOT,"fixture_resource_id":"safe_single_page.html","discovery_platform_id":None,"created_at":"2026-07-12T12:00:00+09:00"}
    base.update(kwargs)
    with pytest.raises(SiteIntakeError): build_site_intake(**base)

def test_explicit_platform_family_mismatch_requires_review():
    result=build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=ROOT,fixture_resource_id="safe_single_page.html",discovery_platform_id="saramin_direct",created_at="2026-07-12T12:00:00+09:00",requested_platform_family="jobkorea_jrs")
    assert "PLATFORM_FAMILY_MISMATCH" in result.record.validation_codes and result.record.manual_review_required

def test_fixture_loader_is_root_confined_and_opaque():
    resource = load_fixture_resource(ROOT, "safe_single_page.html")
    assert resource.resource_id.startswith("fixture-") and resource.byte_length > 0
    assert "site_intake" not in resource.resource_id
    for unsafe in ("../safe_single_page.html", str(ROOT.resolve() / "safe_single_page.html"), "C:relative.html", "file.txt"):
        with pytest.raises(SiteIntakeError): load_fixture_resource(ROOT, unsafe)

def test_fixture_loader_blocks_binary_large_and_symlink(tmp_path):
    (tmp_path/"binary.html").write_bytes(b"<html>\x00</html>")
    (tmp_path/"large.html").write_bytes(b"x"*1_000_001)
    for name in ("binary.html","large.html"):
        with pytest.raises(SiteIntakeError): load_fixture_resource(tmp_path,name)
    link=tmp_path/"link.html"
    try: link.symlink_to(ROOT.resolve()/"safe_single_page.html")
    except OSError: pytest.skip("symlink creation unavailable")
    with pytest.raises(SiteIntakeError): load_fixture_resource(tmp_path,"link.html")

def test_sensitive_fixture_is_blocked_without_value_disclosure():
    result = build_site_intake(posting_url="https://www.saramin.co.kr/jobs", resolved_application_url="https://company.applyin.co.kr/apply", fixture_root=ROOT, fixture_resource_id="sensitive_sentinel.html", discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00")
    assert result.record.contract_status == "blocked_sensitive_fixture"
    assert "SENSITIVE_FIXTURE" in result.record.validation_codes
    assert "TEST_SESSION_TOKEN_SENTINEL" not in str(asdict(result.record))

def test_sensitive_embedded_url_is_blocked_and_never_enters_schema(tmp_path):
    html='<form action="https://company.applyin.co.kr/submit?session=EMBEDDED_SECRET"><button type="submit">Submit</button></form>'
    (tmp_path/"embedded.html").write_text(html,encoding="utf-8")
    result=build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=tmp_path,fixture_resource_id="embedded.html",discovery_platform_id=None,created_at="2026-07-12T12:00:00+09:00")
    assert result.record.contract_status=="blocked_sensitive_fixture" and result.schema is None
    assert "EMBEDDED_SECRET" not in str(asdict(result.record))

@pytest.mark.parametrize("snippet",[
    '<input type="password" value="SECRET_VALUE">',
    '<div>4111 1111 1111 1111</div>',
    '<script>gtag("config","G-ABCDEF12")</script>',
    '<input value="C:\\Users\\person\\AppData\\Local\\Chrome\\User Data">',
])
def test_additional_sensitive_fixture_classes_are_blocked(tmp_path,snippet):
    (tmp_path/"risk.html").write_text(f'<form action="https://company.applyin.co.kr/submit">{snippet}<button type="submit">Submit</button></form>',encoding="utf-8")
    result=build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=tmp_path,fixture_resource_id="risk.html",discovery_platform_id=None,created_at="2026-07-12T12:00:00+09:00")
    assert result.record.contract_status=="blocked_sensitive_fixture" and "SENSITIVE_FIXTURE" in result.record.validation_codes

def test_safe_fixture_produces_stable_read_only_contract():
    first = load_fixture_resource(ROOT, "safe_single_page.html")
    schema = parse_read_only_schema(first.html, "https://company.applyin.co.kr:443")
    reordered = first.html.replace('id="applicant_name" name="applicant_name" type="text" required maxlength="40"', 'maxlength="40" required type="text" name="applicant_name" id="applicant_name"')
    assert canonical_schema_sha256(schema) == canonical_schema_sha256(parse_read_only_schema(reordered, "https://company.applyin.co.kr:443"))
    result = build_site_intake(posting_url="https://www.saramin.co.kr/jobs", resolved_application_url="https://company.applyin.co.kr/apply", fixture_root=ROOT, fixture_resource_id="safe_single_page.html", discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00", known_structure=SAFE_STRUCTURE, adapter_schema_sha256="a" * 64)
    assert result.record.contract_status == "read_only_contract_ready"
    assert result.contract and result.contract.mutation_enabled is False and result.contract.live_enabled is False


def test_m4_site_intake_records_explicit_adapter_schema_lineage(tmp_path):
    (tmp_path / "safe.html").write_text(SAFE_FORM, encoding="utf-8")
    result = build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply",
        fixture_root=tmp_path, fixture_resource_id="safe.html", discovery_platform_id=None,
        created_at="2026-07-12T12:00:00+09:00", valid_until="2026-07-12T13:00:00+09:00",
        known_structure=SAFE_STRUCTURE, adapter_schema_sha256="b" * 64)

    assert result.contract is not None
    assert result.contract.schema_sha256 != result.contract.adapter_schema_sha256 == "b" * 64


def test_m4_site_intake_without_adapter_schema_lineage_fails_closed(tmp_path):
    (tmp_path / "safe.html").write_text(SAFE_FORM, encoding="utf-8")
    result = build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply",
        fixture_root=tmp_path, fixture_resource_id="safe.html", discovery_platform_id=None,
        created_at="2026-07-12T12:00:00+09:00", valid_until="2026-07-12T13:00:00+09:00",
        known_structure=SAFE_STRUCTURE)

    assert result.contract is None
    assert result.record.manual_review_required is True
    assert "ADAPTER_SCHEMA_LINEAGE_UNVERIFIED" in result.record.validation_codes

@pytest.mark.parametrize(("structure_override", "expected_code"), UNSAFE_STRUCTURE_CASES)
def test_every_unverified_structure_status_blocks_ready(tmp_path, structure_override, expected_code):
    known_structure = {} if not structure_override else {**SAFE_STRUCTURE, **structure_override}
    result = build_site_intake(
        posting_url=None,
        resolved_application_url="https://company.applyin.co.kr/apply",
        fixture_root=ROOT,
        fixture_resource_id="safe_single_page.html",
        discovery_platform_id=None,
        created_at="2026-07-12T12:00:00+09:00",
        known_structure=known_structure,
    )
    assert expected_code in result.record.validation_codes
    assert result.record.manual_review_required is True
    assert result.contract is None

def test_review_evidence_changes_intake_identity(monkeypatch):
    kwargs = {
        "posting_url": None,
        "resolved_application_url": "https://company.applyin.co.kr/apply",
        "fixture_root": ROOT,
        "fixture_resource_id": "safe_single_page.html",
        "discovery_platform_id": None,
        "created_at": "2026-07-12T12:00:00+09:00",
        "known_structure": SAFE_STRUCTURE,
    }
    first = build_site_intake(**kwargs)
    second = build_site_intake(**kwargs)
    assert first.record.intake_id == second.record.intake_id

    login_required = build_site_intake(
        **{**kwargs, "known_structure": {**SAFE_STRUCTURE, "login_status": "required"}}
    )
    assert login_required.record.intake_id != first.record.intake_id

    monkeypatch.setattr(
        "career_pipeline.site_intake._risks",
        lambda *_: ("MANUAL_FIELD_MAPPING_REQUIRED",),
    )
    changed_codes = build_site_intake(**kwargs)
    assert changed_codes.record.intake_id not in {
        first.record.intake_id,
        login_required.record.intake_id,
    }

@pytest.mark.parametrize(("html", "expected_code"), STRUCTURE_CASES)
def test_unsupported_html_structures_require_manual_review(tmp_path, html, expected_code):
    def build_inline_intake(tmp_path, html):
        (tmp_path / "case.html").write_text(html, encoding="utf-8")
        return build_site_intake(
            posting_url=None,
            resolved_application_url="https://company.applyin.co.kr/apply",
            fixture_root=tmp_path,
            fixture_resource_id="case.html",
            discovery_platform_id=None,
            created_at="2026-07-12T12:00:00+09:00",
            known_structure=SAFE_STRUCTURE,
        )

    result = build_inline_intake(tmp_path, html)
    assert expected_code in result.record.validation_codes
    assert result.record.manual_review_required is True
    assert result.contract is None

@pytest.mark.parametrize("old,new", [
    ('required maxlength="40"','maxlength="40"'),
    ('maxlength="40"','maxlength="41"'),
    ('type="text"','type="email"'),
    ('value="finance"','value="technology"'),
    ('/apply/submit','/apply/final-submit'),
    ('id="submit" type="submit"','id="submit" type="button"'),
    ('</form>','<iframe src="https://frame.example.invalid"></iframe></form>'),
    ('</body>','<script src="https://script.example.invalid/a.js"></script></body>'),
])
def test_security_relevant_schema_changes_change_hash(old,new):
    html=load_fixture_resource(ROOT,"safe_single_page.html").html
    baseline=parse_read_only_schema(html,"https://company.applyin.co.kr:443")
    changed=parse_read_only_schema(html.replace(old,new,1),"https://company.applyin.co.kr:443")
    assert canonical_schema_sha256(baseline)!=canonical_schema_sha256(changed)

def test_multistep_and_password_fixtures_do_not_become_ready():
    multi = build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply", fixture_root=ROOT, fixture_resource_id="multistep_unknown.html", discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00")
    assert multi.record.manual_review_required and "REDIRECT_STRUCTURE_UNKNOWN" in multi.record.validation_codes
    risk = build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply", fixture_root=ROOT, fixture_resource_id="risk_password.html", discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00")
    assert "PASSWORD_FIELD_DETECTED" in risk.record.validation_codes

def test_visible_captcha_text_and_known_structure_metadata_block_ready(tmp_path):
    html=load_fixture_resource(ROOT,"safe_single_page.html").html.replace("</form>","<p>CAPTCHA required</p></form>")
    (tmp_path/"captcha.html").write_text(html,encoding="utf-8")
    captcha=build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=tmp_path,fixture_resource_id="captcha.html",discovery_platform_id=None,created_at="2026-07-12T12:00:00+09:00")
    assert "CAPTCHA_DETECTED" in captcha.record.validation_codes
    unknown=build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=ROOT,fixture_resource_id="safe_single_page.html",discovery_platform_id=None,created_at="2026-07-12T12:00:00+09:00",known_structure={"popup_status":"unknown","redirect_status":"unknown","attachment_status":"unknown"})
    assert unknown.record.manual_review_required

def test_schema_contains_only_sanitized_embedded_urls():
    html=load_fixture_resource(ROOT,"safe_single_page.html").html.replace('/apply/submit"','/apply/submit?view=1#fragment"')
    schema=parse_read_only_schema(html,"https://company.applyin.co.kr:443")
    rendered=str(schema)
    assert "view=1" not in rendered and "fragment" not in rendered
    assert schema["forms"][0]["action_path"]=="/apply/submit"

def test_intake_registry_is_idempotent_and_versioned(tmp_path):
    result = build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply", fixture_root=ROOT, fixture_resource_id="safe_single_page.html", discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00")
    path = tmp_path / "registry.json"
    assert persist_intake(path, result, expected_version=0)["version"] == 1
    assert persist_intake(path, result, expected_version=1)["version"] == 1
    with pytest.raises(SiteIntakeError, match="stale"):
        persist_intake(path, result, expected_version=0)
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(SiteIntakeError, match="corrupt"):
        persist_intake(path, result)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(SiteIntakeError, match="corrupt"):
        persist_intake(path, result)

def test_registry_write_failure_preserves_previous_json(tmp_path, monkeypatch):
    result=build_site_intake(posting_url=None,resolved_application_url="https://company.applyin.co.kr/apply",fixture_root=ROOT,fixture_resource_id="safe_single_page.html",discovery_platform_id="saramin_direct",created_at="2026-07-12T12:00:00+09:00")
    path=tmp_path/"registry.json"; persist_intake(path,result)
    original=path.read_bytes()
    import career_pipeline.site_intake as module
    monkeypatch.setattr(module,"write_json",lambda *_: (_ for _ in ()).throw(OSError("simulated")))
    changed=replace(result,record=replace(result.record,intake_id="intake-other",created_at="2026-07-12T12:01:00+09:00"))
    with pytest.raises(OSError): persist_intake(path,changed)
    assert path.read_bytes()==original

def test_cli_sensitive_schema_output_never_contains_fixture_value(tmp_path,capsys):
    fixture_root=tmp_path/"tests"/"fixtures"/"site_intake"; fixture_root.mkdir(parents=True)
    shutil.copy(ROOT/"sensitive_sentinel.html",fixture_root/"sensitive_sentinel.html")
    from career_pipeline.__main__ import build_parser,run_application_command
    args=build_parser().parse_args(["application","site-intake","schema","--root",str(tmp_path),"--resolved-application-url","https://company.applyin.co.kr/apply","--fixture-resource-id","sensitive_sentinel.html"])
    assert run_application_command(args)==2
    output=capsys.readouterr().out
    assert "TEST_SESSION_TOKEN_SENTINEL" not in output and '"schema": null' in output


def _registry_result():
    return build_site_intake(posting_url=None, resolved_application_url="https://company.applyin.co.kr/apply", fixture_root=ROOT, fixture_resource_id="safe_single_page.html", discovery_platform_id="saramin_direct", created_at="2026-07-12T12:00:00+09:00")


def test_intake_registry_preserves_stale_lock_and_maps_timeout_error(tmp_path, monkeypatch):
    from career_pipeline.path_policy import LockOwner, exclusive_lock as real_exclusive_lock
    path = tmp_path / "registry.json"
    lock_path = path.with_suffix(path.suffix + ".lock")
    owner = LockOwner(1, "d" * 32, 1, "host", (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat())
    lock_path.write_text(json.dumps(owner.__dict__) + "\n", encoding="utf-8")
    original = lock_path.read_bytes()
    import career_pipeline.site_intake as module
    monkeypatch.setattr(module, "exclusive_lock", lambda lock, **_: real_exclusive_lock(lock, timeout_seconds=0.02, poll_interval_seconds=0.001, stale_after_seconds=0))
    with pytest.raises(SiteIntakeError, match="registry lock timeout"):
        persist_intake(path, _registry_result())
    assert lock_path.read_bytes() == original


def test_intake_registry_concurrent_idempotent_writers_leave_valid_registry(tmp_path):
    path, result = tmp_path / "registry.json", _registry_result()
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: persist_intake(path, result), range(16)))
    registry = json.loads(path.read_text(encoding="utf-8"))
    assert len(registry["records"]) == 1 and len(registry["events"]) == 1
    assert not path.with_suffix(path.suffix + ".lock").exists()


def test_site_intake_exact_origin_matches_shared_origin_policy():
    from career_pipeline.origin_policy import origin_from_url
    value = "https://COMPANY.applyin.co.kr/apply?view=1#top"
    assert validate_url_metadata(value).exact_origin == origin_from_url(value)
