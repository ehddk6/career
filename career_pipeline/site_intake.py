"""Offline, read-only intake for user-supplied de-identified HTML fixtures."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path, PureWindowsPath
import re
from typing import Literal
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from .state import write_json
from .platform_catalog import get_platform, PlatformCatalogError
from .origin_policy import OriginPolicyError, origin_from_url
from .path_policy import LockAcquisitionError, PathConfinementError, PathLinkError, confine_path, exclusive_lock

CONTRACT_VERSION = 1
MAX_FIXTURE_BYTES = 1_000_000
SENSITIVE_QUERY_KEYS = {"token", "access_token", "refresh_token", "session", "auth", "authorization", "key", "api_key", "code", "cookie"}

class SiteIntakeError(ValueError):
    pass

@dataclass(frozen=True)
class UrlMetadata:
    normalized_url: str
    exact_origin: str | None
    normalized_host: str
    platform_family: str
    manual_review_required: bool
    validation_codes: tuple[str, ...]

@dataclass(frozen=True)
class FixtureResource:
    resource_id: str
    sha256: str
    byte_length: int
    html: str

@dataclass(frozen=True)
class SiteIntakeRecord:
    intake_id: str
    platform_family: str
    discovery_platform_id: str | None
    original_posting_url: str | None
    resolved_application_url: str | None
    exact_origin: str | None
    normalized_host: str | None
    fixture_resource_id: str | None
    fixture_sha256: str | None
    schema_sha256: str | None
    login_status: str
    mfa_status: str
    captcha_status: str
    iframe_status: str
    popup_status: str
    redirect_status: str
    attachment_status: str
    page_structure: str
    save_control_status: str
    submit_control_status: str
    manual_review_required: bool
    validation_codes: tuple[str, ...]
    contract_status: str
    created_at: str
    contract_version: int

@dataclass(frozen=True)
class SiteReadOnlyContract:
    site_id: str
    platform_family: str
    contract_id: str
    contract_version: Literal[2]
    observed_at: str
    valid_until: str
    exact_origin: str
    allowed_path_patterns: tuple[str, ...]
    fixture_sha256: str
    schema_version: str
    schema_sha256: str
    adapter_id: str
    adapter_contract_version: int
    adapter_schema_sha256: str
    page_steps: tuple[str, ...]
    logical_fields: tuple[dict, ...]
    form_selectors: tuple[str, ...]
    form_actions: tuple[str, ...]
    save_controls: tuple[str, ...]
    next_controls: tuple[str, ...]
    previous_controls: tuple[str, ...]
    preview_controls: tuple[str, ...]
    submit_controls: tuple[str, ...]
    attachment_controls: tuple[str, ...]
    iframe_origins: tuple[str, ...]
    risk_markers: tuple[str, ...]
    allowed_capabilities: tuple[Literal["fill_only", "submit"], ...]
    mutation_enabled: bool
    live_enabled: bool
    manual_review_required: bool
    validation_codes: tuple[str, ...]

@dataclass(frozen=True)
class SiteIntakeResult:
    record: SiteIntakeRecord
    contract: SiteReadOnlyContract | None
    schema: dict | None

def _canonical_host(parsed) -> str:
    if not parsed.hostname or "*" in parsed.hostname:
        raise SiteIntakeError("URL_HOST_INVALID")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()
        if host.encode("ascii").decode("idna").encode("idna").decode("ascii").casefold() != host:
            raise UnicodeError
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    except (UnicodeError, UnicodeDecodeError) as exc:
        raise SiteIntakeError("URL_IDN_NORMALIZATION_FAILED") from exc
    else:
        raise SiteIntakeError("URL_IP_LITERAL_FORBIDDEN")
    labels=host.split(".")
    if len(host)>253 or any(not label or len(label)>63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?",label) for label in labels):
        raise SiteIntakeError("URL_HOST_INVALID")
    return host

def validate_url_metadata(value: str) -> UrlMetadata:
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise SiteIntakeError("URL_CONTROL_CHARACTER")
    try:
        parsed = urlsplit(value)
        port = parsed.port or 443
    except ValueError as exc:
        raise SiteIntakeError("URL_MALFORMED") from exc
    if parsed.scheme.casefold() != "https":
        raise SiteIntakeError("URL_HTTPS_REQUIRED")
    if parsed.username or parsed.password:
        raise SiteIntakeError("URL_USERINFO_FORBIDDEN")
    host = _canonical_host(parsed)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key.casefold() in SENSITIVE_QUERY_KEYS for key, _ in query) or parsed.fragment and any(word in parsed.fragment.casefold() for word in SENSITIVE_QUERY_KEYS):
        raise SiteIntakeError("URL_SENSITIVE_METADATA")
    normalized = urlunsplit(("https", host if port == 443 else f"{host}:{port}", parsed.path or "/", "", ""))
    codes: list[str] = []
    family = "unknown"
    try: exact: str | None = origin_from_url(value)
    except OriginPolicyError as exc: raise SiteIntakeError("URL_MALFORMED") from exc
    if host == "applyin.co.kr" or host.endswith(".applyin.co.kr"):
        family = "saramin_applyin"
    elif host == "jrs.jobkorea.co.kr":
        family = "jobkorea_jrs"; exact = None; codes.append("JRS_APPLICATION_ORIGIN_UNRESOLVED")
    elif host == "www.saramin.co.kr":
        family = "saramin_direct"; exact = None; codes.append("APPLICATION_DESTINATION_UNRESOLVED")
    else:
        codes.append("UNKNOWN_APPLICATION_FAMILY")
    return UrlMetadata(normalized, exact, host, family, bool(codes), tuple(codes))

def load_fixture_resource(root: Path, resource_name: str) -> FixtureResource:
    root = Path(root).resolve(strict=True)
    raw = Path(resource_name)
    win = PureWindowsPath(resource_name)
    if raw.is_absolute() or win.is_absolute() or win.drive or ".." in raw.parts or raw.suffix.casefold() not in {".html", ".htm"}:
        raise SiteIntakeError("FIXTURE_PATH_INVALID")
    try:
        resolved = confine_path(root, raw, require_file=True)
    except PathLinkError as exc:
        raise SiteIntakeError("FIXTURE_LINK_FORBIDDEN") from exc
    except PathConfinementError as exc:
        raise SiteIntakeError("FIXTURE_PATH_INVALID") from exc
    if resolved.stat().st_size > MAX_FIXTURE_BYTES:
        raise SiteIntakeError("FIXTURE_SIZE_INVALID")
    payload = resolved.read_bytes()
    if b"\x00" in payload: raise SiteIntakeError("FIXTURE_BINARY_FORBIDDEN")
    try: html = payload.decode("utf-8")
    except UnicodeDecodeError as exc: raise SiteIntakeError("FIXTURE_UTF8_REQUIRED") from exc
    digest = sha256(payload).hexdigest()
    return FixtureResource("fixture-" + sha256(resource_name.replace("\\", "/").encode()).hexdigest()[:20], digest, len(payload), html)

def _sensitive_codes(html: str) -> tuple[str, ...]:
    lower = html.casefold()
    patterns = {
        "SENSITIVE_FIXTURE_EMAIL": r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
        "SENSITIVE_FIXTURE_PHONE": r"(?:01[016789])[- ]?\d{3,4}[- ]?\d{4}",
        "SENSITIVE_FIXTURE_ID": r"\b\d{6}[- ]?[1-4]\d{6}\b",
        "SENSITIVE_FIXTURE_FINANCIAL_ID": r"\b(?:\d[ -]?){13,19}\b",
        "SENSITIVE_FIXTURE_ADDRESS": r"(?:\b\d{5}\b.{0,30}(?:road|street|ro|gil)|(?:시|도)\s+[^<\n]{1,30}(?:로|길)\s*\d+)",
        "SENSITIVE_FIXTURE_PATH": r"(?:[a-z]:\\(?:users|documents and settings)\\|onedrive|appdata\\(?:local|roaming)|chrome\\user data|firefox\\profiles|/home/[^/]+/|[a-z]:\\fakepath\\)",
        "SENSITIVE_FIXTURE_TOKEN": r"(?:test_sensitive_email_sentinel|test_session_token_sentinel|bearer\s+|eyj[a-z0-9_-]{10,}|access[_-]?token|refresh[_-]?token|authorization\s*:)",
        "SENSITIVE_FIXTURE_COOKIE": r"(?:cookie\s*:|set-cookie|document\.cookie)",
        "SENSITIVE_FIXTURE_ANALYTICS": r"(?:\bg-[a-z0-9]{6,}\b|\bua-\d{4,}-\d+\b|googletagmanager|datalayer|mixpanel|segment\.com)",
        "SENSITIVE_FIXTURE_PASSWORD_VALUE": r"<input[^>]+type=[\"']password[\"'][^>]+value=[\"'][^\"']+[\"']",
    }
    codes = [code for code, pattern in patterns.items() if re.search(pattern, lower, re.I)]
    if re.search(r"[?&](?:token|access_token|refresh_token|session|auth|authorization|key|api_key|code|cookie)=",lower): codes.append("SENSITIVE_FIXTURE_URL_METADATA")
    if re.search(r'<input[^>]+type=["\']hidden["\'][^>]+value=["\'][^"\']{9,}', html, re.I): codes.append("SENSITIVE_FIXTURE_HIDDEN_VALUE")
    return tuple(sorted(set(codes)))

class _SchemaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.forms=[]; self.fields=[]; self.buttons=[]; self.iframes=[]; self.scripts=[]; self.steps=[]; self.redirect_unknown=False; self.security_text=set(); self.base_count=0; self.formaction_count=0; self.form_depth=0; self.nested_form=False; self.malformed_form=False
    def handle_starttag(self, tag, attrs):
        a = {k.casefold(): (v or "") for k,v in attrs}; tag = tag.casefold()
        if tag == "base": self.base_count += 1
        if "formaction" in a: self.formaction_count += 1
        selector = "#" + a["id"] if a.get("id") else "[name=" + a["name"] + "]" if a.get("name") else None
        if tag == "form":
            if self.form_depth > 0: self.nested_form = True
            self.form_depth += 1
            self.forms.append({"selector":selector,"method":a.get("method","get").casefold(),"action":a.get("action","")})
        elif tag in {"input","textarea","select"}:
            typ = "textarea" if tag=="textarea" else "select" if tag=="select" else a.get("type","text").casefold()
            self.fields.append({"selector":selector,"logical_candidate":a.get("name") or a.get("id") or None,"type":typ,"has_name":bool(a.get("name")),"has_id":bool(a.get("id")),"required":"required" in a,"readonly":"readonly" in a,"disabled":"disabled" in a,"maxlength":int(a["maxlength"]) if a.get("maxlength","").isdigit() else None,"pattern_present":bool(a.get("pattern")),"autocomplete":a.get("autocomplete") or None,"options":[],"accept":a.get("accept") or None,"multiple":"multiple" in a,"hidden":typ=="hidden"})
        elif tag == "button": self.buttons.append({"selector":selector,"type":a.get("type","submit").casefold(),"role":a.get("data-role") or None})
        elif tag == "iframe": self.iframes.append(a.get("src", ""))
        elif tag == "script": self.scripts.append(a.get("src", "inline"))
        if "data-step" in a: self.steps.append(a["data-step"])
        if a.get("data-redirect","").casefold() == "unknown": self.redirect_unknown=True
    def handle_endtag(self, tag):
        if tag.casefold() == "form":
            if self.form_depth > 0: self.form_depth -= 1
            else: self.malformed_form = True
    def handle_startendtag(self, tag, attrs):
        if tag.casefold() == "form": self.malformed_form = True
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)
    def handle_data(self,data):
        text=data.casefold()
        for marker in ("captcha","otp","mfa","one-time password"):
            if marker in text: self.security_text.add("otp" if marker=="one-time password" else marker)

def _select_options(html: str, fields: list[dict]) -> None:
    for name, body in re.findall(r'<select[^>]+(?:name|id)=["\']([^"\']+)["\'][^>]*>(.*?)</select>', html, re.I|re.S):
        options = re.findall(r'<option[^>]+value=["\']([^"\']*)["\']', body, re.I)
        for field in fields:
            if field["logical_candidate"] == name: field["options"] = options

def _origin_or_none(url: str) -> str | None:
    try:
        meta = validate_url_metadata(url); return meta.exact_origin or (f"https://{meta.normalized_host}:443" if meta.platform_family=="jobkorea_jrs" else None)
    except SiteIntakeError: return None

def _safe_embedded_url(value: str, exact_origin: str) -> tuple[str | None,str | None]:
    if not value: return None,None
    absolute=urljoin(exact_origin+"/",value)
    meta=validate_url_metadata(absolute)
    parsed=urlsplit(meta.normalized_url)
    return meta.exact_origin,parsed.path or "/"

def parse_read_only_schema(html: str, exact_origin: str) -> dict:
    parser = _SchemaParser(); parser.feed(html); parser.malformed_form = parser.malformed_form or parser.form_depth != 0; _select_options(html, parser.fields)
    forms=[]
    for form in parser.forms:
        try: action_origin,action_path=_safe_embedded_url(form["action"],exact_origin)
        except SiteIntakeError: action_origin,action_path=None,None
        forms.append({"selector":form["selector"],"method":form["method"],"action_origin":action_origin,"action_path":action_path})
    script_origins=[]
    for source in parser.scripts:
        if source=="inline": script_origins.append("inline")
        else:
            try: origin,_=_safe_embedded_url(source,exact_origin); script_origins.append(origin or "invalid")
            except SiteIntakeError: script_origins.append("invalid")
    return {"forms":forms,"fields":parser.fields,"buttons":parser.buttons,"iframe_origins":sorted(filter(None,(_origin_or_none(urljoin(exact_origin+"/",x)) for x in parser.iframes))),"iframe_count":len(parser.iframes),"script_origins":sorted(script_origins),"script_count":len(parser.scripts),"security_markers":sorted(parser.security_text),"page_steps":sorted(parser.steps),"redirect_unknown":parser.redirect_unknown,"base_count":parser.base_count,"formaction_count":parser.formaction_count,"nested_form":parser.nested_form,"malformed_form":parser.malformed_form,"expected_origin":exact_origin}

def canonical_schema_sha256(schema: dict) -> str:
    return sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _risks(schema: dict, exact_origin: str) -> tuple[str, ...]:
    codes=[]; fields=schema["fields"]; buttons=schema["buttons"]
    types={f["type"] for f in fields}
    if "password" in types: codes.append("PASSWORD_FIELD_DETECTED")
    if "captcha" in schema["security_markers"]: codes.append("CAPTCHA_DETECTED")
    if any(x in schema["security_markers"] for x in ("otp","mfa")): codes.append("MFA_DETECTED")
    if any(f["hidden"] for f in fields): codes.append("UNKNOWN_HIDDEN_FIELD")
    if "file" in types: codes.append("ATTACHMENT_POLICY_UNKNOWN")
    if any(f["selector"] is None for f in fields) or len([f["selector"] for f in fields]) != len(set(f["selector"] for f in fields)): codes.append("MANUAL_FIELD_MAPPING_REQUIRED")
    if any(form["action_origin"] != exact_origin for form in schema["forms"]): codes.append("EXTERNAL_FORM_ACTION")
    if schema["base_count"]: codes.append("BASE_ELEMENT_REVIEW_REQUIRED")
    if schema["formaction_count"]: codes.append("FORMACTION_REVIEW_REQUIRED")
    if schema["nested_form"]: codes.append("NESTED_FORM_DETECTED")
    if len(schema["forms"]) != 1: codes.append("MULTIPLE_FORMS_DETECTED")
    if schema["malformed_form"]: codes.append("MALFORMED_FORM_STRUCTURE")
    if schema["iframe_count"]: codes.append("EXTERNAL_IFRAME")
    if schema["script_count"]: codes.append("SCRIPT_STRUCTURE_REVIEW_REQUIRED")
    if schema["redirect_unknown"]: codes.append("REDIRECT_STRUCTURE_UNKNOWN")
    if schema["page_steps"]: codes.append("POPUP_STRUCTURE_UNKNOWN")
    submits=[b for b in buttons if b["type"]=="submit"]
    saves=[b for b in buttons if b["role"]=="save"]
    if len(submits)!=1 or len(saves)!=1: codes.append("SAVE_SUBMIT_AMBIGUOUS")
    return tuple(sorted(set(codes)))

def build_site_intake(*,posting_url,resolved_application_url,fixture_root,fixture_resource_id,discovery_platform_id,created_at,requested_platform_family="auto",known_structure=None,valid_until=None) -> SiteIntakeResult:
    try: timestamp=datetime.fromisoformat(created_at.replace("Z","+00:00"))
    except (AttributeError,ValueError) as exc: raise SiteIntakeError("CREATED_AT_INVALID") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None: raise SiteIntakeError("CREATED_AT_INVALID")
    # The public CLI is intentionally unchanged in M3.  Direct callers can
    # supply an explicit expiry; legacy read-only intake keeps a bounded day.
    if valid_until is None:
        expiry = timestamp + timedelta(days=1)
        valid_until = expiry.isoformat(timespec="seconds")
    else:
        try: expiry=datetime.fromisoformat(valid_until.replace("Z","+00:00"))
        except (AttributeError,ValueError) as exc: raise SiteIntakeError("VALID_UNTIL_INVALID") from exc
        if expiry.tzinfo is None or expiry.utcoffset() is None or expiry<=timestamp: raise SiteIntakeError("VALID_UNTIL_INVALID")
    if discovery_platform_id is not None:
        try: discovery=get_platform(discovery_platform_id)
        except PlatformCatalogError as exc: raise SiteIntakeError("DISCOVERY_PLATFORM_INVALID") from exc
        if discovery.platform_role not in {"discovery","both"}: raise SiteIntakeError("DISCOVERY_PLATFORM_INVALID")
    posting_meta = validate_url_metadata(posting_url) if posting_url else None
    target = validate_url_metadata(resolved_application_url) if resolved_application_url else None
    codes=list(target.validation_codes if target else ("APPLICATION_DESTINATION_UNRESOLVED",))
    family=target.platform_family if target else "unknown"; exact=target.exact_origin if target else None
    if family=="saramin_direct": family="unknown"
    if requested_platform_family not in {"auto","jobkorea_jrs","saramin_applyin","saramin_direct","unknown"}:
        raise SiteIntakeError("PLATFORM_FAMILY_INVALID")
    if requested_platform_family != "auto" and requested_platform_family != family:
        codes.append("PLATFORM_FAMILY_MISMATCH")
    resource=None; schema=None; contract=None
    if fixture_resource_id:
        resource=load_fixture_resource(Path(fixture_root),fixture_resource_id)
        sensitive=_sensitive_codes(resource.html)
        if sensitive: codes.extend(("SENSITIVE_FIXTURE",*sensitive))
        elif exact:
            schema=parse_read_only_schema(resource.html,exact); codes.extend(_risks(schema,exact))
    if family=="unknown" and "UNKNOWN_APPLICATION_FAMILY" not in codes: codes.append("UNKNOWN_APPLICATION_FAMILY")
    known_structure=dict(known_structure or {})
    allowed_structure={"login_status":{"unknown","none","required"},"mfa_status":{"unknown","none","present"},"captcha_status":{"unknown","none","present"},"iframe_status":{"unknown","none","present"},"popup_status":{"unknown","none","present"},"redirect_status":{"unknown","none","present"},"attachment_status":{"unknown","unsupported","required"}}
    if any(key not in allowed_structure or value not in allowed_structure[key] for key,value in known_structure.items()): raise SiteIntakeError("KNOWN_STRUCTURE_INVALID")
    structure_risks = {
        "login_status": {
            "unknown": "LOGIN_STATUS_UNVERIFIED",
            "required": "LOGIN_REQUIRED",
        },
        "mfa_status": {
            "unknown": "MFA_STATUS_UNVERIFIED",
            "present": "MFA_DETECTED",
        },
        "captcha_status": {
            "unknown": "CAPTCHA_STATUS_UNVERIFIED",
            "present": "CAPTCHA_DETECTED",
        },
        "iframe_status": {
            "unknown": "IFRAME_STATUS_UNVERIFIED",
            "present": "EXTERNAL_IFRAME",
        },
        "popup_status": {
            "unknown": "POPUP_STRUCTURE_UNKNOWN",
            "present": "POPUP_STRUCTURE_UNKNOWN",
        },
        "redirect_status": {
            "unknown": "REDIRECT_STRUCTURE_UNKNOWN",
            "present": "REDIRECT_STRUCTURE_UNKNOWN",
        },
        "attachment_status": {
            "unknown": "ATTACHMENT_POLICY_UNKNOWN",
            "required": "ATTACHMENT_REQUIRED",
        },
    }
    for key, mappings in structure_risks.items():
        code = mappings.get(known_structure.get(key, "unknown"))
        if code:
            codes.append(code)
    codes=sorted(set(codes)); sensitive="SENSITIVE_FIXTURE" in codes
    ready=bool(resource and schema and exact and family!="unknown" and not codes)
    status="read_only_contract_ready" if ready else "blocked_sensitive_fixture" if sensitive else "blocked_invalid_origin" if not exact else "manual_review_required"
    fixture_sha=resource.sha256 if resource else None; schema_sha=canonical_schema_sha256(schema) if schema else None
    identity_payload = {
        "platform_family": family,
        "exact_origin": exact,
        "fixture_sha256": fixture_sha,
        "schema_sha256": schema_sha,
        "validation_codes": codes,
        "known_structure": {key: known_structure.get(key, "unknown") for key in sorted(allowed_structure)},
        "contract_version": 2,
        "observed_at": created_at,
        "valid_until": valid_until,
    }
    identity = json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity_sha = sha256(identity.encode()).hexdigest()
    intake_id="intake-"+identity_sha[:24]
    record=SiteIntakeRecord(intake_id,family,discovery_platform_id,posting_meta.normalized_url if posting_meta else None,target.normalized_url if target else None,exact,target.normalized_host if target else None,resource.resource_id if resource else None,fixture_sha,schema_sha,known_structure.get("login_status","unknown"),known_structure.get("mfa_status","unknown"),known_structure.get("captcha_status","unknown"),known_structure.get("iframe_status","unknown"),known_structure.get("popup_status","unknown"),known_structure.get("redirect_status","unknown"),known_structure.get("attachment_status","unknown"),"multistep" if schema and schema["page_steps"] else "single_page" if schema else "unknown","identified" if schema and any(b["role"]=="save" for b in schema["buttons"]) else "unknown","identified" if schema and len([b for b in schema["buttons"] if b["type"]=="submit"])==1 else "unknown",not ready,tuple(codes),status,created_at,2)
    if ready:
        site_id="site-"+sha256((family+"|"+exact).encode()).hexdigest()[:20]
        adapter_id = {"jobkorea_jrs":"jobkorea_jrs_fixture", "saramin_applyin":"saramin_applyin_fixture"}.get(family, "unknown")
        schema_version = f"{adapter_id}_v1"
        contract=SiteReadOnlyContract(site_id,family,"contract-"+identity_sha[:24],2,created_at,valid_until,exact,(urlsplit(target.normalized_url).path or "/",),fixture_sha,schema_version,schema_sha,adapter_id,1,schema_sha,tuple(schema["page_steps"]),tuple(schema["fields"]),tuple(f["selector"] for f in schema["forms"] if f["selector"]),tuple(f["action_path"] for f in schema["forms"] if f["action_path"]),tuple(b["selector"] for b in schema["buttons"] if b["role"]=="save" and b["selector"]),tuple(b["selector"] for b in schema["buttons"] if b["role"]=="next" and b["selector"]),tuple(b["selector"] for b in schema["buttons"] if b["role"]=="previous" and b["selector"]),tuple(b["selector"] for b in schema["buttons"] if b["role"]=="preview" and b["selector"]),tuple(b["selector"] for b in schema["buttons"] if b["type"]=="submit" and b["selector"]),tuple(f["selector"] for f in schema["fields"] if f["type"]=="file" and f["selector"]),tuple(schema["iframe_origins"]),(),(),False,False,False,())
    return SiteIntakeResult(record,contract,schema)

@contextmanager
def _lock(path: Path):
    try:
        with exclusive_lock(path):
            yield
    except LockAcquisitionError as error:
        raise SiteIntakeError("registry lock timeout") from error

def persist_intake(path: Path, result: SiteIntakeResult, expected_version: int | None = None) -> dict:
    path=Path(path)
    with _lock(path.with_suffix(path.suffix+".lock")):
        try: path = confine_path(path.parent, path, must_exist=False)
        except PathConfinementError as error: raise SiteIntakeError("registry symlink forbidden") from error
        registry=load_intake_registry(path) if path.exists() else {"schema_version":1,"version":0,"records":{},"contracts":{},"events":[]}
        version=registry.get("version")
        if expected_version is not None and expected_version!=version: raise SiteIntakeError("stale intake writer")
        if result.record.intake_id in registry["records"]: return registry
        registry["records"][result.record.intake_id]=asdict(result.record)
        if result.contract: registry["contracts"][result.contract.contract_id]=asdict(result.contract)
        registry["version"]=version+1
        registry["events"].append({"event_type":"site_intake_recorded","intake_id":result.record.intake_id,"contract_status":result.record.contract_status,"occurred_at":result.record.created_at})
        write_json(path,registry); return registry

def load_intake_registry(path: Path) -> dict:
    path=Path(path)
    if not path.is_file() or path.is_symlink(): raise SiteIntakeError("intake registry missing or unsafe")
    try: registry=json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError,UnicodeDecodeError) as exc: raise SiteIntakeError("corrupt intake registry") from exc
    if registry.get("schema_version")!=1 or not isinstance(registry.get("version"),int) or not isinstance(registry.get("records"),dict) or not isinstance(registry.get("contracts"),dict) or not isinstance(registry.get("events"),list): raise SiteIntakeError("corrupt intake registry")
    return registry
