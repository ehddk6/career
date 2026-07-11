from __future__ import annotations

from pathlib import Path
import re


class ApplyError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ApplyError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def update_discovery(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "MAX_SITEMAP_FILES = 10" in text:
        return

    text = replace_once(
        text,
        "MAX_SITEMAP_URLS = 500\nMAX_SITEMAP_DEPTH = 1",
        "MAX_SITEMAP_URLS = 500\nMAX_SITEMAP_FILES = 10\nMAX_SITEMAP_DEPTH = 1",
        "sitemap limit",
    )
    text = replace_once(
        text,
        '''    for domain in source.allowed_domains:
        normalized = domain.strip().lower().rstrip(".")
        if not normalized or "/" in normalized or "://" in normalized:
            issues.append(f"allowed_domains: invalid domain {domain}")
        elif parsed.hostname and not host_matches_official_domain(parsed.hostname, normalized):
            issues.append(f"allowed_domains: entry URL is outside allowlist: {domain}")
''',
        '''    normalized_domains: list[str] = []
    for domain in source.allowed_domains:
        normalized = domain.strip().lower().rstrip(".")
        if not normalized or "/" in normalized or "://" in normalized:
            issues.append(f"allowed_domains: invalid domain {domain}")
        else:
            normalized_domains.append(normalized)
    if parsed.hostname and normalized_domains and not any(
        host_matches_official_domain(parsed.hostname, domain)
        for domain in normalized_domains
    ):
        issues.append("allowed_domains: entry URL is outside allowlist")
''',
        "allowlist any-match",
    )
    text = replace_once(
        text,
        '''def _allowed_candidate_url(source: DiscoverySource, url: str, *, resolver: Resolver) -> str | None:
    try:
        parsed = validate_public_https_url(url, resolver=resolver)
    except PostingSourceError:
        return None
    host = parsed.hostname or ""
    if not any(host_matches_official_domain(host, domain) for domain in source.allowed_domains):
        return None
    canonical = canonicalize_url(url)
    lowered = canonical.casefold()
''',
        '''def _allowed_source_url(source: DiscoverySource, url: str, *, resolver: Resolver) -> str | None:
    try:
        parsed = validate_public_https_url(url, resolver=resolver)
    except PostingSourceError:
        return None
    host = parsed.hostname or ""
    if not any(host_matches_official_domain(host, domain) for domain in source.allowed_domains):
        return None
    return canonicalize_url(url)


def _allowed_candidate_url(source: DiscoverySource, url: str, *, resolver: Resolver) -> str | None:
    canonical = _allowed_source_url(source, url, resolver=resolver)
    if canonical is None:
        return None
    lowered = canonical.casefold()
''',
        "source URL validator",
    )
    text, count = re.subn(
        r'(def _xml_links\(content: bytes\) -> list\[str\]:\n    text = content\.decode\("utf-8", errors="replace"\)\n)    if re\.search\([^\n]+\):',
        r'\1    if re.search(r"<!\\s*(DOCTYPE|ENTITY)\\b", text, re.IGNORECASE):',
        text,
        count=1,
    )
    if count != 1:
        raise ApplyError("XML declaration guard not found")
    text = replace_once(
        text,
        '''        for url in links[:MAX_SITEMAP_URLS]:
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
''',
        '''        for url in links[:MAX_SITEMAP_FILES]:
            candidate_url = _allowed_source_url(source, url, resolver=resolver)
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
                if len(nested) >= MAX_SITEMAP_URLS:
                    break
        return nested[:MAX_SITEMAP_URLS]
''',
        "bounded sitemap traversal",
    )
    text = replace_once(
        text,
        '''        pagination = source.config.get("pagination", {})
        if pagination.get("enabled"):
''',
        '''        pagination = source.config.get("pagination", {})
        limit = int(source.config.get("max_candidates", MAX_CANDIDATES))
        if pagination.get("enabled"):
''',
        "pagination limit variable",
    )
    text = replace_once(
        text,
        "            return tuple(list(unique.values())[:MAX_CANDIDATES])",
        "            return tuple(list(unique.values())[:limit])",
        "pagination configured limit",
    )
    text = replace_once(
        text,
        '''    try:
        datetime.fromisoformat(evaluation_time.replace("Z", "+00:00"))
    except ValueError as error:
        raise DiscoveryValidationError("evaluation_time must be ISO-8601") from error
''',
        '''    try:
        parsed_evaluation_time = datetime.fromisoformat(evaluation_time.replace("Z", "+00:00"))
    except ValueError as error:
        raise DiscoveryValidationError("evaluation_time must be ISO-8601") from error
    if parsed_evaluation_time.tzinfo is None or parsed_evaluation_time.utcoffset() is None:
        raise DiscoveryValidationError("evaluation_time must include a timezone")
''',
        "timezone-aware evaluation",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def update_registry(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_loaded_sha256" in text:
        return

    text = replace_once(
        text,
        '''def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RegistryError(f"invalid registry JSON: line {error.lineno}") from error
''',
        '''def _read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise RegistryError("registry JSON must be UTF-8") from error
    except json.JSONDecodeError as error:
        raise RegistryError(f"invalid registry JSON: line {error.lineno}") from error
    return payload, sha256(raw).hexdigest()
''',
        "registry loaded hash",
    )
    text = replace_once(
        text,
        '''        self.postings: dict[str, PostingRecord] = {}
        self.queue: dict[str, ReviewQueueItem] = {}
''',
        '''        self.postings: dict[str, PostingRecord] = {}
        self.queue: dict[str, ReviewQueueItem] = {}
        self._loaded_sha256: str | None = None
''',
        "registry hash state",
    )
    text = replace_once(
        text,
        "        payload = _read_json(registry.path)",
        "        payload, registry._loaded_sha256 = _read_json(registry.path)",
        "registry load hash",
    )
    text = replace_once(
        text,
        '''    def save(self) -> None:
        with _registry_lock(self.lock_path):
            write_json(self.path, self._payload())
''',
        '''    def save(self) -> None:
        payload = self._payload()
        with _registry_lock(self.lock_path):
            if self.path.exists():
                current_sha256 = sha256(self.path.read_bytes()).hexdigest()
                if self._loaded_sha256 is None or current_sha256 != self._loaded_sha256:
                    raise RegistryLockError("registry changed concurrently; reload and retry")
            elif self._loaded_sha256 is not None:
                raise RegistryLockError("registry disappeared after it was loaded; reload and retry")
            write_json(self.path, payload)
            self._loaded_sha256 = sha256(self.path.read_bytes()).hexdigest()
''',
        "registry optimistic concurrency",
    )
    text = replace_once(
        text,
        '''    def write_snapshot(self, posting_id: str, content: bytes, raw_sha256: str) -> Path:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
''',
        '''    def write_snapshot(self, posting_id: str, content: bytes, raw_sha256: str) -> Path:
        if sha256(content).hexdigest() != raw_sha256:
            raise RegistryError("snapshot SHA-256 does not match content")
        if self.snapshots_dir.is_symlink():
            raise RegistryError("snapshot directory must not be a symbolic link")
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
''',
        "snapshot integrity",
    )
    text = replace_once(
        text,
        '''        if item.queue_status in {"superseded", "expired"}:
            raise RegistryError("cannot decide a superseded or expired queue item")
        updated = replace(item, queue_status=decision, updated_at=at)
''',
        '''        if item.queue_status in {"superseded", "expired"}:
            raise RegistryError("cannot decide a superseded or expired queue item")
        if item.queue_status in {"approved", "rejected", "deferred"}:
            if item.queue_status == decision:
                return item
            raise RegistryError(f"queue item is already decided as {item.queue_status}")
        updated = replace(item, queue_status=decision, updated_at=at)
''',
        "immutable queue decisions",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    update_discovery(root / "career_pipeline" / "discovery.py")
    update_registry(root / "career_pipeline" / "registry.py")


if __name__ == "__main__":
    main()
