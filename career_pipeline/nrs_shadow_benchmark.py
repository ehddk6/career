"""PRIVATE shadow benchmark helpers for Narrative Realization Search.

The module is intentionally dependency-light. In the real repository, callers
should pass the existing Narrative Compiler validator and Preference Writer
candidate-issue checker instead of duplicating those boundaries.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .narrative_realization_shadow import (
    POLICY_VERSION,
    NarrativeKernel,
    RealizationPlan,
    build_nrs_prompt,
    realization_diagnostics,
)

ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]
PayloadValidator = Callable[[Mapping[str, Any], Mapping[str, Any], str], dict[str, Any]]
ResponseBuilder = Callable[[Mapping[str, Any], Mapping[str, Any]], Any]
IssueChecker = Callable[[Any], Sequence[Any]]

SCHEMA_VERSION = 1
ARCHITECTURE = "nrs_shadow_benchmark_v1"


def _coerce(value: dict[str, Any] | str, stage: str) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError(f"invalid object at {stage}")
    return value


def _candidate_id(question_index: int, plan_id: str, answer: str) -> str:
    digest = sha256(
        f"{question_index}\0{plan_id}\0{answer}".encode("utf-8")
    ).hexdigest()[:12].upper()
    return "N" + digest


def generate_nrs_candidates(
    *,
    blueprint: Mapping[str, Any],
    packet: Mapping[str, Any],
    route: Mapping[str, Any],
    kernel: NarrativeKernel,
    plans: Sequence[RealizationPlan],
    runner: ModelRunner,
    model_id: str,
    timeout_ms: int,
    validate_payload: PayloadValidator,
    make_response: ResponseBuilder | None = None,
    candidate_issues: IssueChecker | None = None,
    prior_answers: Sequence[Mapping[str, Any]] = (),
    surface_preferences: Sequence[str] = (),
    semantic_preferences: Sequence[str] = (),
    anchor_texts: Sequence[str] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate NRS candidates using injected canonical validation callbacks."""
    valid: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen_answers: set[str] = set()

    for position, plan in enumerate(plans, start=1):
        stage = f"nrs_shadow_generate_q{blueprint['question_index']}_{position}"
        prompt = build_nrs_prompt(
            blueprint,
            packet,
            route,
            kernel,
            plan,
            prior_answers=prior_answers,
            surface_preferences=surface_preferences,
            semantic_preferences=semantic_preferences,
        )
        try:
            raw = _coerce(runner(stage, prompt, model_id, timeout_ms), stage)
            payload = validate_payload(raw, blueprint, stage)
        except Exception as error:  # validator-specific error types remain upstream
            failures.append({
                "stage": stage,
                "plan_id": plan.plan_id,
                "codes": ["payload_contract"],
                "message": str(error),
            })
            continue

        normalized = " ".join(str(payload["answer"]).split())
        if normalized in seen_answers:
            failures.append({
                "stage": stage,
                "plan_id": plan.plan_id,
                "codes": ["duplicate_realisation"],
            })
            continue
        seen_answers.add(normalized)

        if make_response is not None and candidate_issues is not None:
            response = make_response(payload, blueprint)
            issues = list(candidate_issues(response))
            if issues:
                failures.append({
                    "stage": stage,
                    "plan_id": plan.plan_id,
                    "codes": [str(getattr(item, "code", item)) for item in issues],
                })
                continue

        candidate_id = _candidate_id(
            int(blueprint["question_index"]), plan.plan_id, str(payload["answer"])
        )
        valid.append({
            "candidate_id": candidate_id,
            "plan_id": plan.plan_id,
            "family": plan.family,
            "payload": payload,
            "move_sequence": list(plan.move_sequence),
            "diagnostics": realization_diagnostics(
                str(payload["answer"]), anchor_texts=anchor_texts, plan=plan
            ),
        })
    return valid, failures


def blind_pair(
    *,
    question_index: int,
    baseline_answer: str,
    nrs_answer: str,
    salt: str = "",
) -> dict[str, Any]:
    """Return a deterministic, blinded human-comparison row.

    `source_by_label` belongs in PRIVATE machine metadata only. A rendered human
    packet must not expose it.
    """
    parity = int(
        sha256(f"{question_index}\0{salt}".encode("utf-8")).hexdigest()[-1], 16
    ) % 2
    if parity:
        answers = {"A": nrs_answer, "B": baseline_answer}
        source = {"A": "nrs", "B": "baseline"}
    else:
        answers = {"A": baseline_answer, "B": nrs_answer}
        source = {"A": "baseline", "B": "nrs"}
    return {
        "question_index": question_index,
        "answers": answers,
        "source_by_label": source,
        "human_review": {
            "preferred": None,
            "sounds_like_me": None,
            "more_specific_memorable": None,
            "more_natural_korean": None,
            "more_interview_speakable": None,
            "reject_both": None,
            "notes": None,
        },
    }


def render_blind_packet(rows: Sequence[Mapping[str, Any]]) -> str:
    """Render only A/B answers and null human fields; never reveal arm identity."""
    lines = [
        "# PRIVATE Blind Writer Preference Packet",
        "",
        "- baseline/NRS identity is intentionally hidden.",
        "- A/B order is deterministic-counterbalanced.",
        "- Human fields must be filled by a person only.",
        "",
    ]
    for row in rows:
        q = int(row["question_index"])
        answers = row["answers"]
        lines.extend([
            f"## Question {q}",
            "",
            "### A",
            str(answers["A"]),
            "",
            "### B",
            str(answers["B"]),
            "",
            "| field | human input |",
            "|---|---|",
            "| preferred |  |",
            "| sounds_like_me |  |",
            "| more_specific_memorable |  |",
            "| more_natural_korean |  |",
            "| more_interview_speakable |  |",
            "| reject_both |  |",
            "| notes |  |",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def build_private_report(
    *,
    question_index: int,
    kernel: NarrativeKernel,
    plans: Sequence[RealizationPlan],
    baseline_candidate_id: str,
    nrs_candidates: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "policy_version": POLICY_VERSION,
        "private": True,
        "decision_effect": "none_shadow_mode",
        "factual_authority_granted": False,
        "human_labels_performed": False,
        "question_index": question_index,
        "baseline_candidate_id": baseline_candidate_id,
        "kernel": asdict(kernel),
        "plans": [asdict(plan) for plan in plans],
        "nrs_candidates": [dict(item) for item in nrs_candidates],
        "candidate_failures": [dict(item) for item in failures],
    }


def write_private_artifacts(
    out_dir: Path,
    *,
    reports: Sequence[Mapping[str, Any]],
    blind_rows: Sequence[Mapping[str, Any]],
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    detail = out_dir / "nrs_shadow_benchmark.private.json"
    blind = out_dir / "NRS_HUMAN_PREFERENCE_blind.md"

    detail.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "architecture": ARCHITECTURE,
                "policy_version": POLICY_VERSION,
                "private": True,
                "human_labels_performed": False,
                "reports": [dict(item) for item in reports],
                "blind_pairs": [dict(item) for item in blind_rows],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    blind.write_text(render_blind_packet(blind_rows), encoding="utf-8")
    return detail, blind
