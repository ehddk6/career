"""Dependency-free exact HTTPS origin normalization."""
from __future__ import annotations

from urllib.parse import urlsplit


class OriginPolicyError(ValueError):
    """An origin does not satisfy the shared HTTPS policy."""


def _normalized_origin(value: str, *, require_bare: bool) -> str:
    if not isinstance(value, str) or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise OriginPolicyError("invalid origin")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme.casefold() != "https" or not host or parsed.username or parsed.password:
            raise OriginPolicyError("origin must be credential-free HTTPS")
        if "*" in host:
            raise OriginPolicyError("invalid origin host")
        if host.endswith("."):
            host = host[:-1]
        if not host:
            raise OriginPolicyError("invalid origin host")
        normalized_host = host.encode("idna").decode("ascii").casefold()
        port = parsed.port or 443
    except OriginPolicyError:
        raise
    except (UnicodeError, ValueError, TypeError) as error:
        raise OriginPolicyError("invalid origin host or port") from error
    if require_bare and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise OriginPolicyError("origin must not contain path, query, or fragment")
    if ":" in normalized_host and not normalized_host.startswith("["):
        normalized_host = f"[{normalized_host}]"
    return f"https://{normalized_host}:{port}"


def normalize_origin(value: str) -> str:
    """Return the canonical form of a bare HTTPS origin."""
    return _normalized_origin(value, require_bare=True)


def origin_from_url(value: str) -> str:
    """Return the canonical HTTPS origin from a URL, discarding URL suffixes."""
    return _normalized_origin(value, require_bare=False)
