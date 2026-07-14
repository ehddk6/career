from dataclasses import replace
from pathlib import Path

import pytest

from career_pipeline.eligibility import compare_postings
from career_pipeline.models import PostingRecord
from career_pipeline.registry import PostingRegistry, RegistryError, posting_lifecycle_status


def record(
    *,
    posting_id: str = "posting-1",
    url: str = "https://jobs.example.or.kr/jobs/1",
    body: str = "a" * 64,
    normalized: str = "b" * 64,
    deadline: str | None = "2026-07-31",
    timezone: str | None = "+09:00",
    status: str = "active",
) -> PostingRecord:
    return PostingRecord(
        1,
        posting_id,
        url,
        "jobs.example.or.kr",
        "2026-07-01",
        deadline,
        "Example posting",
        "Example",
        "Engineer",
        body,
        "2026-07-01T12:00:00+09:00",
        "verified_domain",
        (),
        (),
        (),
        timezone=timezone,
        normalized_content_sha256=normalized,
        status=status,
    )


def test_compare_postings_distinguishes_duplicate_and_change_classes():
    previous = record()
    assert compare_postings(None, previous).event == "new"
    assert compare_postings(previous, replace(previous)).event == "exact_duplicate"
    assert compare_postings(previous, replace(previous, body_sha256="c" * 64)).event == "unchanged"
    assert compare_postings(previous, replace(previous, url="https://jobs.example.or.kr/jobs/2")).event == "content_duplicate"
    assert compare_postings(previous, replace(previous, normalized_content_sha256="d" * 64)).event == "changed"
    assert compare_postings(previous, replace(previous, posting_id="posting-2", url="https://jobs.example.or.kr/jobs/2", normalized_content_sha256="d" * 64)).event == "distinct"


def test_registry_preserves_exact_duplicate_and_unchanged_events(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    evaluation = "2026-07-12T09:00:00+09:00"
    first_event, stored, _ = registry.upsert(record(), evaluation_time=evaluation, run_id="run-1")
    assert first_event == "new"

    exact_event, _, _ = registry.upsert(record(), evaluation_time=evaluation, run_id="run-2")
    assert exact_event == "exact_duplicate"

    normalized_only = replace(record(), body_sha256="c" * 64)
    unchanged_event, _, _ = registry.upsert(normalized_only, evaluation_time=evaluation, run_id="run-3")
    assert unchanged_event == "unchanged"


def test_lifecycle_requires_timezone_and_handles_date_only_deadlines():
    active, _ = posting_lifecycle_status(record(deadline="2026-07-31"), "2026-07-12T00:00:00+00:00")
    expired, _ = posting_lifecycle_status(record(deadline="2026-07-10"), "2026-07-12T00:00:00+00:00")
    unknown, reason = posting_lifecycle_status(record(deadline="2026-07-31", timezone=None), "2026-07-12T00:00:00+00:00")
    invalid, invalid_reason = posting_lifecycle_status(record(deadline="2026-07-31", timezone="+99:99"), "2026-07-12T00:00:00+00:00")

    assert active == "active"
    assert expired == "expired"
    assert unknown == "manual_review" and reason is not None
    assert invalid == "manual_review" and invalid_reason is not None


def test_snapshot_rejects_symlink_and_invalid_hash(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    with pytest.raises(RegistryError, match="SHA-256"):
        registry.write_snapshot("posting-1", b"x", "../outside")

    real_snapshots = tmp_path / "real-snapshots"
    real_snapshots.mkdir()
    snapshots = tmp_path / "snapshots"
    try:
        snapshots.symlink_to(real_snapshots, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows test runner")
    with pytest.raises(RegistryError, match="symlink"):
        registry.write_snapshot("posting-1", b"x", "a" * 64)


def test_registry_sanitizes_persisted_urls(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = PostingRegistry.load(registry_path)
    _, stored, _ = registry.upsert(
        record(url="https://jobs.example.or.kr/jobs/1?utm_source=x&api_key=secret&b=2"),
        evaluation_time="2026-07-12T09:00:00+09:00",
    )
    assert stored.url == "https://jobs.example.or.kr/jobs/1?b=2"
    assert "secret" not in registry_path.read_text(encoding="utf-8")
