from dataclasses import replace
from pathlib import Path
import socket

from docx import Document
import pytest

from career_pipeline.inventory import digest_path
from career_pipeline.posting_loader import (
    MAX_POSTING_BYTES,
    PostingSourceError,
    TransportResponse,
    load_posting_source,
    validate_public_https_url,
    write_posting_snapshot,
)


def make_docx(path: Path, text: str) -> Path:
    document = Document()
    document.add_paragraph(text)
    document.save(path)
    return path


def public_resolver(host: str, port: int, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def response(
    content: bytes = b"<html><body>posting</body></html>",
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
    location: str | None = None,
) -> TransportResponse:
    headers = {"content-type": content_type}
    if location:
        headers["location"] = location
    return TransportResponse(status=status, headers=headers, content=content)


def test_load_local_pdf_requires_official_attestation(tmp_path: Path):
    path = tmp_path / "posting.pdf"
    path.write_bytes(b"%PDF fixture")

    with pytest.raises(PostingSourceError, match="official"):
        load_posting_source(path, official_source=False)


def test_load_local_docx_records_user_attested_status(tmp_path: Path):
    path = make_docx(tmp_path / "posting.docx", "담당업무: 고객 안내")

    loaded = load_posting_source(path, official_source=True)

    assert loaded.metadata.official_status == "user_attested"
    assert loaded.metadata.content_sha256 == digest_path(path)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.or.kr/posting",
        "https://localhost/posting",
        "https://127.0.0.1/posting",
        "https://169.254.169.254/latest/meta-data",
        "https://user:secret@example.or.kr/posting",
    ],
)
def test_validate_public_https_url_rejects_unsafe_targets(url: str):
    with pytest.raises(PostingSourceError):
        validate_public_https_url(url, resolver=public_resolver)


def test_load_url_verifies_official_domain():
    loaded = load_posting_source(
        "https://jobs.example.or.kr/posting",
        official_domains=("example.or.kr",),
        resolver=public_resolver,
        transport=lambda url: response(),
    )

    assert loaded.metadata.official_status == "verified_domain"
    assert loaded.extension == ".html"


def test_load_url_rejects_official_domain_mismatch():
    with pytest.raises(PostingSourceError, match="official domain"):
        load_posting_source(
            "https://jobs.example.com/posting",
            official_domains=("example.or.kr",),
            resolver=public_resolver,
            transport=lambda url: response(),
        )


@pytest.mark.parametrize(
    ("content", "content_type", "message"),
    [
        pytest.param(
            b"x" * (MAX_POSTING_BYTES + 1),
            "text/html",
            "20MB",
            id="oversized",
        ),
        pytest.param(b"image", "image/png", "content type", id="unsupported"),
    ],
)
def test_load_url_rejects_oversized_or_unsupported_response(
    content: bytes, content_type: str, message: str
):
    with pytest.raises(PostingSourceError, match=message):
        load_posting_source(
            "https://example.or.kr/posting",
            official_domains=("example.or.kr",),
            resolver=public_resolver,
            transport=lambda url: response(content, content_type=content_type),
        )


def test_redirect_destination_is_revalidated():
    calls: list[str] = []

    def redirecting(url: str) -> TransportResponse:
        calls.append(url)
        return response(status=302, location="https://127.0.0.1/private")

    with pytest.raises(PostingSourceError):
        load_posting_source(
            "https://example.or.kr/posting",
            official_domains=("example.or.kr",),
            resolver=public_resolver,
            transport=redirecting,
        )

    assert calls == ["https://example.or.kr/posting"]


def test_write_posting_snapshot_is_immutable(tmp_path: Path):
    path = make_docx(tmp_path / "posting.docx", "담당업무: 고객 안내")
    loaded = load_posting_source(path, official_source=True)
    run_dir = tmp_path / "run"

    first = write_posting_snapshot(run_dir, loaded)
    second = write_posting_snapshot(run_dir, loaded)

    assert first == second
    assert first.read_bytes() == path.read_bytes()

    changed = replace(loaded, content=b"different")
    with pytest.raises(PostingSourceError, match="different content"):
        write_posting_snapshot(run_dir, changed)
