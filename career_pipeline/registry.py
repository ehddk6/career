"""Persistent posting registry, lifecycle classification, and review queue."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import time as time_module
from typing import Any, Iterator

from .eligibility import (
    compare_postings,
    decision_to_dict,
    evaluate_eligibility,
    posting_record_from_dict,
    posting_record_to_dict,
)
from .models import (
    DecisionReason,
    EligibilityDecision,
    PostingRecord,
    RegistryEvent,
    ReviewQueueItem,
)
from .state import write_json


REGISTRY_SCHEMA_VERSION = 1
QUEUE_STATUSES = {"pending", "approved", "rejected", "deferred", "superseded", "expired"}
DISCOVERY_EVENTS = {"new", "exact_duplicate", "content_duplicate", "changed", "unchanged", "expired", "closed", "manual_review", "distinct"}


class RegistryError(ValueError):
    pass


class RegistryLockError(RegistryError):
    pass


@contextmanager
def _registry_lock(path: Path, *, timeout_seconds: float = 5.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time_module.monotonic() + timeout_seconds
    handle = None
    while handle is None:
        try:
            handle = path.open("x", encoding="utf-8")
            handle.write("lock\n")
            handle.flush()
        except FileExistsError:
            if time_module.monotonic() >= deadline:
                raise RegistryLockError(f"could not acquire registry lock: {path}")
            time_module.sleep(0.05)
    try:
        yield
    finally:
        handle.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RegistryError(f"invalid registry JSON: line {error.lineno}") from error


def _parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RegistryError(f"evaluation time must be ISO-8601: {value}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RegistryError("evaluation time must include a timezone")
    return parsed


def _offset(value: str) -> timezone:
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":":
        raise RegistryError(f"invalid posting timezone: {value}")
    try:
        hours = int(value[1:3])
        minutes = int(value[4:6])
    except ValueError as error:
        raise RegistryError(f"invalid posting timezone: {value}") from error
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(delta if value[0] == "+" else -delta)


def posting_lifecycle_status(record: PostingRecord, evaluation_time: str) -> tuple[str, DecisionReason | None]:
    if record.status == "closed":
        return "closed", DecisionReason("posting_closed", "posting", "공고가 모집 종료 상태로 표시되어 있습니다.")
    if record.status == "manual_review":
        return "manual_review", DecisionReason("posting_manual_review", "posting", "공고 상태가 수동 검토로 지정되어 있습니다.")
    try:
        evaluation = _parse_iso(evaluation_time)
    except RegistryError:
        return "manual_review", DecisionReason("evaluation_time_invalid", "deadline", "평가 시각에 timezone이 없거나 형식이 잘못되었습니다.")
    if not record.deadline_at:
        return "manual_review", DecisionReason("deadline_unknown", "deadline", "공고 마감일이 확인되지 않았습니다.")
    if not record.timezone:
        return "manual_review", DecisionReason("posting_timezone_unknown", "deadline", "공고 timezone이 확인되지 않았습니다.")
    try:
        posting_zone = _offset(record.timezone)
        raw_deadline = record.deadline_at.replace("Z", "+00:00")
        if len(raw_deadline) == 10:
            deadline = datetime.combine(
                date.fromisoformat(raw_deadline), time(23, 59, 59), tzinfo=posting_zone
            )
        else:
            deadline = datetime.fromisoformat(raw_deadline)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=posting_zone)
    except ValueError as error:
        return "manual_review", DecisionReason("deadline_invalid", "deadline", "공고 마감일 형식을 확인할 수 없습니다.")
    if evaluation.astimezone(timezone.utc) > deadline.astimezone(timezone.utc):
        return "expired", DecisionReason("posting_expired", "deadline", "공고 마감일이 평가 시각보다 지났습니다.")
    return "active", None


def _change_metadata(before: PostingRecord, after: PostingRecord) -> list[dict[str, str]]:
    fields = (
        ("role", before.role, after.role),
        ("locations", ",".join(before.locations), ",".join(after.locations)),
        ("deadline_at", before.deadline_at or "", after.deadline_at or ""),
        ("requirements", json.dumps([asdict(item) for item in before.required_rules], ensure_ascii=False, sort_keys=True), json.dumps([asdict(item) for item in after.required_rules], ensure_ascii=False, sort_keys=True)),
        ("preferences", json.dumps([asdict(item) for item in before.preferred_rules], ensure_ascii=False, sort_keys=True), json.dumps([asdict(item) for item in after.preferred_rules], ensure_ascii=False, sort_keys=True)),
        ("question_hash", before.question_hash or "", after.question_hash or ""),
    )
    return [
        {
            "change_type": f"{field}_changed",
            "field": field,
            "before_sha256": sha256(before_value.encode("utf-8")).hexdigest(),
            "after_sha256": sha256(after_value.encode("utf-8")).hexdigest(),
        }
        for field, before_value, after_value in fields
        if before_value != after_value
    ]


def _priority(
    eligibility_status: str | None,
    *,
    deadline_at: str | None,
    evaluation_time: str,
    role_match: bool = False,
    changed: bool = False,
) -> tuple[int, tuple[str, ...]]:
    score = {"eligible": 40, "eligible_with_gaps": 20, "manual_review": 5, None: 5}.get(eligibility_status, 0)
    reasons: list[str] = []
    if eligibility_status in {"eligible", "eligible_with_gaps", "manual_review"}:
        reasons.append(f"eligibility:{eligibility_status or 'manual_review'}")
    if deadline_at:
        try:
            days = (date.fromisoformat(deadline_at[:10]) - _parse_iso(evaluation_time).date()).days
            if 0 <= days <= 3:
                score += 20
                reasons.append("deadline_within_3_days")
            elif 0 <= days <= 7:
                score += 10
                reasons.append("deadline_within_7_days")
        except (ValueError, RegistryError):
            pass
    if role_match:
        score += 10
        reasons.append("role_keyword_match")
    if changed:
        score += 5
        reasons.append("posting_changed")
    return score, tuple(reasons)


class PostingRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.snapshots_dir = self.path.parent / "snapshots"
        self.events_path = self.path.parent / "events.jsonl"
        self.lock_path = self.path.parent / ".registry.lock"
        self.postings: dict[str, PostingRecord] = {}
        self.queue: dict[str, ReviewQueueItem] = {}

    @classmethod
    def load(cls, path: Path) -> "PostingRegistry":
        registry = cls(path)
        if not registry.path.exists():
            return registry
        payload = _read_json(registry.path)
        if not isinstance(payload, dict) or payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise RegistryError("unsupported registry schema version")
        raw_postings = payload.get("postings", [])
        raw_queue = payload.get("queue", [])
        if not isinstance(raw_postings, list) or not isinstance(raw_queue, list):
            raise RegistryError("registry postings and queue must be arrays")
        for item in raw_postings:
            posting = posting_record_from_dict(item)
            if posting.posting_id in registry.postings:
                raise RegistryError(f"duplicate posting_id in registry: {posting.posting_id}")
            registry.postings[posting.posting_id] = posting
        for item in raw_queue:
            queue_item = queue_item_from_dict(item)
            if queue_item.queue_id in registry.queue:
                raise RegistryError(f"duplicate queue_id in registry: {queue_item.queue_id}")
            registry.queue[queue_item.queue_id] = queue_item
        return registry

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "postings": [posting_record_to_dict(self.postings[key]) for key in sorted(self.postings)],
            "queue": [queue_item_to_dict(self.queue[key]) for key in sorted(self.queue)],
        }

    def save(self) -> None:
        with _registry_lock(self.lock_path):
            write_json(self.path, self._payload())

    def _event(self, event_type: str, *, occurred_at: str, source_id: str | None, posting_id: str | None, run_id: str | None, metadata: dict[str, Any] | None = None) -> RegistryEvent:
        event_key = "|".join((event_type, occurred_at, source_id or "", posting_id or "", run_id or ""))
        event = RegistryEvent(
            event_id="event-" + sha256(event_key.encode("utf-8")).hexdigest()[:24],
            event_type=event_type,
            occurred_at=occurred_at,
            source_id=source_id,
            posting_id=posting_id,
            run_id=run_id,
            metadata=metadata or {},
        )
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with _registry_lock(self.lock_path):
            if self.events_path.exists():
                for line in self.events_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        existing = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(existing, dict):
                        continue
                    if existing.get("event_id") == event.event_id:
                        return event
                    if (
                        run_id
                        and existing.get("run_id") == run_id
                        and existing.get("source_id") == source_id
                        and existing.get("posting_id") == posting_id
                        and existing.get("event_type") in {
                            "posting_added",
                            "posting_seen",
                            "posting_changed",
                            "posting_duplicate",
                        }
                        and event.event_type in {
                            "posting_added",
                            "posting_seen",
                            "posting_changed",
                            "posting_duplicate",
                        }
                    ):
                        return event
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
        return event

    def record_event(
        self,
        event_type: str,
        *,
        occurred_at: str,
        source_id: str | None,
        posting_id: str | None,
        run_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> RegistryEvent:
        return self._event(
            event_type,
            occurred_at=occurred_at,
            source_id=source_id,
            posting_id=posting_id,
            run_id=run_id,
            metadata=metadata,
        )

    def write_snapshot(self, posting_id: str, content: bytes, raw_sha256: str) -> Path:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", posting_id).strip("._")[:80] or "posting"
        path = self.snapshots_dir / f"{safe_id}-{raw_sha256}.bin"
        if path.exists():
            if path.read_bytes() != content:
                raise RegistryError(f"snapshot hash collision: {path.name}")
            return path
        try:
            with path.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise RegistryError(f"snapshot hash collision: {path.name}")
        return path

    def upsert(
        self,
        record: PostingRecord,
        *,
        evaluation_time: str,
        source_id: str | None = None,
        run_id: str | None = None,
        role_match: bool = False,
    ) -> tuple[str, PostingRecord, tuple[dict[str, str], ...]]:
        lifecycle, lifecycle_reason = posting_lifecycle_status(record, evaluation_time)
        current = replace(
            record,
            source_id=source_id or record.source_id,
            canonical_url=record.canonical_url or record.url,
            status=lifecycle,
            first_seen_at=record.first_seen_at or evaluation_time,
            last_seen_at=evaluation_time,
        )
        direct = self.postings.get(current.posting_id)
        if direct is None:
            direct = next(
                (item for item in self.postings.values() if (item.canonical_url or item.url) == (current.canonical_url or current.url)),
                None,
            )
        if direct is None:
            content_hash = current.normalized_content_sha256 or current.body_sha256
            duplicate = next(
                (item for item in self.postings.values() if (item.normalized_content_sha256 or item.body_sha256) == content_hash),
                None,
            )
            if duplicate is not None:
                alias = tuple(sorted(set((*duplicate.alias_urls, current.url))))
                self.postings[duplicate.posting_id] = replace(duplicate, alias_urls=alias, last_seen_at=evaluation_time)
                self._event("posting_duplicate", occurred_at=evaluation_time, source_id=source_id, posting_id=duplicate.posting_id, run_id=run_id, metadata={"classification": "content_duplicate"})
                self.save()
                return "content_duplicate", self.postings[duplicate.posting_id], ()
            self.postings[current.posting_id] = current
            new_event = lifecycle if lifecycle in {"expired", "closed"} else "new"
            self._event("posting_added", occurred_at=evaluation_time, source_id=source_id, posting_id=current.posting_id, run_id=run_id, metadata={"classification": new_event})
            self.save()
            return new_event, current, ()
        comparison = compare_postings(direct, current)
        if comparison.event in {"exact_duplicate", "unchanged"}:
            event = "expired" if lifecycle == "expired" else ("closed" if lifecycle == "closed" else "unchanged")
            merged = replace(direct, last_seen_at=evaluation_time, status=lifecycle, source_id=source_id or direct.source_id)
            self.postings[direct.posting_id] = merged
            self._event("posting_seen", occurred_at=evaluation_time, source_id=source_id, posting_id=direct.posting_id, run_id=run_id, metadata={"classification": event})
            self.save()
            return event, merged, ()
        changes = tuple(_change_metadata(direct, current))
        self.postings[direct.posting_id] = replace(
            current,
            posting_id=direct.posting_id,
            first_seen_at=direct.first_seen_at or evaluation_time,
            alias_urls=tuple(sorted(set((*direct.alias_urls, direct.url, current.url)))),
        )
        event = "changed"
        self._event("posting_changed", occurred_at=evaluation_time, source_id=source_id, posting_id=direct.posting_id, run_id=run_id, metadata={"changes": list(changes)})
        self.save()
        return event, self.postings[direct.posting_id], changes

    def create_queue_item(
        self,
        posting: PostingRecord,
        *,
        discovery_status: str,
        evaluation: EligibilityDecision | None,
        evaluation_time: str,
        source_id: str | None,
        role_match: bool = False,
        extra_reasons: tuple[DecisionReason, ...] = (),
    ) -> ReviewQueueItem | None:
        if discovery_status == "ineligible":
            return None
        if discovery_status not in DISCOVERY_EVENTS:
            raise RegistryError(f"unknown discovery status: {discovery_status}")
        eligibility_status = evaluation.status if evaluation else None
        if evaluation and evaluation.status == "ineligible":
            return None
        status_reasons = {
            "expired": DecisionReason("posting_expired", "deadline", "공고 마감일이 평가 시각보다 지났습니다."),
            "closed": DecisionReason("posting_closed", "posting", "공고가 모집 종료 상태로 표시되어 있습니다."),
            "content_duplicate": DecisionReason("content_duplicate", "posting", "다른 URL에서 같은 공고 본문이 발견되었습니다."),
            "changed": DecisionReason("posting_changed", "posting", "기존 공고의 의미 있는 내용이 변경되었습니다."),
            "manual_review": DecisionReason("posting_manual_review", "posting", "공고 상태를 자동으로 확정할 수 없습니다."),
        }
        reasons = tuple((*extra_reasons, *(evaluation.reasons if evaluation else ()), *(item for item in (status_reasons.get(discovery_status),) if item)))
        version_key = "|".join((posting.posting_id, posting.normalized_content_sha256 or posting.body_sha256, discovery_status, evaluation_time[:10]))
        queue_id = "queue-" + sha256(version_key.encode("utf-8")).hexdigest()[:24]
        existing = self.queue.get(queue_id)
        if existing is not None:
            return existing
        if discovery_status == "changed":
            for key, item in list(self.queue.items()):
                if item.posting_id == posting.posting_id and item.queue_status in {"pending", "approved", "deferred"}:
                    self.queue[key] = replace(item, queue_status="superseded", updated_at=evaluation_time)
        if discovery_status in {"expired", "closed"}:
            queue_status = "expired"
        else:
            queue_status = "pending"
        priority, priority_reasons = _priority(
            eligibility_status,
            deadline_at=posting.deadline_at,
            evaluation_time=evaluation_time,
            role_match=role_match,
            changed=discovery_status == "changed",
        )
        item = ReviewQueueItem(
            schema_version=1,
            queue_id=queue_id,
            posting_id=posting.posting_id,
            source_id=source_id,
            created_at=evaluation_time,
            updated_at=evaluation_time,
            priority=priority,
            priority_reasons=priority_reasons,
            queue_status=queue_status,
            discovery_status=discovery_status,
            eligibility_status=eligibility_status,
            human_review_required=True,
            reasons=reasons,
        )
        self.queue[queue_id] = item
        self._event("queue_created", occurred_at=evaluation_time, source_id=source_id, posting_id=posting.posting_id, run_id=None, metadata={"queue_id": queue_id, "priority": priority})
        self.save()
        return item

    def decide_queue(self, queue_id: str, decision: str, *, at: str) -> ReviewQueueItem:
        if decision not in {"approved", "rejected", "deferred"}:
            raise RegistryError("queue decision must be approved, rejected, or deferred")
        item = self.queue.get(queue_id)
        if item is None:
            raise RegistryError(f"queue item not found: {queue_id}")
        if item.queue_status in {"superseded", "expired"}:
            raise RegistryError("cannot decide a superseded or expired queue item")
        updated = replace(item, queue_status=decision, updated_at=at)
        self.queue[queue_id] = updated
        self._event("queue_decided", occurred_at=at, source_id=item.source_id, posting_id=item.posting_id, run_id=None, metadata={"queue_id": queue_id, "decision": decision})
        self.save()
        return updated


def queue_item_to_dict(item: ReviewQueueItem) -> dict[str, Any]:
    return asdict(item)


def queue_item_from_dict(value: Any) -> ReviewQueueItem:
    if not isinstance(value, dict):
        raise RegistryError("queue item: expected object")
    raw_reasons = value.get("reasons", [])
    reasons = tuple(
        DecisionReason(item.get("code", "unknown"), item.get("field"), item.get("message", ""))
        for item in raw_reasons
        if isinstance(item, dict)
    )
    item = ReviewQueueItem(
        schema_version=value.get("schema_version", 1),
        queue_id=value.get("queue_id", ""),
        posting_id=value.get("posting_id", ""),
        source_id=value.get("source_id"),
        created_at=value.get("created_at", ""),
        updated_at=value.get("updated_at", ""),
        priority=value.get("priority", 0),
        priority_reasons=tuple(value.get("priority_reasons", [])),
        queue_status=value.get("queue_status", "pending"),
        discovery_status=value.get("discovery_status", "manual_review"),
        eligibility_status=value.get("eligibility_status"),
        human_review_required=bool(value.get("human_review_required", True)),
        reasons=reasons,
    )
    if item.schema_version != 1 or item.queue_status not in QUEUE_STATUSES or not item.queue_id or not item.posting_id:
        raise RegistryError("invalid review queue item")
    return item
