from dataclasses import replace
import pytest
from career_pipeline.platform_catalog import (CATALOG, PlatformCatalogError, classify_application_url,
    get_platform, validate_catalog)

def test_catalog_has_required_platforms_and_roles():
    validate_catalog(CATALOG)
    assert {p.platform_id for p in CATALOG}=={"jobkorea_jrs","saramin_applyin","saramin_direct","work24","wanted","catch","jasoseol"}
    assert get_platform("saramin_applyin").fixture_adapter_id=="saramin_applyin_fixture"
    assert get_platform("catch").platform_role=="discovery"

def test_applyin_suffix_detection_preserves_exact_origin():
    result=classify_application_url("https://company.applyin.co.kr/apply?id=1",discovery_platform_id="saramin_direct",detected_at="2026-07-12T12:00:00+09:00")
    assert result.detected_application_family=="saramin_applyin"
    assert result.exact_resolved_origin=="https://company.applyin.co.kr:443"
    assert result.manual_review_required is False

def test_unregistered_discovery_platform_is_blocked():
    with pytest.raises(PlatformCatalogError, match="unregistered"):
        classify_application_url("https://company.applyin.co.kr/apply", discovery_platform_id="unknown", detected_at="2026-07-12T12:00:00+09:00")

@pytest.mark.parametrize("url",["http://company.applyin.co.kr","https://applyin.co.kr.evil.com","https://user@company.applyin.co.kr","not-a-url"])
def test_unsafe_or_unknown_application_url_requires_manual_review(url):
    result=classify_application_url(url,discovery_platform_id="saramin_direct",detected_at="2026-07-12T12:00:00+09:00")
    assert result.detected_application_family is None and result.manual_review_required

@pytest.mark.parametrize("change",["duplicate","blank","role","http","query","wildcard","execution_on_discovery","adapter_mismatch","live_adapter","live","exact","suffix_overlap","origin_suffix_conflict"])
def test_invalid_catalog_is_rejected(change):
    items=list(CATALOG)
    if change=="duplicate": items.append(items[0])
    elif change=="blank": items[0]=replace(items[0],platform_id="")
    elif change=="role": items[0]=replace(items[0],platform_role="bad")
    elif change=="http": items[0]=replace(items[0],public_origins=("http://bad.example",))
    elif change=="query": items[0]=replace(items[0],public_origins=("https://bad.example?q=1",))
    elif change=="wildcard": items[0]=replace(items[0],public_origins=("https://*.example",))
    elif change=="execution_on_discovery": items[5]=replace(items[5],fixture_adapter_id="bad")
    elif change=="adapter_mismatch": items[0]=replace(items[0],fixture_adapter_id="bad")
    elif change=="live_adapter": items[0]=replace(items[0],live_adapter_id="live")
    elif change=="live": items[0]=replace(items[0],live_enabled=True)
    elif change=="exact": items[0]=replace(items[0],requires_exact_execution_origin=False)
    elif change=="suffix_overlap": items[0]=replace(items[0],recognized_host_suffixes=("company.applyin.co.kr",))
    else: items[0]=replace(items[0],public_origins=("https://company.applyin.co.kr",))
    with pytest.raises(PlatformCatalogError): validate_catalog(tuple(items))
