"""Luna·Terra·Sol 논리 tier와 실제 모델 ID 매핑."""

from dataclasses import dataclass
import os
from typing import Literal


ModelTier = Literal["luna", "terra", "sol"]
MODEL_ENV = {
    "luna": "CAREER_MODEL_LUNA",
    "terra": "CAREER_MODEL_TERRA",
    "sol": "CAREER_MODEL_SOL",
}


@dataclass(frozen=True)
class ModelConfig:
    tier: ModelTier
    model_id: str | None


def resolve_model(tier: ModelTier) -> ModelConfig:
    return ModelConfig(tier=tier, model_id=os.environ.get(MODEL_ENV[tier]) or None)


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
    }
    tier: ModelTier = "terra" if reasons.intersection(structural) else "luna"
    return resolve_model(tier)
