"""Aggregate-only calibration for adaptive interview question selection.

This is not a hiring-probability model and not a psychometric information
function. It learns a conservative diagnostic-yield proxy from prior mock
interview turns: how often a question family/dimension produced an observable
weakness or a non-neutral bounded semantic signal. Raw answers are never stored.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

CALIBRATION_PROFILE = ".career_profile/interview_diagnostic_calibration.json"
RUN_ARTIFACT = "08_면접정보이득.json"
SCHEMA_VERSION = 1
PRIOR_YIELD = 0.5
PRIOR_STRENGTH = 4.0
EMA_ALPHA = 0.30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _empty_profile() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "policy": {
            "stores_raw_answers": False,
            "stores_hiring_probability": False,
            "quantity": "diagnostic_yield_proxy_not_psychometric_information",
        },
        "families": {},
    }


def load_calibration(root: Path | None) -> dict[str, Any]:
    if root is None:
        return _empty_profile()
    payload = _read(root.resolve() / CALIBRATION_PROFILE, {})
    if not isinstance(payload, Mapping) or int(payload.get("schema_version", 0) or 0) != SCHEMA_VERSION:
        return _empty_profile()
    result = _empty_profile()
    result.update(dict(payload))
    result["families"] = (
        dict(payload.get("families", {}))
        if isinstance(payload.get("families"), Mapping)
        else {}
    )
    return result


def _turn_dimension_signal(turn: Mapping[str, Any], dimension: str) -> float:
    deterministic = (
        turn.get("deterministic", {})
        if isinstance(turn.get("deterministic"), Mapping)
        else {}
    )
    weak = set(str(value) for value in deterministic.get("weak_dimensions", []) if str(value))
    if dimension in weak:
        return 1.0
    semantic = turn.get("semantic", {}) if isinstance(turn.get("semantic"), Mapping) else {}
    scores = (
        semantic.get("aggregate_scores", {})
        if isinstance(semantic.get("aggregate_scores"), Mapping)
        else {}
    )
    score = scores.get(dimension)
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        deviation = min(1.0, abs(float(score) - 2.5) / 1.5)
        return round(0.35 + 0.65 * deviation, 4)
    return 0.20


def update_calibration(root: Path, plan: Mapping[str, Any], evaluation: Mapping[str, Any]) -> Path:
    root = root.resolve()
    path = root / CALIBRATION_PROFILE
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = load_calibration(root)
    families = (
        dict(profile.get("families", {}))
        if isinstance(profile.get("families"), Mapping)
        else {}
    )
    bank = {
        str(item.get("question_id")): item
        for item in plan.get("question_bank", [])
        if isinstance(item, Mapping) and item.get("question_id")
    }
    for turn in evaluation.get("turns", []) or []:
        if not isinstance(turn, Mapping):
            continue
        question = bank.get(str(turn.get("question_id", "")), {})
        if not isinstance(question, Mapping) or question.get("standardized"):
            continue
        family = str(question.get("family", "unknown"))
        record = (
            dict(families.get(family, {}))
            if isinstance(families.get(family), Mapping)
            else {}
        )
        dimensions = (
            dict(record.get("dimensions", {}))
            if isinstance(record.get("dimensions"), Mapping)
            else {}
        )
        family_signals: list[float] = []
        for dimension in question.get("dimensions", []) or []:
            dimension = str(dimension)
            if not dimension:
                continue
            signal = _turn_dimension_signal(turn, dimension)
            old = (
                dimensions.get(dimension, {})
                if isinstance(dimensions.get(dimension), Mapping)
                else {}
            )
            observations = int(old.get("observations", 0)) + 1
            previous = old.get("yield_ema")
            ema = (
                signal
                if not isinstance(previous, (int, float)) or isinstance(previous, bool)
                else float(previous) * (1.0 - EMA_ALPHA) + signal * EMA_ALPHA
            )
            dimensions[dimension] = {
                "observations": observations,
                "yield_ema": round(ema, 4),
                "last_yield": round(signal, 4),
            }
            family_signals.append(signal)
        if family_signals:
            family_signal = sum(family_signals) / len(family_signals)
            observations = int(record.get("observations", 0)) + 1
            previous = record.get("yield_ema")
            ema = (
                family_signal
                if not isinstance(previous, (int, float)) or isinstance(previous, bool)
                else float(previous) * (1.0 - EMA_ALPHA) + family_signal * EMA_ALPHA
            )
            record.update(
                observations=observations,
                yield_ema=round(ema, 4),
                last_yield=round(family_signal, 4),
                dimensions=dimensions,
            )
            families[family] = record
    output = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "policy": _empty_profile()["policy"],
        "families": families,
    }
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _shrunk_yield(record: Mapping[str, Any] | None) -> float:
    if not isinstance(record, Mapping):
        return PRIOR_YIELD
    observations = max(0, int(record.get("observations", 0) or 0))
    estimate = record.get("yield_ema")
    if not isinstance(estimate, (int, float)) or isinstance(estimate, bool):
        return PRIOR_YIELD
    return (
        observations * float(estimate) + PRIOR_STRENGTH * PRIOR_YIELD
    ) / (observations + PRIOR_STRENGTH)


def _weakness_gap(plan: Mapping[str, Any], dimension: str) -> float:
    profile = (
        plan.get("weakness_profile", {})
        if isinstance(plan.get("weakness_profile"), Mapping)
        else {}
    )
    dimensions = (
        profile.get("dimensions", {})
        if isinstance(profile.get("dimensions"), Mapping)
        else {}
    )
    row = dimensions.get(dimension, {}) if isinstance(dimensions.get(dimension), Mapping) else {}
    gaps: list[float] = []
    score = row.get("ema_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        gaps.append(max(0.0, 4.0 - float(score)) / 4.0)
    weak_signal = row.get("weak_signal_ema")
    if isinstance(weak_signal, (int, float)) and not isinstance(weak_signal, bool):
        gaps.append(max(0.0, min(1.0, float(weak_signal))))
    return max(gaps, default=0.0)


def calibrate_plan(plan: Mapping[str, Any], root: Path | None) -> dict[str, Any]:
    from .interview_intelligence.questions import _recommended_sequence

    profile = load_calibration(root)
    families = (
        profile.get("families", {})
        if isinstance(profile.get("families"), Mapping)
        else {}
    )
    result = dict(plan)
    bank = []
    calibration_rows = []
    for raw in plan.get("question_bank", []) or []:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        if item.get("standardized"):
            bank.append(item)
            continue
        family = str(item.get("family", "unknown"))
        family_record = (
            families.get(family, {})
            if isinstance(families.get(family), Mapping)
            else {}
        )
        dim_records = (
            family_record.get("dimensions", {})
            if isinstance(family_record.get("dimensions"), Mapping)
            else {}
        )
        expected: list[tuple[float, float]] = []
        for dimension in item.get("dimensions", []) or []:
            dimension = str(dimension)
            specific = (
                dim_records.get(dimension, {})
                if isinstance(dim_records.get(dimension), Mapping)
                else {}
            )
            estimate = _shrunk_yield(specific) if specific else _shrunk_yield(family_record)
            gap = _weakness_gap(plan, dimension)
            expected.append((estimate, 0.5 + gap))
        expected_yield = (
            sum(value * weight for value, weight in expected)
            / sum(weight for _, weight in expected)
            if expected
            else _shrunk_yield(family_record)
        )
        prior = float(
            item.get("prior_base_diagnostic_value", item.get("base_diagnostic_value", 1.0))
        )
        bonus = max(-0.6, min(0.6, (expected_yield - PRIOR_YIELD) * 1.2))
        calibrated = max(0.1, prior + bonus)
        item["prior_base_diagnostic_value"] = prior
        item["base_diagnostic_value"] = round(calibrated, 4)
        item["calibrated_expected_diagnostic_yield"] = round(expected_yield, 4)
        item["calibration_observations"] = int(family_record.get("observations", 0) or 0)
        bank.append(item)
        calibration_rows.append(
            {
                "question_id": item.get("question_id"),
                "family": family,
                "prior_base_diagnostic_value": prior,
                "calibrated_base_diagnostic_value": round(calibrated, 4),
                "expected_diagnostic_yield": round(expected_yield, 4),
                "observations": int(family_record.get("observations", 0) or 0),
            }
        )
    result["question_bank"] = bank
    result["interview_calibration"] = {
        "schema_version": SCHEMA_VERSION,
        "profile_status": (
            "available"
            if any(
                isinstance(row, Mapping) and int(row.get("observations", 0) or 0) > 0
                for row in families.values()
            )
            else "prior_only"
        ),
        "profile_path": str(root.resolve() / CALIBRATION_PROFILE) if root is not None else None,
        "quantity": "diagnostic_yield_proxy_not_hiring_probability",
        "raw_answers_stored": False,
        "rows": calibration_rows,
    }
    result["recommended_sequence"] = _recommended_sequence(result)
    return result


def calibrated_select_next_question(
    plan: Mapping[str, Any],
    session: Mapping[str, Any] | None,
    root: Path | None,
) -> dict[str, Any] | None:
    from .interview_intelligence.questions import select_next_question

    calibrated = calibrate_plan(plan, root)
    result = select_next_question(calibrated, session)
    if result is not None and not result.get("standardized"):
        result = dict(result)
        result["selection_reason"] = "calibrated_expected_diagnostic_utility"
    return result


def write_calibration_artifact(
    run_dir: Path,
    plan: Mapping[str, Any],
    root: Path | None,
) -> tuple[Path, dict[str, Any]]:
    calibrated = calibrate_plan(plan, root)
    payload = calibrated.get("interview_calibration", {})
    path = run_dir.resolve() / RUN_ARTIFACT
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, calibrated
