"""Safe snapshot adapter for official company-research sources.

It reuses the hardened posting loader's HTTPS/SSRF/redirect/content checks rather
than creating a second network security boundary.
"""
from __future__ import annotations

from pathlib import Path
import socket
from typing import Any, Callable, Mapping

from .posting_loader import Transport, load_posting_source
from .research_source_registry import classify_source, official_domains_from_registry


def retrieve_research_source(
    run_dir: Path,
    url: str,
    *,
    source_type: str,
    registry: Mapping[str, Any],
    publisher: str = "",
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    transport: Transport | None = None,
) -> dict[str, Any]:
    allowed = official_domains_from_registry(registry)
    kwargs: dict[str, Any] = {
        "official_domains": allowed,
        "resolver": resolver,
    }
    if transport is not None:
        kwargs["transport"] = transport
    loaded = load_posting_source(url, **kwargs)
    snapshot_dir = run_dir.resolve() / "04_리서치원문"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    digest = loaded.metadata.content_sha256
    output = snapshot_dir / f"{digest[:16]}{loaded.extension}"
    if output.exists() and output.read_bytes() != loaded.content:
        raise ValueError("research snapshot hash collision or changed content")
    if not output.exists():
        output.write_bytes(loaded.content)
    classification = classify_source(
        loaded.metadata.location,
        source_type=source_type,
        registry=registry,
        publisher=publisher,
    )
    return {
        **classification,
        "retrieved_at": loaded.metadata.retrieved_at,
        "content_sha256": digest,
        "content_type": loaded.metadata.content_type,
        "snapshot_path": str(output),
    }
