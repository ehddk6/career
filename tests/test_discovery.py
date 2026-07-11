from hashlib import sha256
import json
from pathlib import Path

import pytest

from career_pipeline.__main__ import main
from career_pipeline.discovery import discover_candidates, run_discovery
from career_pipeline.models import DiscoverySource, EligibilityRule, PostingRecord
from career_pipeline.posting_loader import TransportResponse
from career_pipeline.registry import PostingRegistry, RegistryLockError


def resolver(host: str, port: int, *args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def response(content: bytes, content_type: str) -> TransportResponse:
    return TransportResponse(200, {"content-type": content_type}, content)


def source(source_type: str, url: str, **config) -> DiscoverySource:
    return DiscoverySource(
        1,
        "source-1",
        "기관",
        source_type,
        url,
        ("example.or.kr",),
        (),
        (),
        True,
        "2026-07-11T12:00:00+09:00",
        "2026-07-11T12:00:00+09:00",
        config,
    )


def fake_transport(url: str) -> TransportResponse:
    if url.endswith("/list"):
        return response(
            '<a href="/jobs/1">행정지원</a><a href="https://other.example/jobs/2">외부</a><a href="/login">로그인</a>'.encode(),
            "text/html",
        )
    return response(
        "기관명: 공식기관\n직무: 행정지원\n담당업무: 고객 안내".encode(),
        "text/plain",
    )


def test_official_list_page_filters_domains_and_login_links():
    candidates = discover_candidates(
        source("official_list_page", "https://jobs.example.or.kr/list"),
        evaluation_time="2026-07-11T12:00:00+09:00",
        resolver=resolver,
        transport=fake_transport,
    )

    assert [item.canonical_url for item in candidates] == ["https://jobs.example.or.kr/jobs/1"]


def test_rss_sitemap_and_json_api_discovery_use_explicit_formats():
    payloads = {
        "https://jobs.example.or.kr/feed": response(
            b"<rss><channel><item><link>/jobs/rss</link></item></channel></rss>",
            "application/rss+xml",
        ),
        "https://jobs.example.or.kr/map": response(
            b"<urlset><url><loc>https://jobs.example.or.kr/jobs/map</loc></url></urlset>",
            "application/xml",
        ),
        "https://jobs.example.or.kr/api": response(
            b'{"items":[{"url":"https://jobs.example.or.kr/jobs/api"}]}',
            "application/json",
        ),
    }

    def transport(url: str) -> TransportResponse:
        return payloads[url]

    for source_type, url, expected in (
        ("official_rss", "https://jobs.example.or.kr/feed", "/jobs/rss"),
        ("official_sitemap", "https://jobs.example.or.kr/map", "/jobs/map"),
        ("official_json_api", "https://jobs.example.or.kr/api", "/jobs/api"),
    ):
        config = (
            {"items_path": "items", "url_field": "url"}
            if source_type == "official_json_api"
            else ({"include_pattern": r"/jobs/"} if source_type == "official_sitemap" else {})
        )
        candidates = discover_candidates(
            source(source_type, url, **config),
            evaluation_time="2026-07-11T12:00:00+09:00",
            resolver=resolver,
            transport=transport,
        )
        assert [item.canonical_url for item in candidates] == [f"https://jobs.example.or.kr{expected}"]


def test_discovery_run_persists_registry_snapshot_queue_and_is_idempotent(tmp_path: Path):
    registry_path = tmp_path / ".career_profile" / "posting_registry" / "registry.json"
    registry = PostingRegistry.load(registry_path)
    configured = source("official_list_page", "https://jobs.example.or.kr/list")
    evaluation_time = "2026-07-11T12:00:00+09:00"

    first = run_discovery(
        configured,
        registry=registry,
        evaluation_time=evaluation_time,
        resolver=resolver,
        transport=fake_transport,
    )

    assert first.status == "completed"
    assert first.new_count == 1
    assert len(registry.postings) == 1
    assert len(registry.queue) == 1
    assert next(iter(registry.postings.values())).status == "manual_review"
    assert list((registry_path.parent / "snapshots").glob("*.bin"))
    assert (registry_path.parent / "events.jsonl").exists()
    first_event_count = len((registry_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines())

    reloaded = PostingRegistry.load(registry_path)
    second = run_discovery(
        configured,
        registry=reloaded,
        evaluation_time=evaluation_time,
        resolver=resolver,
        transport=fake_transport,
    )

    assert second.status == "completed"
    assert second.duplicate_count == 1
    assert len(reloaded.queue) == 1
    assert len((registry_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()) == first_event_count


def test_expired_posting_does_not_enter_submission_queue(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = PostingRegistry.load(registry_path)
    content_hash = sha256(b"posting").hexdigest()
    record = PostingRecord(
        1,
        "posting-1",
        "https://jobs.example.or.kr/jobs/1",
        "jobs.example.or.kr",
        "2026-07-01",
        "2026-07-10",
        "공고",
        "기관",
        "직무",
        content_hash,
        "2026-07-01T12:00:00+09:00",
        "verified_domain",
        (),
        (),
        (),
        timezone="+09:00",
    )
    event, stored, _ = registry.upsert(
        record, evaluation_time="2026-07-11T12:00:00+09:00", source_id="source-1"
    )
    item = registry.create_queue_item(
        stored,
        discovery_status=event,
        evaluation=None,
        evaluation_time="2026-07-11T12:00:00+09:00",
        source_id="source-1",
    )

    assert event == "expired"
    assert item is None


def test_source_add_cli_writes_allowlisted_source(tmp_path: Path):
    result = main(
        [
            "discovery",
            "source-add",
            "--root",
            str(tmp_path),
            "--organization",
            "기관",
            "--type",
            "manual_url",
            "--url",
            "https://jobs.example.or.kr/jobs/1",
            "--allow-domain",
            "example.or.kr",
        ]
    )

    assert result == 0
    assert (tmp_path / ".career_profile" / "discovery_sources.json").exists()
    events = (tmp_path / ".career_profile" / "posting_registry" / "events.jsonl").read_text(encoding="utf-8")
    assert '"event_type": "source_added"' in events


def test_changed_posting_supersedes_previous_queue_item(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    current = PostingRecord(
        1, "posting-1", "https://jobs.example.or.kr/jobs/1", "jobs.example.or.kr",
        "2026-07-01", "2026-07-31", "공고", "기관", "직무", "a" * 64,
        "2026-07-01T12:00:00+09:00", "verified_domain", (), (), (), timezone="+09:00",
    )
    event, stored, _ = registry.upsert(current, evaluation_time="2026-07-11T12:00:00+09:00")
    registry.create_queue_item(
        stored, discovery_status="manual_review", evaluation=None,
        evaluation_time="2026-07-11T12:00:00+09:00", source_id=None,
    )
    changed = PostingRecord(**{**current.__dict__, "body_sha256": "b" * 64})
    event, stored, _ = registry.upsert(changed, evaluation_time="2026-07-12T12:00:00+09:00")
    registry.create_queue_item(
        stored, discovery_status=event, evaluation=None,
        evaluation_time="2026-07-12T12:00:00+09:00", source_id=None,
    )

    assert event == "changed"
    assert any(item.queue_status == "superseded" for item in registry.queue.values())
    assert any(item.queue_status == "pending" for item in registry.queue.values())


def test_registry_lock_collision_is_safe(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    registry.lock_path.parent.mkdir(parents=True, exist_ok=True)
    registry.lock_path.write_text("held", encoding="utf-8")
    try:
        with pytest.raises(RegistryLockError):
            registry.save()
    finally:
        registry.lock_path.unlink()


def test_failed_discovery_is_recorded_as_running_then_retried_with_new_run_id(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    calls = {"detail": 0}

    def transport(url: str) -> TransportResponse:
        if url.endswith("/list"):
            return response(b'<a href="/jobs/1">Job 1</a>', "text/html")
        calls["detail"] += 1
        if calls["detail"] == 1:
            return TransportResponse(503, {"content-type": "text/plain"}, b"temporary failure")
        return response("Example\nEngineer\nOfficial role details".encode(), "text/plain")

    configured = source("official_list_page", "https://jobs.example.or.kr/list")
    first = run_discovery(
        configured,
        registry=registry,
        evaluation_time="2026-07-12T09:00:00+09:00",
        resolver=resolver,
        transport=transport,
    )
    second = run_discovery(
        configured,
        registry=registry,
        evaluation_time="2026-07-12T09:00:00+09:00",
        resolver=resolver,
        transport=transport,
    )

    assert first.status == "completed_with_errors"
    assert second.status == "completed"
    assert first.run_id != second.run_id
    assert (tmp_path / "discovery_runs" / f"{first.run_id}.json").exists()
    assert (tmp_path / "discovery_runs" / f"{second.run_id}.json").exists()
    assert json.loads((tmp_path / "discovery_runs" / f"{second.run_id}.json").read_text(encoding="utf-8"))["status"] == "completed"
