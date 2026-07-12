"""Read-only form discovery and fail-closed review planning."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import json
import re
from typing import Any, Mapping, Protocol

from .application_package import ApplicationPackageError, materialize_package_values
from .eligibility import canonicalize_url
from .models import ApplicationPackage, FormAutomationResult, FormFieldDescriptor, FormFieldMapping, FormFillAction
from .state import write_json

IGNORED_INPUT_TYPES = {"submit", "button", "reset"}
AUTH_MARKERS = ("login", "signin", "password", "로그인", "비밀번호")
FIELD_ALIASES = {
    "full_name": ("name", "applicant name", "성명", "이름"),
    "email": ("email", "e-mail", "이메일"),
    "phone": ("phone", "mobile", "전화번호", "휴대전화"),
    "resume": ("resume", "cv", "이력서"),
}


class FormAdapterError(ValueError): pass


class FormDriver(Protocol):
    def discover_fields(self) -> tuple[FormFieldDescriptor, ...]: ...
    def page_text(self) -> str: ...
    def current_url(self) -> str | None: ...


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", value.casefold())


def _aliases(package: ApplicationPackage) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for key in package.private_field_keys:
        result[key] = {_normalize(v) for v in (key, key.replace("_", " "), *FIELD_ALIASES.get(key, ())) if _normalize(v)}
    for answer in package.answers:
        result[answer.field_key] = {_normalize(v) for v in (answer.field_key, answer.prompt, f"question {answer.question_index}", f"문항 {answer.question_index}") if _normalize(v)}
    for item in package.attachments:
        result[item.field_key] = {_normalize(v) for v in (item.field_key, item.field_key.replace("_", " "), *FIELD_ALIASES.get(item.field_key, ())) if _normalize(v)}
    return result


def map_form_fields(package: ApplicationPackage, fields: tuple[FormFieldDescriptor, ...]) -> tuple[FormFieldMapping, ...]:
    aliases, used, mappings = _aliases(package), set(), []
    seen_ids: set[str] = set()
    for field in fields:
        if field.field_id in seen_ids:
            mappings.append(FormFieldMapping(field.field_id, None, "ambiguous", "duplicate form field identifier")); continue
        seen_ids.add(field.field_id)
        if field.input_type in IGNORED_INPUT_TYPES:
            mappings.append(FormFieldMapping(field.field_id, None, "ignored", f"ignored input type: {field.input_type}")); continue
        parts = {_normalize(v) for v in (field.label, field.name or "", field.role or "", field.field_id) if _normalize(v)}
        matches = [key for key, candidates in aliases.items() if any(c in parts or (len(c) >= 5 and any(c in p for p in parts)) for c in candidates)]
        available = [key for key in matches if key not in used]
        if len(available) == 1:
            used.add(available[0]); mappings.append(FormFieldMapping(field.field_id, available[0], "matched", "label/name/role match"))
        elif matches:
            mappings.append(FormFieldMapping(field.field_id, None, "ambiguous", "multiple or duplicate package fields match"))
        else:
            mappings.append(FormFieldMapping(field.field_id, None, "unmapped", "new or unknown form field"))
    return tuple(mappings)


def form_schema_sha256(fields: tuple[FormFieldDescriptor, ...]) -> str:
    return sha256(json.dumps([asdict(f) for f in fields], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _security(driver: FormDriver, fields: tuple[FormFieldDescriptor, ...]) -> tuple[bool, bool, bool]:
    combined = _normalize(driver.page_text() + " " + " ".join(f"{f.label} {f.name or ''}" for f in fields))
    captcha = any(v in combined for v in ("captcha", "recaptcha", "hcaptcha", "자동입력방지"))
    mfa = any(v in combined for v in ("mfa", "twofactor", "otp", "verificationcode", "인증번호", "2단계인증")) or any(f.input_type == "password" for f in fields) or any(v in combined for v in AUTH_MARKERS)
    return captcha, mfa, any(f.input_type == "submit" for f in fields)


class ReviewRequiredFormAdapter:
    """Inspect and validate only. This class never mutates page state."""

    def run(self, driver: FormDriver, *, root: Path, package: ApplicationPackage, private_data_path: Path,
            attachments: Mapping[str, Path] | None = None, evaluation_time: str | None = None) -> FormAutomationResult:
        now = evaluation_time or datetime.now().astimezone().isoformat(timespec="seconds")
        try: parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError as error: raise FormAdapterError("evaluation_time must be timezone-aware ISO-8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None: raise FormAdapterError("evaluation_time must be timezone-aware ISO-8601")
        fields = driver.discover_fields(); schema = form_schema_sha256(fields); captcha, mfa, submit = _security(driver, fields)
        mappings = map_form_fields(package, fields); issues: list[str] = []; stop: str | None = None; status = "review_required"
        if package.validation_status == "blocked": status, stop = "blocked", "package_blocked"
        elif package.validation_status != "ready_for_review": status, stop = "manual_review", "package_requires_manual_review"
        elif captcha: status, stop = "blocked", "captcha_detected"
        elif mfa: status, stop = "blocked", "mfa_or_authentication_detected"
        elif any(m.status in {"unmapped", "ambiguous"} for m in mappings): status, stop = "manual_review", "unknown_or_ambiguous_field"
        actions: list[FormFillAction] = []
        if stop is None:
            try: values = materialize_package_values(root, package, private_data_path=private_data_path, attachments=attachments)
            except ApplicationPackageError as error: status, stop, issues = "blocked", "package_materialization_failed", [str(error)]
            else:
                by_id = {f.field_id: f for f in fields}
                for mapping in mappings:
                    if mapping.status != "matched" or mapping.package_field_key is None: continue
                    field, value = by_id[mapping.field_id], values.get(mapping.package_field_key)
                    if value is None: issues.append(f"{field.field_id}: required package value missing"); continue
                    if field.disabled or field.readonly: issues.append(f"{field.field_id}: field is disabled or readonly")
                    if field.max_length is not None and field.input_type != "file" and len(value) > field.max_length: issues.append(f"{field.field_id}: value exceeds max length")
                    if field.input_type == "select" and field.options and value not in field.options: issues.append(f"{field.field_id}: select option unavailable")
                    if field.input_type == "file":
                        item = next((a for a in package.attachments if a.field_key == mapping.package_field_key), None)
                        accepted = {a.casefold() for a in field.accept}
                        if item and accepted and not any(a == item.suffix or a == item.media_type or (a == "image/*" and item.media_type.startswith("image/")) for a in accepted):
                            issues.append(f"{field.field_id}: attachment type is not accepted")
                    action = "file" if field.input_type == "file" else "select" if field.input_type == "select" else "check" if field.input_type in {"checkbox", "radio"} else "text"
                    actions.append(FormFillAction(field.field_id, mapping.package_field_key, action, sha256(value.encode()).hexdigest(), "planned"))
                if issues: status, stop, actions = "manual_review", "form_value_incompatible", []
        final_fields = driver.discover_fields(); unchanged = form_schema_sha256(final_fields) == schema
        if not unchanged:
            status, stop, actions = "blocked", "form_schema_changed", []
            issues.append("form schema changed during inspection")
        elif stop is None:
            actions = [FormFillAction(a.field_id, a.package_field_key, a.action, a.value_sha256, "validated") for a in actions]
        url = driver.current_url()
        return FormAutomationResult(1, "form-" + sha256(f"{package.package_id}|{now}".encode()).hexdigest()[:24], package.package_id,
            "review_required", now, now, status, stop, canonicalize_url(url) if url else None, captcha, mfa, submit, schema,
            unchanged, mappings, tuple(actions), tuple(issues))


class _FixtureParser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.fields=[]; self.labels={}; self.text=[]; self.label_for=None; self.label_text=[]; self.select=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=="label": self.label_for=a.get("for"); self.label_text=[]
        if tag in {"input","textarea","select"}:
            fid=a.get("id") or a.get("name") or f"field-{len(self.fields)+1}"; typ="select" if tag=="select" else "textarea" if tag=="textarea" else a.get("type","text").lower(); ml=a.get("maxlength")
            self.fields.append(dict(field_id=fid,label=a.get("aria-label",""),name=a.get("name"),role=a.get("role"),input_type=typ,
                required="required" in a or a.get("aria-required")=="true",options=[],max_length=int(ml) if ml and ml.isdigit() else None,
                accept=tuple(x.strip() for x in a.get("accept","").split(",") if x.strip()),disabled="disabled" in a,readonly="readonly" in a))
            if tag=="select": self.select=len(self.fields)-1
    def handle_endtag(self, tag):
        if tag=="label" and self.label_for: self.labels[self.label_for]=" ".join(" ".join(self.label_text).split()); self.label_for=None
        if tag=="select": self.select=None
    def handle_data(self,data):
        self.text.append(data)
        if self.label_for: self.label_text.append(data)
        if self.select is not None and data.strip(): self.fields[self.select]["options"].append(data.strip())


class FixtureFormDriver:
    def __init__(self, html: str, *, url="https://fixture.invalid/application"):
        p=_FixtureParser(); p.feed(html)
        for item in p.fields: item["label"]=item["label"] or p.labels.get(item["field_id"],""); item["options"]=tuple(item["options"])
        self._fields=tuple(FormFieldDescriptor(**i) for i in p.fields); self._text=" ".join(p.text); self._url=url
    @classmethod
    def from_path(cls,path:Path,*,url="https://fixture.invalid/application"): return cls(Path(path).read_text(encoding="utf-8"),url=url)
    def discover_fields(self): return self._fields
    def page_text(self): return self._text
    def current_url(self): return self._url


class PlaywrightFormDriver:
    """Read-only duck-typed Playwright Page adapter."""
    def __init__(self,page:Any): self.page=page
    def discover_fields(self):
        locator=self.page.locator("input, textarea, select"); fields=[]
        for i in range(locator.count()):
            item=locator.nth(i); tag=(item.evaluate("el => el.tagName.toLowerCase()") or "input").lower(); fid=item.get_attribute("id") or item.get_attribute("name") or f"field-{i+1}"
            label=item.get_attribute("aria-label") or ""; typ="select" if tag=="select" else "textarea" if tag=="textarea" else (item.get_attribute("type") or "text").lower(); ml=item.get_attribute("maxlength")
            fields.append(FormFieldDescriptor(fid,label,item.get_attribute("name"),item.get_attribute("role"),typ,
                item.get_attribute("required") is not None or item.get_attribute("aria-required")=="true",
                tuple(item.locator("option").all_text_contents()) if tag=="select" else (), int(ml) if ml and ml.isdigit() else None,
                tuple(x.strip() for x in (item.get_attribute("accept") or "").split(",") if x.strip()),
                item.get_attribute("disabled") is not None, item.get_attribute("readonly") is not None))
        return tuple(fields)
    def page_text(self): return self.page.locator("body").inner_text()
    def current_url(self): return getattr(self.page,"url",None)


def form_automation_result_to_dict(result: FormAutomationResult) -> dict[str, Any]: return asdict(result)
def write_form_result(path: Path, result: FormAutomationResult) -> None: write_json(path, form_automation_result_to_dict(result))


def load_form_result(path: Path) -> FormAutomationResult:
    from .models import FormFieldMapping, FormFillAction
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    value["mappings"] = tuple(FormFieldMapping(**item) for item in value.get("mappings", []))
    value["actions"] = tuple(FormFillAction(**item) for item in value.get("actions", []))
    value["verification_issues"] = tuple(value.get("verification_issues", []))
    return FormAutomationResult(**value)
