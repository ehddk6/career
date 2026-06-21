from career_pipeline.conflicts import apply_overrides, detect_conflicts, override_key
from career_pipeline.models import FactClaim


TOKENS = frozenset({"서울시청", "숙박비", "의료인력", "검증", "예산"})


def claim(path: str, value: str, unit: str, context: str) -> FactClaim:
    return FactClaim(
        path,
        0,
        context,
        "budget_savings",
        value,
        value,
        unit,
        TOKENS,
    )


def test_detects_same_experience_with_different_savings_values():
    claims = [
        claim(
            "a.docx",
            "40000000원",
            "money",
            "서울시청 의료인력 숙박비 검증으로 예산 4천만원 절감",
        ),
        claim(
            "b.docx",
            "100000000원",
            "money",
            "서울시청 의료인력 숙박비 검증으로 예산 1억 원 방지",
        ),
        claim(
            "c.docx",
            "40%",
            "percentage",
            "서울시청 의료인력 숙박비 검증으로 예산 40% 절감",
        ),
    ]

    conflicts = detect_conflicts(claims)

    assert len(conflicts) == 1
    assert set(conflicts[0].values) == {"40000000원", "100000000원", "40%"}


def test_explicit_override_keeps_only_the_confirmed_value():
    claims = [
        claim("a.docx", "40000000원", "money", "서울시청 숙박비 예산 4천만원 절감"),
        claim("b.docx", "100000000원", "money", "서울시청 숙박비 예산 1억원 절감"),
    ]
    overrides = {override_key(claims[0]): "40000000원"}

    resolved = apply_overrides(claims, overrides)

    assert [item.normalized_value for item in resolved] == ["40000000원"]
