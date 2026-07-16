from __future__ import annotations

from career_pipeline.quality_profiles import QUALITY_PROFILES, get_quality_profile


def test_quality_profiles_have_bounded_cost_and_mandatory_rigorous_roles():
    assert get_quality_profile("fast").max_selection_calls == 0
    assert get_quality_profile("fast").selection_mode == "single"
    assert get_quality_profile("balanced").max_selection_calls == 6
    assert get_quality_profile("high_quality").max_selection_calls == 9
    maximum = get_quality_profile("max_quality")
    assert maximum.max_selection_calls == 31
    assert maximum.candidate_repair_attempts == 2
    assert maximum.synthesis_repair_attempts == 7
    assert "NATURAL_VOICE" in maximum.strategies
    assert "INTERVIEW_DEFENSE" in maximum.strategies
    assert "INTERVIEW_COACH" in maximum.judges


def test_quality_profiles_are_monotonic_in_candidates_judges_and_budget():
    ordered = [
        QUALITY_PROFILES[name]
        for name in ("fast", "balanced", "high_quality", "max_quality")
    ]
    assert [len(item.strategies) for item in ordered] == sorted(
        len(item.strategies) for item in ordered
    )
    assert [len(item.judges) for item in ordered] == sorted(
        len(item.judges) for item in ordered
    )
    assert [item.max_selection_calls for item in ordered] == sorted(
        item.max_selection_calls for item in ordered
    )
