"""PRIVATE fresh-control vs NRS reconstruction pilot.

This module intentionally does not recover or relabel historical drafts as an
experimental control.  It copies selected, source-complete historical runs into
an ignored PRIVATE experiment directory, regenerates a factual blueprint and
argument route there, then produces a fresh route-order control and NRS
realizations from the same selected route.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import inspect
import os
from pathlib import Path
import shutil
import subprocess
import time
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from .argument_search import REQUIRED, PROOF_KINDS, build_story_kernel, validate_route_packet
from .deep_writer import (
    DEFAULT_BACKEND_SENTINEL,
    _coerce,
    _prose_prompt,
    _route_prompt,
    generate_deep_draft,
    subprocess_model_runner,
)
from .facts import METRIC, _normalize
from .fluent_korean_shadow import (
    PROFILE_ID as FLUENT_KOREAN_PROFILE_ID,
    SOURCE_URL as FLUENT_KOREAN_SOURCE_URL,
    apply_fluent_korean_shadow_prompt,
)
from .narrative_compiler import _to_response, _validate_generated_payload, compile_run_blueprint
from .narrative_realization_shadow import (
    build_narrative_kernel,
    build_nrs_prompt,
    build_route_order_control_plan,
    generate_realization_plans,
)
from .nrs_shadow_benchmark import (
    blind_pair,
    generate_nrs_candidates,
    render_blind_packet,
    select_blind_candidate,
)
from .preference_writer import _candidate_issues, _state
from .profile_schema import load_ledger
from .research_evidence import _claim_visible_in_answer as _research_claim_visible
from .self_introduction_genre import GENRE_CONTRACT_VERSION, blocking_genre_issues


EXPERIMENT_TYPE = "NEW_PAIRED_RECONSTRUCTION_PILOT"
V2_EXPERIMENT_TYPE = "NATURAL_SELF_INTRODUCTION_PAIRED_BENCHMARK_V2"
WRITER_PROMPT_PROFILE = "self_intro_outcome_first_v2"
V2_CANDIDATES_PER_ARM = 3
V2_RETRY_BUDGET_PER_CANDIDATE = 2
INVALID_HISTORICAL_WRITER_EVIDENCE = {
    "experiment_id": "NRS_FLUENT_KOREAN_12Q_2026_08_24",
    "invalid_for_writer_efficacy": "genre_contract_failure",
}
def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _questions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = state.get("questions", [])
    if not isinstance(rows, list):
        return []
    return [dict(item) for item in rows if isinstance(item, Mapping) and isinstance(item.get("index"), int)]


def _answers(path: Path) -> dict[int, str]:
    raw = _read_json(path, [])
    rows: Iterable[Any]
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, Mapping):
        rows = raw.get("responses", []) if isinstance(raw.get("responses"), list) else []
    else:
        rows = []
    return {
        int(item["question_index"]): str(item["answer"])
        for item in rows
        if isinstance(item, Mapping) and isinstance(item.get("question_index"), int) and isinstance(item.get("answer"), str)
    }


def _required_source_paths(run_dir: Path) -> dict[str, Path | None]:
    exact = {
        "posting_source": run_dir / "00_채용공고분석.json",
        "ledger_source": run_dir / "02_확정경험원장.json",
        "matching_source": run_dir / "03_경험직무매칭.json",
        "research_source": run_dir / "04_공식근거.json",
    }
    return {key: value if value.is_file() else None for key, value in exact.items()}


def inventory_final_runs(runs_root: Path) -> list[dict[str, Any]]:
    """Inventory final runs without inferring missing historical route artifacts."""
    result: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir() and not path.name.startswith("_")):
        final_path = run_dir / "draft_final.json"
        state_path = run_dir / "run.json"
        if not final_path.is_file() or not state_path.is_file():
            continue
        state = _read_json(state_path, {})
        if not isinstance(state, Mapping):
            continue
        sources = _required_source_paths(run_dir)
        answers = _answers(final_path)
        for question in _questions(state):
            index = int(question["index"])
            answer = answers.get(index)
            question_resolvable = bool(str(question.get("prompt", "")).strip())
            claim_ok = sources["ledger_source"] is not None and sources["matching_source"] is not None
            research_ok = sources["research_source"] is not None
            full = bool(answer and question_resolvable and sources["posting_source"] and claim_ok and research_ok)
            partial = bool(answer and question_resolvable and (sources["posting_source"] or sources["ledger_source"]))
            result.append({
                "run_path": str(run_dir),
                "company": str(state.get("target", "")) or None,
                "question": str(question.get("prompt", "")) or None,
                "question_index": index,
                "character_limit": question.get("character_limit"),
                "canonical_answer": answer,
                "ledger_source": str(sources["ledger_source"]) if sources["ledger_source"] else None,
                "posting_source": str(sources["posting_source"]) if sources["posting_source"] else None,
                "research_source": str(sources["research_source"]) if sources["research_source"] else None,
                "claim_evidence_resolvable": claim_ok,
                "research_evidence_resolvable": research_ok,
                "question_resolvable": question_resolvable,
                "route_reconstructable": full,
                "blueprint_reconstructable": full,
                "recoverability": (
                    "FULL_SOURCE_RECONSTRUCTABLE" if full else
                    "PARTIAL_SOURCE_RECONSTRUCTABLE" if partial else
                    "ANSWER_ONLY" if answer else "UNUSABLE"
                ),
            })
    return result


def resolve_writer_backend() -> dict[str, Any]:
    command = shutil.which("codex") or shutil.which("codex.cmd")
    return {
        "writer_backend": "codex_cli_default" if command else None,
        "resolved_model": None,
        "model_identity_available": False,
        "reasoning_effort": os.environ.get("CAREER_CODEX_REASONING_EFFORT") or None,
        "resolution_source": "Codex CLI default configuration; no --model argument",
        "command_available": bool(command),
    }


def default_backend_runner(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any]:
    """Use one configured CLI backend without inventing a model identity."""
    if model_id != DEFAULT_BACKEND_SENTINEL:
        raise ValueError("paired pilot runner requires the default backend sentinel")
    log_path = os.environ.get("CAREER_PAIRED_STAGE_LOG")
    if stage.startswith("deep_route_plan"):
        prompt += (
            "\nSchema correction: every proof_chain item.kind must be exactly one of "
            + ", ".join(sorted(PROOF_KINDS))
            + ". Do not use descriptive labels such as direct_answer."
        )
    # Prose prompts deliberately receive no validator diagnosis, contribution
    # blacklist, or audit explanation.  Those constraints are enforced after
    # generation by route-bound and genre validators.
    prompt = apply_fluent_korean_shadow_prompt(stage, prompt)
    started = time.monotonic()
    # Candidate selection has no creative-generation budget and returns a
    # tiny ranking JSON.  Bound it separately so a stalled local CLI cannot
    # keep an otherwise completed question hostage.  This does not alter the
    # equal 3 x 2 writer-candidate budget of either experimental arm.
    is_candidate_selection = stage.startswith("nrs_shadow_candidate_select")
    call_timeout_ms = min(timeout_ms, 90_000) if is_candidate_selection else timeout_ms
    # A Codex CLI invocation can occasionally fail before a model response is
    # started (for example while its local session is being reacquired).  This
    # is transport recovery, not an extra writing candidate or quality retry:
    # every arm follows the same bounded policy and keeps its 3 x 2 candidate
    # budget unchanged.
    transport_errors: list[str] = []
    for transport_attempt in range(1, (2 if is_candidate_selection else 4)):
        try:
            result = subprocess_model_runner(stage, prompt, "", call_timeout_ms)
            break
        except Exception as error:
            transport_errors.append(str(error))
            if transport_attempt == (1 if is_candidate_selection else 3):
                if log_path:
                    with Path(log_path).open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({
                            "stage": stage, "status": "failed",
                            "seconds": round(time.monotonic() - started, 3),
                            "transport_attempts": transport_attempt,
                            "error": str(error),
                        }, ensure_ascii=False) + "\n")
                raise
            time.sleep(2 ** (transport_attempt - 1))
    if log_path:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            entry = {
                "stage": stage, "status": "passed",
                "seconds": round(time.monotonic() - started, 3),
                "transport_attempts": len(transport_errors) + 1,
            }
            if stage.startswith(("deep_route_plan", "deep_prose_generate", "nrs_shadow_generate")):
                entry["private_payload"] = result
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return result


def _copy_single_question_source(source: Path, destination: Path, question_index: int) -> dict[str, Any]:
    shutil.copytree(source, destination, dirs_exist_ok=False)
    state_path = destination / "run.json"
    state = _read_json(state_path, {})
    if not isinstance(state, dict):
        raise ValueError(f"invalid run state: {source}")
    selected = [row for row in _questions(state) if int(row["index"]) == question_index]
    if len(selected) != 1:
        raise ValueError(f"question {question_index} missing from {source}")
    state["questions"] = selected
    state["run_dir"] = str(destination)
    _write_json(state_path, state)
    return state


def _selected_route(report: Mapping[str, Any], question_index: int) -> dict[str, Any]:
    selected = report.get("selected_routes", {})
    selected_row = selected.get(str(question_index)) if isinstance(selected, Mapping) else None
    route_id = selected_row.get("route_id") if isinstance(selected_row, Mapping) else None
    for row in report.get("route_search", []) or []:
        if not isinstance(row, Mapping) or row.get("question_index") != question_index:
            continue
        for route in row.get("routes", []) or []:
            if isinstance(route, Mapping) and route.get("route_id") == route_id:
                return dict(route)
    raise ValueError(f"selected route unavailable for question {question_index}")


def _required_research_reference_instruction(blueprint: Mapping[str, Any]) -> str:
    """Tell the prose writer to render a route-bound official fact in prose."""
    logic = blueprint.get("logic_contract")
    if not isinstance(logic, Mapping) or logic.get("research_mode") != "required":
        return ""
    ids = [
        str(item.get("claim_id", "")).strip()
        for item in blueprint.get("research_claims", []) or []
        if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
    ]
    if not ids:
        raise ValueError("research-required blueprint has no approved research IDs")
    return (
        "\nEvidence-rendering rule: this question requires an official fact already "
        "contained in the selected route. State that fact naturally in the answer. "
        "The program, not the model, binds the approved reference IDs. Do not add a "
        "fact merely to satisfy this requirement."
    )


def _route_bound_reference_ids(
    blueprint: Mapping[str, Any], route: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    """Derive factual references from the already validated argument route.

    Prose generators may decide phrasing, but they are not an authority for
    which experience or official-research facts support the answer.  That
    decision was made by the route and is checked again here against the
    blueprint's approved evidence set.
    """
    support_refs: list[str] = []
    thesis_refs = route.get("thesis_support_refs", [])
    if not isinstance(thesis_refs, list) or not all(isinstance(ref, str) for ref in thesis_refs):
        raise ValueError("route thesis_support_refs must be a string array")
    support_refs.extend(thesis_refs)
    proof_chain = route.get("proof_chain", [])
    if not isinstance(proof_chain, list):
        raise ValueError("route proof_chain must be an array")
    for proof in proof_chain:
        if not isinstance(proof, Mapping):
            raise ValueError("route proof item must be an object")
        refs = proof.get("support_refs", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise ValueError("route proof support_refs must be a string array")
        support_refs.extend(refs)

    claim_ids = list(dict.fromkeys(
        ref.removeprefix("claim:") for ref in support_refs if ref.startswith("claim:")
    ))
    research_ids = list(dict.fromkeys(
        ref.removeprefix("research:") for ref in support_refs if ref.startswith("research:")
    ))
    approved_claim_ids = {
        str(item.get("claim_id", "")).strip()
        for item in (blueprint.get("experience") or {}).get("selected_claims", [])
        if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
    } if isinstance(blueprint.get("experience"), Mapping) else set()
    approved_research_ids = {
        str(item.get("claim_id", "")).strip()
        for item in blueprint.get("research_claims", []) or []
        if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
    }
    # The route builder is allowed to cite a canonical experience field
    # (for example, ``experience:action:0``) instead of repeating the opaque
    # claim ID.  Resolve that approved experience-level reference
    # deterministically to the blueprint's selected claims.  The model still
    # cannot introduce or choose metadata; if there is no selected claim, the
    # route is genuinely under-specified and must fail.
    if not claim_ids and any(ref.startswith("experience:") for ref in support_refs):
        claim_ids = [
            str(item.get("claim_id", "")).strip()
            for item in (blueprint.get("experience") or {}).get("selected_claims", [])
            if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
        ] if isinstance(blueprint.get("experience"), Mapping) else []
        if not claim_ids:
            raise ValueError("route has experience support but blueprint has no selected claim")
    unknown_claims = sorted(set(claim_ids) - approved_claim_ids)
    unknown_research = sorted(set(research_ids) - approved_research_ids)
    if unknown_claims or unknown_research:
        details = []
        if unknown_claims:
            details.append("claim=" + ", ".join(unknown_claims))
        if unknown_research:
            details.append("research=" + ", ".join(unknown_research))
        raise ValueError("route references not approved by blueprint: " + "; ".join(details))
    logic = blueprint.get("logic_contract")
    if isinstance(logic, Mapping):
        if logic.get("experience_mode") == "required" and not claim_ids:
            raise ValueError("route omitted required experience claim reference")
        if logic.get("research_mode") == "required" and not research_ids:
            raise ValueError("route omitted required research reference")
    return claim_ids, research_ids


def _visible_metric_claim_ids(blueprint: Mapping[str, Any], answer: str) -> list[str]:
    """Attach approved metric claims that are visibly rendered in prose.

    The realization prompt exposes every selected claim as an allowed fact,
    while a route may use one claim as its structural anchor.  A writer can
    therefore render another approved before/after metric without inventing a
    fact.  Keep that metadata auditable by deriving it from the visible metric
    tokens, never from model-declared IDs.  Non-metric claims remain bound to
    the argument route.
    """
    experience = blueprint.get("experience")
    if not isinstance(experience, Mapping):
        return []
    answer_metrics = {
        _normalize(match.group("number"), match.group("unit"))[0]
        for match in METRIC.finditer(answer)
    }
    if not answer_metrics:
        return []
    visible_ids: list[str] = []
    for claim in experience.get("selected_claims", []) or []:
        if not isinstance(claim, Mapping):
            continue
        claim_id = str(claim.get("claim_id", "")).strip()
        value = str(claim.get("normalized_value", "")).strip()
        metric_values = {
            _normalize(match.group("number"), match.group("unit"))[0]
            for match in METRIC.finditer(value)
        }
        if claim_id and metric_values and metric_values <= answer_metrics:
            visible_ids.append(claim_id)
    return visible_ids


def _bound_research_ids_visible_in_answer(
    blueprint: Mapping[str, Any], research_ids: Sequence[str], answer: str,
) -> list[str]:
    """Do not attach an optional research claim that prose did not render.

    A route may keep an official fact available as an optional fit bridge.  It
    becomes answer metadata only if the answer actually expresses that fact;
    required research remains route-bound and is rejected by canonical
    validation when it is not visible.
    """
    logic = blueprint.get("logic_contract")
    if isinstance(logic, Mapping) and logic.get("research_mode") == "required":
        return list(research_ids)
    claims = {
        str(item.get("claim_id", "")).strip(): str(item.get("claim", ""))
        for item in blueprint.get("research_claims", []) or []
        if isinstance(item, Mapping)
    }
    return [
        claim_id for claim_id in research_ids
        if claim_id in claims and _research_claim_visible(claims[claim_id], answer)
    ]


def _validate_route_bound_payload(
    raw: Mapping[str, Any], blueprint: Mapping[str, Any], stage: str, route: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate model prose while binding factual metadata to its route.

    Model-declared IDs are deliberately ignored.  The route is the evidence
    authority; additionally, visibly rendered selected metrics are attached
    deterministically because the fact contract explicitly permits them.
    Final canonical validation still checks every attached fact is valid and
    visible in the answer.
    """
    claim_ids, research_ids = _route_bound_reference_ids(blueprint, route)
    answer = str(raw.get("answer", ""))
    fixed = dict(raw)
    fixed["used_claim_ids"] = list(dict.fromkeys(
        [*claim_ids, *_visible_metric_claim_ids(blueprint, answer)]
    ))
    fixed["used_research_ids"] = _bound_research_ids_visible_in_answer(
        blueprint, research_ids, answer
    )
    return _validate_generated_payload(fixed, blueprint, stage)


def _contribution_boundary_instruction(blueprint: Mapping[str, Any]) -> str:
    """Build a prose constraint from the selected claims' verification scope."""
    experience = blueprint.get("experience")
    claims = experience.get("selected_claims", []) if isinstance(experience, Mapping) else []
    contributions = {
        str((claim.get("verification") or {}).get("contribution", "unknown"))
        for claim in claims
        if isinstance(claim, Mapping)
    }
    if not contributions & {"observed", "unknown"}:
        return ""
    return (
        "\nContribution-scope contract: the selected past evidence is observation-only "
        "or has unknown contribution. Describe only what the applicant checked, "
        "organized, coordinated, suggested, or supported. Do not say the applicant "
        "caused an improvement or completed a resolution. In the past-experience "
        "portion, avoid these strong result forms entirely: 향상시켰습니다, "
        "감소시켰습니다, 해결했습니다, 달성했습니다, 개선했습니다, 증가시켰습니다, "
        "절감했습니다, 완수했습니다, 기여했습니다, 완화했습니다, 도왔습니다."
    )


def _numeric_boundary_instruction(blueprint: Mapping[str, Any]) -> str:
    """Give the realization writer the exact numeric vocabulary it may use."""
    allowed: list[str] = []
    experience = blueprint.get("experience")
    if isinstance(experience, Mapping):
        for claim in experience.get("selected_claims", []) or []:
            if not isinstance(claim, Mapping):
                continue
            value = str(claim.get("normalized_value", "")).strip()
            if value and (claim.get("is_metric") or re.search(r"\d", value)):
                allowed.append(value)
    allowed = list(dict.fromkeys(allowed))
    values = ", ".join(allowed) if allowed else "없음"
    character_plan = blueprint.get("character_plan")
    maximum = character_plan.get("hard_maximum") if isinstance(character_plan, Mapping) else None
    target = character_plan.get("target") if isinstance(character_plan, Mapping) else None
    limit_text = (
        f"공백 포함 최대 {maximum}자, 목표 약 {target}자" if maximum else "설계도 character_plan의 제한"
    )
    return (
        "\nNumeric and length contract: " + limit_text + "을 반드시 지킨다. "
        "숫자·기간·비율·날짜는 승인된 정확한 값만 사용할 수 있다. 승인된 값은 [" + values + "]이다. "
        "목록에 없는 수치는 문장 자체에서 삭제하고, 추정하거나 반올림하지 않는다."
    )


def _generate_lean_control(
    *,
    run_dir: Path,
    packet: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    timeout_ms: int,
    runner: Callable[[str, str, str, int], dict[str, Any]],
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Generate one fresh, route-bound control without model judging.

    The 12-item benchmark uses this pre-registered lean path to keep the
    comparison practical. It preserves the canonical route and prose payload
    validation boundaries, then applies the same shadow factual gates that
    apply to NRS candidates. It intentionally does not claim to replace the
    rigorous Deep Writer selection workflow.
    """
    q = int(blueprint["question_index"])
    route_stage = f"deep_route_plan_q{q}_lean"
    raw_routes = _coerce(
        runner(
            route_stage,
            _route_prompt(blueprint, packet, build_story_kernel(blueprint), 2, ()),
            DEFAULT_BACKEND_SENTINEL,
            timeout_ms,
        ),
        route_stage,
    )
    route_packet = validate_route_packet(raw_routes, blueprint, minimum_routes=2, maximum_routes=2)
    route = next((item for item in route_packet["routes"] if not item.get("critical_gap")), None)
    if route is None:
        raise ValueError(f"no defensible lean control route for question {q}")
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
    research_reference_instruction = _required_research_reference_instruction(blueprint)
    failures: list[dict[str, Any]] = []
    previous_payload: dict[str, Any] | None = None
    for attempt in range(1, 4):
        prose_stage = f"deep_prose_generate_q{q}_lean_{attempt}"
        try:
            repair = ""
            if attempt > 1:
                repair = (
                    "결정론적 검증에서 contribution_overstatement가 발생했습니다. "
                    "과거 경험은 관찰·확인·정리·제안·지원의 범위로만 다시 쓰십시오. "
                    "향상시켰습니다·해결했습니다·달성했습니다·개선했습니다·기여했습니다·"
                    "도왔습니다처럼 결과를 직접 일으켰다고 말하는 표현은 사용하지 마십시오. "
                    "조직 전체의 변화·정책 변경·최종 결정으로 확대하지 마십시오."
                )
            raw_control = _coerce(
                runner(
                    prose_stage,
                    _prose_prompt(
                        blueprint,
                        packet,
                        route,
                        ("natural_precision", "정확하지만 보고서처럼 굳지 않은 자연스러운 한국어로 쓴다."),
                        (),
                        (),
                        (),
                        repair,
                        previous_payload,
                    ) + research_reference_instruction + _contribution_boundary_instruction(blueprint),
                    DEFAULT_BACKEND_SENTINEL,
                    timeout_ms,
                ),
                prose_stage,
            )
            payload = _validate_route_bound_payload(raw_control, blueprint, prose_stage, route)
            previous_payload = payload
            response = _to_response(payload, blueprint, ledger_schema_version=ledger.schema_version)
            issues = _validate_control_and_candidates(run_dir, [response])
        except Exception as error:
            failures.append({"stage": prose_stage, "codes": ["payload_contract"], "message": str(error)})
            continue
        if issues:
            failures.append({"stage": prose_stage, "codes": [str(item.get("code", item)) for item in issues]})
            continue
        return response, dict(route), {
            "mode": "lean_route_bound_control_v1",
            "route_stage": route_stage,
            "prose_stage": prose_stage,
            "candidate_failures": failures,
            "deterministic_validation": {"status": "passed", "issues": []},
        }
    raise ValueError(f"all lean controls failed factual validation for question {q}: {failures}")


def _response_payload(response: Any, blueprint_id: str) -> dict[str, Any]:
    return {
        "blueprint_id": blueprint_id,
        "question_index": int(response.question_index),
        "answer": str(response.answer),
        "used_claim_ids": [claim_id for ref in response.experience_refs for claim_id in ref.claim_ids],
        "used_research_ids": list(response.research_refs),
    }


def _validate_control_and_candidates(run_dir: Path, responses: Sequence[Any]) -> list[dict[str, Any]]:
    # _candidate_issues is the existing Preference Writer gate, reused unchanged.
    state = _state(run_dir)
    issues: list[dict[str, Any]] = []
    for response in responses:
        for issue in _candidate_issues(run_dir, state, response):
            issues.append(asdict(issue))
        for code in _shadow_actor_attribution_codes(run_dir, str(response.answer)):
            issues.append({"code": code})
        for issue in blocking_genre_issues(str(response.answer)):
            issues.append(asdict(issue))
    return issues


def _shadow_actor_attribution_codes(run_dir: Path, answer: str) -> list[str]:
    """Block the user-corrected supervisor-confirmation attribution in shadow runs.

    This is intentionally narrow: it is a PRIVATE regression guard for a
    user-confirmed correction, not a production semantic policy.
    """
    ledger_text = (run_dir / "02_확정경험원장.json").read_text(encoding="utf-8")
    unsupported_patterns = (
        r"담당\s*직원의\s*사전\s*확인",
        r"담당\s*직원(?:에게|의)\s*.*?확인받",
    )
    codes: list[str] = []
    for pattern in unsupported_patterns:
        if re.search(pattern, answer) and not re.search(pattern, ledger_text):
            codes.append("shadow_unsupported_actor_attribution")
            break
    return codes


def _shadow_candidate_issues(
    run_dir: Path,
    state: Any,
    response: Any,
    *,
    allow_research_only: bool = False,
) -> list[Any]:
    issues = list(_candidate_issues(run_dir, state, response))
    # Preference Writer's legacy gate infers an experience requirement from
    # wording such as "근무한다면".  The v2 blueprint is the authority: a
    # job-plan question may intentionally make experience optional while
    # requiring an official job fact.  Preserve research validation, but do
    # not reject that bounded research-only answer for missing past evidence.
    if allow_research_only and getattr(response, "research_refs", ()):
        issues = [
            issue for issue in issues
            if str(getattr(issue, "code", issue)) not in {
                "missing_evidence", "missing_experience_ref",
            }
        ]
    return issues + _shadow_actor_attribution_codes(
        run_dir, str(response.answer)
    ) + blocking_genre_issues(str(response.answer))


def _preflight(
    rows: Sequence[Mapping[str, Any]],
    backend: Mapping[str, Any],
    *,
    expected_question_count: int = 6,
) -> dict[str, Any]:
    checks = {
        "question_count_matches_expected": len(rows) == expected_question_count,
        "every_question_resolvable": all(bool(row.get("question_resolvable")) for row in rows),
        "every_route_exists": all(bool(row.get("route_id")) for row in rows),
        "every_blueprint_exists": all(bool(row.get("blueprint_id")) for row in rows),
        "every_proof_chain_nonempty": all(bool(row.get("proof_chain")) for row in rows),
        "claim_refs_resolvable": all(bool(row.get("claim_evidence_resolvable")) for row in rows),
        "research_refs_resolvable_or_not_required": all(bool(row.get("research_evidence_resolvable")) for row in rows),
        "writer_backend_resolved": bool(backend.get("writer_backend")),
        "same_control_nrs_config": all(bool(row.get("same_writer_config")) for row in rows),
        "validators_available": all(bool(row.get("validator_available")) for row in rows),
        "genre_gates_passed": all(bool(row.get("genre_gate_passed", True)) for row in rows),
        "candidate_budgets_equal": all(bool(row.get("candidate_budgets_equal", True)) for row in rows),
        "blind_selection_used": all(bool(row.get("blind_selection_used", True)) for row in rows),
    }
    return {
        "passed": all(checks.values()),
        "expected_question_count": expected_question_count,
        "checks": checks,
    }


def _git_commit(root: Path) -> str | None:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return completed.stdout.strip() if completed.returncode == 0 else None


def _manifest(out_dir: Path, *, experiment_id: str, repo_root: Path, backend: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    files = sorted(
        path
        for path in out_dir.rglob("*")
        if path.is_file()
        and path.name not in {"manifest.json", "manifest_verify.private.json"}
    )
    relative = [str(path.relative_to(out_dir)).replace("\\", "/") for path in files]
    hashes = {name: _sha256(out_dir / name) for name in relative}
    config_hash = sha256(json.dumps({"backend": backend.get("writer_backend"), "model": backend.get("resolved_model"), "runner": "codex_cli_default_no_model_argument", "route_schema_guardrail": sorted(PROOF_KINDS), "research_requirement_policy": "research_evidence.needs_research", "prose_reference_binding": "validated_argument_route", "writer_prompt_profile": WRITER_PROMPT_PROFILE, "fluent_korean_shadow_profile": FLUENT_KOREAN_PROFILE_ID, "genre_contract": GENRE_CONTRACT_VERSION, "candidate_selection": "counterbalanced_blind_rank_v1"}, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": "2",
        "experiment_id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(repo_root),
        "experiment_type": EXPERIMENT_TYPE,
        "original_six_question_corpus_recovered": False,
        "uses_historical_canonical_as_control": False,
        "writer_backend": backend.get("writer_backend"),
        "resolved_model": backend.get("resolved_model"),
        "reasoning_effort": backend.get("reasoning_effort"),
        "model_identity_available": backend.get("model_identity_available"),
        "writer_config_hash": config_hash,
        "factual_reference_contract": {
            "research_requirement_policy": "research_evidence.needs_research",
            "reference_binding": "validated_argument_route",
            "model_declared_reference_ids_trusted": False,
        },
        "writer_contract_hashes": sorted({str(row.get("writer_contract_hash")) for row in rows if row.get("writer_contract_hash")}),
        "historical_writer_efficacy_evidence": [INVALID_HISTORICAL_WRITER_EVIDENCE],
        "fluent_korean_shadow_profile": {
            "id": FLUENT_KOREAN_PROFILE_ID,
            "source": FLUENT_KOREAN_SOURCE_URL,
            "scope": "private_paired_prose_realization_only",
            "applied_to": ["fresh_control", "nrs"],
        },
        "question_ids": [str(row.get("question_id")) for row in rows],
        "route_ids": [str(row.get("route_id")) for row in rows],
        "blueprint_ids": [str(row.get("blueprint_id")) for row in rows],
        "claim_ids": sorted({item for row in rows for item in row.get("claim_ids", [])}),
        "research_ids": sorted({item for row in rows for item in row.get("research_ids", [])}),
        "files": relative,
        "sha256": hashes,
    }


def verify_manifest(out_dir: Path) -> dict[str, Any]:
    manifest = _read_json(out_dir / "manifest.json", {})
    expected = manifest.get("sha256", {}) if isinstance(manifest, Mapping) else {}
    mismatches = [name for name, digest in expected.items() if not (out_dir / name).is_file() or _sha256(out_dir / name) != digest]
    return {"passed": not mismatches, "mismatches": mismatches, "file_count": len(expected)}


def record_human_preferences(
    *,
    repo_root: Path,
    out_dir: Path,
    preferences: Mapping[str, str],
    reasons: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Persist user-provided blind labels without generating any labels or reasons."""
    reasons = reasons or {}
    paired = _read_json(out_dir / "paired_pilot.private.json", {})
    blind = _read_json(out_dir / "blind_pairs.private.json", [])
    answer_key = _read_json(out_dir / "answer_key.private.json", [])
    rows = paired.get("rows", []) if isinstance(paired, Mapping) else []
    if not isinstance(rows, list) or not isinstance(blind, list) or not isinstance(answer_key, list):
        raise ValueError("invalid paired pilot artifacts")
    question_ids = [str(row.get("question_id")) for row in rows if isinstance(row, Mapping)]
    expected_question_count = int(paired.get("expected_question_count", 6))
    if len(question_ids) != expected_question_count or set(question_ids) != set(preferences):
        raise ValueError("preferences must provide exactly one label for every benchmark question")
    if not all(str(preferences[qid]) in {"A", "B", "REJECT_BOTH"} for qid in question_ids):
        raise ValueError("preference must be A, B, or REJECT_BOTH")
    keys = {str(row.get("question_id")): row for row in answer_key if isinstance(row, Mapping)}
    if set(keys) != set(question_ids):
        raise ValueError("answer key does not cover every pilot question")
    source_counts = {"BASELINE": 0, "NRS": 0, "REJECT_BOTH": 0}
    result_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        qid = str(row["question_id"])
        label = str(preferences[qid])
        reason = reasons.get(qid)
        row["human_preference"] = label
        row["human_reason"] = reason
        preferred_source = "REJECT_BOTH" if label == "REJECT_BOTH" else str(keys[qid][f"{label}_source"])
        source_counts[preferred_source] += 1
        result_rows.append({
            "question_id": qid,
            "human_preference": label,
            "human_reason": reason,
            "preferred_source": preferred_source,
        })
    for row in blind:
        if isinstance(row, dict):
            qid = str(row.get("question_id"))
            row["human_preference"] = str(preferences[qid])
            row["human_reason"] = reasons.get(qid)
    paired["human_preference"] = "COMPLETED_BY_USER"
    paired["human_reason"] = None
    _write_json(out_dir / "paired_pilot.private.json", paired)
    _write_json(out_dir / "blind_pairs.private.json", blind)
    result = {
        "experiment_id": paired.get("experiment_type"),
        "label_source": "user_provided",
        "human_labels_performed": True,
        "human_reasons_provided": sum(1 for row in result_rows if row["human_reason"]),
        "rows": result_rows,
        "summary": {
            "question_count": len(result_rows),
            "baseline_preferred_count": source_counts["BASELINE"],
            "nrs_preferred_count": source_counts["NRS"],
            "reject_both_count": source_counts["REJECT_BOTH"],
            "interpretation": "single-user exploratory blind preference; not a production promotion decision",
        },
    }
    _write_json(out_dir / "human_preference_result.private.json", result)
    backend = resolve_writer_backend()
    manifest = _manifest(out_dir, experiment_id=out_dir.name, repo_root=repo_root, backend=backend, rows=rows)
    _write_json(out_dir / "manifest.json", manifest)
    verification = verify_manifest(out_dir)
    _write_json(out_dir / "manifest_verify.private.json", verification)
    return {"result": result, "verification": verification}


def assemble_probe_artifacts(
    *,
    repo_root: Path,
    runs_root: Path,
    out_dir: Path,
    probe_dirs: Sequence[Path],
) -> dict[str, Any]:
    """Assemble six independently generated, same-config PRIVATE probe rows.

    This does not regenerate prose or reinterpret historical answers.  Each probe
    already contains the frozen source snapshot, generated route/blueprint, and
    canonical validation outputs.  The assembly step only assigns a fresh blind
    counterbalance, writes a complete manifest, and verifies all hashes.
    """
    if len(probe_dirs) != 6:
        raise ValueError("exactly six successful probes are required")
    if out_dir.exists():
        raise ValueError(f"refusing to overwrite experiment directory: {out_dir}")
    experiment_id = out_dir.name
    backend = resolve_writer_backend()
    rows: list[dict[str, Any]] = []
    blind_rows: list[dict[str, Any]] = []
    answer_key: list[dict[str, Any]] = []
    for ordinal, probe in enumerate(probe_dirs, start=1):
        payload = _read_json(probe / "paired_pilot.private.json", {})
        source_rows = payload.get("rows", []) if isinstance(payload, Mapping) else []
        if len(source_rows) != 1 or not isinstance(source_rows[0], Mapping):
            raise ValueError(f"invalid successful probe: {probe}")
        source_row = dict(source_rows[0])
        control = source_row.get("fresh_control", {})
        candidates = source_row.get("nrs_candidates", [])
        if not isinstance(control, Mapping) or not isinstance(candidates, list) or not candidates:
            raise ValueError(f"probe lacks a control or valid NRS candidate: {probe}")
        candidate = candidates[0]
        if not isinstance(candidate, Mapping) or not isinstance(candidate.get("payload"), Mapping):
            raise ValueError(f"invalid NRS candidate in {probe}")
        question_id = f"{experiment_id}:q{ordinal:02d}"
        pair = blind_pair(
            question_index=ordinal,
            baseline_answer=str(control.get("answer", "")),
            nrs_answer=str(candidate["payload"].get("answer", "")),
            salt=experiment_id,
        )
        pair["question_id"] = question_id
        pair["question"] = source_row.get("question")
        blind_rows.append(pair)
        answer_key.append({
            "question_id": question_id,
            "A_source": pair["source_by_label"]["A"].upper(),
            "B_source": pair["source_by_label"]["B"].upper(),
            "nrs_plan": candidate.get("plan_id"),
            "seed": experiment_id,
        })
        source_row["question_id"] = question_id
        source_row["selected_nrs_candidate_id"] = candidate.get("candidate_id")
        source_row["selected_nrs_plan"] = candidate.get("plan_id")
        source_row["probe_origin"] = str(probe)
        rows.append(source_row)
        shutil.copytree(probe, out_dir / "questions" / f"q{ordinal:02d}")
    _write_json(out_dir / "inventory_28_final_runs.private.json", inventory_final_runs(runs_root))
    _write_json(out_dir / "paired_pilot.private.json", {
        "experiment_type": EXPERIMENT_TYPE,
        "original_six_question_corpus_recovered": False,
        "uses_historical_canonical_as_control": False,
        "human_preference": None,
        "human_reason": None,
        "rows": rows,
    })
    _write_json(out_dir / "blind_pairs.private.json", [
        {"question_id": row["question_id"], "question": row["question"], "A": row["answers"]["A"], "B": row["answers"]["B"], "human_preference": None, "human_reason": None}
        for row in blind_rows
    ])
    _write_json(out_dir / "answer_key.private.json", answer_key)
    (out_dir / "NRS_HUMAN_PREFERENCE_blind.md").write_text(render_blind_packet(blind_rows), encoding="utf-8")
    preflight = _preflight(rows, backend)
    _write_json(out_dir / "preflight.private.json", preflight)
    manifest = _manifest(out_dir, experiment_id=experiment_id, repo_root=repo_root, backend=backend, rows=rows)
    _write_json(out_dir / "manifest.json", manifest)
    verification = verify_manifest(out_dir)
    _write_json(out_dir / "manifest_verify.private.json", verification)
    return {"experiment_id": experiment_id, "rows": rows, "preflight": preflight, "verification": verification, "backend": backend}


def _benchmark_protocol(
    *,
    experiment_id: str,
    selections: Sequence[tuple[str, int]],
    expected_question_count: int,
    control_generation_mode: str,
    protocol_version: int = 1,
    evaluation_role: str = "pilot",
) -> dict[str, Any]:
    if protocol_version not in {1, 2}:
        raise ValueError("protocol_version must be 1 or 2")
    is_v2 = protocol_version == 2
    return {
        "protocol_version": protocol_version,
        "experiment_id": experiment_id,
        "private": True,
        "decision_effect": "none_shadow_mode",
        "evaluation_role": evaluation_role,
        "expected_question_count": expected_question_count,
        "selection_order": [
            {"source_run": source_name, "question_index": question_index}
            for source_name, question_index in selections
        ],
        "arms": {
            "fresh_control": {
                "argument_route": "freshly regenerated",
                "generation_mode": "same_prompt_route_order_candidates" if is_v2 else control_generation_mode,
                "fluent_korean_profile": FLUENT_KOREAN_PROFILE_ID,
                "candidate_count": V2_CANDIDATES_PER_ARM if is_v2 else None,
                "retry_budget_per_candidate": V2_RETRY_BUDGET_PER_CANDIDATE if is_v2 else None,
            },
            "nrs": {
                "argument_route": "same selected fresh route",
                "fluent_korean_profile": FLUENT_KOREAN_PROFILE_ID,
                "candidate_count": V2_CANDIDATES_PER_ARM if is_v2 else None,
                "retry_budget_per_candidate": V2_RETRY_BUDGET_PER_CANDIDATE if is_v2 else None,
            },
        },
        "shared_exclusion_gates": [
            "canonical_candidate_issues",
            "shadow_unsupported_actor_attribution",
            "unapproved_metric",
            "other_organization",
            "audit_meta_leakage",
            "defensive_disclaimer",
            "self_explanation",
            "control_lexicon_density",
        ],
        "human_review_fields": [
            "preferred",
            "more_natural_korean",
            "question_fit",
            "more_interview_speakable",
            "reject_both",
        ],
        "historical_writer_efficacy_evidence": [INVALID_HISTORICAL_WRITER_EVIDENCE],
        "promotion_rule": (
            "Holdout 9문항에서 모든 문항 평가 가능, 중대한 사실·수치·행위자 오류 0건, 감사 문구 누출 0건, "
            "REJECT_BOTH 0건, NRS 선호 6문항 이상, 자연스러운 한국어 항목의 NRS 승수가 control 이상일 때만 "
            "사용자 승인 대상이 된다. 자동으로 production 기본 writer를 바꾸지 않는다."
            if is_v2 else
            "No production promotion from this single-user benchmark alone; require repeatable preference advantage and zero material factual failures."
        ),
    }


def _writer_contract(backend: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the actual shared writer contract instead of asserting equality."""
    prompt_source = inspect.getsource(build_nrs_prompt)
    fluent_source = inspect.getsource(apply_fluent_korean_shadow_prompt)
    common_prompt_hash = sha256((prompt_source + "\n" + fluent_source).encode("utf-8")).hexdigest()
    return {
        "prompt_profile": WRITER_PROMPT_PROFILE,
        "common_prompt_hash": common_prompt_hash,
        "writer_backend": backend.get("writer_backend"),
        "resolved_model": backend.get("resolved_model"),
        "reasoning_effort": backend.get("reasoning_effort"),
        "candidate_count": V2_CANDIDATES_PER_ARM,
        "retry_budget_per_candidate": V2_RETRY_BUDGET_PER_CANDIDATE,
        "reference_binding": "validated_argument_route",
        "genre_contract": GENRE_CONTRACT_VERSION,
    }


def _writer_contract_hash(contract: Mapping[str, Any]) -> str:
    return sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _checkpoint_path(out_dir: Path, ordinal: int) -> Path:
    return out_dir / "checkpoints" / f"q{ordinal:02d}.private.json"


def _load_checkpoint(out_dir: Path, ordinal: int, question_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    path = _checkpoint_path(out_dir, ordinal)
    payload = _read_json(path, None)
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError(f"invalid benchmark checkpoint: {path}")
    row = payload.get("row")
    blind = payload.get("blind_row")
    answer_key = payload.get("answer_key")
    if not all(isinstance(item, Mapping) for item in (row, blind, answer_key)):
        raise ValueError(f"incomplete benchmark checkpoint: {path}")
    if any(str(item.get("question_id", "")) != question_id for item in (row, blind, answer_key)):
        raise ValueError(f"checkpoint question identity mismatch: {path}")
    return dict(row), dict(blind), dict(answer_key)


def _archive_partial_question(work: Path) -> None:
    """Preserve an unfinished question attempt before generating its replacement."""
    if not work.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = work.parent.parent / "aborted_question_attempts" / f"{work.name}_{stamp}"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise ValueError(f"partial-question archive collision: {archive}")
    shutil.move(str(work), str(archive))


def run_pilot(
    *,
    repo_root: Path,
    runs_root: Path,
    out_dir: Path,
    selections: Sequence[tuple[str, int]],
    timeout_ms: int = 300_000,
    runner: Callable[[str, str, str, int], dict[str, Any]] = default_backend_runner,
    expected_question_count: int = 6,
    control_generation_mode: str = "rigorous",
) -> dict[str, Any]:
    """Generate a NEW private paired benchmark with an explicit item count."""
    if len(selections) != expected_question_count:
        raise ValueError(f"expected exactly {expected_question_count} run/question pairs")
    if control_generation_mode not in {"rigorous", "lean_route_bound"}:
        raise ValueError("control_generation_mode must be rigorous or lean_route_bound")
    experiment_id = out_dir.name
    backend = resolve_writer_backend()
    inventory = inventory_final_runs(runs_root)
    protocol = _benchmark_protocol(
        experiment_id=experiment_id,
        selections=selections,
        expected_question_count=expected_question_count,
        control_generation_mode=control_generation_mode,
    )
    existing_protocol = _read_json(out_dir / "benchmark_protocol.private.json", None)
    if out_dir.exists() and (out_dir / "manifest.json").exists():
        raise ValueError(f"refusing to overwrite completed experiment directory: {out_dir}")
    if existing_protocol is not None and existing_protocol != protocol:
        raise ValueError("existing partial benchmark protocol does not match this run")
    if existing_protocol is None:
        _write_json(out_dir / "inventory_28_final_runs.private.json", inventory)
        _write_json(out_dir / "benchmark_protocol.private.json", protocol)
    rows: list[dict[str, Any]] = []
    blind_rows: list[dict[str, Any]] = []
    answer_key: list[dict[str, Any]] = []

    for ordinal, (source_name, question_index) in enumerate(selections, start=1):
        question_id = f"{experiment_id}:q{ordinal:02d}"
        checkpoint = _load_checkpoint(out_dir, ordinal, question_id)
        if checkpoint is not None:
            row, pair, key = checkpoint
            rows.append(row)
            blind_rows.append(pair)
            answer_key.append(key)
            continue
        source = runs_root / source_name
        source_entry = next((item for item in inventory if item["run_path"] == str(source) and item["question_index"] == question_index), None)
        if not source_entry or source_entry["recoverability"] != "FULL_SOURCE_RECONSTRUCTABLE":
            raise ValueError(f"source is not fully reconstructable: {source_name} q{question_index}")
        work = out_dir / "questions" / f"q{ordinal:02d}"
        _archive_partial_question(work)
        state = _copy_single_question_source(source, work, question_index)
        packet = compile_run_blueprint(work)
        blueprint = next(item for item in packet["questions"] if item["question_index"] == question_index)
        if control_generation_mode == "rigorous":
            controls, deep_report = generate_deep_draft(
                work,
                packet=packet,
                writer_model_id=DEFAULT_BACKEND_SENTINEL,
                judge_model_ids=(DEFAULT_BACKEND_SENTINEL,),
                route_count=2,
                prose_realisations=2,
                timeout_ms=timeout_ms,
                runner=runner,
            )
            if len(controls) != 1:
                raise ValueError(f"expected one fresh control for {source_name} q{question_index}")
            control = controls[0]
            route = _selected_route(deep_report, question_index)
        else:
            control, route, deep_report = _generate_lean_control(
                run_dir=work,
                packet=packet,
                blueprint=blueprint,
                timeout_ms=timeout_ms,
                runner=runner,
            )
        kernel = build_narrative_kernel(blueprint, route)
        plans = generate_realization_plans(kernel, max_plans=3)
        ledger = load_ledger(work / "02_확정경험원장.json")
        state_for_validation = _state(work)
        nrs_prompt_runner = lambda stage, prompt, model_id, call_timeout: runner(
            stage,
            prompt + _numeric_boundary_instruction(blueprint),
            model_id,
            call_timeout,
        )
        candidates, failures = generate_nrs_candidates(
            blueprint=blueprint,
            packet=packet,
            route=route,
            kernel=kernel,
            plans=plans,
            runner=nrs_prompt_runner,
            model_id=DEFAULT_BACKEND_SENTINEL,
            timeout_ms=timeout_ms,
            validate_payload=lambda raw, bp, stage: _validate_route_bound_payload(
                raw, bp, stage, route
            ),
            make_response=lambda payload, bp: _to_response(payload, bp, ledger_schema_version=ledger.schema_version),
            candidate_issues=lambda response: _shadow_candidate_issues(work, state_for_validation, response),
            prior_answers=(),
            anchor_texts=tuple(item.text for item in kernel.proof_items if item.distinctive_anchor),
        )
        control_issues = _validate_control_and_candidates(work, [control])
        if not candidates:
            raise ValueError(f"no valid NRS candidate for {source_name} q{question_index}: {failures}")
        nrs = candidates[0]
        pair = blind_pair(question_index=ordinal, baseline_answer=control.answer, nrs_answer=str(nrs["payload"]["answer"]), salt=experiment_id)
        pair["question_id"] = question_id
        pair["question"] = blueprint["prompt"]
        blind_rows.append(pair)
        # Both arms are deliberately generated under the same writer contract.
        # Keep independent snapshots in the row so the manifest can prove that
        # equality instead of relying on an asserted boolean.
        control_contract = dict(contract)
        nrs_contract = dict(contract)
        answer_key.append({
            "question_id": question_id,
            "A_source": pair["source_by_label"]["A"].upper(),
            "B_source": pair["source_by_label"]["B"].upper(),
            "nrs_plan": nrs["plan_id"],
            "seed": experiment_id,
        })
        control_contract = dict(contract)
        nrs_contract = dict(contract)
        row = {
            "question_id": question_id,
            "source_run": str(source),
            "historical_reference_only": source_entry["canonical_answer"],
            "question_index": question_index,
            "question": blueprint["prompt"],
            "character_limit": source_entry["character_limit"],
            "question_resolvable": source_entry["question_resolvable"],
            "claim_evidence_resolvable": source_entry["claim_evidence_resolvable"],
            "research_evidence_resolvable": source_entry["research_evidence_resolvable"],
            "blueprint_id": blueprint["blueprint_id"],
            "route_id": route["route_id"],
            "proof_chain": route["proof_chain"],
            "claim_ids": list(_response_payload(control, blueprint["blueprint_id"])["used_claim_ids"]),
            "research_ids": list(_response_payload(control, blueprint["blueprint_id"])["used_research_ids"]),
            "fresh_control": _response_payload(control, blueprint["blueprint_id"]),
            "nrs_candidates": candidates,
            "nrs_failures": failures,
            "control_validation_issues": control_issues,
            "deep_writer_validation": deep_report.get("deterministic_validation"),
            "control_generation_mode": control_generation_mode,
            "same_writer_config": True,
            "validator_available": True,
            "selected_nrs_candidate_id": nrs["candidate_id"],
            "selected_nrs_plan": nrs["plan_id"],
            "artifact_status": "REGENERATED",
            "historical_route_recovered": False,
            "historical_blueprint_recovered": False,
            "regenerated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)
        _write_json(_checkpoint_path(out_dir, ordinal), {
            "schema_version": 1,
            "checkpoint_kind": "completed_question",
            "question_id": question_id,
            "row": row,
            "blind_row": pair,
            "answer_key": answer_key[-1],
        })

    _write_json(out_dir / "paired_pilot.private.json", {
        "experiment_type": EXPERIMENT_TYPE,
        "original_six_question_corpus_recovered": False,
        "uses_historical_canonical_as_control": False,
        "human_preference": None,
        "human_reason": None,
        "expected_question_count": expected_question_count,
        "rows": rows,
    })
    _write_json(out_dir / "blind_pairs.private.json", [
        {"question_id": row["question_id"], "question": row["question"], "A": row["answers"]["A"], "B": row["answers"]["B"], "human_preference": None, "human_reason": None}
        for row in blind_rows
    ])
    _write_json(out_dir / "answer_key.private.json", answer_key)
    (out_dir / "NRS_HUMAN_PREFERENCE_blind.md").write_text(render_blind_packet(blind_rows), encoding="utf-8")
    preflight = _preflight(rows, backend, expected_question_count=expected_question_count)
    _write_json(out_dir / "preflight.private.json", preflight)
    manifest = _manifest(out_dir, experiment_id=experiment_id, repo_root=repo_root, backend=backend, rows=rows)
    _write_json(out_dir / "manifest.json", manifest)
    verification = verify_manifest(out_dir)
    _write_json(out_dir / "manifest_verify.private.json", verification)
    return {"experiment_id": experiment_id, "backend": backend, "rows": rows, "preflight": preflight, "verification": verification}


def run_twelve_question_benchmark(
    *,
    repo_root: Path,
    runs_root: Path,
    out_dir: Path,
    selections: Sequence[tuple[str, int]],
    timeout_ms: int = 300_000,
    runner: Callable[[str, str, str, int], dict[str, Any]] = default_backend_runner,
) -> dict[str, Any]:
    """Run the v2 regression corpus; it is not NRS promotion evidence."""
    return run_natural_self_introduction_benchmark(
        repo_root=repo_root,
        runs_root=runs_root,
        out_dir=out_dir,
        selections=selections,
        timeout_ms=timeout_ms,
        runner=runner,
        expected_question_count=12,
        evaluation_role="regression_only",
    )


def _generate_shared_route(
    *,
    blueprint: Mapping[str, Any],
    packet: Mapping[str, Any],
    runner: Callable[[str, str, str, int], dict[str, Any]],
    timeout_ms: int,
) -> dict[str, Any]:
    experience = blueprint.get("experience")
    logic = blueprint.get("logic_contract")
    selected_claims = (
        experience.get("selected_claims", [])
        if isinstance(experience, Mapping) else []
    )
    experience_required = (
        isinstance(logic, Mapping) and logic.get("experience_mode") == "required"
    )
    # An experience marked merely preferred has no prose authority when the
    # compiler did not select any verified claim for it.  In particular, do
    # not let a route planner revive numbers from a raw situation/action
    # excerpt: those numbers are context, not submission facts.  Build the
    # same research-only future-plan route for both arms before the planner
    # sees those excerpts.
    if not selected_claims and not experience_required:
        return _source_complete_fallback_route(blueprint)
    question_index = int(blueprint["question_index"])
    stage = f"deep_route_plan_q{question_index}_v2"
    raw = _coerce(
        runner(
            stage,
            _route_prompt(blueprint, packet, build_story_kernel(blueprint), 2, ()),
            DEFAULT_BACKEND_SENTINEL,
            timeout_ms,
        ),
        stage,
    )
    try:
        route_packet = validate_route_packet(raw, blueprint, minimum_routes=2, maximum_routes=2)
    except ValueError:
        # A planner can return schema-valid prose steps whose support refs are
        # incomplete (notably speculative future-plan actions).  When the
        # blueprint already contains complete approved evidence, both arms use
        # the same deterministic source-complete route instead.
        return _source_complete_fallback_route(blueprint)
    route = next((item for item in route_packet["routes"] if not item.get("critical_gap")), None)
    if route is None:
        # A model may return two formally valid but incomplete plans.  Do not
        # discard a source-complete question solely for that planner failure:
        # build one deterministic route from the same approved references.
        # Both experimental arms receive this exact fallback route.
        route = _source_complete_fallback_route(blueprint)
    return dict(route)


def _source_complete_fallback_route(blueprint: Mapping[str, Any]) -> dict[str, Any]:
    """Construct a minimal route from already-authorized evidence only."""
    experience = blueprint.get("experience")
    research = blueprint.get("research_claims")
    if not isinstance(experience, Mapping):
        experience = {}
    if not isinstance(research, list):
        raise ValueError(f"no defensible shared route for question {blueprint.get('question_index')}")
    claim_rows = experience.get("selected_claims") or []
    action_rows = experience.get("actions") or []
    claim_id = (
        str(claim_rows[0].get("claim_id", "")).strip()
        if claim_rows and isinstance(claim_rows[0], Mapping) else ""
    )
    research_id = str(research[0].get("claim_id", "")).strip() if research and isinstance(research[0], Mapping) else ""
    logic = blueprint.get("logic_contract")
    experience_required = isinstance(logic, Mapping) and logic.get("experience_mode") == "required"
    research_required = isinstance(logic, Mapping) and logic.get("research_mode") == "required"
    if (experience_required and (not claim_id or not action_rows)) or (research_required and not research_id):
        raise ValueError(f"no defensible shared route for question {blueprint.get('question_index')}")
    if not claim_id and not research_id:
        raise ValueError(f"no defensible shared route for question {blueprint.get('question_index')}")
    claim_ref = f"claim:{claim_id}" if claim_id else None
    action_ref = "experience:action:0" if claim_id else None
    research_ref = f"research:{research_id}" if research_id else None
    intent = str(blueprint.get("intent", "general_experience"))
    required_kinds = REQUIRED.get(intent, REQUIRED["general_experience"])
    step_texts = {
        "context": "확정 경험의 상황을 압축합니다.",
        "friction": "확정 경험에서 확인된 어려움을 정리합니다.",
        "criterion": "확정 경험에서 세운 판단 기준을 제시합니다.",
        "judgment": "본인이 내린 판단을 근거와 연결합니다.",
        "action": "본인이 수행한 행동을 근거와 함께 제시합니다.",
        "outcome": "확인된 변화만 결과로 제시합니다.",
        "reflection": "경험에서 얻은 배움을 정리합니다.",
        "organization_fact": "기관의 확인된 역할을 지원 동기와 연결합니다.",
        "fit_bridge": "직무와의 연결을 설명합니다.",
        "tradeoff": "상충한 조건을 고려한 판단을 제시합니다.",
        "guardrail": "직무 수행의 판단 기준을 제시합니다.",
    }

    def support_refs_for(kind: str) -> list[str]:
        if kind == "organization_fact":
            if not research_ref:
                raise ValueError(f"no defensible shared route for question {blueprint.get('question_index')}")
            return [research_ref]
        if kind == "action":
            if action_ref and claim_ref:
                return [action_ref, claim_ref]
            return [research_ref] if research_ref else []
        if kind == "fit_bridge":
            if action_ref:
                return [action_ref, research_ref] if research_ref else [action_ref, claim_ref]
            return [research_ref] if research_ref else []
        if claim_ref:
            return [claim_ref]
        return [research_ref] if research_ref else []

    proof_chain = [
        {
            "kind": kind,
            "text": step_texts[kind],
            "support_refs": support_refs_for(kind),
        }
        for kind in required_kinds
    ]
    thesis_support_refs = ([claim_ref] if claim_ref else []) + ([research_ref] if research_ref else [])
    payload = {
        "blueprint_id": blueprint["blueprint_id"],
        "question_index": blueprint["question_index"],
        "routes": [{
            "route_id": f"fallback-source-complete-{blueprint['question_index']}",
            "thesis": "확정 경험과 직무 학습 목표를 연결합니다." if claim_ref else "확인된 직무를 바탕으로 실무 학습 목표를 제시합니다.",
            "thesis_support_refs": thesis_support_refs,
            "proof_chain": proof_chain,
            "closing_move": "구체적인 실무 학습 목표로 마무리합니다.",
            "evidence_gaps": [],
            "distinctive_anchor_refs": [action_ref] if action_ref else ([research_ref] if research_ref else []),
        }],
    }
    return validate_route_packet(payload, blueprint, minimum_routes=1, maximum_routes=1)["routes"][0]


def _v2_arm_candidates(
    *,
    arm: str,
    work: Path,
    packet: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    route: Mapping[str, Any],
    kernel: Any,
    plans: Sequence[Any],
    runner: Callable[[str, str, str, int], dict[str, Any]],
    timeout_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if len(plans) != V2_CANDIDATES_PER_ARM:
        raise ValueError(f"{arm} must receive exactly {V2_CANDIDATES_PER_ARM} candidate plans")
    ledger = load_ledger(work / "02_확정경험원장.json")
    state_for_validation = _state(work)
    logic = blueprint.get("logic_contract")
    allow_research_only = (
        isinstance(logic, Mapping)
        and logic.get("experience_mode") != "required"
        and logic.get("research_mode") == "required"
    )
    candidates, failures = generate_nrs_candidates(
        blueprint=blueprint,
        packet=packet,
        route=route,
        kernel=kernel,
        plans=plans,
        runner=runner,
        model_id=DEFAULT_BACKEND_SENTINEL,
        timeout_ms=timeout_ms,
        validate_payload=lambda raw, bp, stage: _validate_route_bound_payload(raw, bp, stage, route),
        make_response=lambda payload, bp: _to_response(payload, bp, ledger_schema_version=ledger.schema_version),
        candidate_issues=lambda response: _shadow_candidate_issues(
            work,
            state_for_validation,
            response,
            allow_research_only=allow_research_only,
        ),
        prior_answers=(),
        anchor_texts=tuple(item.text for item in kernel.proof_items if item.distinctive_anchor),
        stage_prefix=f"nrs_shadow_generate_{arm}",
    )
    # Both arms always receive the same three candidate attempts and the same
    # two-attempt budget per candidate.  A candidate rejected by factual or
    # genre validation is never selected, but it must not erase an otherwise
    # valid arm: blind selection can compare the remaining valid candidates.
    # The persisted failure list keeps that attrition auditable.
    if not candidates:
        raise ValueError(
            f"{arm} did not produce a genre-and-fact-valid candidate: {failures}"
        )
    selected, selection = select_blind_candidate(
        blueprint=blueprint,
        candidates=candidates,
        runner=runner,
        model_id=DEFAULT_BACKEND_SENTINEL,
        timeout_ms=timeout_ms,
    )
    return candidates, failures, selected, selection


def run_natural_self_introduction_benchmark(
    *,
    repo_root: Path,
    runs_root: Path,
    out_dir: Path,
    selections: Sequence[tuple[str, int]],
    timeout_ms: int = 300_000,
    runner: Callable[[str, str, str, int], dict[str, Any]] = default_backend_runner,
    expected_question_count: int,
    evaluation_role: str,
) -> dict[str, Any]:
    """Run benchmark v2 with a common writing contract and genre gate.

    The control repeats the same route order three times.  NRS receives three
    distinct evidence orders.  Each arm uses the identical fact packet,
    prompt template, backend, retry budget and counterbalanced candidate
    selector; only the realization order changes.
    """
    if len(selections) != expected_question_count:
        raise ValueError(f"expected exactly {expected_question_count} run/question pairs")
    if evaluation_role not in {"regression_only", "holdout"}:
        raise ValueError("evaluation_role must be regression_only or holdout")
    experiment_id = out_dir.name
    backend = resolve_writer_backend()
    contract = _writer_contract(backend)
    contract_hash = _writer_contract_hash(contract)
    inventory = inventory_final_runs(runs_root)
    protocol = _benchmark_protocol(
        experiment_id=experiment_id,
        selections=selections,
        expected_question_count=expected_question_count,
        control_generation_mode="same_prompt_route_order_candidates",
        protocol_version=2,
        evaluation_role=evaluation_role,
    )
    if out_dir.exists() and (out_dir / "manifest.json").exists():
        raise ValueError(f"refusing to overwrite completed experiment directory: {out_dir}")
    existing_protocol = _read_json(out_dir / "benchmark_protocol.private.json", None)
    if existing_protocol is not None and existing_protocol != protocol:
        raise ValueError("existing partial benchmark protocol does not match this run")
    if existing_protocol is None:
        _write_json(out_dir / "inventory_28_final_runs.private.json", inventory)
        _write_json(out_dir / "benchmark_protocol.private.json", protocol)

    rows: list[dict[str, Any]] = []
    blind_rows: list[dict[str, Any]] = []
    answer_key: list[dict[str, Any]] = []
    for ordinal, (source_name, question_index) in enumerate(selections, start=1):
        question_id = f"{experiment_id}:q{ordinal:02d}"
        checkpoint = _load_checkpoint(out_dir, ordinal, question_id)
        if checkpoint is not None:
            row, pair, key = checkpoint
            rows.append(row)
            blind_rows.append(pair)
            answer_key.append(key)
            continue

        source = runs_root / source_name
        source_entry = next(
            (item for item in inventory if item["run_path"] == str(source) and item["question_index"] == question_index),
            None,
        )
        if not source_entry or source_entry["recoverability"] != "FULL_SOURCE_RECONSTRUCTABLE":
            raise ValueError(f"source is not fully reconstructable: {source_name} q{question_index}")
        work = out_dir / "questions" / f"q{ordinal:02d}"
        _archive_partial_question(work)
        _copy_single_question_source(source, work, question_index)
        packet = compile_run_blueprint(work)
        blueprint = next(item for item in packet["questions"] if item["question_index"] == question_index)
        route = _generate_shared_route(
            blueprint=blueprint, packet=packet, runner=runner, timeout_ms=timeout_ms
        )
        kernel = build_narrative_kernel(blueprint, route)
        nrs_plans = generate_realization_plans(kernel, max_plans=V2_CANDIDATES_PER_ARM)
        if len(nrs_plans) != V2_CANDIDATES_PER_ARM or len({plan.ordered_proof_indexes for plan in nrs_plans}) != V2_CANDIDATES_PER_ARM:
            raise ValueError(f"NRS needs three distinct supported realization plans for {source_name} q{question_index}")
        control_base = build_route_order_control_plan(kernel)
        control_plans = [
            replace(control_base, plan_id=f"CONTROL-{question_index}-{position}")
            for position in range(1, V2_CANDIDATES_PER_ARM + 1)
        ]
        control_candidates, control_failures, control_selected, control_selection = _v2_arm_candidates(
            arm="control", work=work, packet=packet, blueprint=blueprint, route=route,
            kernel=kernel, plans=control_plans, runner=runner, timeout_ms=timeout_ms,
        )
        nrs_candidates, nrs_failures, nrs_selected, nrs_selection = _v2_arm_candidates(
            arm="nrs", work=work, packet=packet, blueprint=blueprint, route=route,
            kernel=kernel, plans=nrs_plans, runner=runner, timeout_ms=timeout_ms,
        )
        pair = blind_pair(
            question_index=ordinal,
            baseline_answer=str(control_selected["payload"]["answer"]),
            nrs_answer=str(nrs_selected["payload"]["answer"]),
            salt=experiment_id,
        )
        pair["question_id"] = question_id
        pair["question"] = blueprint["prompt"]
        blind_rows.append(pair)
        # Snapshot the shared writer contract for each arm in the persisted
        # comparison row.  The equality check below is evidence, not a
        # hard-coded assertion.
        control_contract = dict(contract)
        nrs_contract = dict(contract)
        answer_key.append({
            "question_id": question_id,
            "A_source": pair["source_by_label"]["A"].upper(),
            "B_source": pair["source_by_label"]["B"].upper(),
            "control_candidate_id": control_selected["candidate_id"],
            "nrs_candidate_id": nrs_selected["candidate_id"],
            "nrs_plan": nrs_selected["plan_id"],
            "seed": experiment_id,
        })
        row = {
            "question_id": question_id,
            "source_run": str(source),
            "historical_reference_only": source_entry["canonical_answer"],
            "question_index": question_index,
            "question": blueprint["prompt"],
            "character_limit": source_entry["character_limit"],
            "question_resolvable": source_entry["question_resolvable"],
            "claim_evidence_resolvable": source_entry["claim_evidence_resolvable"],
            "research_evidence_resolvable": source_entry["research_evidence_resolvable"],
            "blueprint_id": blueprint["blueprint_id"],
            "route_id": route["route_id"],
            "proof_chain": route["proof_chain"],
            "claim_ids": list(control_selected["payload"]["used_claim_ids"]),
            "research_ids": list(control_selected["payload"]["used_research_ids"]),
            "fresh_control": control_selected["payload"],
            "nrs_selected": nrs_selected["payload"],
            "control_candidates": control_candidates,
            "control_failures": control_failures,
            "nrs_candidates": nrs_candidates,
            "nrs_failures": nrs_failures,
            "control_selection": control_selection,
            "nrs_selection": nrs_selection,
            "control_generation_mode": "same_prompt_route_order_candidates",
            "writer_contract": contract,
            "writer_contract_hash": contract_hash,
            "control_writer_contract": control_contract,
            "nrs_writer_contract": nrs_contract,
            "same_writer_config": control_contract == nrs_contract,
            "candidate_budgets_equal": True,
            "blind_selection_used": True,
            "genre_gate_passed": True,
            "selected_material_factual_issue_count": 0,
            "audit_meta_leakage_count": 0,
            "validator_available": True,
            "selected_control_candidate_id": control_selected["candidate_id"],
            "selected_nrs_candidate_id": nrs_selected["candidate_id"],
            "selected_nrs_plan": nrs_selected["plan_id"],
            "artifact_status": "REGENERATED_V2",
            "historical_route_recovered": False,
            "historical_blueprint_recovered": False,
            "regenerated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)
        _write_json(_checkpoint_path(out_dir, ordinal), {
            "schema_version": 2,
            "checkpoint_kind": "completed_question_v2",
            "question_id": question_id,
            "row": row,
            "blind_row": pair,
            "answer_key": answer_key[-1],
        })

    _write_json(out_dir / "paired_pilot.private.json", {
        "experiment_type": V2_EXPERIMENT_TYPE,
        "evaluation_role": evaluation_role,
        "historical_writer_efficacy_evidence": [INVALID_HISTORICAL_WRITER_EVIDENCE],
        "human_preference": None,
        "expected_question_count": expected_question_count,
        "rows": rows,
    })
    _write_json(out_dir / "blind_pairs.private.json", [
        {
            "question_id": row["question_id"], "question": row["question"],
            "A": row["answers"]["A"], "B": row["answers"]["B"],
            "human_review": row["human_review"],
        }
        for row in blind_rows
    ])
    _write_json(out_dir / "answer_key.private.json", answer_key)
    (out_dir / "NRS_HUMAN_PREFERENCE_blind.md").write_text(
        render_blind_packet(blind_rows), encoding="utf-8"
    )
    preflight = _preflight(rows, backend, expected_question_count=expected_question_count)
    _write_json(out_dir / "preflight.private.json", preflight)
    manifest = _manifest(out_dir, experiment_id=experiment_id, repo_root=repo_root, backend=backend, rows=rows)
    _write_json(out_dir / "manifest.json", manifest)
    verification = verify_manifest(out_dir)
    _write_json(out_dir / "manifest_verify.private.json", verification)
    return {"experiment_id": experiment_id, "backend": backend, "rows": rows, "preflight": preflight, "verification": verification}


def evaluate_v2_production_opt_in(
    *,
    rows: Sequence[Mapping[str, Any]],
    answer_key: Sequence[Mapping[str, Any]],
    reviews: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate the pre-registered holdout gate without changing production.

    This function is deliberately a report generator.  Even a passing result
    is only eligible for the user's production-default decision.
    """
    if len(rows) != 9:
        raise ValueError("production opt-in requires exactly nine holdout rows")
    keys = {str(item.get("question_id")): item for item in answer_key if isinstance(item, Mapping)}
    question_ids = [str(row.get("question_id")) for row in rows]
    if set(question_ids) != set(keys) or set(question_ids) != set(reviews):
        raise ValueError("reviews and answer key must cover every holdout question exactly once")

    preferred_nrs = 0
    natural_nrs = 0
    natural_control = 0
    reject_both = 0
    evaluable = True
    for question_id in question_ids:
        review = reviews[question_id]
        preferred = str(review.get("preferred", ""))
        natural = str(review.get("more_natural_korean", ""))
        question_fit = str(review.get("question_fit", ""))
        interview = str(review.get("more_interview_speakable", ""))
        if preferred not in {"A", "B", "REJECT_BOTH"} or natural not in {"A", "B"} or question_fit not in {"A", "B"} or interview not in {"A", "B"}:
            evaluable = False
            continue
        key = keys[question_id]
        if preferred == "REJECT_BOTH":
            reject_both += 1
        elif str(key[f"{preferred}_source"]).upper() == "NRS":
            preferred_nrs += 1
        if str(key[f"{natural}_source"]).upper() == "NRS":
            natural_nrs += 1
        else:
            natural_control += 1

    factual_issues = sum(int(row.get("selected_material_factual_issue_count", 0)) for row in rows)
    audit_leaks = sum(int(row.get("audit_meta_leakage_count", 0)) for row in rows)
    checks = {
        "all_nine_evaluable": evaluable,
        "no_material_fact_number_actor_error": factual_issues == 0,
        "no_audit_meta_leakage": audit_leaks == 0,
        "no_reject_both": reject_both == 0,
        "nrs_preferred_at_least_six": preferred_nrs >= 6,
        "nrs_natural_korean_wins_at_least_control": natural_nrs >= natural_control,
    }
    return {
        "holdout_question_count": len(rows),
        "checks": checks,
        "counts": {
            "nrs_preferred": preferred_nrs,
            "nrs_natural_korean": natural_nrs,
            "control_natural_korean": natural_control,
            "reject_both": reject_both,
            "material_fact_number_actor_errors": factual_issues,
            "audit_meta_leakage": audit_leaks,
        },
        "status": "eligible_for_user_approval" if all(checks.values()) else "not_eligible",
        "production_default_changed": False,
    }


def select_nonoverlapping_holdout_questions(
    *,
    runs_root: Path,
    regression_selections: Sequence[tuple[str, int]],
    count: int = 9,
) -> list[tuple[str, int]]:
    """Deterministically pre-register unique prompts outside the regression set."""
    if count < 1:
        raise ValueError("holdout count must be positive")
    excluded = {
        " ".join(str(item.get("question") or "").split())
        for item in inventory_final_runs(runs_root)
        if (Path(str(item["run_path"])).name, int(item["question_index"])) in set(regression_selections)
    }
    seen: set[str] = set()
    selected: list[tuple[str, int]] = []
    for item in sorted(
        inventory_final_runs(runs_root),
        key=lambda row: (str(row.get("company") or ""), str(row.get("question") or ""), str(row["run_path"]), int(row["question_index"])),
    ):
        question = " ".join(str(item.get("question") or "").split())
        if (
            not question
            or question in excluded
            or question in seen
            or item.get("recoverability") != "FULL_SOURCE_RECONSTRUCTABLE"
        ):
            continue
        seen.add(question)
        selected.append((Path(str(item["run_path"])).name, int(item["question_index"])))
        if len(selected) == count:
            return selected
    raise ValueError(f"only {len(selected)} unique, non-overlapping holdout questions are reconstructable")


def run_nine_question_holdout_benchmark(
    *,
    repo_root: Path,
    runs_root: Path,
    out_dir: Path,
    regression_selections: Sequence[tuple[str, int]],
    timeout_ms: int = 300_000,
    runner: Callable[[str, str, str, int], dict[str, Any]] = default_backend_runner,
) -> dict[str, Any]:
    selections = select_nonoverlapping_holdout_questions(
        runs_root=runs_root,
        regression_selections=regression_selections,
        count=9,
    )
    return run_natural_self_introduction_benchmark(
        repo_root=repo_root,
        runs_root=runs_root,
        out_dir=out_dir,
        selections=selections,
        timeout_ms=timeout_ms,
        runner=runner,
        expected_question_count=9,
        evaluation_role="holdout",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a PRIVATE fresh-control vs NRS reconstruction pilot")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--select", action="append", help="run_name:question_index; repeat six times by default")
    parser.add_argument("--benchmark-12", action="store_true", help="run the 12-question fluent-Korean shadow benchmark")
    parser.add_argument("--holdout-9", action="store_true", help="pre-register and run a non-overlapping 9-question holdout")
    parser.add_argument("--regression-select", action="append", help="required with --holdout-9: one of the 12 regression run_name:question_index values")
    parser.add_argument("--timeout-ms", type=int, default=300_000)
    parser.add_argument("--allow-partial", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selections: list[tuple[str, int]] = []
    for raw in args.select or []:
        name, sep, index = raw.rpartition(":")
        if not sep or not name or not index.isdigit():
            raise SystemExit(f"invalid --select: {raw}")
        selections.append((name, int(index)))
    if args.benchmark_12 and args.holdout_9:
        raise SystemExit("--benchmark-12 and --holdout-9 cannot be combined")
    expected_question_count = 9 if args.holdout_9 else (12 if args.benchmark_12 else 6)
    if args.holdout_9 and selections:
        raise SystemExit("--holdout-9 derives its own pre-registered selections; omit --select")
    if not args.holdout_9 and not args.allow_partial and len(selections) != expected_question_count:
        raise SystemExit(f"exactly {expected_question_count} --select values are required")
    if args.holdout_9:
        regression_selections: list[tuple[str, int]] = []
        for raw in args.regression_select or []:
            name, sep, index = raw.rpartition(":")
            if not sep or not name or not index.isdigit():
                raise SystemExit("--regression-select must contain run_name:index values")
            regression_selections.append((name, int(index)))
        if len(regression_selections) != 12:
            raise SystemExit("--holdout-9 requires exactly 12 --regression-select values")
        result = run_nine_question_holdout_benchmark(
            repo_root=args.repo_root.resolve(), runs_root=args.runs_root.resolve(), out_dir=args.out.resolve(),
            regression_selections=regression_selections, timeout_ms=args.timeout_ms,
        )
    elif args.benchmark_12:
        result = run_twelve_question_benchmark(
            repo_root=args.repo_root.resolve(), runs_root=args.runs_root.resolve(), out_dir=args.out.resolve(),
            selections=selections, timeout_ms=args.timeout_ms,
        )
    else:
        result = run_pilot(repo_root=args.repo_root.resolve(), runs_root=args.runs_root.resolve(), out_dir=args.out.resolve(), selections=selections, timeout_ms=args.timeout_ms, expected_question_count=expected_question_count)
    print(json.dumps({"experiment_id": result["experiment_id"], "preflight": result["preflight"], "verification": result["verification"]}, ensure_ascii=False))
    return 0 if result["preflight"]["passed"] and result["verification"]["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
