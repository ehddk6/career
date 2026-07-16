"""Luna·Terra·Sol 논리 tier와 실제 모델 ID 매핑."""

from dataclasses import dataclass
import os
from typing import Literal


ModelTier = Literal["luna", "terra", "sol"]
ModelRole = Literal["generation", "judge", "synthesis", "comparison"]
MODEL_ENV = {
    "luna": "CAREER_MODEL_LUNA",
    "terra": "CAREER_MODEL_TERRA",
    "sol": "CAREER_MODEL_SOL",
}
ROLE_ENV = {
    "generation": "CAREER_MODEL_GENERATION",
    "judge": "CAREER_MODEL_JUDGE",
    "synthesis": "CAREER_MODEL_SYNTHESIS",
    "comparison": "CAREER_MODEL_COMPARISON",
}


@dataclass(frozen=True)
class ModelConfig:
    tier: ModelTier
    model_id: str | None


@dataclass(frozen=True)
class RoleModelConfig:
    role: ModelRole
    model_id: str | None
    source: str


def resolve_model(tier: ModelTier) -> ModelConfig:
    return ModelConfig(tier=tier, model_id=os.environ.get(MODEL_ENV[tier]) or None)


def resolve_role_model(
    role: ModelRole, *, fallback_tier: ModelTier = "sol"
) -> RoleModelConfig:
    """단계 역할별 모델을 읽고 기존 tier 설정을 호환 fallback으로 사용한다."""
    role_model = os.environ.get(ROLE_ENV[role]) or None
    if role_model:
        return RoleModelConfig(role=role, model_id=role_model, source=ROLE_ENV[role])
    fallback = resolve_model(fallback_tier)
    return RoleModelConfig(
        role=role,
        model_id=fallback.model_id,
        source=MODEL_ENV[fallback_tier],
    )


def choose_tier(diagnostics, requested: ModelTier | None = None) -> ModelConfig:
    if requested is not None:
        return resolve_model(requested)
    reasons = {
        reason
        for item in diagnostics
        for reason in item.style_reasons
    }
    structural = {
        "같은 문장 시작 표현 반복",
        "문장 길이 분산이 지나치게 낮음",
        "문항 간 표현 중복",
        "피동 표현 과다",
        "'할 수 있습니다' 반복",
        "긴 관형절이 겹친 문장",
        "같은 의미의 문장 반복",
        "과도한 목록 구성",
    }
    has_structural_risk = bool(reasons.intersection(structural)) or any(
        reason.startswith("연결어 반복:") for reason in reasons
    )
    tier: ModelTier = "terra" if has_structural_risk else "luna"
    return resolve_model(tier)
