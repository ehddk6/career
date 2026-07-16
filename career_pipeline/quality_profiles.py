"""모델 비용과 품질 목표를 분리한 rigorous 실행 프로필."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


QualityProfileName = Literal[
    "fast",
    "balanced",
    "high_quality",
    "max_quality",
]


@dataclass(frozen=True)
class QualityProfile:
    name: QualityProfileName
    strategies: tuple[str, ...]
    judges: tuple[str, ...]
    max_selection_calls: int
    selection_mode: Literal["single", "rigorous"]
    candidate_repair_attempts: int = 0
    synthesis_repair_attempts: int = 0


QUALITY_PROFILES: dict[QualityProfileName, QualityProfile] = {
    "fast": QualityProfile(
        name="fast",
        strategies=(),
        judges=(),
        max_selection_calls=0,
        selection_mode="single",
    ),
    "balanced": QualityProfile(
        name="balanced",
        strategies=("FACT_QUESTION_SAFE", "JOB_COMPANY_FIT"),
        judges=("RECRUITER", "JOB_FACT_AUDITOR"),
        max_selection_calls=6,
        selection_mode="rigorous",
    ),
    "high_quality": QualityProfile(
        name="high_quality",
        strategies=(
            "FACT_FIRST",
            "QUESTION_FIRST",
            "EXPERIENCE_DIVERSITY",
            "JOB_COMPANY_FIT",
        ),
        judges=("RECRUITER", "JOB_FACT_AUDITOR", "KOREAN_EDITOR"),
        max_selection_calls=9,
        selection_mode="rigorous",
    ),
    "max_quality": QualityProfile(
        name="max_quality",
        strategies=(
            "FACT_FIRST",
            "EXPERIENCE_DIVERSITY",
            "JOB_COMPANY_FIT",
            "NATURAL_VOICE",
            "INTERVIEW_DEFENSE",
            "APPLICANT_DISTINCTIVENESS",
        ),
        judges=(
            "RECRUITER",
            "JOB_FACT_AUDITOR",
            "KOREAN_EDITOR",
            "INTERVIEW_COACH",
        ),
        # 후보 6 + 후보별 복구 최대 12 + 심사 4 + 최종 정제·복구 8 + 비교 1
        max_selection_calls=31,
        selection_mode="rigorous",
        candidate_repair_attempts=2,
        synthesis_repair_attempts=7,
    ),
}


def get_quality_profile(name: str) -> QualityProfile:
    try:
        return QUALITY_PROFILES[name]  # type: ignore[index]
    except KeyError as error:
        choices = ", ".join(QUALITY_PROFILES)
        raise ValueError(f"quality_profile must be one of: {choices}") from error


def legacy_rigorous_profile() -> QualityProfile:
    """기존 ``--selection-mode rigorous``의 호출 수와 후보 수를 보존한다."""
    return QUALITY_PROFILES["high_quality"]
