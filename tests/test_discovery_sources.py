import pytest

from career_pipeline.discovery import (
    DiscoveryValidationError,
    discover_candidates,
)
from career_pipeline.models import DiscoverySource
from career_pipeline.posting_loader import TransportResponse


def public_resolver(host: str, port: int, *args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def source(source_type: str, url: str, **config) -> DiscoverySource:
    return DiscoverySource(
        1,
        f"{source_type}-source",
        "Example",
        source_type,
        url,
        ("jobs.example.or.kr",),
        (),
        (),
        True,
        "2026-07-12T09:00:00+09:00",
        "2026-07-12T09:00:00+09:00",
        config,
    )


def html(body: str) -> TransportResponse:
    return TransportResponse(200, {"content-type": "text/html; charset=utf-8"}, body.encode())


def xml(body: str, content_type: str = "application/xml") -> TransportResponse:
    return TransportResponse(200, {"content-type": content_type}, body.encode())


def test_manual_url_discovers_only_the_registered_url():
    candidates = discover_candidates(
        source("manual_url", "https://jobs.example.or.kr/jobs/42"),
        evaluation_time="2026-07-12T09:00:00+09:00",
        resolver=public_resolver,
        transport=lambda _url: pytest.fail("manual_url must not fetch or crawl"),
    )

    assert len(candidates) == 1
    assert candidates[0].canonical_url == "https://jobs.example.or.kr/jobs/42"


def test_list_page_pagination_is_explicit_and_bounded():
    requested: list[str] = []

    def transport(url: str) -> TransportResponse:
        requested.append(url)
        page = url.split("page=")[-1] if "page=" in url else "1"
        return html(f'<a href="/jobs/{page}">Job {page}</a>')

    candidates = discover_candidates(
        source(
            "official_list_page",
            "https://jobs.example.or.kr/list?page=1",
            pagination={"enabled": True, "strategy": "query_page", "max_pages": 3},
        ),
        evaluation_time="2026-07-12T09:00:00+09:00",
        resolver=public_resolver,
        transport=transport,
    )

    assert [item.canonical_url for item in candidates] == [
        "https://jobs.example.or.kr/jobs/1",
        "https://jobs.example.or.kr/jobs/2",
        "https://jobs.example.or.kr/jobs/3",
    ]
    assert len(requested) == 3


def test_rss_accepts_atom_and_rejects_malformed_xml():
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="/jobs/1" /></entry></feed>'
    candidates = discover_candidates(
        source("official_rss", "https://jobs.example.or.kr/feed"),
        resolver=public_resolver,
        transport=lambda _url: TransportResponse(200, {"content-type": "application/atom+xml"}, atom),
    )
    assert [item.canonical_url for item in candidates] == ["https://jobs.example.or.kr/jobs/1"]

    with pytest.raises(DiscoveryValidationError, match="invalid discovery XML"):
        discover_candidates(
            source("official_rss", "https://jobs.example.or.kr/feed"),
            resolver=public_resolver,
            transport=lambda _url: xml("<rss><channel>"),
        )


def test_xml_external_entities_are_rejected():
    malicious = b'<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///secret"> ]><urlset />'
    with pytest.raises(DiscoveryValidationError, match="DTD and ENTITY"):
        discover_candidates(
            source("official_sitemap", "https://jobs.example.or.kr/map", include_pattern=r"/jobs/"),
            resolver=public_resolver,
            transport=lambda _url: TransportResponse(200, {"content-type": "application/xml"}, malicious),
        )


def test_sitemap_index_is_limited_to_one_nested_level_and_applies_filter():
    payloads = {
        "https://jobs.example.or.kr/map": xml(
            "<sitemapindex><sitemap><loc>/nested.xml</loc></sitemap></sitemapindex>"
        ),
        "https://jobs.example.or.kr/nested.xml": xml(
            "<urlset><url><loc>/jobs/1</loc></url><url><loc>/other/2</loc></url></urlset>"
        ),
    }
    candidates = discover_candidates(
        source("official_sitemap", "https://jobs.example.or.kr/map", include_pattern=r"/jobs/"),
        resolver=public_resolver,
        transport=payloads.__getitem__,
    )
    assert [item.canonical_url for item in candidates] == ["https://jobs.example.or.kr/jobs/1"]


def test_json_api_requires_explicit_schema_and_does_not_auto_discover_endpoints():
    response = TransportResponse(
        200,
        {"content-type": "application/json"},
        b'{"items":[{"url":"/jobs/1"}]}',
    )
    candidates = discover_candidates(
        source("official_json_api", "https://jobs.example.or.kr/api", items_path="items", url_field="url"),
        resolver=public_resolver,
        transport=lambda url: response if url.endswith("/api") else pytest.fail(url),
    )
    assert [item.canonical_url for item in candidates] == ["https://jobs.example.or.kr/jobs/1"]

    with pytest.raises(DiscoveryValidationError, match="items_path"):
        discover_candidates(
            source("official_json_api", "https://jobs.example.or.kr/api", items_path="missing", url_field="url"),
            resolver=public_resolver,
            transport=lambda _url: response,
        )


def test_source_schema_rejects_bad_pagination_and_regex():
    with pytest.raises(DiscoveryValidationError, match="max_pages"):
        discover_candidates(
            source(
                "official_list_page",
                "https://jobs.example.or.kr/list",
                pagination={"enabled": True, "strategy": "query_page", "max_pages": 4},
            ),
            resolver=public_resolver,
            transport=lambda _url: html(""),
        )

    with pytest.raises(DiscoveryValidationError, match="invalid regular expression"):
        discover_candidates(
            source("official_list_page", "https://jobs.example.or.kr/list", detail_pattern="["),
            resolver=public_resolver,
            transport=lambda _url: html(""),
        )
