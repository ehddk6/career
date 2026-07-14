"""Live Saramin Applyin action plans with an exact-origin allowlist.

Only the KODIT recruitment tenant inspected on 2026-07-13 is enabled.  Other
Applyin tenants must be independently observed and added as a separate exact
contract; sharing a platform family is not authority to mutate another origin.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Iterable, Mapping

from ..live_application import LiveActionPlan, LiveApplicationError, LiveConditionalValue, LiveFieldAction

PLATFORM_ID = "saramin_applyin"
ADAPTER_ID = "saramin_applyin_kodit_live"
ADAPTER_VERSION = 1
KODIT_ORIGIN = "https://kodit2.saramin.co.kr:443"
KODIT_PRECONFIRM_PATH = "/service/kodit2/3872/applicant/apply/pre_confirm.asp"
KODIT_PRECONFIRM_ACTION = "https://kodit2.saramin.co.kr/service/kodit2/3872/applicant/apply/pre_confirm_ok.asp"

_FIELD_ORDER = (
    ("privacy_general", "id", "check1", "check", "privacy_general", "checkbox", True, None, ()),
    ("privacy_sensitive", "id", "check2", "check", "privacy_sensitive", "checkbox", True, None, ()),
    ("privacy_processing", "id", "check3", "check", "privacy_processing", "checkbox", True, None, ()),
    ("privacy_third_party", "id", "check4", "check", "privacy_third_party", "checkbox", True, None, ()),
    ("privacy_final_confirmation", "id", "check5", "check", "privacy_final_confirmation", "checkbox", True, None, ()),
    ("recruitment_track", "id", "field1", "select", "recruitment_track", "select-one", True, None,
        ("체험형 청년인턴1(보증)", "체험형 청년인턴2(보험)")),
    ("headquarters", "id", "field2", "select", "headquarters", "select-one", True, None, ()),
    ("branch", "id", "field3", "select", "branch", "select-one", True, None, ()),
    ("applicant_name", "name", "kor_name", "fill", "applicant_name", "text", True, 10, ()),
    ("phone_prefix", "name", "hp1", "fill", "phone_prefix", "text", True, 3, ()),
    ("phone_middle", "name", "hp2", "fill", "phone_middle", "text", True, 4, ()),
    ("phone_suffix", "name", "hp3", "fill", "phone_suffix", "text", True, 4, ()),
    ("email_local", "id", "email1", "fill", "email_local", "text", True, 20, ()),
    ("email_domain", "name", "email2_select", "select", "email_domain", "select-one", True, None,
        ("naver.com", "nate.com", "gmail.com", "직접입력")),
    ("email_domain_custom", "name", "email2_etc", "fill", "email_domain_custom", "text", False, 20, ()),
    ("email_local_confirm", "id", "email1_check", "fill", "email_local_confirm", "text", True, None, ()),
    ("email_domain_confirm", "name", "email2_select_check", "select", "email_domain_confirm", "select-one", True, None,
        ("naver.com", "nate.com", "gmail.com", "직접입력")),
    ("email_domain_custom_confirm", "name", "email2_etc_check", "fill", "email_domain_custom_confirm", "text", False, 20, ()),
)


def normalize_preconfirm_schema(snapshot: Mapping) -> dict:
    """Return the non-sensitive structural subset used for drift detection."""
    fields = []
    for field in snapshot.get("fields", ()):  # values are intentionally ignored
        options = tuple(item.get("text", "") for item in (field.get("options") or ()) if item.get("text"))
        fields.append({
            "tag": field.get("tag"), "type": field.get("type"), "name": field.get("name"),
            "id": field.get("id"), "required": bool(field.get("required")),
            "maxlength": field.get("maxlength"), "options": options,
        })
    forms = tuple({"method": form.get("method"), "action": form.get("action")} for form in snapshot.get("forms", ()))
    return {
        "schema_version": "saramin-applyin-kodit-preconfirm-v1",
        "origin": snapshot.get("origin"), "path": snapshot.get("path"),
        "forms": forms, "fields": tuple(fields),
        "iframe_count": int(snapshot.get("iframe_count", 0)),
        "captcha": bool(snapshot.get("captcha")), "mfa": bool(snapshot.get("mfa")),
    }


def schema_sha256(schema: Mapping) -> str:
    return sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_preconfirm_schema(schema: Mapping) -> None:
    if schema.get("origin") != KODIT_ORIGIN or schema.get("path") != KODIT_PRECONFIRM_PATH:
        raise LiveApplicationError("KODIT exact origin or path mismatch")
    if schema.get("iframe_count") or schema.get("captcha") or schema.get("mfa"):
        raise LiveApplicationError("KODIT security marker requires manual review")
    forms = tuple(schema.get("forms", ()))
    if len(forms) != 1 or forms[0].get("method", "").casefold() != "post" or forms[0].get("action") != KODIT_PRECONFIRM_ACTION:
        raise LiveApplicationError("KODIT form action changed")
    actual = {(field.get("id") or field.get("name")): field for field in schema.get("fields", ())}
    expected_keys = {locator for _logical, _kind, locator, _action, _key, _type, _required, _max, _options in _FIELD_ORDER}
    if set(actual) != expected_keys:
        raise LiveApplicationError("KODIT field set changed")
    for _logical, _kind, locator, _action, _key, expected_type, _required, max_length, options in _FIELD_ORDER:
        field = actual[locator]
        if field.get("type") != expected_type or field.get("maxlength") != max_length:
            raise LiveApplicationError("KODIT field contract changed")
        actual_options = tuple(item for item in field.get("options", ()) if item not in {"선택", "선택하세요"})
        if options and actual_options != options:
            raise LiveApplicationError("KODIT select options changed")


def build_preconfirm_plan(snapshot: Mapping, *, created_at: str) -> LiveActionPlan:
    schema = normalize_preconfirm_schema(snapshot)
    validate_preconfirm_schema(schema)
    digest = schema_sha256(schema)
    actions = tuple(LiveFieldAction(*field) for field in _FIELD_ORDER)
    plan_id = "saramin-kodit-preconfirm-" + sha256(f"{digest}|{created_at}".encode()).hexdigest()[:24]
    return LiveActionPlan(1, plan_id, ADAPTER_ID, ADAPTER_VERSION, KODIT_ORIGIN,
        KODIT_PRECONFIRM_PATH, KODIT_PRECONFIRM_ACTION, digest, actions,
        (("email_local", "email_local_confirm"), ("email_domain", "email_domain_confirm"),
         ("email_domain_custom", "email_domain_custom_confirm")),
        (LiveConditionalValue("email_domain_custom", "email_domain", "직접입력", True, True),),
        "id", "confirm", created_at)


def private_value_keys() -> tuple[str, ...]:
    return tuple(field[4] for field in _FIELD_ORDER)


def validate_private_consents(values: Mapping[str, str]) -> None:
    for key in ("privacy_general", "privacy_sensitive", "privacy_processing", "privacy_third_party", "privacy_final_confirmation"):
        if values.get(key, "").casefold() not in {"true", "yes", "1"}:
            raise LiveApplicationError("all privacy consents require explicit confirmation")
    if values.get("email_local") != values.get("email_local_confirm"):
        raise LiveApplicationError("email confirmation differs")
    if values.get("email_domain") != values.get("email_domain_confirm"):
        raise LiveApplicationError("email domain confirmation differs")
    if values.get("email_domain") == "직접입력":
        if not values.get("email_domain_custom") or values.get("email_domain_custom") != values.get("email_domain_custom_confirm"):
            raise LiveApplicationError("custom email domain confirmation differs")
    elif values.get("email_domain_custom") or values.get("email_domain_custom_confirm"):
        raise LiveApplicationError("custom email domain must be blank for a predefined domain")
