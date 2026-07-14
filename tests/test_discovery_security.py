from pathlib import Path

import pytest

from career_pipeline.eligibility import canonicalize_url
from career_pipeline.posting_loader import (
    MAX_POSTING_BYTES,
    PostingSourceError,
    TransportResponse,
    load_posting_source,
    validate_public_https_url,
)


def public_resolver(host: str, port: int, *args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def resolver_for(address: str):
    def resolve(host: str, port: int, *args, **kwargs):
        return [(2, 1, 6, "", (address, port))]

    return resolve


@pytest.mark.parametrize(
    "url, resolver, message",
    [
        ("http://jobs.example.or.kr/jobs/1", public_resolver, "HTTPS"),
        ("https://user:secret@jobs.example.or.kr/jobs/1", public_resolver, "credentials"),
        ("https://localhost/jobs/1", public_resolver, "localhost"),
        ("https://jobs.example.or.kr/jobs/1?api_key=secret", public_resolver, "sensitive"),
        ("https://jobs.example.or.kr/jobs/1?token=secret", public_resolver, "sensitive"),
        ("https://127.0.0.1/jobs/1", public_resolver, "non-public"),
        ("https://169.254.169.254/latest/meta-data", public_resolver, "non-public"),
        ("https://[::1]/jobs/1", public_resolver, "non-public"),
        ("https://[fe80::1]/jobs/1", public_resolver, "non-public"),
        ("https://[fc00::1]/jobs/1", public_resolver, "non-public"),
    ],
)
def test_public_https_validation_rejects_unsafe_urls(url, resolver, message):
    with pytest.raises(PostingSourceError, match=message):
        validate_public_https_url(url, resolver=resolver)


def test_dns_result_must_be_public():
    with pytest.raises(PostingSourceError, match="non-public"):
        validate_public_https_url(
            "https://jobs.example.or.kr/jobs/1",
            resolver=resolver_for("10.0.0.8"),
        )


def test_redirect_is_revalidated_for_allowlist_and_dns():
    calls: list[str] = []

    def transport(url: str) -> TransportResponse:
        calls.append(url)
        return TransportResponse(
            302,
            {"location": "https://attacker.example/jobs/1"},
            b"",
        )

    with pytest.raises(PostingSourceError, match="official domain"):
        load_posting_source(
            "https://jobs.example.or.kr/jobs/1",
            official_domains=("jobs.example.or.kr",),
            resolver=public_resolver,
            transport=transport,
        )
    assert calls == ["https://jobs.example.or.kr/jobs/1"]

    def private_redirect(url: str) -> TransportResponse:
        if url.endswith("/1"):
            return TransportResponse(302, {"location": "https://jobs.example.or.kr/jobs/2"}, b"")
        return TransportResponse(200, {"content-type": "text/html"}, b"job")

    calls.clear()
    with pytest.raises(PostingSourceError, match="non-public"):
        load_posting_source(
            "https://jobs.example.or.kr/jobs/1",
            official_domains=("jobs.example.or.kr",),
            resolver=lambda host, port, *args, **kwargs: (
                [(2, 1, 6, "", ("93.184.216.34", port))]
                if host == "jobs.example.or.kr" and calls == []
                else [(2, 1, 6, "", ("10.0.0.8", port))]
            ),
            transport=lambda url: (calls.append(url) or private_redirect(url)),
        )


def test_content_type_and_size_limits_are_enforced():
    with pytest.raises(PostingSourceError, match="unsupported posting content type"):
        load_posting_source(
            "https://jobs.example.or.kr/jobs/1",
            resolver=public_resolver,
            transport=lambda _url: TransportResponse(200, {"content-type": "application/octet-stream"}, b"x"),
        )

    with pytest.raises(PostingSourceError, match="20MB"):
        load_posting_source(
            "https://jobs.example.or.kr/jobs/1",
            resolver=public_resolver,
            transport=lambda _url: TransportResponse(
                200,
                {"content-type": "text/html"},
                b"x" * (MAX_POSTING_BYTES + 1),
            ),
        )


def test_canonical_url_removes_fragments_and_tracking_but_preserves_posting_query():
    assert canonicalize_url(
        "HTTPS://Jobs.Example.OR.KR/jobs/1/?utm_source=x&b=2&fbclid=y&a=1#section"
    ) == "https://jobs.example.or.kr/jobs/1?a=1&b=2"


def test_sensitive_urls_are_not_written_to_snapshots_or_registry(tmp_path: Path):
    # Direct registry writes are covered separately; this asserts the loader never
    # accepts a sensitive query that could otherwise reach persisted metadata.
    with pytest.raises(PostingSourceError, match="sensitive"):
        load_posting_source(
            "https://jobs.example.or.kr/jobs/1?password=secret",
            resolver=public_resolver,
            transport=lambda _url: pytest.fail("must reject before transport"),
        )
