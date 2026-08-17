"""Source hierarchy and dynamic official-domain registry for company research."""
from __future__ import annotations

from urllib.parse import urlsplit
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1

# Compatibility seeds only. New organizations should be supplied/discovered at run time.
KNOWN_OFFICIAL_DOMAIN_SEEDS = {
    "HUG": "khug.or.kr",
    "주택도시보증공사": "khug.or.kr",
    "HF": "hf.go.kr",
    "한국주택금융공사": "hf.go.kr",
    "NPS": "nps.or.kr",
    "국민연금공단": "nps.or.kr",
}

SOURCE_TYPE_TIERS = {
    "posting": 0,
    "job_description": 0,
    "law_or_regulation": 0,
    "official_disclosure": 0,
    "annual_report": 1,
    "business_report": 1,
    "ir": 1,
    "official_service_page": 1,
    "official_program_page": 1,
    "press_release": 2,
    "newsroom": 2,
    "official_blog": 2,
    "executive_interview": 2,
    "government": 3,
    "regulator": 3,
    "related_public_body": 3,
    "reputable_news": 4,
    "community": 5,
    "personal_blog": 5,
    "video": 5,
    "unknown": 5,
}

FACT_AUTHORITY_MAX_TIER = 3
SUBMISSION_AUTHORITY_MAX_TIER = 2


def normalize_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not value:
        return ""
    if "://" in value:
        value = (urlsplit(value).hostname or "").lower().rstrip(".")
    return value


def host_matches_domain(host: str, domain: str) -> bool:
    host = normalize_domain(host)
    domain = normalize_domain(domain)
    return bool(host and domain and (host == domain or host.endswith("." + domain)))


def tier_for_source_type(source_type: str) -> int:
    return SOURCE_TYPE_TIERS.get(source_type.strip().lower(), SOURCE_TYPE_TIERS["unknown"])


def build_source_registry(
    target: str,
    *,
    explicit_domains: Iterable[str] = (),
    discovered_sources: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    domains = {normalize_domain(item) for item in explicit_domains if normalize_domain(item)}
    for marker, domain in KNOWN_OFFICIAL_DOMAIN_SEEDS.items():
        if marker.lower() in target.lower():
            domains.add(domain)

    sources: list[dict[str, Any]] = []
    for raw in discovered_sources:
        url = str(raw.get("url", "")).strip()
        source_type = str(raw.get("source_type", "unknown")).strip().lower() or "unknown"
        host = normalize_domain(url)
        official = bool(raw.get("official", False))
        if official and host:
            domains.add(host)
        tier = int(raw.get("source_tier", tier_for_source_type(source_type)))
        sources.append(
            {
                "url": url,
                "host": host,
                "publisher": str(raw.get("publisher", "")).strip(),
                "source_type": source_type,
                "source_tier": tier,
                "official": official,
                "factual_authority": tier <= FACT_AUTHORITY_MAX_TIER,
                "submission_authority": official and tier <= SUBMISSION_AUTHORITY_MAX_TIER,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "official_domains": sorted(domains),
        "source_hierarchy": [
            {"tier": 0, "meaning": "채용공고·직무기술서·법령·공식 공시", "submission_authority": True},
            {"tier": 1, "meaning": "연차/사업보고서·IR·공식 사업 페이지", "submission_authority": True},
            {"tier": 2, "meaning": "보도자료·뉴스룸·공식 블로그·공식 인터뷰", "submission_authority": True},
            {"tier": 3, "meaning": "정부·감독기관·유관 공공기관", "submission_authority": False},
            {"tier": 4, "meaning": "신뢰도 높은 언론 - 탐색/맥락용", "submission_authority": False},
            {"tier": 5, "meaning": "커뮤니티·개인 블로그·영상 - 탐색 전용", "submission_authority": False},
        ],
        "sources": sources,
    }


def official_domains_from_registry(registry: Mapping[str, Any]) -> tuple[str, ...]:
    values = registry.get("official_domains", []) if isinstance(registry, Mapping) else []
    return tuple(sorted({normalize_domain(str(item)) for item in values if normalize_domain(str(item))}))


def classify_source(
    url: str,
    *,
    source_type: str,
    registry: Mapping[str, Any],
    publisher: str = "",
) -> dict[str, Any]:
    host = normalize_domain(url)
    official_domains = official_domains_from_registry(registry)
    official = any(host_matches_domain(host, domain) for domain in official_domains)
    tier = tier_for_source_type(source_type)
    return {
        "url": url,
        "host": host,
        "publisher": publisher,
        "source_type": source_type,
        "source_tier": tier,
        "official": official,
        "factual_authority": tier <= FACT_AUTHORITY_MAX_TIER,
        "submission_authority": official and tier <= SUBMISSION_AUTHORITY_MAX_TIER,
    }
