import json
from pathlib import Path

from career_pipeline.interview_calibration import (
    CALIBRATION_PROFILE,
    calibrate_plan,
    calibrated_select_next_question,
    load_calibration,
    update_calibration,
)


def _plan():
    return {
        "question_bank": [
            {
                "question_id": "probe:causal",
                "family": "causality_probe",
                "standardized": False,
                "dimensions": ["causal_precision"],
                "target_nodes": ["n1"],
                "base_diagnostic_value": 1.0,
                "risk": 1.0,
                "difficulty": 3,
            },
            {
                "question_id": "probe:generic",
                "family": "generic_probe",
                "standardized": False,
                "dimensions": ["causal_precision"],
                "target_nodes": ["n2"],
                "base_diagnostic_value": 1.0,
                "risk": 1.0,
                "difficulty": 3,
            },
        ],
        "weakness_profile": {"dimensions": {}},
    }


def test_calibration_persists_only_aggregate_diagnostic_yield(tmp_path: Path):
    plan = _plan()
    evaluation = {
        "turns": [
            {
                "question_id": "probe:causal",
                "answer_excerpt": "SECRET_RAW_ANSWER",
                "deterministic": {"weak_dimensions": ["causal_precision"]},
                "semantic": {"aggregate_scores": {}},
            },
            {
                "question_id": "probe:generic",
                "answer_excerpt": "ANOTHER_SECRET",
                "deterministic": {"weak_dimensions": []},
                "semantic": {"aggregate_scores": {"causal_precision": 2.5}},
            },
        ]
    }
    path = update_calibration(tmp_path, plan, evaluation)
    text = path.read_text(encoding="utf-8")
    assert "SECRET_RAW_ANSWER" not in text
    assert "ANOTHER_SECRET" not in text
    profile = load_calibration(tmp_path)
    assert (
        profile["families"]["causality_probe"]["yield_ema"]
        > profile["families"]["generic_probe"]["yield_ema"]
    )
    assert profile["policy"]["stores_hiring_probability"] is False


def test_calibrated_selector_refines_prior_without_overriding_core(tmp_path: Path):
    plan = _plan()
    profile_path = tmp_path / CALIBRATION_PROFILE
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2026-08-17T00:00:00+00:00",
                "policy": {},
                "families": {
                    "causality_probe": {
                        "observations": 20,
                        "yield_ema": 0.9,
                        "dimensions": {
                            "causal_precision": {
                                "observations": 20,
                                "yield_ema": 0.9,
                            }
                        },
                    },
                    "generic_probe": {
                        "observations": 20,
                        "yield_ema": 0.1,
                        "dimensions": {
                            "causal_precision": {
                                "observations": 20,
                                "yield_ema": 0.1,
                            }
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    calibrated = calibrate_plan(plan, tmp_path)
    values = {
        row["question_id"]: row["base_diagnostic_value"]
        for row in calibrated["question_bank"]
    }
    assert values["probe:causal"] > values["probe:generic"]
    selected = calibrated_select_next_question(
        plan, {"turns": [], "weak_dimensions": []}, tmp_path
    )
    assert selected["question_id"] == "probe:causal"
    assert selected["selection_reason"] == "calibrated_expected_diagnostic_utility"

    with_core = dict(plan)
    with_core["question_bank"] = [
        {
            "question_id": "core:intro:60",
            "family": "core_intro",
            "standardized": True,
            "dimensions": ["directness"],
            "target_nodes": [],
            "base_diagnostic_value": 1.0,
            "risk": 1.0,
            "difficulty": 2,
        }
    ] + plan["question_bank"]
    core = calibrated_select_next_question(with_core, {"turns": []}, tmp_path)
    assert core["question_id"] == "core:intro:60"
    assert core["selection_reason"] == "standardized_backbone"
