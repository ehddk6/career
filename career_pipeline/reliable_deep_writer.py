"""Reliable final-prose selection for Deep Writer.

Uses Deep Writer's existing fixed score schema so schema-enforced model runners
remain compatible. Candidate order is swapped and a second rubric lens is used
only when needed. Unstable semantic evaluation never forces a semantic winner.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import deep_writer as dw
from .argument_search import SEMANTIC_DIMENSIONS, validate_judgement
from .narrative_compiler import NarrativeCompilerError, _to_response, _validate_generated_payload
from .preference_writer import _candidate_issues
from .reliable_judge import summarize_canonical_preferences
from .semantic_preference import (
    semantic_preference_directives,
    semantic_preference_weights,
)
from .style_diagnostics import diagnose_text
from .writing_preference import preference_directives, preference_distance

REPORT_JSON = "05_신뢰평가.json"


def _weighted_score(row: Mapping[str, Any], weights: Mapping[str, float]) -> float | None:
    if row.get("fatal_issue") is True:
        return None
    scores = row.get("scores", {})
    if not isinstance(scores, Mapping):
        return None
    total = 0.0
    weight_total = 0.0
    for dimension in SEMANTIC_DIMENSIONS:
        value = scores.get(dimension)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        weight = float(weights.get(dimension, 1.0))
        total += float(value) * weight
        weight_total += weight
    return total / weight_total if weight_total else None


def _preference_from_judgement(
    judgement: Sequence[Mapping[str, Any]],
    candidate_a: str,
    candidate_b: str,
    weights: Mapping[str, float],
    *,
    tie_delta: float = 0.18,
) -> str:
    by_id = {str(row.get("route_id")): row for row in judgement if isinstance(row, Mapping)}
    a = _weighted_score(by_id.get(candidate_a, {}), weights)
    b = _weighted_score(by_id.get(candidate_b, {}), weights)
    if a is None and b is None:
        return "ABSTAIN"
    if a is None:
        return "B"
    if b is None:
        return "A"
    if abs(a - b) <= tie_delta:
        return "TIE"
    return "A" if a > b else "B"


def _deterministic_fallback(valid: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    return min(
        valid,
        key=lambda row: (
            float(row.get("style_risk", 1_000_000)),
            float(row.get("surface_distance", 1_000_000)),
            str(row.get("candidate_id", "")),
        ),
    )


def _record_selection(run_dir: Path, row: Mapping[str, Any]) -> None:
    path = run_dir / REPORT_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = []
    if not isinstance(payload, list):
        payload = []
    question_index = row.get("question_index")
    payload = [
        item
        for item in payload
        if not (isinstance(item, Mapping) and item.get("question_index") == question_index)
    ]
    payload.append(dict(row))
    payload.sort(
        key=lambda item: int(item.get("question_index", 0)) if isinstance(item, Mapping) else 0
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reliable_generate_prose(
    run_dir: Path,
    state: Mapping[str, Any],
    packet: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    route: Mapping[str, Any],
    writer: str,
    judges: Sequence[str],
    timeout_ms: int,
    runner: dw.ModelRunner,
    calls: list[dict[str, Any]],
    surface_profile: Mapping[str, Any] | None,
    semantic_profile: Mapping[str, Any] | None,
    prior: Sequence[Mapping[str, Any]],
    schema_version: int,
    count: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for pos, mode in enumerate(dw.PROSE_MODES[:count], 1):
        stage = f"deep_prose_generate_q{blueprint['question_index']}_{pos}"
        raw = dw._coerce(
            runner(
                stage,
                dw._prose_prompt(
                    blueprint,
                    packet,
                    route,
                    mode,
                    preference_directives(surface_profile),
                    semantic_preference_directives(semantic_profile),
                    prior,
                ),
                writer,
                timeout_ms,
            ),
            stage,
        )
        calls.append({"stage": stage, "model_id": writer, "role": "route_bound_prose_writer"})
        try:
            payload = _validate_generated_payload(raw, blueprint, stage)
        except NarrativeCompilerError as error:
            failures.append({"stage": stage, "codes": ["payload_contract"], "message": str(error)})
            continue
        response = _to_response(payload, blueprint, ledger_schema_version=schema_version)
        issues = _candidate_issues(run_dir, state, response)
        if issues:
            failures.append({"stage": stage, "codes": [item.code for item in issues]})
            continue
        valid.append(
            {
                "candidate_id": dw._candidate_id(payload, mode[0]),
                "payload": payload,
                "mode": mode[0],
                "style_risk": diagnose_text(payload["answer"]).style_risk_score,
                "surface_distance": preference_distance(payload["answer"], surface_profile),
            }
        )
    if not valid:
        raise dw.DeepWriterError(
            f"all prose realisations failed for question {blueprint['question_index']}"
        )
    if len(valid) == 1:
        return valid[0]["payload"], failures
    if len(valid) != 2:
        chosen = _deterministic_fallback(valid)
        _record_selection(
            run_dir,
            {
                "question_index": int(blueprint["question_index"]),
                "protocol": "reliable_prose_selection_v1",
                "status": "evaluation_uncertain",
                "reason": "pairwise_protocol_requires_exactly_two_candidates",
                "selected_candidate_id": chosen["candidate_id"],
                "selection_source": "deterministic_fallback",
            },
        )
        return chosen["payload"], failures

    candidate_a, candidate_b = valid[0], valid[1]
    candidate_ids = {candidate_a["candidate_id"], candidate_b["candidate_id"]}
    weights = semantic_preference_weights(semantic_profile)
    base_directives = list(semantic_preference_directives(semantic_profile))
    variants = (
        (
            "evidence_first",
            "structured_reviewer",
            "Prioritize evidence defensibility, exact question fit, and causal/ownership boundaries.",
            base_directives,
        ),
        (
            "question_first",
            "skeptical_reviewer",
            "Prioritize directness to the question, replaceability test, then evidence defensibility.",
            list(reversed(base_directives)),
        ),
    )
    preference_rows: list[dict[str, Any]] = []
    for variant, role, lens, directives in variants:
        for model in judges:
            for orientation in ("AB", "BA"):
                order = valid if orientation == "AB" else list(reversed(valid))
                stage = (
                    f"deep_prose_judge_reliable_q{blueprint['question_index']}_"
                    f"{variant}_{orientation.lower()}_{model}"
                )
                prompt = lens + "\n" + dw._prose_judge_prompt(
                    blueprint, route, order, directives
                )
                raw = dw._coerce(runner(stage, prompt, model, timeout_ms), stage)
                judgement = validate_judgement(raw, candidate_ids)
                preference = _preference_from_judgement(
                    judgement,
                    candidate_a["candidate_id"],
                    candidate_b["candidate_id"],
                    weights,
                )
                preference_rows.append(
                    {
                        "model_id": model,
                        "rubric_variant": variant,
                        "role": role,
                        "orientation": orientation,
                        "canonical_preference": preference,
                    }
                )
                calls.append(
                    {
                        "stage": stage,
                        "model_id": model,
                        "role": role,
                        "orientation": orientation,
                        "selection_protocol": "reliable_prose_selection_v1",
                    }
                )
        summary = summarize_canonical_preferences(preference_rows)
        if summary.get("stable"):
            break

    summary = summarize_canonical_preferences(preference_rows)
    semantic_winner = summary.get("winner") if summary.get("stable") else None
    if semantic_winner == "A":
        chosen = candidate_a
        selection_source = "stable_semantic_pairwise"
    elif semantic_winner == "B":
        chosen = candidate_b
        selection_source = "stable_semantic_pairwise"
    else:
        chosen = _deterministic_fallback(valid)
        selection_source = "deterministic_fallback"

    report = {
        "question_index": int(blueprint["question_index"]),
        "protocol": "reliable_prose_selection_v1",
        "status": "decided" if semantic_winner else "evaluation_uncertain",
        "summary": summary,
        "candidate_ids": [candidate_a["candidate_id"], candidate_b["candidate_id"]],
        "selected_candidate_id": chosen["candidate_id"],
        "selection_source": selection_source,
        "semantic_winner": semantic_winner,
        "judgments": preference_rows,
        "factual_authority_granted": False,
    }
    _record_selection(run_dir, report)
    calls.append(
        {
            "stage": f"deep_prose_reliable_selection_q{blueprint['question_index']}",
            "role": "selection_protocol",
            "status": report["status"],
            "selected_candidate_id": chosen["candidate_id"],
            "selection_source": selection_source,
            "position_flip_rate": summary.get("position_flip_rate"),
        }
    )
    return chosen["payload"], failures
