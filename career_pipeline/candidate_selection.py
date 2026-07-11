"""Patina/copyeditor 후보 생성 및 선택. 점수 게이팅과 의미 보존을 통해 최적 후보를 선택합니다."""
from dataclasses import asdict
from pathlib import Path
import re
from typing import Callable

from .character_count import count_characters
from .models import DraftResponse, Question
from .patina_adapter import (
    HumanizationResult,
    PatinaScoreResult,
    humanize_text,
)
from .quality import MINIMUM_FILL_RATIO, score_answer_quality


Rewriter = Callable[..., HumanizationResult]
Scorer = Callable[..., PatinaScoreResult]
PATINA_HEADROOM_RATIO = 0.92
VARIANTS = (
    ("original", None, None),
    ("formal", "formal", "professional"),
    ("narrative", "narrative", "narrative"),
)


def generate_and_select_candidates(
    responses: list[DraftResponse],
    questions: list[Question],
    target_org: str,
    *,
    job_terms: tuple[str, ...] = (),
    backend: str = "codex-cli",
    timeout_ms: int = 180_000,
    voice_sample: Path | None = None,
    max_retries: int = 1,
    scorer: Scorer | None = None,
    ai_score_threshold: int = 30,
    conditional_rewrite: bool = False,
    rewriter: Rewriter = humanize_text,
) -> tuple[list[DraftResponse], list[dict[str, object]]]:
    question_by_index = {question.index: question for question in questions}
    selected: list[DraftResponse] = []
    reports: list[dict[str, object]] = []
    peer_answers: list[str] = []
    for response in responses:
        question = question_by_index[response.question_index]
        input_length = count_characters(response.answer, question.count_mode)
        input_fill_ratio = (
            input_length / question.character_limit
            if question.character_limit
            else 0.0
        )
        protected_terms = tuple(
            dict.fromkeys(
                term
                for term in (
                    target_org,
                    *re.findall(r"[가-힣A-Za-z0-9]+", target_org),
                    *job_terms,
                )
                if len(term) >= 2 and term in response.answer
            )
        )
        pre_score: PatinaScoreResult | None = None
        if conditional_rewrite and scorer is not None:
            pre_score = scorer(
                response.answer,
                threshold=ai_score_threshold,
                backend=backend,
                timeout_ms=timeout_ms,
                profile="formal",
                max_retries=max_retries,
            )
            if pre_score.score is None or pre_score.score <= ai_score_threshold:
                baseline_score = score_answer_quality(
                    question,
                    response.answer,
                    target_org,
                    job_terms=job_terms,
                    baseline_text=response.answer,
                    peer_answers=tuple(peer_answers),
                )
                length = count_characters(response.answer, question.count_mode)
                minimum = (
                    round(question.character_limit * MINIMUM_FILL_RATIO)
                    if question.character_limit and question.character_limit >= 200
                    else 0
                )
                candidate = {
                    "variant": "copyedited",
                    "status": "copyedited_baseline",
                    "message": "",
                    "answer": response.answer,
                    "length": length,
                    "count_mode": question.count_mode,
                    "eligible_length": (
                        (not question.character_limit or length <= question.character_limit)
                        and length >= minimum
                    ),
                    "ai_score": pre_score.score,
                    "ai_score_status": pre_score.status,
                    "ai_score_message": pre_score.message,
                    "score": asdict(baseline_score),
                }
                peer_answers.append(response.answer)
                selected.append(response)
                reports.append(
                    {
                        "question_index": response.question_index,
                        "selected_variant": "copyedited",
                        "selected_score": candidate["score"],
                        "selected_ai_score": pre_score.score,
                        "ai_score_threshold": ai_score_threshold,
                        "ai_score_gate": (
                            "passed" if pre_score.score is not None else "unavailable"
                        ),
                        "input_length": input_length,
                        "input_fill_ratio": round(input_fill_ratio, 4),
                        "headroom_target": PATINA_HEADROOM_RATIO,
                        "headroom_target_met": (
                            not question.character_limit
                            or input_fill_ratio <= PATINA_HEADROOM_RATIO
                        ),
                        "patina_score_attempted": True,
                        "patina_attempted": False,
                        "patina_applied": False,
                        "patina_result": (
                            "not_needed"
                            if pre_score.score is not None
                            else "score_unavailable"
                        ),
                        "candidates": [candidate],
                    }
                )
                continue
        candidates: list[dict[str, object]] = []
        for variant, profile, tone in VARIANTS:
            result = (
                HumanizationResult(response.answer, "original")
                if variant == "original"
                else rewriter(
                    response.answer,
                    character_limit=question.character_limit,
                    count_mode=question.count_mode,
                    backend=backend,
                    timeout_ms=timeout_ms,
                    profile=profile,
                    tone=tone,
                    voice_sample=voice_sample,
                    protected_terms=protected_terms,
                    max_retries=max_retries,
                )
            )
            score = score_answer_quality(
                question,
                result.text,
                target_org,
                job_terms=job_terms,
                baseline_text=response.answer,
                peer_answers=tuple(peer_answers),
            )
            length = count_characters(result.text, question.count_mode)
            minimum = (
                round(question.character_limit * MINIMUM_FILL_RATIO)
                if question.character_limit and question.character_limit >= 200
                else 0
            )
            eligible_length = (
                (not question.character_limit or length <= question.character_limit)
                and length >= minimum
            )
            candidates.append(
                {
                    "variant": variant,
                    "status": result.status,
                    "message": result.message,
                    "answer": result.text,
                    "length": length,
                    "count_mode": question.count_mode,
                    "eligible_length": eligible_length,
                    "ai_score": None,
                    "ai_score_status": "not_scored",
                    "score": asdict(score),
                }
            )
        def ranking_key(item: dict[str, object]) -> tuple[bool, bool, int, bool]:
            return (
                bool(item["eligible_length"]),
                not str(item["status"]).startswith("fallback_"),
                int(item["score"]["total"]),
                item["variant"] != "original",
            )
        ranked = sorted(candidates, key=ranking_key, reverse=True)
        winner = ranked[0]
        score_gate_result = "not_requested"
        if scorer is not None:
            score_gate_result = "failed"
            seen_answers: set[str] = set()
            for candidate in ranked:
                candidate_answer = str(candidate["answer"])
                if (
                    not candidate["eligible_length"]
                    or str(candidate["status"]).startswith("fallback_")
                    or candidate_answer in seen_answers
                ):
                    continue
                seen_answers.add(candidate_answer)
                score_result = (
                    pre_score
                    if candidate["variant"] == "original" and pre_score is not None
                    else scorer(
                        candidate_answer,
                        threshold=ai_score_threshold,
                        backend=backend,
                        timeout_ms=timeout_ms,
                        profile="formal",
                        max_retries=max_retries,
                    )
                )
                candidate["ai_score"] = score_result.score
                candidate["ai_score_status"] = score_result.status
                candidate["ai_score_message"] = score_result.message
                if score_result.score is None:
                    score_gate_result = "unavailable"
                    break
                if score_result.score <= ai_score_threshold:
                    winner = candidate
                    score_gate_result = "passed"
                    break
            if score_gate_result != "passed":
                winner = next(
                    item for item in candidates if item["variant"] == "original"
                )
        answer = str(winner["answer"])
        peer_answers.append(answer)
        selected.append(
            DraftResponse(
                response.question_index,
                answer,
                response.evidence_paths,
                response.experience_refs,
                response.research_refs,
            )
        )
        reports.append(
            {
                "question_index": response.question_index,
                "selected_variant": winner["variant"],
                "selected_score": winner["score"],
                "selected_ai_score": winner.get("ai_score"),
                "ai_score_threshold": ai_score_threshold,
                "ai_score_gate": score_gate_result,
                "input_length": input_length,
                "input_fill_ratio": round(input_fill_ratio, 4),
                "headroom_target": PATINA_HEADROOM_RATIO,
                "headroom_target_met": (
                    not question.character_limit
                    or input_fill_ratio <= PATINA_HEADROOM_RATIO
                ),
                "patina_attempted": True,
                "patina_score_attempted": scorer is not None,
                "patina_applied": winner["variant"] != "original",
                "patina_result": (
                    "accepted" if winner["variant"] != "original" else "not_selected"
                ),
                "candidates": candidates,
            }
        )
    return selected, reports
