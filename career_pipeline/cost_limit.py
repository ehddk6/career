"""자본 한도 추적기.

Patina/copyeditor 등 외부 API 호출 횟수와 비용 상한을 추적합니다.
한도를 초과하면 CostLimitExceeded 예외를 발생시켜 무한 루프나 과도한 호출을 방지합니다.
"""

from collections import Counter
from dataclasses import dataclass, field


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

    @property
    def calls(self) -> int:
        return sum(self.calls_by_backend.values())

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.calls)

    def record_call(self, backend: str) -> None:
        if self.calls >= self.budget:
            raise CostLimitExceeded(self.calls, self.budget)
        self.calls_by_backend[backend] += 1

    def summary(self) -> dict:
        return {
            **dict(self.calls_by_backend),
            "total": self.calls,
            "budget": self.budget,
        }

    def to_dict(self) -> dict:
        return {
            "budget": self.budget,
            "calls": dict(self.calls_by_backend),
            "remaining": self.remaining,
        }

