from dataclasses import replace
from pathlib import Path

import pytest

from career_pipeline.models import DecisionReason, EligibilityDecision, PostingRecord
from career_pipeline.registry import PostingRegistry, RegistryError


def posting(status: str = "active", posting_id: str = "posting-1") -> PostingRecord:
    return PostingRecord(
        1,
        posting_id,
        "https://jobs.example.or.kr/jobs/1",
        "jobs.example.or.kr",
        "2026-07-01",
        "2026-07-31",
        "Example posting",
        "Example",
        "Engineer",
        "a" * 64,
        "2026-07-01T12:00:00+09:00",
        "verified_domain",
        (),
        (),
        (),
        timezone="+09:00",
        normalized_content_sha256="b" * 64,
        status=status,
    )


def decision(status: str) -> EligibilityDecision:
    return EligibilityDecision(
        1,
        f"decision-{status}",
        "posting-1",
        "profile-1",
        status,
        "2026-07-12T09:00:00+09:00",
        (),
        (DecisionReason("test", "posting", "test"),),
        status in {"manual_review", "eligible_with_gaps"},
    )


def test_eligible_variants_and_manual_review_enter_pending_queue(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    evaluation_time = "2026-07-12T09:00:00+09:00"
    for index, status in enumerate(("eligible", "eligible_with_gaps", "manual_review"), start=1):
        item = registry.create_queue_item(
            posting(posting_id=f"posting-{index}"),
            discovery_status="new",
            evaluation=decision(status),
            evaluation_time=evaluation_time,
            source_id="source-1",
        )
        assert item is not None
        assert item.queue_status == "pending"
        assert item.human_review_required is True
        assert item.eligibility_status == status


def test_ineligible_duplicates_and_closed_or_expired_are_not_queued(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    at = "2026-07-12T09:00:00+09:00"
    assert registry.create_queue_item(posting(), discovery_status="ineligible", evaluation=decision("ineligible"), evaluation_time=at, source_id=None) is None
    assert registry.create_queue_item(posting(), discovery_status="content_duplicate", evaluation=None, evaluation_time=at, source_id=None) is None
    assert registry.create_queue_item(posting(status="expired"), discovery_status="expired", evaluation=None, evaluation_time=at, source_id=None) is None
    assert registry.create_queue_item(posting(status="closed"), discovery_status="closed", evaluation=None, evaluation_time=at, source_id=None) is None
    assert registry.queue == {}


def test_changed_item_supersedes_pending_and_approved_but_same_version_is_idempotent(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    at = "2026-07-12T09:00:00+09:00"
    first = registry.create_queue_item(posting(), discovery_status="new", evaluation=decision("eligible"), evaluation_time=at, source_id="source-1")
    assert first is not None
    registry.decide_queue(first.queue_id, "approved", at=at)
    changed = replace(posting(), normalized_content_sha256="c" * 64)
    second = registry.create_queue_item(changed, discovery_status="changed", evaluation=decision("eligible"), evaluation_time=at, source_id="source-1")
    assert second is not None
    assert registry.queue[first.queue_id].queue_status == "superseded"
    assert registry.create_queue_item(changed, discovery_status="changed", evaluation=decision("eligible"), evaluation_time=at, source_id="source-1") == second


def test_queue_decision_is_one_way_and_requires_timezone(tmp_path: Path):
    registry = PostingRegistry.load(tmp_path / "registry.json")
    at = "2026-07-12T09:00:00+09:00"
    item = registry.create_queue_item(posting(), discovery_status="new", evaluation=decision("eligible"), evaluation_time=at, source_id=None)
    assert item is not None
    assert registry.decide_queue(item.queue_id, "deferred", at=at).queue_status == "deferred"
    with pytest.raises(RegistryError, match="already been decided"):
        registry.decide_queue(item.queue_id, "approved", at=at)
    with pytest.raises(RegistryError, match="timezone"):
        registry.decide_queue(item.queue_id, "approved", at="2026-07-12 09:00:00")
