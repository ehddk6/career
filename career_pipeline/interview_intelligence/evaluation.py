"""Deterministic and optional semantic evaluation for mock-interview turns."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from statistics import median
from typing import Any, Callable, Mapping, Sequence

from ..facts import METRIC, _normalize
from .questions import select_next_question
from .schema import (
    BEHAVIOR_ANCHORS, DIMENSIONS, DIMENSION_LABELS, SCHEMA_VERSION, WEAKNESS_PROFILE,
    InterviewIntelligenceError, _CAUSAL_VERBS, _BOUNDARY_CUES, _DECISION_CUES,
    _OWNERSHIP_CUES, _PRESSURE_CUES, _REFLECTION_CUES, _compact, _metric_values, _now, _read_json, _tokens,
)

ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]

def _allowed_metrics(plan: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for node in plan.get("claim_graph", {}).get("nodes", []):
        if isinstance(node, Mapping) and node.get("factual_authority") is True:
            result.update(str(value) for value in node.get("metric_values", []))
    return result


def _node_map(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("node_id")): dict(node)
        for node in plan.get("claim_graph", {}).get("nodes", [])
        if isinstance(node, Mapping) and node.get("node_id")
    }


def _bank_map(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("question_id")): dict(item)
        for item in plan.get("question_bank", [])
        if isinstance(item, Mapping) and item.get("question_id")
    }


def _deterministic_answer_check(
    answer: str,
    question: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    allowed_metrics: set[str],
    elapsed_seconds: float | None,
) -> dict[str, Any]:
    metrics = list(_metric_values(answer))
    target_nodes = [nodes[node_id] for node_id in question.get("target_nodes", []) if node_id in nodes]
    target_metric_values = {
        str(value)
        for node in target_nodes
        if node.get("factual_authority") is True
        for value in node.get("metric_values", [])
    }
    scoped_allowed_metrics = target_metric_values if question.get("target_nodes") else allowed_metrics
    unsupported = [value for value in metrics if value not in scoped_allowed_metrics]
    anchor_pool: set[str] = set()
    for node in target_nodes:
        anchor_pool.update(str(value).lower() for value in node.get("anchors", []))
    answer_tokens = _tokens(answer)
    anchor_hits = sorted(anchor_pool.intersection(answer_tokens))
    anchor_ratio = min(1.0, len(anchor_hits) / max(1, min(len(anchor_pool), 8))) if anchor_pool else 1.0
    dimensions = set(str(value) for value in question.get("dimensions", []))
    flags: list[str] = []
    weak_dimensions: set[str] = set()
    if unsupported:
        flags.append("unsupported_metric")
        weak_dimensions.update(("evidence_defensibility", "causal_precision"))
    if target_nodes and anchor_ratio < 0.25:
        flags.append("low_evidence_anchor_overlap")
        weak_dimensions.update(("evidence_defensibility", "specificity"))
    if "ownership_precision" in dimensions:
        ownership = any(cue in answer for cue in _OWNERSHIP_CUES)
        boundary = any(cue in answer for cue in _BOUNDARY_CUES)
        if not ownership:
            flags.append("ownership_not_explicit")
            weak_dimensions.add("ownership_precision")
        if not boundary:
            flags.append("team_boundary_not_explicit")
            weak_dimensions.add("ownership_precision")
        risky_nodes = [
            node for node in target_nodes
            if node.get("source_kind") == "applicant"
            and str(node.get("verification", {}).get("contribution")) in {"observed", "unknown"}
        ]
        if risky_nodes and any(verb in answer for verb in _CAUSAL_VERBS) and any(cue in answer for cue in _OWNERSHIP_CUES):
            flags.append("ownership_overclaim_risk")
            weak_dimensions.update(("ownership_precision", "causal_precision"))
    if "decision_visibility" in dimensions and not any(cue in answer for cue in _DECISION_CUES):
        flags.append("decision_basis_missing")
        weak_dimensions.add("decision_visibility")
    if "reflection_quality" in dimensions and not any(cue in answer for cue in _REFLECTION_CUES):
        flags.append("reflection_missing")
        weak_dimensions.add("reflection_quality")
    if "pressure_resilience" in dimensions and question.get("difficulty", 1) >= 4 and not any(cue in answer for cue in _PRESSURE_CUES):
        flags.append("boundary_language_missing_under_pressure")
        weak_dimensions.add("pressure_resilience")
    expected = question.get("expected_seconds")
    duration_status = "unknown"
    if elapsed_seconds is not None and isinstance(expected, (int, float)) and expected:
        ratio = float(elapsed_seconds) / float(expected)
        if ratio < 0.5:
            duration_status = "too_short"
            flags.append("response_too_short_for_target_time")
            weak_dimensions.add("communication_density")
        elif ratio > 1.6:
            duration_status = "too_long"
            flags.append("response_too_long_for_target_time")
            weak_dimensions.add("communication_density")
        else:
            duration_status = "within_range"
    text_length = len(re.sub(r"\s+", "", answer))
    if text_length < 35:
        flags.append("answer_content_too_thin")
        weak_dimensions.update(("specificity", "communication_density"))
    return {
        "metrics": metrics,
        "unsupported_metrics": unsupported,
        "anchor_hits": anchor_hits[:12],
        "anchor_ratio": round(anchor_ratio, 3),
        "text_length": text_length,
        "elapsed_seconds": elapsed_seconds,
        "duration_status": duration_status,
        "flags": list(dict.fromkeys(flags)),
        "weak_dimensions": sorted(weak_dimensions),
    }


def _semantic_context(question: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    bounded = []
    for node_id in question.get("target_nodes", []):
        node = nodes.get(str(node_id))
        if node is None:
            continue
        if node.get("source_kind") == "applicant":
            bounded.append(
                {
                    "node_id": node.get("node_id"),
                    "kind": "applicant",
                    "experience_id": node.get("experience_id"),
                    "claim_id": node.get("claim_id"),
                    "claim_field": node.get("claim_field"),
                    "claim_value": node.get("claim_value"),
                    "role": node.get("role"),
                    "situation": node.get("situation"),
                    "actions": node.get("actions"),
                    "outcomes": node.get("outcomes"),
                    "verification": node.get("verification"),
                }
            )
        else:
            bounded.append(
                {
                    "node_id": node.get("node_id"),
                    "kind": "research",
                    "claim_id": node.get("claim_id"),
                    "claim": node.get("claim"),
                    "claim_type": node.get("claim_type"),
                    "source_url": node.get("source_url"),
                    "checked_at": node.get("checked_at"),
                }
            )
    return {"question": dict(question), "authority_nodes": bounded}


def _judge_prompt(
    *,
    role: str,
    question: Mapping[str, Any],
    answer: str,
    deterministic: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
) -> str:
    dims = [str(value) for value in question.get("dimensions", []) if str(value) in DIMENSIONS]
    rubric = {
        dim: {
            "label": DIMENSION_LABELS[dim],
            "anchors": {str(level): description for level, description in BEHAVIOR_ANCHORS[dim].items()},
            "scale": "Use 0/2/4 anchors; 1 and 3 are justified intermediate judgments.",
        }
        for dim in dims
    }
    payload = {
        "role": role,
        "task": "Evaluate this mock-interview answer only against the bounded authority context and the answer itself.",
        "rules": [
            "Do not use outside knowledge.",
            "Do not estimate hiring probability or pass/fail probability.",
            "Do not reward facts absent from authority_nodes.",
            "Score only listed dimensions on 0-4.",
            "For every score provide a short evidence phrase or explicit absence reason from the answer.",
            "If deterministic.unsupported_metrics is non-empty, evidence_defensibility must be <=1 and causal_precision must be <=1 when scored.",
            "If the answer expands personal ownership beyond the authority contribution boundary, ownership_precision must be <=1.",
            "Return JSON only.",
        ],
        "rubric": rubric,
        "context": _semantic_context(question, nodes),
        "deterministic": deterministic,
        "answer": answer,
        "output_schema": {
            "scores": {dim: "integer 0..4" for dim in dims},
            "evidence": {dim: "short answer-grounded reason" for dim in dims},
            "risks": ["short diagnostic risk"],
            "probe_focus": ["dimension name"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _parse_json_response(value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise InterviewIntelligenceError("judge returned non-JSON value")
    text = value.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise InterviewIntelligenceError("judge JSON must be an object")
    return payload


def _run_semantic_judges(
    *,
    question: Mapping[str, Any],
    answer: str,
    deterministic: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    judge_model_ids: Sequence[str],
    runner: ModelRunner,
    timeout_ms: int,
) -> dict[str, Any]:
    roles = ("structured_interviewer", "skeptical_interviewer")
    judgments: list[dict[str, Any]] = []
    for model_id in judge_model_ids:
        for role in roles:
            raw = runner(
                f"interview_judge_{role}",
                _judge_prompt(
                    role=role,
                    question=question,
                    answer=answer,
                    deterministic=deterministic,
                    nodes=nodes,
                ),
                model_id,
                timeout_ms,
            )
            payload = _parse_json_response(raw)
            scores = payload.get("scores", {})
            if not isinstance(scores, Mapping):
                raise InterviewIntelligenceError("judge scores must be an object")
            clean: dict[str, int] = {}
            for dim in question.get("dimensions", []):
                if dim not in DIMENSIONS:
                    continue
                score = scores.get(dim)
                if not isinstance(score, (int, float)) or isinstance(score, bool):
                    raise InterviewIntelligenceError(f"judge missing numeric score for {dim}")
                clean[dim] = max(0, min(4, int(round(float(score)))))
            judgments.append(
                {
                    "model_id": model_id,
                    "role": role,
                    "scores": clean,
                    "evidence": payload.get("evidence", {}),
                    "risks": payload.get("risks", []),
                    "probe_focus": payload.get("probe_focus", []),
                }
            )
    aggregate: dict[str, float] = {}
    for dim in question.get("dimensions", []):
        values = [item["scores"][dim] for item in judgments if dim in item.get("scores", {})]
        if values:
            aggregate[dim] = round(float(median(values)), 2)
    if deterministic.get("unsupported_metrics"):
        if "evidence_defensibility" in aggregate:
            aggregate["evidence_defensibility"] = min(1.0, aggregate["evidence_defensibility"])
        if "causal_precision" in aggregate:
            aggregate["causal_precision"] = min(1.0, aggregate["causal_precision"])
    if "ownership_overclaim_risk" in deterministic.get("flags", []) and "ownership_precision" in aggregate:
        aggregate["ownership_precision"] = min(1.0, aggregate["ownership_precision"])
    return {
        "status": "scored",
        "judgments": judgments,
        "aggregate_scores": aggregate,
    }


def evaluate_transcript(
    plan: Mapping[str, Any],
    transcript: Sequence[Mapping[str, Any]],
    *,
    judge_model_ids: Sequence[str] = (),
    runner: ModelRunner | None = None,
    timeout_ms: int = 180_000,
) -> dict[str, Any]:
    bank = _bank_map(plan)
    nodes = _node_map(plan)
    allowed_metrics = _allowed_metrics(plan)
    turns: list[dict[str, Any]] = []
    weak_counter: Counter[str] = Counter()
    semantic_scores: dict[str, list[float]] = defaultdict(list)
    observed_dimensions: set[str] = set()
    for position, raw_turn in enumerate(transcript, 1):
        if not isinstance(raw_turn, Mapping):
            raise InterviewIntelligenceError(f"transcript[{position}] must be an object")
        qid = str(raw_turn.get("question_id", ""))
        answer = raw_turn.get("answer")
        if qid not in bank:
            raise InterviewIntelligenceError(f"transcript[{position}] unknown question_id: {qid}")
        if not isinstance(answer, str) or not answer.strip():
            raise InterviewIntelligenceError(f"transcript[{position}] answer is empty")
        elapsed = raw_turn.get("elapsed_seconds")
        if elapsed is not None and (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0):
            raise InterviewIntelligenceError(f"transcript[{position}] elapsed_seconds is invalid")
        question = bank[qid]
        observed_dimensions.update(
            str(dim) for dim in question.get("dimensions", []) if str(dim) in DIMENSIONS
        )
        deterministic = _deterministic_answer_check(
            answer.strip(), question, nodes, allowed_metrics, float(elapsed) if elapsed is not None else None
        )
        weak_counter.update(deterministic["weak_dimensions"])
        semantic = {"status": "not_run", "aggregate_scores": {}, "judgments": []}
        if judge_model_ids:
            if runner is None:
                raise InterviewIntelligenceError("runner is required when judge_model_ids are supplied")
            semantic = _run_semantic_judges(
                question=question,
                answer=answer.strip(),
                deterministic=deterministic,
                nodes=nodes,
                judge_model_ids=judge_model_ids,
                runner=runner,
                timeout_ms=timeout_ms,
            )
            for dim, score in semantic.get("aggregate_scores", {}).items():
                semantic_scores[str(dim)].append(float(score))
                if float(score) < 2.5:
                    weak_counter[str(dim)] += 2
        turns.append(
            {
                "turn": position,
                "question_id": qid,
                "family": question.get("family"),
                "answer_excerpt": _compact(answer.strip(), 240),
                "deterministic": deterministic,
                "semantic": semantic,
            }
        )
    dimension_summary = {
        dim: round(sum(values) / len(values), 2)
        for dim, values in semantic_scores.items()
        if values
    }
    weak_dimensions = [
        dim for dim, _ in sorted(weak_counter.items(), key=lambda item: (-item[1], item[0]))
    ]
    session_for_selection = {
        "turns": [{"question_id": turn["question_id"]} for turn in turns],
        "weak_dimensions": weak_dimensions,
    }
    next_question = select_next_question(plan, session_for_selection)
    flags = Counter(
        flag
        for turn in turns
        for flag in turn["deterministic"].get("flags", [])
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": "structured_adaptive_claim_defense_v1",
        "evaluated_at": _now(),
        "policy": {
            "semantic_judges_are_diagnostic_only": True,
            "deterministic_fact_gate_authoritative": True,
            "hiring_probability_estimation": False,
        },
        "turns": turns,
        "summary": {
            "turn_count": len(turns),
            "dimension_scores": dimension_summary,
            "observed_dimensions": sorted(observed_dimensions),
            "weak_dimensions": weak_dimensions,
            "weak_dimension_hits": dict(sorted(weak_counter.items())),
            "deterministic_flags": dict(sorted(flags.items())),
            "unsupported_metric_turns": sum(bool(turn["deterministic"].get("unsupported_metrics")) for turn in turns),
        },
        "next_question": next_question,
    }


def update_weakness_profile(root: Path, evaluation: Mapping[str, Any]) -> Path:
    root = root.resolve()
    path = root / WEAKNESS_PROFILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        payload = _read_json(path)
        profile = dict(payload) if isinstance(payload, Mapping) else {}
    else:
        profile = {}
    dimensions = dict(profile.get("dimensions", {})) if isinstance(profile.get("dimensions"), Mapping) else {}
    scores = evaluation.get("summary", {}).get("dimension_scores", {})
    if isinstance(scores, Mapping):
        for dim, value in scores.items():
            if dim not in DIMENSIONS or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            old = dimensions.get(dim, {}) if isinstance(dimensions.get(dim), Mapping) else {}
            observations = int(old.get("observations", 0)) + 1
            old_ema = old.get("ema_score")
            ema = float(value) if not isinstance(old_ema, (int, float)) else float(old_ema) * 0.65 + float(value) * 0.35
            dimensions[dim] = {
                "ema_score": round(ema, 3),
                "last_score": round(float(value), 3),
                "observations": observations,
            }
    summary = evaluation.get("summary", {}) if isinstance(evaluation.get("summary"), Mapping) else {}
    observed = set(str(dim) for dim in summary.get("observed_dimensions", []) if str(dim) in DIMENSIONS)
    weak_hits = summary.get("weak_dimension_hits", {})
    weak_hits = weak_hits if isinstance(weak_hits, Mapping) else {}
    for dim in observed:
        old = dimensions.get(dim, {}) if isinstance(dimensions.get(dim), Mapping) else {}
        hit_count = weak_hits.get(dim, 0)
        signal = min(1.0, max(0.0, float(hit_count) / 2.0)) if isinstance(hit_count, (int, float)) and not isinstance(hit_count, bool) else 0.0
        previous = old.get("weak_signal_ema")
        weak_ema = signal if not isinstance(previous, (int, float)) or isinstance(previous, bool) else float(previous) * 0.65 + signal * 0.35
        merged = dict(old)
        merged["weak_signal_ema"] = round(weak_ema, 3)
        merged["weak_signal_observations"] = int(old.get("weak_signal_observations", 0)) + 1
        dimensions[dim] = merged
    flags = Counter(profile.get("flags", {}) if isinstance(profile.get("flags"), Mapping) else {})
    new_flags = evaluation.get("summary", {}).get("deterministic_flags", {})
    if isinstance(new_flags, Mapping):
        for flag, count in new_flags.items():
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                flags[str(flag)] += count
    output = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "policy": {
            "stores_raw_answers": False,
            "stores_hiring_probability": False,
            "purpose": "cross-session mock-interview weakness prioritization only",
        },
        "dimensions": dimensions,
        "flags": dict(sorted(flags.items())),
    }
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
