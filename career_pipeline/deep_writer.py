"""Evidence-to-Argument Search writer for high-stakes Korean self-introductions.

The writer spends model compute on choosing *what to prove* before wording.
Weak argument routes are replaced at the planning layer; only residual style
problems are repaired at the prose layer.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import argparse
import json
import subprocess
import tempfile

from .argument_search import (
    DIMENSION_LABELS, SEMANTIC_DIMENSIONS, ArgumentSearchError,
    aggregate_judgements, build_story_kernel, pareto_frontier,
    select_portfolio_routes, short_partial_duplicate_pairs,
    validate_judgement, validate_route_packet,
)
from .copyeditor_adapter import _resolved_codex_command
from .model_policy import resolve_model
from .models import DraftResponse, ValidationIssue
from .narrative_compiler import (
    NarrativeCompilerError, _compact_blueprint, _to_response,
    _validate_generated_payload, compile_run_blueprint,
)
from .narrative_realization_shadow import (
    NarrativeRealizationError, build_narrative_kernel, generate_realization_plans,
)
from .nrs_shadow_benchmark import (
    generate_nrs_candidates,
    missing_selected_metric,
    select_blind_candidate,
)
from .preference_writer import (
    _candidate_issues, _portfolio_issues, _preference_profile, _state,
)
from .profile_schema import load_ledger
from .semantic_preference import (
    load_semantic_preference, semantic_preference_directives,
    semantic_preference_weights,
)
from .state import write_json
from .style_diagnostics import diagnose_text
from .self_introduction_genre import GENRE_CONTRACT_VERSION, blocking_genre_issues
from .writing_preference import preference_directives, preference_distance

ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]
DEFAULT_BACKEND_SENTINEL = "__codex_default_backend__"


def _reported_model_id(model_id: str) -> str | None:
    return None if model_id == DEFAULT_BACKEND_SENTINEL else model_id

ROUTE_JUDGE_ROLES = (
    ("hiring_manager", "직무 수행 가능성과 문항 적합성을 본다. 실제 판단·행동 증거를 우선한다."),
    ("skeptical_interviewer", "면접에서 한 문장씩 캐물어도 방어 가능한지 본다. 다른 지원자로 바꿔도 성립하는 계획을 낮게 평가한다."),
    ("narrative_editor", "논증의 긴장·전개·기억 가능성을 본다. polished generic prose로 쉽게 변할 계획을 낮게 평가한다."),
)
PROSE_MODES = (
    ("natural_precision", "정확하지만 보고서처럼 굳지 않은 자연스러운 한국어로 쓴다."),
    ("restrained_distinctive", "과장 없이 지원자만의 장면·판단·행동 디테일을 살린다."),
)
DEFAULT_PROSE_STRATEGY = "nrs_v2"
PROSE_STRATEGIES = frozenset({DEFAULT_PROSE_STRATEGY, "deep_route"})
NRS_CANDIDATE_BUDGET = 3
NRS_RETRY_ATTEMPTS = 2
ROUTE_RESELECT_CODES = {
    "question_gap", "weak_thesis", "generic_scene", "action_blur",
    "causal_gap", "forced_job_bridge", "company_brochure",
    "overloaded_answer", "portfolio_redundancy", "policy_tradeoff_gap",
}
SURFACE_REPAIR_CODES = {"generic_closing", "artificial_voice"}
CRITIC_CODES = tuple(sorted(ROUTE_RESELECT_CODES | SURFACE_REPAIR_CODES | {"evidence_risk"}))

_ROUTE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["blueprint_id", "question_index", "routes"],
    "properties": {
        "blueprint_id": {"type": "string"},
        "question_index": {"type": "integer"},
        "routes": {"type": "array", "minItems": 2, "maxItems": 5, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["route_id", "argument_posture", "thesis", "thesis_support_refs",
                         "proof_chain", "closing_move", "evidence_gaps", "distinctive_anchor_refs"],
            "properties": {
                "route_id": {"type": "string"},
                "argument_posture": {"type": "string"},
                "thesis": {"type": "string"},
                "thesis_support_refs": {"type": "array", "items": {"type": "string"}},
                "proof_chain": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["kind", "text", "support_refs"],
                    "properties": {
                        "kind": {"type": "string"},
                        "text": {"type": "string"},
                        "support_refs": {"type": "array", "items": {"type": "string"}},
                    }}},
                "closing_move": {"type": "string"},
                "evidence_gaps": {"type": "array", "items": {"type": "string"}},
                "distinctive_anchor_refs": {"type": "array", "items": {"type": "string"}},
            }}},
    },
}
_JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["routes"],
    "properties": {"routes": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["route_id", "scores", "fatal_issue"],
        "properties": {
            "route_id": {"type": "string"},
            "scores": {"type": "object", "additionalProperties": False,
                       "required": list(SEMANTIC_DIMENSIONS),
                       "properties": {d: {"type": "integer", "minimum": 0, "maximum": 4}
                                      for d in SEMANTIC_DIMENSIONS}},
            "fatal_issue": {"type": "boolean"},
        }}}},
}
_CRITIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["issues"],
    "properties": {"issues": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["question_index", "code", "severity", "message", "repair_instruction"],
        "properties": {
            "question_index": {"type": "integer"},
            "code": {"type": "string", "enum": list(CRITIC_CODES)},
            "severity": {"type": "string", "enum": ["MINOR", "MATERIAL", "HARD"]},
            "message": {"type": "string"},
            "repair_instruction": {"type": "string"},
        }}}},
}

_NRS_CANDIDATE_SELECTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["ranking"],
    "properties": {"ranking": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "rank"],
        "properties": {
            "candidate_id": {"type": "string"},
            "rank": {"type": "integer", "minimum": 1},
        },
    }}},
}

class DeepWriterError(ValueError):
    pass

def _schema(stage: str) -> dict[str, Any]:
    if stage.startswith("deep_route_plan"):
        return _ROUTE_SCHEMA
    if stage.startswith("deep_route_judge") or stage.startswith("deep_prose_judge"):
        return _JUDGE_SCHEMA
    if stage.startswith("deep_portfolio_critic"):
        return _CRITIC_SCHEMA
    if stage.startswith(("nrs_shadow_candidate_select", "nrs_production_candidate_select")):
        return _NRS_CANDIDATE_SELECTION_SCHEMA
    from .narrative_compiler import _GENERATION_SCHEMA
    return _GENERATION_SCHEMA

def subprocess_model_runner(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="career-deep-writer-") as temp:
        root = Path(temp)
        schema = root / "schema.json"
        schema.write_text(json.dumps(_schema(stage), ensure_ascii=False), encoding="utf-8")
        try:
            completed = subprocess.run(
                _resolved_codex_command(root, schema, resolve=True, model_id=model_id),
                input=prompt, text=True, encoding="utf-8", capture_output=True,
                timeout=max(1, timeout_ms // 1000 + 30),
            )
        except subprocess.TimeoutExpired as error:
            raise DeepWriterError(f"model call timed out: {stage}") from error
    if completed.returncode:
        detail = completed.stderr.strip().replace("\n", " ")[-1200:]
        suffix = f": {detail}" if detail else ""
        raise DeepWriterError(f"model call failed: {stage}{suffix}")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise DeepWriterError(f"non-object model output: {stage}")
    return value

def _coerce(value: dict[str, Any] | str, stage: str) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise DeepWriterError(f"invalid object: {stage}")
    return value

def _semantic_profile(run_dir: Path, state: Mapping[str, Any], explicit: Path | None) -> dict[str, Any] | None:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if state.get("semantic_writing_preference_profile"):
        candidates.append(Path(str(state["semantic_writing_preference_profile"])))
    if state.get("root"):
        candidates.append(Path(str(state["root"])) / ".career_profile" / "semantic_writing_preference.json")
    for path in candidates:
        resolved = path if path.is_absolute() else run_dir / path
        profile = load_semantic_preference(resolved.resolve())
        if profile:
            return profile
    return None

def _route_prompt(blueprint: Mapping[str, Any], packet: Mapping[str, Any], kernel: Mapping[str, Any],
                  route_count: int, directives: Sequence[str]) -> str:
    motivation_contract = (
        " For a motivation question, the applicant may state a present-tense purpose for this "
        "active application when it is derived only from the target role, approved organization/job "
        "facts, and confirmed experience. Treat that present application intent as an answer to the "
        "current prompt, not as an unsupported historical fact. Do not invent a past origin story, "
        "long-held value, emotion, or triggering event."
        if blueprint.get("intent") == "motivation"
        else ""
    )
    return (
        f"Create exactly {route_count} materially different argument plans, not prose. "
        "Every factual note must cite support refs from story_kernel.support. "
        "Do not invent historical motives, trade-offs or reasons: if unsupported, list the gap. "
        + motivation_contract + " "
        "Routes must differ in what they prove, not wording. Apply the applicant-swap test: "
        "another qualified applicant should not be able to use the same argument unchanged. JSON only.\n"
        + json.dumps({
            "blueprint": _compact_blueprint(blueprint, packet),
            "story_kernel": kernel,
            "semantic_preferences": list(directives),
        }, ensure_ascii=False)
    )

def _judge_prompt(blueprint: Mapping[str, Any], routes: Sequence[Mapping[str, Any]],
                  role: str, role_instruction: str, directives: Sequence[str]) -> str:
    visible = [{
        "route_id": r["route_id"], "argument_posture": r.get("argument_posture"),
        "thesis": r.get("thesis"), "proof_chain": r.get("proof_chain"),
        "evidence_gaps": r.get("evidence_gaps"),
        "missing_required_kinds": r.get("missing_required_kinds"),
    } for r in routes]
    motivation_contract = (
        " For this motivation question, a present-tense application purpose grounded only in the "
        "target role, approved organization/job facts, and confirmed experience is permitted and "
        "is not an invented historical fact. A fabricated past origin, value, emotion, or event remains fatal."
        if blueprint.get("intent") == "motivation"
        else ""
    )
    return (
        f"You are the {role} evaluator. {role_instruction} Score every route independently 0..4 "
        "on each fixed dimension. These are plans: do not reward polished wording. "
        "fatal_issue=true only when the route needs invented facts or misses a central requirement. "
        + motivation_contract + " "
        "Candidate order is arbitrary. JSON only.\n"
        + json.dumps({"question": blueprint.get("prompt"), "rubric": DIMENSION_LABELS,
                      "preferences": list(directives), "routes": visible}, ensure_ascii=False)
    )

def _ordered(routes: Sequence[Mapping[str, Any]], offset: int, reverse: bool) -> list[Mapping[str, Any]]:
    rows = list(routes)
    if rows:
        offset %= len(rows)
        rows = rows[offset:] + rows[:offset]
    return list(reversed(rows)) if reverse else rows

def _judge_routes(blueprint: Mapping[str, Any], routes: Sequence[Mapping[str, Any]],
                  judges: Sequence[str], directives: Sequence[str], timeout_ms: int,
                  runner: ModelRunner, calls: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ids = {str(r["route_id"]) for r in routes}
    result = []
    for mi, model in enumerate(judges):
        for ri, (role, instruction) in enumerate(ROUTE_JUDGE_ROLES):
            for repeat in range(2):
                stage = f"deep_route_judge_q{blueprint['question_index']}_{mi}_{ri}_{repeat}"
                raw = _coerce(runner(stage, _judge_prompt(
                    blueprint, _ordered(routes, mi + ri + repeat, bool(repeat)),
                    role, instruction, directives), model, timeout_ms), stage)
                result.append(validate_judgement(raw, ids))
                calls.append({"stage": stage, "model_id": _reported_model_id(model), "role": role, "balanced_order": repeat})
    return result

def _prose_prompt(blueprint: Mapping[str, Any], packet: Mapping[str, Any],
                  route: Mapping[str, Any], mode: tuple[str, str],
                  surface: Sequence[str], semantic: Sequence[str],
                  prior: Sequence[Mapping[str, Any]], repair: str = "",
                  original: Mapping[str, Any] | None = None) -> str:
    task = "Repair only the stated surface problem." if repair else "Render the selected route."
    return (
        f"{task} Use route logic without headings. Answer the prompt in the first two sentences. "
        "Use only blueprint evidence and preserve causality/contribution limits. "
        "Sound like a capable applicant, not a brochure or work manual. JSON only.\n"
        + json.dumps({
            "blueprint": _compact_blueprint(blueprint, packet), "route": route,
            "mode": {"name": mode[0], "instruction": mode[1]},
            "surface_preferences": list(surface), "semantic_preferences": list(semantic),
            "prior_answers": list(prior), "repair_instruction": repair, "original": original,
        }, ensure_ascii=False)
    )

def _candidate_id(payload: Mapping[str, Any], mode: str) -> str:
    from hashlib import sha256
    return "P" + sha256((mode + "\0" + str(payload.get("answer", ""))).encode()).hexdigest()[:12].upper()

def _prose_judge_prompt(blueprint: Mapping[str, Any], route: Mapping[str, Any],
                        candidates: Sequence[Mapping[str, Any]], directives: Sequence[str]) -> str:
    return (
        "Score each answer 0..4 on the fixed dimensions. Candidate order is arbitrary. "
        "Reward faithful natural realization of the selected route; penalize filler, brochure/checklist "
        "language, unsupported claims and replaceable generic prose. JSON only.\n"
        + json.dumps({
            "question": blueprint.get("prompt"), "route": route, "rubric": DIMENSION_LABELS,
            "preferences": list(directives),
            "routes": [{"route_id": c["candidate_id"], "answer": c["payload"]["answer"]} for c in candidates],
        }, ensure_ascii=False)
    )

def _generate_prose(run_dir: Path, state: Mapping[str, Any], packet: Mapping[str, Any],
                    blueprint: Mapping[str, Any], route: Mapping[str, Any],
                    writer: str, judges: Sequence[str], timeout_ms: int, runner: ModelRunner,
                    calls: list[dict[str, Any]], surface_profile: Mapping[str, Any] | None,
                    semantic_profile: Mapping[str, Any] | None, prior: Sequence[Mapping[str, Any]],
                    schema_version: int, count: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    valid, failures = [], []
    for pos, mode in enumerate(PROSE_MODES[:count], 1):
        stage = f"deep_prose_generate_q{blueprint['question_index']}_{pos}"
        raw = _coerce(runner(stage, _prose_prompt(
            blueprint, packet, route, mode, preference_directives(surface_profile),
            semantic_preference_directives(semantic_profile), prior), writer, timeout_ms), stage)
        calls.append({"stage": stage, "model_id": _reported_model_id(writer), "role": "route_bound_prose_writer"})
        try:
            payload = _validate_generated_payload(raw, blueprint, stage)
        except NarrativeCompilerError as error:
            failures.append({"stage": stage, "codes": ["payload_contract"], "message": str(error)})
            continue
        response = _to_response(payload, blueprint, ledger_schema_version=schema_version)
        issues = _candidate_issues(run_dir, state, response)
        if issues:
            failures.append({"stage": stage, "codes": [x.code for x in issues]})
            continue
        valid.append({
            "candidate_id": _candidate_id(payload, mode[0]), "payload": payload,
            "mode": mode[0], "style_risk": diagnose_text(payload["answer"]).style_risk_score,
            "surface_distance": preference_distance(payload["answer"], surface_profile),
        })
    if not valid:
        raise DeepWriterError(f"all prose realisations failed for question {blueprint['question_index']}")
    if len(valid) == 1:
        return valid[0]["payload"], failures
    pseudo = [{
        "route_id": c["candidate_id"], "intent": route.get("intent"),
        "argument_posture": route.get("argument_posture"), "thesis": c["payload"]["answer"],
        "proof_chain": [], "critical_gap": False,
    } for c in valid]
    judgements = []
    ids = {c["candidate_id"] for c in valid}
    for mi, model in enumerate(judges):
        for repeat in range(2):
            order = list(reversed(valid)) if repeat else valid
            stage = f"deep_prose_judge_q{blueprint['question_index']}_{mi}_{repeat}"
            raw = _coerce(runner(stage, _prose_judge_prompt(
                blueprint, route, order, semantic_preference_directives(semantic_profile)),
                model, timeout_ms), stage)
            judgements.append(validate_judgement(raw, ids))
            calls.append({"stage": stage, "model_id": _reported_model_id(model), "role": "blind_prose_judge", "balanced_order": repeat})
    scored = aggregate_judgements(pseudo, judgements,
        semantic_preference_weights=semantic_preference_weights(semantic_profile))
    selected = str(scored[0]["route_id"])
    return next(c["payload"] for c in valid if c["candidate_id"] == selected), failures


def _generate_nrs_prose(
    run_dir: Path,
    state: Mapping[str, Any],
    packet: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    route: Mapping[str, Any],
    writer: str,
    judges: Sequence[str],
    timeout_ms: int,
    runner: ModelRunner,
    calls: list[dict[str, Any]],
    surface_profile: Mapping[str, Any] | None,
    semantic_profile: Mapping[str, Any] | None,
    prior: Sequence[Mapping[str, Any]],
    schema_version: int,
    count: int,
    selections: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Render one route through Narrative Realization Search.

    The NRS path is the production default.  It keeps the proof kernel and
    writer prompt separate from validation-only constraints, then selects among
    valid, differently ordered candidates through a counterbalanced blind
    ranking.  If NRS cannot yield a valid candidate, the established route
    writer remains a fail-closed fallback and must clear the same genre gate.
    """
    question_index = int(blueprint["question_index"])

    def fallback(reason: str, failures: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        calls.append({
            "stage": f"nrs_production_fallback_q{question_index}",
            "model_id": _reported_model_id(writer),
            "role": "nrs_v2_control_fallback",
            "reason": reason,
        })
        payload, fallback_failures = _generate_prose(
            run_dir, state, packet, blueprint, route, writer, judges, timeout_ms,
            runner, calls, surface_profile, semantic_profile, prior, schema_version, count,
        )
        genre = blocking_genre_issues(str(payload["answer"]))
        if genre:
            codes = ", ".join(issue.code for issue in genre)
            raise DeepWriterError(
                f"NRS fallback failed self-introduction genre gate for question {question_index}: {codes}"
            )
        if missing_selected_metric(blueprint, str(payload["answer"])):
            raise DeepWriterError(
                f"NRS fallback omitted a selected approved metric for question {question_index}"
            )
        selections.append({
            "question_index": question_index,
            "selection_source": "deep_route_fallback",
            "reason": reason,
            "selected_candidate_id": None,
            "valid_candidate_count": 0,
            "failures": failures,
        })
        return payload, failures + fallback_failures

    try:
        kernel = build_narrative_kernel(blueprint, route)
        plans = generate_realization_plans(kernel, max_plans=NRS_CANDIDATE_BUDGET)
    except NarrativeRealizationError as error:
        return fallback("kernel_construction_failed", [{
            "stage": f"nrs_production_generate_q{question_index}",
            "codes": ["nrs_kernel"],
            "message": str(error),
        }])
    if not plans:
        return fallback("no_supported_realization_plan", [{
            "stage": f"nrs_production_generate_q{question_index}",
            "codes": ["nrs_plan"],
            "message": "no supported realization plan",
        }])

    def tracked_runner(stage: str, prompt: str, model_id: str, timeout: int) -> dict[str, Any] | str:
        role = (
            "nrs_v2_candidate_selection"
            if stage.startswith("nrs_production_candidate_select")
            else "nrs_v2_realization"
        )
        calls.append({"stage": stage, "model_id": _reported_model_id(model_id), "role": role})
        return runner(stage, prompt, model_id, timeout)

    candidates, failures = generate_nrs_candidates(
        blueprint=blueprint,
        packet=packet,
        route=route,
        kernel=kernel,
        plans=plans,
        runner=tracked_runner,
        model_id=writer,
        timeout_ms=timeout_ms,
        validate_payload=_validate_generated_payload,
        make_response=lambda payload, bp: _to_response(
            payload, bp, ledger_schema_version=schema_version,
        ),
        candidate_issues=lambda response: _candidate_issues(run_dir, state, response),
        genre_issues=blocking_genre_issues,
        prior_answers=prior,
        surface_preferences=preference_directives(surface_profile),
        semantic_preferences=semantic_preference_directives(semantic_profile),
        anchor_texts=tuple(item.text for item in kernel.proof_items if item.distinctive_anchor),
        stage_prefix="nrs_production_generate",
    )
    if not candidates:
        return fallback("no_valid_nrs_candidate", failures)
    try:
        selected, selection = select_blind_candidate(
            blueprint=blueprint,
            candidates=candidates,
            runner=tracked_runner,
            model_id=judges[0],
            timeout_ms=timeout_ms,
            stage_prefix="nrs_production_candidate_select",
        )
    except Exception as error:
        return fallback("candidate_selection_failed", failures + [{
            "stage": f"nrs_production_candidate_select_q{question_index}",
            "codes": ["nrs_candidate_selection"],
            "message": str(error),
        }])
    selections.append({
        "question_index": question_index,
        "selection_source": "nrs_v2",
        "candidate_budget": NRS_CANDIDATE_BUDGET,
        "retry_attempts_per_candidate": NRS_RETRY_ATTEMPTS,
        "valid_candidate_count": len(candidates),
        "selected_candidate_id": selection.get("selected_candidate_id"),
        "selection": selection,
    })
    return dict(selected["payload"]), failures


def _generate_prose_with_strategy(
    strategy: str,
    run_dir: Path,
    state: Mapping[str, Any],
    packet: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    route: Mapping[str, Any],
    writer: str,
    judges: Sequence[str],
    timeout_ms: int,
    runner: ModelRunner,
    calls: list[dict[str, Any]],
    surface_profile: Mapping[str, Any] | None,
    semantic_profile: Mapping[str, Any] | None,
    prior: Sequence[Mapping[str, Any]],
    schema_version: int,
    count: int,
    selections: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if strategy == DEFAULT_PROSE_STRATEGY:
        return _generate_nrs_prose(
            run_dir, state, packet, blueprint, route, writer, judges, timeout_ms,
            runner, calls, surface_profile, semantic_profile, prior, schema_version,
            count, selections,
        )
    return _generate_prose(
        run_dir, state, packet, blueprint, route, writer, judges, timeout_ms,
        runner, calls, surface_profile, semantic_profile, prior, schema_version, count,
    )

def _critic_prompt(packet: Mapping[str, Any], routes: Mapping[int, Mapping[str, Any]],
                   payloads: Sequence[Mapping[str, Any]]) -> str:
    return (
        "Review the application as one portfolio. Identify only material defects. "
        "Ask: does it prove the exact prompt, could another applicant submit it unchanged, "
        "and can every important sentence survive interview follow-up? Structural problems "
        "must be marked separately from surface voice problems. JSON only.\n"
        + json.dumps({"portfolio": packet.get("portfolio"),
                      "selected_routes": {str(k): v for k, v in routes.items()},
                      "drafts": list(payloads)}, ensure_ascii=False)
    )

def _validate_critic(raw: Mapping[str, Any], indexes: set[int]) -> list[dict[str, Any]]:
    rows = raw.get("issues")
    if not isinstance(rows, list):
        raise DeepWriterError("critic issues missing")
    out = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise DeepWriterError("invalid critic issue")
        q = row.get("question_index"); code = row.get("code"); severity = row.get("severity")
        if not isinstance(q, int) or q not in indexes or code not in CRITIC_CODES or severity not in {"MINOR","MATERIAL","HARD"}:
            raise DeepWriterError("critic issue contract mismatch")
        out.append({"question_index": q, "code": str(code), "severity": str(severity),
                    "message": str(row.get("message","")),
                    "repair_instruction": str(row.get("repair_instruction",""))})
    return out

def _write_gap(run_dir: Path, question_index: int, routes: Sequence[Mapping[str, Any]]) -> None:
    payload = {
        "question_index": question_index,
        "reason": "no_defensible_argument_route",
        "routes": [{"route_id": r.get("route_id"), "missing_required_kinds": r.get("missing_required_kinds"),
                    "evidence_gaps": r.get("evidence_gaps"), "fatal_judge_votes": r.get("fatal_judge_votes")}
                   for r in routes],
    }
    write_json(run_dir / "05_서사정보공백.json", payload)
    lines = ["# 서사 정보 공백", "", f"- 문항: {question_index}",
             "- 이유: 검증 가능한 근거만으로 방어 가능한 논증 경로가 없습니다.",
             "- 해결: 동기·판단 기준·제약·트레이드오프 등 실제 근거를 보강해야 합니다."]
    (run_dir / "05_서사정보공백.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

def generate_deep_draft(
    run_dir: Path, *, packet: dict[str, Any] | None = None,
    writer_model_id: str | None = None, judge_model_ids: Sequence[str] = (),
    route_count: int = 3, prose_realisations: int = 2, timeout_ms: int = 300_000,
    prose_strategy: str = DEFAULT_PROSE_STRATEGY,
    surface_preference_profile_path: Path | None = None,
    semantic_preference_profile_path: Path | None = None,
    runner: ModelRunner = subprocess_model_runner,
) -> tuple[list[DraftResponse], dict[str, Any]]:
    run_dir = run_dir.resolve()
    state = _state(run_dir)
    packet = packet or compile_run_blueprint(run_dir)
    writer = writer_model_id or resolve_model("sol").model_id
    writer_backend = (
        "codex_cli_default"
        if writer == DEFAULT_BACKEND_SENTINEL
        else "configured_model_id"
    )
    if not writer:
        if judge_model_ids:
            raise DeepWriterError(
                "writer model is required when explicit judge model IDs are configured"
            )
        if runner is subprocess_model_runner:
            # The local Codex CLI may have a valid default model even when its
            # model identity is intentionally unavailable to this process.
            # Use that configured backend without inventing or persisting a
            # model ID.  The import is lazy because the paired-reconstruction
            # module reuses this writer.
            from .nrs_paired_reconstruction import (
                default_backend_runner,
                resolve_writer_backend,
            )

            backend = resolve_writer_backend()
            if not backend.get("command_available"):
                raise DeepWriterError("writer backend is unavailable")
            runner = default_backend_runner
            writer_backend = str(backend.get("writer_backend") or "codex_cli_default")
        else:
            writer_backend = "injected_runner"
        writer = DEFAULT_BACKEND_SENTINEL
    judges = tuple(x for x in judge_model_ids if x) or (writer,)
    reported_writer = _reported_model_id(writer)
    reported_judges = [_reported_model_id(model) for model in judges]
    if not 2 <= route_count <= 5:
        raise ValueError("route_count must be 2..5")
    maximum_realisations = (
        NRS_CANDIDATE_BUDGET
        if prose_strategy == DEFAULT_PROSE_STRATEGY
        else len(PROSE_MODES)
    )
    if not 1 <= prose_realisations <= maximum_realisations:
        raise ValueError("invalid prose_realisations")
    if prose_strategy not in PROSE_STRATEGIES:
        raise ValueError(f"unsupported prose_strategy: {prose_strategy}")
    surface_profile = _preference_profile(run_dir, state, surface_preference_profile_path)
    semantic_profile = _semantic_profile(run_dir, state, semantic_preference_profile_path)
    sdirect = semantic_preference_directives(semantic_profile)
    sweights = semantic_preference_weights(semantic_profile)
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
    blueprints = [x for x in packet.get("questions", []) if isinstance(x, Mapping)]
    calls, route_report = [], []
    selectable: dict[int, list[dict[str, Any]]] = {}
    bmap = {int(x["question_index"]): x for x in blueprints}

    for blueprint in blueprints:
        q = int(blueprint["question_index"])
        kernel = build_story_kernel(blueprint)
        stage = f"deep_route_plan_q{q}"
        raw = _coerce(runner(stage, _route_prompt(
            blueprint, packet, kernel, route_count, sdirect), writer, timeout_ms), stage)
        calls.append({"stage": stage, "model_id": reported_writer, "role": "argument_route_planner"})
        try:
            route_packet = validate_route_packet(raw, blueprint,
                minimum_routes=route_count, maximum_routes=route_count)
        except ArgumentSearchError as error:
            raise DeepWriterError(str(error)) from error
        routes = route_packet["routes"]
        judgements = _judge_routes(blueprint, routes, judges, sdirect, timeout_ms, runner, calls)
        scored = aggregate_judgements(routes, judgements, semantic_preference_weights=sweights)
        frontier = pareto_frontier(scored)
        choices = [r for r in frontier if not r.get("critical_gap") and int(r.get("fatal_judge_votes",0)) == 0]
        if not choices:
            _write_gap(run_dir, q, scored)
            raise DeepWriterError(f"question {q} has no defensible route; see 05_서사정보공백.md")
        selectable[q] = choices
        route_report.append({"question_index": q, "story_kernel": kernel, "routes": scored,
                             "selectable_route_ids": [r["route_id"] for r in choices]})

    portfolio = select_portfolio_routes(selectable)
    routes_by_q = {q: next(dict(r) for r in selectable[q] if r["route_id"] == rid)
                   for q, rid in portfolio["selected"].items()}
    payloads, prose_failures, prior = {}, {}, []
    nrs_selections: list[dict[str, Any]] = []
    for q in sorted(routes_by_q):
        payload, failures = _generate_prose_with_strategy(
            prose_strategy, run_dir, state, packet, bmap[q], routes_by_q[q], writer, judges,
            timeout_ms, runner, calls, surface_profile, semantic_profile, prior,
            ledger.schema_version, prose_realisations, nrs_selections)
        payloads[q] = payload; prose_failures[q] = failures
        prior.append({"question_index": q, "answer": payload["answer"]})

    def payload_list() -> list[dict[str, Any]]:
        return [payloads[q] for q in sorted(payloads)]

    stage = "deep_portfolio_critic"
    critic = _validate_critic(_coerce(runner(
        stage, _critic_prompt(packet, routes_by_q, payload_list()),
        judges[0], timeout_ms), stage), set(routes_by_q))
    calls.append({"stage": stage, "model_id": reported_judges[0], "role": "portfolio_critic"})
    history = [{"stage": stage, "issues": critic}]
    substitutions = []

    for q in sorted({x["question_index"] for x in critic
                     if x["severity"] in {"MATERIAL","HARD"} and x["code"] in ROUTE_RESELECT_CODES}):
        old = routes_by_q[q]
        alternatives = [r for r in selectable[q] if r["route_id"] != old["route_id"]]
        if not alternatives:
            continue
        alternate = alternatives[0]
        try:
            new_payload, _ = _generate_prose_with_strategy(
                prose_strategy, run_dir, state, packet, bmap[q], alternate, writer, judges,
                timeout_ms, runner, calls, surface_profile, semantic_profile,
                [{"question_index": k, "answer": v["answer"]} for k,v in payloads.items() if k != q],
                ledger.schema_version, prose_realisations, nrs_selections)
        except DeepWriterError:
            continue
        old_payload = payloads[q]
        routes_by_q[q], payloads[q] = dict(alternate), new_payload
        s2 = f"deep_portfolio_critic_after_route_swap_q{q}"
        new_critic = _validate_critic(_coerce(runner(
            s2, _critic_prompt(packet, routes_by_q, payload_list()),
            judges[0], timeout_ms), s2), set(routes_by_q))
        calls.append({"stage": s2, "model_id": reported_judges[0], "role": "portfolio_critic"})
        before = sum(x["severity"] in {"MATERIAL","HARD"} for x in critic)
        after = sum(x["severity"] in {"MATERIAL","HARD"} for x in new_critic)
        if after <= before:
            substitutions.append({"question_index": q, "from_route_id": old["route_id"],
                                  "to_route_id": alternate["route_id"]})
            critic = new_critic; history.append({"stage": s2, "issues": new_critic})
        else:
            routes_by_q[q], payloads[q] = old, old_payload

    for q in sorted(routes_by_q):
        if prose_strategy == DEFAULT_PROSE_STRATEGY:
            continue
        issues = [x for x in critic if x["question_index"] == q and
                  x["severity"] in {"MATERIAL","HARD"} and x["code"] in SURFACE_REPAIR_CODES]
        if not issues:
            continue
        repair = " ".join(x["repair_instruction"] for x in issues if x["repair_instruction"])
        if not repair:
            continue
        sr = f"deep_surface_repair_q{q}"
        raw = _coerce(runner(sr, _prose_prompt(
            bmap[q], packet, routes_by_q[q], ("minimal_surface_repair","문체만 최소 수정"),
            preference_directives(surface_profile), sdirect, [], repair, payloads[q]),
            writer, timeout_ms), sr)
        calls.append({"stage": sr, "model_id": reported_writer, "role": "minimal_surface_repair"})
        try:
            fixed = _validate_generated_payload(raw, bmap[q], sr)
            response = _to_response(fixed, bmap[q], ledger_schema_version=ledger.schema_version)
            if not _candidate_issues(run_dir, state, response):
                payloads[q] = fixed
        except NarrativeCompilerError:
            pass

    responses = [_to_response(payloads[q], bmap[q], ledger_schema_version=ledger.schema_version)
                 for q in sorted(payloads)]
    deterministic = _portfolio_issues(run_dir, state, responses)
    duplicate_pairs = short_partial_duplicate_pairs((r.question_index, r.answer) for r in responses)
    for pair in duplicate_pairs:
        deterministic.append(ValidationIssue(
            "duplicate_answer", int(pair["right_index"]),
            f"문항 {pair['left_index']}과 답변 내용이 {pair['kind']} 중복입니다."))

    fs = "deep_portfolio_critic_final"
    final_critic = _validate_critic(_coerce(runner(
        fs, _critic_prompt(packet, routes_by_q, payload_list()),
        judges[0], timeout_ms), fs), set(routes_by_q))
    calls.append({"stage": fs, "model_id": reported_judges[0], "role": "portfolio_critic"})
    history.append({"stage": fs, "issues": final_critic})
    material = [x for x in final_critic if x["severity"] in {"MATERIAL","HARD"}]

    return responses, {
        "schema_version": 2,
        "architecture": "evidence_to_argument_search_with_nrs_v2",
        "packet_id": packet.get("packet_id"),
        "writer_model_id": reported_writer,
        "judge_model_ids": reported_judges,
        "writer_backend": writer_backend,
        "model_identity_available": writer != DEFAULT_BACKEND_SENTINEL,
        "judge_independence": "heterogeneous_model_ids" if any(j != writer for j in judges) else "same_model_role_ensemble",
        "route_search": route_report,
        "portfolio_route_selection": portfolio,
        "selected_routes": {str(q): {"route_id": r["route_id"], "argument_posture": r.get("argument_posture"),
                                      "aggregate_score": r.get("aggregate_score")} for q,r in routes_by_q.items()},
        "route_substitutions": substitutions,
        "prose_failures": {str(k): v for k,v in prose_failures.items()},
        "writer_strategy": {
            "configured": prose_strategy,
            "production_default": DEFAULT_PROSE_STRATEGY,
            "active": prose_strategy,
            "candidate_budget": NRS_CANDIDATE_BUDGET if prose_strategy == DEFAULT_PROSE_STRATEGY else prose_realisations,
            "retry_attempts_per_candidate": NRS_RETRY_ATTEMPTS if prose_strategy == DEFAULT_PROSE_STRATEGY else None,
            "candidate_selection": "counterbalanced_blind_rank_v1" if prose_strategy == DEFAULT_PROSE_STRATEGY else "deep_prose_judge",
            "fallback": "deep_route_after_nrs_validity_failure" if prose_strategy == DEFAULT_PROSE_STRATEGY else None,
            "genre_contract_version": GENRE_CONTRACT_VERSION if prose_strategy == DEFAULT_PROSE_STRATEGY else None,
        },
        "nrs_realization_selection": nrs_selections,
        "semantic_preference": {"loaded": semantic_profile is not None, "weights": sweights,
                                "stores_source_text": False},
        "critic_history": history,
        "semantic_validation": {"status": "passed" if not material else "needs_review",
                                "material_or_hard_issues": material},
        "deterministic_validation": {"status": "passed" if not deterministic else "failed",
                                     "issues": [asdict(x) for x in deterministic]},
        "qwen_review": {"short_substring_duplicate_gate_applied": True,
                        "duplicate_pairs": duplicate_pairs},
        "calls": calls,
    }

def write_deep_draft(run_dir: Path, *, output: Path | None = None, force: bool = False, **kwargs: Any):
    run_dir = run_dir.resolve()
    responses, report = generate_deep_draft(run_dir, packet=compile_run_blueprint(run_dir), **kwargs)
    output = output or run_dir / "draft.json"
    if not output.is_absolute():
        output = run_dir / output
    if output.exists() and not force:
        raise DeepWriterError(f"output already exists: {output}; use --force")
    write_json(output, [asdict(x) for x in responses])
    write_json(run_dir / "05_논증검색_검증.json", report)
    if report.get("writer_strategy", {}).get("active") == DEFAULT_PROSE_STRATEGY:
        write_json(run_dir / "05_NRS_서사선택.json", {
            "writer_strategy": report["writer_strategy"],
            "selections": report.get("nrs_realization_selection", []),
        })
    return output, report

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Search argument space before writing prose")
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--writer-model-id")
    p.add_argument("--judge-model-id", action="append", default=[])
    p.add_argument("--routes", type=int, default=3)
    p.add_argument("--prose-realisations", type=int, default=2)
    p.add_argument("--prose-strategy", choices=tuple(sorted(PROSE_STRATEGIES)), default=DEFAULT_PROSE_STRATEGY)
    p.add_argument("--timeout-ms", type=int, default=300_000)
    p.add_argument("--surface-preference-profile", type=Path)
    p.add_argument("--semantic-preference-profile", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--force", action="store_true")
    return p

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output, report = write_deep_draft(
        args.run, output=args.output, force=args.force,
        writer_model_id=args.writer_model_id, judge_model_ids=tuple(args.judge_model_id),
        route_count=args.routes, prose_realisations=args.prose_realisations,
        prose_strategy=args.prose_strategy,
        timeout_ms=args.timeout_ms,
        surface_preference_profile_path=args.surface_preference_profile,
        semantic_preference_profile_path=args.semantic_preference_profile,
    )
    print(output)
    print(args.run.resolve() / "05_논증검색_검증.json")
    return 0 if report["deterministic_validation"]["status"] == "passed" and report["semantic_validation"]["status"] == "passed" else 3

if __name__ == "__main__":
    raise SystemExit(main())
