"""Validated catalog separating discovery platforms from application families."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit
from .application_execution import normalize_origin, ApplicationExecutionError

class PlatformCatalogError(ValueError): pass
@dataclass(frozen=True)
class Platform:
    platform_id:str; display_name:str; platform_role:Literal["discovery","application_family","both"]
    public_origins:tuple[str,...]; recognized_host_suffixes:tuple[str,...]; requires_exact_execution_origin:bool
    fixture_adapter_id:str|None; live_adapter_id:str|None; live_enabled:bool; attachment_supported:bool
    login_policy:str; notes:str; contract_version:int
    actual_execution_origin:str|None=None
    requires_manual_intake:bool=True
@dataclass(frozen=True)
class ApplicationLinkDetection:
    discovery_platform_id:str; original_posting_url:str|None; resolved_application_url:str
    detected_application_family:str|None; exact_resolved_origin:str|None; detection_confidence:str
    manual_review_required:bool; detected_at:str

CATALOG=(
 Platform("jobkorea_jrs","JobKorea JRS","application_family",("https://jrs.jobkorea.co.kr",),(),True,"jobkorea_jrs_fixture",None,False,False,"unsupported","exact company origin requires review",1),
 Platform("saramin_applyin","Saramin Applyin","application_family",("https://www.applyin.co.kr",),("applyin.co.kr",),True,"saramin_applyin_fixture",None,False,False,"unsupported","host suffix is classification-only",1),
 Platform("saramin_direct","Saramin Direct","discovery",("https://www.saramin.co.kr",),(),False,None,None,False,False,"unsupported","discovery only until contract",1),
 Platform("work24","Work24","discovery",("https://www.work24.go.kr",),(),False,None,None,False,False,"unsupported","government service; discovery only",1),
 Platform("wanted","Wanted","discovery",("https://www.wanted.co.kr",),(),False,None,None,False,False,"unsupported","discovery only",1),
 Platform("catch","Catch","discovery",("https://www.catch.co.kr",),(),False,None,None,False,False,"none","discovery only",1),
 Platform("jasoseol","Jasoseol","discovery",("https://jasoseol.com",),(),False,None,None,False,False,"none","discovery only",1),)

FIXTURE_ADAPTER_REGISTRY = {
    "jobkorea_jrs": "jobkorea_jrs_fixture",
    "saramin_applyin": "saramin_applyin_fixture",
}

def validate_catalog(items):
    ids=set(); origins={}; suffixes={}
    for p in items:
        if not p.platform_id or p.platform_id in ids: raise PlatformCatalogError("invalid or duplicate platform_id")
        ids.add(p.platform_id)
        if p.platform_role not in {"discovery","application_family","both"}: raise PlatformCatalogError("invalid platform role")
        if p.live_enabled: raise PlatformCatalogError("live platform is not allowed")
        if p.platform_role=="discovery" and (p.fixture_adapter_id or p.live_adapter_id): raise PlatformCatalogError("discovery platform cannot have execution adapter")
        if p.platform_role in {"application_family","both"} and not p.requires_exact_execution_origin: raise PlatformCatalogError("application family requires exact origin")
        if p.fixture_adapter_id != FIXTURE_ADAPTER_REGISTRY.get(p.platform_id): raise PlatformCatalogError("fixture adapter registry mismatch")
        if p.live_adapter_id is not None: raise PlatformCatalogError("live adapter is not registered")
        for raw in p.public_origins:
            if "*" in raw: raise PlatformCatalogError("wildcard public origin is forbidden")
            try: origin=normalize_origin(raw)
            except ApplicationExecutionError as e: raise PlatformCatalogError("invalid public origin") from e
            if origin in origins: raise PlatformCatalogError("duplicate public origin")
            origins[origin]=p.platform_id
        for suffix in p.recognized_host_suffixes:
            suffix=suffix.casefold().strip(".")
            if not suffix or "*" in suffix or suffix in suffixes: raise PlatformCatalogError("invalid or duplicate suffix")
            if any(suffix.endswith("."+other) or other.endswith("."+suffix) for other in suffixes): raise PlatformCatalogError("overlapping host suffix")
            suffixes[suffix]=p.platform_id
    for origin, owner in origins.items():
        host=urlsplit(origin).hostname
        if any(owner != suffix_owner and (host==suffix or host.endswith("."+suffix)) for suffix,suffix_owner in suffixes.items()):
            raise PlatformCatalogError("public origin conflicts with another platform suffix")
    return tuple(items)
validate_catalog(CATALOG)
def get_platform(platform_id):
    for p in CATALOG:
        if p.platform_id==platform_id: return p
    raise PlatformCatalogError("unregistered platform_id")
def list_platforms(role=None):
    if role is not None and role not in {"discovery","application_family","both"}: raise PlatformCatalogError("invalid platform role")
    return tuple(p for p in CATALOG if role is None or p.platform_role==role)
def classify_application_url(url,*,discovery_platform_id,detected_at,original_posting_url=None):
    get_platform(discovery_platform_id)
    try:
        parsed=urlsplit(url)
        if parsed.scheme.casefold()!="https" or not parsed.hostname or parsed.username or parsed.password: raise ValueError
        host=parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()
        exact=f"https://{host}:{parsed.port or 443}"
    except (ValueError,UnicodeError):
        return ApplicationLinkDetection(discovery_platform_id,original_posting_url,url,None,None,"none",True,detected_at)
    matches=[]
    for p in CATALOG:
        if p.platform_role not in {"application_family","both"}: continue
        for suffix in p.recognized_host_suffixes:
            if host==suffix or host.endswith("."+suffix): matches.append(p.platform_id)
        if any(normalize_origin(o)==exact for o in p.public_origins): matches.append(p.platform_id)
    matches=sorted(set(matches))
    return ApplicationLinkDetection(discovery_platform_id,original_posting_url,url,matches[0] if len(matches)==1 else None,exact if len(matches)==1 else None,"high" if len(matches)==1 else "none",len(matches)!=1,detected_at)
