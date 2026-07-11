"""Allowlisted official job-posting discovery.

This module discovers candidate URLs only. It never logs in, follows an
unbounded crawl, or treats page text as instructions. Actual posting download
is delegated to :mod:`posting_loader`, which revalidates every redirect hop.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from hashlib import sha256
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import socket
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from .eligibility import (
    canonicalize_url,
    evaluate_eligibility,
    normalized_posting_content_sha256,
    posting_record_from_analysis,
)
from .models import DiscoveryCandidate, DiscoveryRun, DiscoverySource, DecisionReason
from .posting_loader import (
    LoadedPosting,
    PostingSourceError,
    Resolver,
    Transport,
    _default_transport,
    load_posting_source,
    host_matches_official_domain,
    validate_public_https_url,
)
from .state import write_json


DISCOVERY_SOURCE_TYPES = {
    "manual_url",
    "official_list_page",
    "official_rss",
    "official_sitemap",
    "official_json_api",
}
MAX_CANDIDATES = 100
MAX_PAGINATION_PAGES = 3
MAX_SITEMAP_URLS = 500
MAX_SITEMAP_DEPTH = 1


class DiscoveryValidationError(ValueError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_discovery_source(source: DiscoverySource) -> DiscoverySource:
    issues: list[str] = []
    if source.schema_version != 1:
        issues.append("schema_version: expected 1")
    for field_name in ("source_id", "organization", "entry_url", "created_at", "updated_at"):
        if not getattr(source, field_name):
            issues.append(f"{field_name}: must not be empty")
    if source.source_type not in DISCOVERY_SOURCE_TYPES:
        issues.append("source_type: unsupported discovery source type")
    parsed = urlsplit(source.entry_url)
    if parsed.scheme != "https":
        issues.append("entry_url: HTTPS is required")
    if parsed.username is not None or parsed.password is not None:
        issues.append("entry_url: credentials are not allowed")
    if not parsed.hostname:
        issues.append("entry_url: host is required")
    if not source.allowed_domains:
        issues.append("allowed_domains: at least one domain is required")
    for domain in source.allowed_domains:
        normalized = domain.strip().lower().rstrip(".")
        if not normalized or "/" in normalized or "://" in normalized:
            issues.append(f"allowed_domains: invalid domain {domain}")
        elif parsed.hostname and not host_matches_official_domain(parsed.hostname, normalized):
            issues.append(f"allowed_domains: entry URL is outside allowlist: {domain}")
    pagination = source.config.get("pagination", {})
    if pagination.get("enabled"):
        if pagination.get("strategy") != "query_page":
            issues.append("pagination.strategy: only query_page is supported")
        max_pages = pagination.get("max_pages", 0)
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= MAX_PAGINATION_PAGES:
            issues.append(f"pagination.max_pages: expected integer from 1 to {MAX_PAGINATION_PAGES}")
    max_candidates = source.config.get("max_candidates", MAX_CANDIDATES)
    if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or not 1 <= max_candidates <= MAX_CANDIDATES:
        issues.append(f"max_candidates: expected integer from 1 to {MAX_CANDIDATES}")
    if source.source_type == "official_sitemap" and not source.config.get("include_pattern"):
        issues.append("official_sitemap requires config.include_pattern")
    if source.source_type == "official_json_api":
        if not source.config.get("items_path") or not source.config.get("url_field"):
            issues.append("official_json_api requires config.items_path and config.url_field")
    for key in ("detail_pattern", "include_pattern", "posting_id_pattern"):
        pattern = source.config.get(key)
        if pattern:
            try:
                re.compile(str(pattern))
            except re.error:
                issues.append(f"config.{key}: invalid regular expression")
    if issues:
        raise DiscoveryValidationError("\n".join(issues))
    return source


def discovery_source_to_dict(source: DiscoverySource) -> dict[str, Any]:
    return asdict(validate_discovery_source(source))


def discovery_source_from_dict(value: Any) -> DiscoverySource:
    if not isinstance(value, dict):
        raise DiscoveryValidationError("source: expected object")
    source = DiscoverySource(
        schema_version=value.get("schema_version", 1),
        source_id=value.get("source_id", ""),
        organization=value.get("organization", ""),
        source_type=value.get("source_type", value.get("type", "")),
        entry_url=value.get("entry_url", value.get("url", "")),
        allowed_domains=tuple(value.get("allowed_domains", value.get("allow_domains", []))),
        role_keywords=tuple(value.get("role_keywords", [])),
        location_keywords=tuple(value.get("location_keywords", [])),
        enabled=value.get("enabled", True),
        created_at=value.get("created_at", ""),
        updated_at=value.get("updated_at", ""),
        config=dict(value.get("config", {})),
    )
    if not isinstance(source.enabled, bool):
        raise DiscoveryValidationError("enabled: expected boolean")
    return validate_discovery_source(source)


def load_discovery_sources(path: Path) -> dict[str, DiscoverySource]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DiscoveryValidationError(f"invalid discovery source JSON: line {error.lineno}") from error
    if not isinstance(payload, dict) or payload.get("schema_version", 1) != 1:
        raise DiscoveryValidationError("discovery sources: unsupported schema version")
    raw_sources = payload.get("sources", [])
    if not isinstance(raw_sources, list):
        raise DiscoveryValidationError("sources: expected array")
    sources = [discovery_source_from_dict(item) for item in raw_sources]
    ids = [item.source_id for item in sources]
    if len(ids) != len(set(ids)):
        raise DiscoveryValidationError("sources: duplicate source_id")
    return {item.source_id: item for item in sources}


def save_discovery_sources(path: Path, sources: dict[str, DiscoverySource]) -> None:
    payload = {
        "schema_version": 1,
        "sources": [discovery_source_to_dict(sources[key]) for key in sorted(sources)],
    }
    write_json(path, payload)


def add_discovery_source(path: Path, source: DiscoverySource, *, force: bool = False) -> None:
    sources = load_discovery_sources(path)
    if source.source_id in sources and not force:
        raise DiscoveryValidationError(f"source already exists: {source.source_id}")
    sources[source.source_id] = validate_discovery_source(source)
    save_discovery_sources(path, sources)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._ignored += 1
        if tag == "a" and not self._ignored:
            attributes = dict(attrs)
            self._href = attributes.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None and not self._ignored:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None
            self._text = []
        if tag in {"script", "style", "noscript"}:
            self._ignored = max(0, self._ignored - 1)


def _allowed_candidate_url(source: DiscoverySource, url: str, *, resolver: Resolver) -> str | None:
    try:
        parsed = validate_public_https_url(url, resolver=resolver)
    except PostingSourceError:
        return None
    host = parsed.hostname or ""
    if not any(host_matches_official_domain(host, domain) for domain in source.allowed_domains):
        return None
    canonical = canonicalize_url(url)
    lowered = canonical.casefold()
    if any(marker in lowered for marker in ("login", "signin", "privacy", "mypage", "apply", "application")):
        return None
    pattern = source.config.get("detail_pattern")
    if pattern and not re.search(pattern, canonical):
        return None
    return canonical


def _keyword_match(source: DiscoverySource, url: str, title: str) -> bool:
    text = f"{url} {title}".casefold()
    if source.role_keywords and not any(keyword.casefold() in text for keyword in source.role_keywords):
        return False
    if source.location_keywords and not any(keyword.casefold() in text for keyword in source.location_keywords):
        return False
    return True


def _posting_id_for_candidate(source: DiscoverySource, candidate: DiscoveryCandidate) -> str | None:
    if candidate.external_id:
        return f"{source.source_id}:{candidate.external_id}"
    pattern = source.config.get("posting_id_pattern")
    if not pattern:
        return None
    match = re.search(str(pattern), candidate.url)
    if not match:
        return None
    return match.groupdict().get("id") or (match.group(1) if match.groups() else match.group(0))


def _candidate(
    source: DiscoverySource,
    url: str,
    discovered_at: str,
    title_hint: str | None,
    resolver: Resolver,
    external_id: str | None = None,
) -> DiscoveryCandidate | None:
    canonical = _allowed_candidate_url(source, url, resolver=resolver)
    if canonical is None or not _keyword_match(source, canonical, title_hint or ""):
        return None
    return DiscoveryCandidate(source.source_id, canonical, canonical, discovered_at, title_hint, external_id)


def _load_page(source: DiscoverySource, url: str, *, resolver: Resolver, transport: Transport) -> LoadedPosting:
    return load_posting_source(
        url,
        official_domains=tuple(source.allowed_domains),
        resolver=resolver,
        transport=transport,
    )


def _list_page_candidates(source: DiscoverySource, loaded: LoadedPosting, *, resolver: Resolver, discovered_at: str) -> list[DiscoveryCandidate]:
    content_type = loaded.metadata.content_type
    if not content_type.startswith("text/html"):
        raise DiscoveryValidationError("official_list_page must return HTML")
    parser = _LinkParser()
    parser.feed(loaded.content.decode("utf-8", errors="replace"))
    candidates: list[DiscoveryCandidate] = []
    for href, title in parser.links:
        candidate = _candidate(source, urljoin(loaded.metadata.location, href), discovered_at, title or None, resolver)
        if candidate and candidate.canonical_url not in {item.canonical_url for item in candidates}:
            candidates.append(candidate)
        if len(candidates) >= int(source.config.get("max_candidates", MAX_CANDIDATES)):
            break
    return candidates


def _xml_links(content: bytes) -> list[str]:
    text = content.decode("utf-8", errors="replace")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise DiscoveryValidationError("XML DTD and ENTITY declarations are not allowed")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise DiscoveryValidationError("invalid discovery XML") from error
    return [item.text.strip() for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "loc" and item.text and item.text.strip()]


def _rss_links(content: bytes) -> list[str]:
    text = content.decode("utf-8", errors="replace")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        raise DiscoveryValidationError("XML DTD and ENTITY declarations are not allowed")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise DiscoveryValidationError("invalid discovery XML") from error
    links: list[str] = []
    for item in root.iter():
        tag = item.tag.rsplit("}", 1)[-1]
        if tag != "link":
            continue
        href = item.attrib.get("href") or (item.text.strip() if item.text else "")
        if href:
            links.append(href)
    return links


def _sitemap_links(
    source: DiscoverySource,
    loaded: LoadedPosting,
    *,
    resolver: Resolver,
    transport: Transport,
    depth: int = 0,
) -> list[str]:
    links = _xml_links(loaded.content)
    if not links:
        return []
    # Sitemap indexes are limited to one nested level and the same allowlist.
    text = loaded.content.decode("utf-8", errors="replace")
    if re.search(r"<(?:[A-Za-z0-9_]+:)?sitemapindex\b", text, re.IGNORECASE):
        if depth >= MAX_SITEMAP_DEPTH:
            return []
        nested: list[str] = []
        for url in links[:MAX_SITEMAP_URLS]:
            candidate_url = _allowed_candidate_url(source, url, resolver=resolver)
            if candidate_url:
                nested_loaded = _load_page(source, candidate_url, resolver=resolver, transport=transport)
                nested.extend(
                    _sitemap_links(
                        source,
                        nested_loaded,
                        resolver=resolver,
                        transport=transport,
                        depth=depth + 1,
                    )
                )
        return nested
    include_pattern = source.config.get("include_pattern")
    if include_pattern:
        links = [url for url in links if re.search(str(include_pattern), url)]
    return links[:MAX_SITEMAP_URLS]


def _json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split(".") if path else []:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def discover_candidates(
    source: DiscoverySource,
    *,
    discovered_at: str | None = None,
    evaluation_time: str | None = None,
    resolver: Resolver = socket.getaddrinfo,
    transport: Transport = _default_transport,
) -> tuple[DiscoveryCandidate, ...]:
    source = validate_discovery_source(source)
    if not source.enabled:
        return ()
    discovered_at = discovered_at or evaluation_time or _now()
    if source.source_type == "manual_url":
        candidate = _candidate(source, source.entry_url, discovered_at, None, resolver)
        return (candidate,) if candidate else ()
    loaded = _load_page(source, source.entry_url, resolver=resolver, transport=transport)
    if source.source_type == "official_list_page":
        candidates = _list_page_candidates(source, loaded, resolver=resolver, discovered_at=discovered_at)
        pagination = source.config.get("pagination", {})
        if pagination.get("enabled"):
            max_pages = pagination["max_pages"]
            for page in range(2, max_pages + 1):
                parsed = urlsplit(source.entry_url)
                query = dict(parse_qsl(parsed.query, keep_blank_values=True))
                query["page"] = str(page)
                page_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
                page_loaded = _load_page(source, page_url, resolver=resolver, transport=transport)
                candidates.extend(_list_page_candidates(source, page_loaded, resolver=resolver, discovered_at=discovered_at))
            unique = {item.canonical_url: item for item in candidates}
            return tuple(list(unique.values())[:MAX_CANDIDATES])
        return tuple(candidates)
    if source.source_type == "official_rss":
        links = _rss_links(loaded.content)
    elif source.source_type == "official_sitemap":
        links = _sitemap_links(source, loaded, resolver=resolver, transport=transport)
    elif source.source_type == "official_json_api":
        try:
            payload = json.loads(loaded.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DiscoveryValidationError("invalid official JSON API response") from error
        items = _json_path(payload, str(source.config.get("items_path", "items")))
        if not isinstance(items, list):
            raise DiscoveryValidationError("official_json_api items_path must resolve to an array")
        field = str(source.config.get("url_field", "url"))
        links = [item.get(field) for item in items if isinstance(item, dict) and isinstance(item.get(field), str)]
    else:
        raise DiscoveryValidationError(f"unsupported discovery source type: {source.source_type}")
    candidates: list[DiscoveryCandidate] = []
    id_field = source.config.get("id_field")
    for url in links:
        external_id = None
        if source.source_type == "official_json_api" and id_field:
            for item in items:
                if isinstance(item, dict) and item.get(field) == url:
                    if item.get(id_field) is not None:
                        external_id = str(item[id_field])
                    break
        candidate = _candidate(source, urljoin(source.entry_url, url), discovered_at, None, resolver, external_id)
        if candidate and candidate.canonical_url not in {item.canonical_url for item in candidates}:
            candidates.append(candidate)
        if len(candidates) >= int(source.config.get("max_candidates", MAX_CANDIDATES)):
            break
    return tuple(candidates)


def run_discovery(
    source: DiscoverySource,
    *,
    registry,
    evaluation_time: str,
    applicant_profile=None,
    run_id: str | None = None,
    resolver: Resolver = socket.getaddrinfo,
    transport: Transport = _default_transport,
) -> DiscoveryRun:
    """Discover, snapshot, register, evaluate, and queue without browser automation."""

    from .posting_parser import parse_posting
    from .registry import RegistryError, posting_lifecycle_status

    source = validate_discovery_source(source)
    try:
        datetime.fromisoformat(evaluation_time.replace("Z", "+00:00"))
    except ValueError as error:
        raise DiscoveryValidationError("evaluation_time must be ISO-8601") from error
    run_id = run_id or "discovery-" + sha256(f"{source.source_id}|{evaluation_time}".encode("utf-8")).hexdigest()[:24]
    started_at = evaluation_time
    registry.record_event(
        "discovery_started",
        occurred_at=started_at,
        source_id=source.source_id,
        posting_id=None,
        run_id=run_id,
    )
    errors: list[dict[str, Any]] = []
    discovered_count = fetched_count = new_count = changed_count = duplicate_count = expired_count = failed_count = 0
    try:
        candidates = discover_candidates(
            source, discovered_at=evaluation_time, resolver=resolver, transport=transport
        )
    except Exception as error:
        error_item = {"code": type(error).__name__, "message": str(error)[:240]}
        run = DiscoveryRun(1, run_id, source.source_id, started_at, evaluation_time, evaluation_time, "failed", 0, 0, 0, 0, 0, 0, 1, (error_item,))
        registry.record_event(
            "discovery_failed",
            occurred_at=evaluation_time,
            source_id=source.source_id,
            posting_id=None,
            run_id=run_id,
            metadata={"failed_count": 1},
        )
        save_discovery_run(registry.path.parent / "discovery_runs" / f"{run_id}.json", run)
        return run
    discovered_count = len(candidates)
    registry_failed = False
    for candidate in candidates:
        try:
            loaded = _load_page(source, candidate.url, resolver=resolver, transport=transport)
            fetched_count += 1
            analysis = parse_posting(loaded, target=candidate.title_hint or source.organization)
            record = posting_record_from_analysis(
                analysis,
                posting_id=_posting_id_for_candidate(source, candidate),
                normalized_content_sha256=normalized_posting_content_sha256(loaded.content),
            )
            record = replace(
                record,
                source_id=source.source_id,
                canonical_url=candidate.canonical_url,
                source_excerpt=(analysis.role or analysis.organization or None),
                unparsed_requirements=tuple(analysis.requirements),
            )
            registry.write_snapshot(record.posting_id, loaded.content, record.body_sha256)
            event, stored, _changes = registry.upsert(
                record,
                evaluation_time=evaluation_time,
                source_id=source.source_id,
                run_id=run_id,
                role_match=bool(candidate.title_hint),
            )
            if event in {"new"}:
                new_count += 1
            elif event == "changed":
                changed_count += 1
            elif event in {"content_duplicate", "exact_duplicate", "unchanged"}:
                duplicate_count += 1
            if stored.status == "expired" or event == "expired":
                expired_count += 1
            if event == "unchanged":
                continue
            lifecycle_status, lifecycle_reason = posting_lifecycle_status(stored, evaluation_time)
            decision = None
            extra_reasons: list[DecisionReason] = []
            if lifecycle_reason:
                extra_reasons.append(lifecycle_reason)
            if event == "content_duplicate":
                extra_reasons.append(DecisionReason("content_duplicate", "posting", "다른 URL에서 같은 공고 본문이 발견되었습니다."))
            if applicant_profile is not None and lifecycle_status == "active" and event not in {"content_duplicate"}:
                decision = evaluate_eligibility(applicant_profile, stored, evaluated_at=evaluation_time)
            elif applicant_profile is None and lifecycle_status == "active":
                extra_reasons.append(DecisionReason("applicant_profile_missing", "profile", "지원자 프로필이 없어 자격 판정을 수행하지 않았습니다."))
            queue_status = event if event in {"changed", "content_duplicate", "expired", "closed"} else lifecycle_status
            registry.create_queue_item(
                stored,
                discovery_status=queue_status,
                evaluation=decision,
                evaluation_time=evaluation_time,
                source_id=source.source_id,
                role_match=bool(candidate.title_hint),
                extra_reasons=tuple(extra_reasons),
            )
        except RegistryError as error:
            registry_failed = True
            failed_count += 1
            errors.append({"url": candidate.canonical_url, "code": type(error).__name__, "message": str(error)[:240]})
            break
        except Exception as error:
            failed_count += 1
            errors.append({"url": candidate.canonical_url, "code": type(error).__name__, "message": str(error)[:240]})
    status = "failed" if registry_failed else ("completed_with_errors" if errors else "completed")
    run = DiscoveryRun(
        1, run_id, source.source_id, started_at, evaluation_time, evaluation_time, status,
        discovered_count, fetched_count, new_count, changed_count, duplicate_count,
        expired_count, failed_count, tuple(errors),
    )
    registry.record_event(
        "discovery_completed" if status != "failed" else "discovery_failed",
        occurred_at=evaluation_time,
        source_id=source.source_id,
        posting_id=None,
        run_id=run_id,
        metadata={"status": status, "discovered_count": discovered_count, "failed_count": failed_count},
    )
    save_discovery_run(registry.path.parent / "discovery_runs" / f"{run_id}.json", run)
    return run


def save_discovery_run(path: Path, run: DiscoveryRun) -> None:
    write_json(path, asdict(run))
