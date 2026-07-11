"""자본 한도 추적기.

Patina/copyeditor 등 외부 API 호출 횟수와 비용 상한을 추적합니다.
한도를 초과하면 CostLimitExceeded 예외를 발생시켜 무한 루프나 과도한 호출을 방지합니다.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter


class CostLimitExceeded(Exception):
    """자본 한도 초과 시 발생."""

    def __init__(self, used: int, budget: int) -> None:
        super().__init__(f"cost limit exceeded: {used}/{budget}")
        self.used = used
        self.budget = budget


@dataclass
class CostTracker:
    """호출 횟수와 자본 한도를 추적합니다."""

    budget: int
    calls_by_backend: Counter = field(default_factory=Counter)
    max_postprocess_calls: int = 1
    max_stage_seconds: float | None = None
    events: list[dict] = field(default_factory=list)
    _postprocess_calls: int = 0

    @property
    def calls(self) -> int:
        return sum(self.calls_by_backend.values())

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.calls)

    def record_call(
        self,
        backend: str,
        *,
        stage: str | None = None,
        model_tier: str | None = None,
        model_id: str | None = None,
    ) -> None:
        if self.calls >= self.budget:
            raise CostLimitExceeded(self.calls, self.budget)
        if stage == "postprocess" and self._postprocess_calls >= self.max_postprocess_calls:
            raise CostLimitExceeded(self._postprocess_calls, self.max_postprocess_calls)
        self.calls_by_backend[backend] += 1
        if stage == "postprocess":
            self._postprocess_calls += 1
        self.events.append(
            {
                "stage": stage or backend,
                "call_count": self.calls,
                "model_tier": model_tier,
                "model_id": model_id,
                "started_at": datetime.now().isoformat(),
                "ended_at": None,
                "duration_seconds": None,
                "status": "started",
                "_started_perf": perf_counter(),
            }
        )

    def finish_call(self, *, status: str) -> bool:
        if not self.events:
            return True
        event = self.events[-1]
        if event["ended_at"] is not None:
            return event["status"] != "stage_timeout"
        started = event.pop("_started_perf", perf_counter())
        event["ended_at"] = datetime.now().isoformat()
        event["duration_seconds"] = round(max(0.0, perf_counter() - started), 4)
        exceeded = (
            self.max_stage_seconds is not None
            and event["duration_seconds"] > self.max_stage_seconds
        )
        event["status"] = "stage_timeout" if exceeded else status
        return not exceeded

    def set_last_status(self, status: str) -> None:
        if self.events:
            self.events[-1]["status"] = status

    def record_completed_call(
        self,
        backend: str,
        *,
        stage: str | None = None,
        model_tier: str | None = None,
        model_id: str | None = None,
        status: str = "complete",
    ) -> None:
        self.record_call(
            backend,
            stage=stage,
            model_tier=model_tier,
            model_id=model_id,
        )
        self.finish_call(status=status)

    def summary(self) -> dict:
        return {
            **dict(self.calls_by_backend),
            "total": self.calls,
            "budget": self.budget,
        }

    def to_dict(self) -> dict:
        return {
            "budget": self.budget,
            "max_model_calls": self.budget,
            "calls": dict(self.calls_by_backend),
            "total": self.calls,
            "remaining": self.remaining,
            "max_postprocess_calls": self.max_postprocess_calls,
            "events": list(self.events),
        }

