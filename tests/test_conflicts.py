from career_pipeline.conflicts import (
    apply_overrides,
    conflict_override_key,
    detect_conflicts,
    override_key,
)
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


def test_unrelated_metrics_with_only_generic_tokens_do_not_conflict():
    left = FactClaim(
        "a.docx",
        0,
        "외주 시스템 검증으로 예산 1억원을 줄임",
        "budget_savings",
        "1억원",
        "100000000원",
        "money",
        frozenset({"예산", "검증", "업무", "외주", "시스템"}),
    )
    right = FactClaim(
        "b.docx",
        0,
        "숙박비 검증으로 예산 4천만원을 줄임",
        "budget_savings",
        "4천만원",
        "40000000원",
        "money",
        frozenset({"예산", "검증", "업무", "숙박비", "고시원"}),
    )

    assert detect_conflicts([left, right]) == []


def test_multiple_measurements_inside_one_source_are_not_conflicts():
    claims = [
        claim("same.docx", "2100000원", "money", "월 숙박비 210만원"),
        claim("same.docx", "12000000원", "money", "총 숙박비 1200만원 절감"),
    ]

    assert detect_conflicts(claims) == []


def test_cluster_requires_similarity_to_the_whole_experience_group():
    left = claim("a.docx", "40000000원", "money", "숙박비 예산 4천만원 절감")
    bridge = FactClaim(
        "b.docx",
        0,
        "숙박비와 시스템 예산",
        "budget_savings",
        "50000000원",
        "50000000원",
        "money",
        frozenset({"서울시청", "숙박비", "의료인력", "시스템", "외주"}),
    )
    unrelated = FactClaim(
        "c.docx",
        0,
        "외주 시스템 예산",
        "budget_savings",
        "100000000원",
        "100000000원",
        "money",
        frozenset({"시스템", "외주", "계약", "유지보수"}),
    )

    conflicts = detect_conflicts([left, bridge, unrelated])

    assert all(2 not in conflict.claim_indexes for conflict in conflicts)


def test_group_override_resolves_claims_with_different_extra_tokens():
    claims = [
        claim("a.docx", "40000000원", "money", "서울시청 숙박비 4천만원 절감"),
        FactClaim(
            "b.docx",
            0,
            "의료인력 숙박비 1억원 방지",
            "budget_savings",
            "1억원",
            "100000000원",
            "money",
            frozenset({"서울시청", "숙박비", "의료인력", "부정수급", "영수증"}),
        ),
    ]
    conflict = detect_conflicts(claims)[0]
    key = conflict_override_key(conflict, claims)

    resolved = apply_overrides(claims, {key: "40000000원"})

    assert [item.normalized_value for item in resolved] == ["40000000원"]
