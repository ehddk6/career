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
import re
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

SCHEMA_VERSION = 2
ARCHITECTURE = "nrs_shadow_benchmark_v2"
_METRIC_VALUE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:조\s*원|억\s*원|천만\s*원|만\s*원|원|건|명|%|페이지|쪽|회|개|시간|분|일|주|개월|년)"
)


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


def _metric_signatures(text: str) -> set[str]:
    return {
        re.sub(r"[\s,]", "", match.group(0))
        for match in _METRIC_VALUE.finditer(str(text))
    }


def _selected_metric_signatures(
    blueprint: Mapping[str, Any], *, required_only: bool = False
) -> set[str]:
    experience = blueprint.get("experience")
    if not isinstance(experience, Mapping):
        return set()
    required_ids = {
        str(value)
        for value in experience.get("required_metric_claim_ids", []) or []
    }
    signatures: set[str] = set()
    for claim in experience.get("selected_claims", []) or []:
        if not isinstance(claim, Mapping) or claim.get("is_metric") is not True:
            continue
        if required_only and str(claim.get("claim_id", "")) not in required_ids:
            continue
        signatures.update(_metric_signatures(str(claim.get("normalized_value", ""))))
    return signatures


def missing_selected_metric(blueprint: Mapping[str, Any], answer: str) -> bool:
    """Return true when the selected metric contract vanished from the prose."""
    experience = blueprint.get("experience")
    required_ids = (
        experience.get("required_metric_claim_ids", [])
        if isinstance(experience, Mapping)
        else []
    )
    selected = _selected_metric_signatures(
        blueprint, required_only=bool(required_ids)
    )
    rendered = _metric_signatures(answer)
    if required_ids:
        return bool(selected - rendered)
    return bool(selected and not rendered.intersection(selected))


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
    genre_issues: Callable[[str], Sequence[Any]] | None = None,
    prior_answers: Sequence[Mapping[str, Any]] = (),
    surface_preferences: Sequence[str] = (),
    semantic_preferences: Sequence[str] = (),
    anchor_texts: Sequence[str] = (),
    stage_prefix: str = "nrs_shadow_generate",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate NRS candidates using injected canonical validation callbacks."""
    valid: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen_answers: set[str] = set()
    character_plan = blueprint.get("character_plan")
    if not isinstance(character_plan, Mapping):
        character_plan = {}
    quality_minimum = character_plan.get("quality_minimum")
    hard_maximum = character_plan.get("hard_maximum")
    length_repair = ""
    if isinstance(quality_minimum, int) and isinstance(hard_maximum, int):
        length_repair = (
            f" 공백 포함 {quality_minimum}자 이상 {hard_maximum}자 이하를 지키고, "
            "문장을 불필요하게 줄이지 마십시오."
        )

    for position, plan in enumerate(plans, start=1):
        base_stage = f"{stage_prefix}_q{blueprint['question_index']}_{position}"
        base_prompt = build_nrs_prompt(
            blueprint,
            packet,
            route,
            kernel,
            plan,
            prior_answers=prior_answers,
            surface_preferences=surface_preferences,
            semantic_preferences=semantic_preferences,
        )
        payload: dict[str, Any] | None = None
        for attempt in range(1, 3):
            stage = base_stage if attempt == 1 else f"{base_stage}_repair"
            repair = ""
            if attempt > 1:
                repair = (
                    "\n이전 문안은 기준을 충족하지 못했습니다. 제공된 사실과 일치하는 주어와 동사로 "
                    "다시 쓰십시오. 본인이 직접 한 행동은 분석·정리·제안처럼 근거에 있는 행동으로 쓰고, "
                    "운영상 변화는 이후 확인된 변화로 별도 문장에 표현하십시오. "
                    "선택한 과거 경험을 쓴다면 allowed_facts의 허용 사실 한 가지를 본문에 정확히 포함하십시오. "
                    "required_metric_claim_ids가 있으면 해당 수치를 모두, 없으면 selected_claims의 is_metric=true 수치 중 한 개를 본문에 표기 그대로 포함하십시오. "
                    "수치·기간은 allowed_facts의 selected_claims가 직접 허용하는 값만 남기고, "
                    "그 밖의 수치는 문장에서 삭제하십시오. 이전 기관명은 confirmed experience excerpt에 "
                    "그대로 확인되는 경우에만 쓰고, 확신할 수 없으면 기관명 없이 경험을 설명하십시오. "
                    + length_repair + " "
                    "질문에 바로 답하는 자연스러운 자기소개서 문단만 반환하십시오."
                )
            try:
                raw = _coerce(runner(stage, base_prompt + repair, model_id, timeout_ms), stage)
                candidate_payload = validate_payload(raw, blueprint, stage)
            except Exception as error:  # validator-specific error types remain upstream
                if attempt == 2:
                    failures.append({
                        "stage": stage,
                        "plan_id": plan.plan_id,
                        "codes": ["payload_contract"],
                        "message": str(error),
                    })
                continue

            normalized = " ".join(str(candidate_payload["answer"]).split())
            if normalized in seen_answers:
                if attempt == 2:
                    failures.append({
                        "stage": stage,
                        "plan_id": plan.plan_id,
                        "codes": ["duplicate_realisation"],
                    })
                continue

            issues: list[Any] = []
            if make_response is not None and candidate_issues is not None:
                response = make_response(candidate_payload, blueprint)
                issues.extend(candidate_issues(response))
            if genre_issues is not None:
                issues.extend(genre_issues(str(candidate_payload["answer"])))
            if missing_selected_metric(
                blueprint, str(candidate_payload["answer"])
            ):
                issues.append("missing_selected_metric")
            if issues:
                if attempt == 2:
                    failures.append({
                        "stage": stage,
                        "plan_id": plan.plan_id,
                        "codes": [str(getattr(item, "code", item)) for item in issues],
                    })
                continue
            payload = candidate_payload
            seen_answers.add(normalized)
            break

        if payload is None:
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


def _selection_prompt(
    *,
    question: str,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    packet = [
        {"candidate_id": item["candidate_id"], "answer": item["payload"]["answer"]}
        for item in candidates
    ]
    return (
        "Role:\n한국어 자기소개서 편집 심사자입니다.\n\n"
        "# Goal\n같은 문항의 후보 중 실제 지원자가 제출하고 면접에서 말하기에 가장 좋은 문안을 순위화합니다.\n\n"
        "# Success Criteria\n"
        "- 질문에 직접 답하는지, 한국어가 자연스러운지, 행동과 결과가 구체적인지 평가합니다.\n"
        "- 설명·감상문 없이 후보의 문안 자체만 비교합니다.\n\n"
        "# Constraints\n후보의 순서, ID, 작성 경로에서 우열을 추정하지 않습니다.\n\n"
        "# Output\n모든 candidate_id를 한 번씩 포함한 JSON {\"ranking\":[{\"candidate_id\":...,\"rank\":1}]}만 반환합니다.\n\n"
        "<question>\n" + question + "\n</question>\n<candidates>\n"
        + json.dumps(packet, ensure_ascii=False)
        + "\n</candidates>"
    )


def _validated_ranking(raw: dict[str, Any] | str, candidate_ids: set[str], stage: str) -> list[str]:
    payload = _coerce(raw, stage)
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or len(ranking) != len(candidate_ids):
        raise ValueError("selection ranking must include every candidate exactly once")
    rows: list[tuple[int, str]] = []
    for item in ranking:
        if not isinstance(item, Mapping):
            raise ValueError("selection ranking item must be object")
        candidate_id = str(item.get("candidate_id", ""))
        rank = item.get("rank")
        if candidate_id not in candidate_ids or isinstance(rank, bool) or not isinstance(rank, int):
            raise ValueError("selection ranking has invalid candidate or rank")
        rows.append((rank, candidate_id))
    if {candidate_id for _, candidate_id in rows} != candidate_ids:
        raise ValueError("selection ranking candidate IDs must be unique")
    if {rank for rank, _ in rows} != set(range(1, len(candidate_ids) + 1)):
        raise ValueError("selection ranks must be consecutive")
    return [candidate_id for _, candidate_id in sorted(rows)]


def select_blind_candidate(
    *,
    blueprint: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    runner: ModelRunner,
    model_id: str,
    timeout_ms: int,
    stage_prefix: str = "nrs_shadow_candidate_select",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Choose a candidate through counterbalanced, arm-blind ranking.

    No candidate is selected merely because it was generated first.  The same
    judge sees the identical candidate set in forward and reverse order; the
    persisted record makes that selection auditable without exposing an arm in
    the human comparison packet.
    """
    if not candidates:
        raise ValueError("cannot select from zero candidates")
    if len(candidates) == 1:
        return dict(candidates[0]), {
            "method": "single_valid_candidate",
            "rounds": [],
            "selected_candidate_id": candidates[0]["candidate_id"],
        }

    ordered = [dict(item) for item in candidates]
    rounds = [ordered, list(reversed(ordered))]
    scores = {str(item["candidate_id"]): 0 for item in ordered}
    evidence: list[dict[str, Any]] = []
    for round_index, presented in enumerate(rounds, start=1):
        stage = f"{stage_prefix}_q{blueprint['question_index']}_{round_index}"
        ranking = _validated_ranking(
            runner(stage, _selection_prompt(question=str(blueprint.get("prompt", "")), candidates=presented), model_id, timeout_ms),
            set(scores),
            stage,
        )
        for rank, candidate_id in enumerate(ranking, start=1):
            scores[candidate_id] += len(ordered) - rank + 1
        evidence.append({"stage": stage, "presented_candidate_ids": [item["candidate_id"] for item in presented], "ranking": ranking})

    winner_id = sorted(scores, key=lambda candidate_id: (-scores[candidate_id], candidate_id))[0]
    selected = next(item for item in ordered if item["candidate_id"] == winner_id)
    return selected, {
        "method": "counterbalanced_blind_rank_v1",
        "rounds": evidence,
        "scores": scores,
        "selected_candidate_id": winner_id,
    }


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
            "more_natural_korean": None,
            "question_fit": None,
            "more_interview_speakable": None,
            "reject_both": None,
            "notes": None,
        },
    }


def render_blind_packet(rows: Sequence[Mapping[str, Any]]) -> str:
    """Render blinded A/B answers with the prompt required for fit review."""
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
        question = str(row.get("question", "")).strip()
        lines.extend([
            f"## Question {q}",
            "",
            "### Question prompt",
            question or "문항 원문이 제공되지 않았습니다. `question_fit`은 평가하지 마십시오.",
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
            "| more_natural_korean |  |",
            "| question_fit |  |",
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
