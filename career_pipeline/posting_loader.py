"""채용공고 로더. URL과 로컬 파일을 지원하며 SSRF 방어와 공식 출처 검증을 수행합니다."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import ipaddress
from pathlib import Path
import socket
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .posting_schema import LoadedPosting, PostingSourceMetadata


MAX_POSTING_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_CONTENT_TYPES = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
LOCAL_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class PostingSourceError(ValueError):
    pass


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    content: bytes


Resolver = Callable[..., list[tuple]]
Transport = Callable[[str], TransportResponse]


def host_matches_official_domain(host: str, domain: str) -> bool:
    host = host.rstrip(".").lower()
    domain = domain.rstrip(".").lower()
    return host == domain or host.endswith("." + domain)


def _resolved_addresses(host: str, resolver: Resolver) -> tuple[str, ...]:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            records = resolver(host, 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise PostingSourceError(f"could not resolve posting host: {host}") from error
        return tuple(record[4][0] for record in records)
    return (host,)


def validate_public_https_url(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
):
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise PostingSourceError("posting URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise PostingSourceError("posting URL must not contain credentials")
    if not parsed.hostname:
        raise PostingSourceError("posting URL requires a host")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise PostingSourceError("localhost posting URL is not allowed")
    addresses = _resolved_addresses(host, resolver)
    if not addresses:
        raise PostingSourceError("posting host did not resolve")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as error:
            raise PostingSourceError(f"invalid resolved IP address: {address}") from error
        if not ip.is_global:
            raise PostingSourceError(f"non-public posting address is not allowed: {address}")
    return parsed


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_transport(url: str) -> TransportResponse:
    opener = build_opener(_NoRedirect())
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain",
            "User-Agent": "career-pipeline/0.1",
        },
        method="GET",
    )
    try:
        response = opener.open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        content = response.read(MAX_POSTING_BYTES + 1)
        headers = {key.lower(): value for key, value in response.headers.items()}
        return TransportResponse(response.status, headers, content)


def _content_metadata(content: bytes) -> str:
    return sha256(content).hexdigest()


def _load_local(path: Path, official_source: bool) -> LoadedPosting:
    if not official_source:
        raise PostingSourceError("local posting requires official source attestation")
    extension = path.suffix.lower()
    if extension not in LOCAL_CONTENT_TYPES:
        raise PostingSourceError("local posting must be PDF or DOCX")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise PostingSourceError(f"could not read posting: {path}") from error
    if len(content) > MAX_POSTING_BYTES:
        raise PostingSourceError("posting exceeds 20MB limit")
    metadata = PostingSourceMetadata(
        kind=extension.removeprefix("."),
        location=str(path.resolve()),
        retrieved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        content_sha256=_content_metadata(content),
        official_status="user_attested",
        content_type=LOCAL_CONTENT_TYPES[extension],
    )
    return LoadedPosting(metadata, extension, content)


def load_posting_source(
    source: str | Path,
    *,
    official_source: bool = False,
    official_domains: tuple[str, ...] = (),
    resolver: Resolver = socket.getaddrinfo,
    transport: Transport = _default_transport,
) -> LoadedPosting:
    if isinstance(source, Path) or not str(source).lower().startswith(("http://", "https://")):
        return _load_local(Path(source), official_source)

    current_url = str(source)
    response: TransportResponse | None = None
    for redirect_count in range(MAX_REDIRECTS + 1):
        parsed = validate_public_https_url(current_url, resolver=resolver)
        host = parsed.hostname or ""
        if official_domains and not any(
            host_matches_official_domain(host, domain) for domain in official_domains
        ):
            raise PostingSourceError("posting host does not match an official domain")
        response = transport(current_url)
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise PostingSourceError("redirect response is missing a location")
            if redirect_count == MAX_REDIRECTS:
                raise PostingSourceError("posting exceeded redirect limit")
            current_url = urljoin(current_url, location)
            continue
        if response.status < 200 or response.status >= 300:
            raise PostingSourceError(f"posting request failed with HTTP {response.status}")
        break
    assert response is not None

    if len(response.content) > MAX_POSTING_BYTES:
        raise PostingSourceError("posting exceeds 20MB limit")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise PostingSourceError(f"unsupported posting content type: {content_type or 'missing'}")
    status = "verified_domain" if official_domains else "unverified"
    metadata = PostingSourceMetadata(
        kind="url",
        location=current_url,
        retrieved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        content_sha256=_content_metadata(response.content),
        official_status=status,
        content_type=content_type,
    )
    return LoadedPosting(metadata, extension, response.content)


def write_posting_snapshot(run_dir: Path, loaded: LoadedPosting) -> Path:
    snapshot_dir = run_dir / "00_채용공고원문"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    output = snapshot_dir / f"source{loaded.extension}"
    if output.exists():
        if output.read_bytes() == loaded.content:
            return output
        raise PostingSourceError("posting snapshot already contains different content")
    try:
        with output.open("xb") as stream:
            stream.write(loaded.content)
    except FileExistsError:
        if output.read_bytes() == loaded.content:
            return output
        raise PostingSourceError("posting snapshot already contains different content")
    return output
