from types import SimpleNamespace

from career_pipeline.model_policy import choose_tier


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
