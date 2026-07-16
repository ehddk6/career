from types import SimpleNamespace

from career_pipeline.model_policy import choose_tier, resolve_role_model


def diagnostic(*reasons: str):
    return SimpleNamespace(style_reasons=reasons)


def test_structural_style_reasons_select_terra():
    result = choose_tier([diagnostic("'할 수 있습니다' 반복")])

    assert result.tier == "terra"


def test_connector_repetition_selects_terra():
    result = choose_tier([diagnostic("연결어 반복: 또한")])

    assert result.tier == "terra"


def test_lexical_cliche_keeps_luna_default():
    result = choose_tier([diagnostic("결론형 상투어 반복")])

    assert result.tier == "luna"


def test_role_model_prefers_role_specific_env(monkeypatch):
    monkeypatch.setenv("CAREER_MODEL_SOL", "fallback-model")
    monkeypatch.setenv("CAREER_MODEL_JUDGE", "judge-model")

    result = resolve_role_model("judge")

    assert result.model_id == "judge-model"
    assert result.source == "CAREER_MODEL_JUDGE"


def test_role_model_falls_back_to_legacy_tier(monkeypatch):
    monkeypatch.delenv("CAREER_MODEL_GENERATION", raising=False)
    monkeypatch.setenv("CAREER_MODEL_SOL", "legacy-quality-model")

    result = resolve_role_model("generation")

    assert result.model_id == "legacy-quality-model"
    assert result.source == "CAREER_MODEL_SOL"
