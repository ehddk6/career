"""Preference-optimized self-introduction generation on top of Narrative Compiler.

This module keeps factual authority in the existing evidence validators while
adding test-time prose search. For each question it generates several bounded
realisations, rejects invalid candidates before subjective judging, ranks the
remaining candidates twice in opposite presentation orders, then runs a
portfolio-level critic and minimal repair pass.

The preference judge never receives model/provider labels. A local writing
preference profile can steer prose rhythm using aggregate structural metrics;
raw Claude/Gemini/GPT comparison text is never persisted by this module.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import tempfile
from hashlib import sha256
from typing import Any, Callable, Mapping

from .copyeditor_adapter import _resolved_codex_command
from .model_policy import resolve_model
from .models import DraftResponse, Question, ValidationIssue
from .narrative_compiler import (
    NarrativeCompilerError,
    _CRITIC_CODES,
    _GENERATION_SCHEMA,
    _compact_blueprint,
    _to_response,
    _validate_generated_payload,
    compile_run_blueprint,
)
from .profile_schema import ExperienceLedger, load_ledger
from .research_evidence import load_research_claims, validate_research_evidence
from .state import write_json
from .style_diagnostics import diagnose_text
from .validation import validate_draft
from .writing_preference import (
    load_preference_profile,
    preference_directives,
    preference_distance,
)


ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]

REALISATION_MODES: tuple[tuple[str, str], ...] = (
    (
        "judgment_centered",
        "핵심 판단과 선택 기준이 글을 끌고 가게 쓴다. 장면은 그 판단을 증명하는 만큼만 사용한다.",
    ),
    (
        "scene_rhythm",
        "첫 두 문장의 직접 답변 뒤 하나의 구체 장면을 살리고, 짧은 판단 문장과 설명 문장의 호흡을 섞는다.",
    ),
    (
        "restrained_natural",
        "꾸민 표현보다 담백한 한국어를 우선하고, 연결어·추상적 다짐 대신 행동·관찰·생각의 변화로 이어간다.",
    ),
    (
        "distinctive_voice",
        "지원자에게만 있을 법한 관찰·판단·행동의 디테일을 중심으로 기억에 남게 쓰되 과장하지 않는다.",
    ),
)

_RANKING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ranking"],
    "properties": {
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidate_id", "score", "reason"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reason": {"type": "string"},
                },
            },
        },
        "set_level_concerns": {"type": "array", "items": {"type": "string"}},
    },
}

_CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issues"],
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "question_index",
                    "code",
                    "severity",
                    "message",
                    "repair_instruction",
                ],
                "properties": {
                    "question_index": {"type": "integer"},
                    "code": {"type": "string", "enum": list(_CRITIC_CODES)},
                    "severity": {"type": "string", "enum": ["MINOR", "MATERIAL", "HARD"]},
                    "message": {"type": "string"},
                    "repair_instruction": {"type": "string"},
                },
            },
        }
    },
}


def _schema_for_stage(stage: str) -> dict[str, Any]:
    if stage.startswith("preference_rank"):
        return _RANKING_SCHEMA
    if stage.startswith("preference_critic"):
        return _CRITIC_SCHEMA
    return _GENERATION_SCHEMA


def subprocess_model_runner(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="career-preference-writer-") as temp:
        root = Path(temp)
        schema = root / "schema.json"
        schema.write_text(
            json.dumps(_schema_for_stage(stage), ensure_ascii=False), encoding="utf-8"
        )
        try:
            completed = subprocess.run(
                _resolved_codex_command(root, schema, resolve=True, model_id=model_id),
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                timeout=max(1, timeout_ms // 1000 + 30),
            )
        except subprocess.TimeoutExpired as error:
            raise NarrativeCompilerError(f"model call timed out at {stage}") from error
        except OSError as error:
            raise NarrativeCompilerError(f"model call could not start at {stage}: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if len(detail) > 1600:
            detail = detail[-1600:]
        raise NarrativeCompilerError(
            f"model call failed at {stage}" + (f": {detail}" if detail else "")
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise NarrativeCompilerError(f"invalid JSON at {stage}") from error
    if not isinstance(value, dict):
        raise NarrativeCompilerError(f"non-object model output at {stage}")
    return value


def _coerce(value: dict[str, Any] | str, stage: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise NarrativeCompilerError(f"invalid JSON at {stage}") from error
    if not isinstance(value, dict):
        raise NarrativeCompilerError(f"invalid object at {stage}")
    return value


def _state(run_dir: Path) -> dict[str, Any]:
    value = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NarrativeCompilerError("run.json must be an object")
    return value


def _questions(state: Mapping[str, Any]) -> list[Question]:
    return sorted(
        [Question(**dict(item)) for item in state.get("questions", []) if isinstance(item, Mapping)],
        key=lambda item: item.index,
    )


def _known_sources(ledger: ExperienceLedger) -> set[str]:
    return {
        evidence.source_path
        for experience in ledger.experiences
        for claim in experience.claims
        for evidence in claim.evidence
    }


def _candidate_issues(
    run_dir: Path,
    state: Mapping[str, Any],
    response: DraftResponse,
) -> list[ValidationIssue]:
    question = next(
        (item for item in _questions(state) if item.index == response.question_index), None
    )
    if question is None:
        return [ValidationIssue("unknown_question_index", response.question_index, "unknown question")]
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
    issues = validate_draft(
        [question],
        [response],
        str(state.get("target", "")),
        _known_sources(ledger),
        profile_ledger=ledger,
        require_experience_refs=True,
    )
    research_path = run_dir / "04_공식근거.json"
    if research_path.is_file():
        issues.extend(
            validate_research_evidence(
                [question],
                [response],
                load_research_claims(research_path),
                allowed_domains=tuple(
                    str(item)
                    for item in state.get("official_research_domains", []) or []
                ),
            )
        )
    return issues


def _portfolio_issues(
    run_dir: Path,
    state: Mapping[str, Any],
    responses: list[DraftResponse],
) -> list[ValidationIssue]:
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
    questions = _questions(state)
    issues = validate_draft(
        questions,
        responses,
        str(state.get("target", "")),
        _known_sources(ledger),
        profile_ledger=ledger,
        require_experience_refs=True,
    )
    research_path = run_dir / "04_공식근거.json"
    if research_path.is_file():
        issues.extend(
            validate_research_evidence(
                questions,
                responses,
                load_research_claims(research_path),
                allowed_domains=tuple(
                    str(item)
                    for item in state.get("official_research_domains", []) or []
                ),
            )
        )
    return issues


def _preference_profile(
    run_dir: Path,
    state: Mapping[str, Any],
    explicit: Path | None,
) -> dict[str, Any] | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    configured = state.get("writing_preference_profile")
    if configured:
        candidates.append(Path(str(configured)).expanduser())
    root = state.get("root")
    if root:
        candidates.append(Path(str(root)) / ".career_profile" / "writing_preference.json")
    candidates.append(run_dir.parent.parent / ".career_profile" / "writing_preference.json")
    for path in candidates:
        resolved = path if path.is_absolute() else (run_dir / path)
        profile = load_preference_profile(resolved.resolve())
        if profile is not None:
            return profile
    return None


def _draft_prompt(
    blueprint: Mapping[str, Any],
    packet: Mapping[str, Any],
    *,
    prior_answers: list[dict[str, Any]],
    mode: tuple[str, str],
    preference_profile: Mapping[str, Any] | None,
    original: Mapping[str, Any] | None = None,
    repair_issues: list[dict[str, Any]] | None = None,
) -> str:
    context = {
        "blueprint": _compact_blueprint(blueprint, packet),
        "prior_answers_for_portfolio_diversity": prior_answers,
        "realisation": {"mode": mode[0], "instruction": mode[1]},
        "learned_style_preferences": preference_directives(preference_profile),
        "repair": {
            "original": original,
            "issues": repair_issues or [],
        },
    }
    principles = [
        "문항의 핵심 질문에 첫 두 문장 안에서 답한다.",
        "하나의 장면과 하나의 판단 축을 중심으로 자연스러운 한국어 산문을 만든다.",
        "상황보다 지원자의 판단과 직접 행동에 더 많은 지면을 쓴다.",
        "기관 사실은 지원자의 선택 논리를 증명하는 데 필요한 만큼만 사용한다.",
        "문장 의미 자체로 흐름을 연결하고, 설명용 연결어와 추상적 다짐은 필요한 곳에만 쓴다.",
        "selected_claims/research_claims에 있는 사실·수치만 사용하며 기여도보다 강한 인과를 만들지 않는다.",
        "blueprint beat는 논증 순서이지 소제목이나 체크리스트가 아니다.",
        "면접에서 그대로 설명할 수 있는 어휘와 호흡을 유지한다.",
    ]
    task = (
        "기존 답변의 좋은 문장은 보존하고 지정된 MATERIAL/HARD 문제만 최소 범위로 고친다."
        if repair_issues
        else "위 설계도와 산문 실현 방식을 바탕으로 자기소개서 답변 하나를 작성한다."
    )
    return (
        "<context>\n"
        + json.dumps(context, ensure_ascii=False)
        + "\n</context>\n<writing_principles>\n- "
        + "\n- ".join(principles)
        + "\n</writing_principles>\n<task>\n"
        + task
        + " 글자수/count_mode를 지키고, 실제 사용한 claim/research ID만 포함한 JSON만 반환한다.\n</task>"
    )


def _candidate_id(payload: Mapping[str, Any]) -> str:
    digest = sha256(str(payload.get("answer", "")).encode("utf-8")).hexdigest()[:10].upper()
    return "C" + digest


def _ranking_prompt(
    blueprint: Mapping[str, Any],
    candidates: list[dict[str, Any]],
    preference_profile: Mapping[str, Any] | None,
) -> str:
    return (
        "<context>\n"
        + json.dumps(
            {
                "question": blueprint.get("prompt"),
                "intent": blueprint.get("intent"),
                "logic_contract": blueprint.get("logic_contract"),
                "learned_style_preferences": preference_directives(preference_profile),
                "candidates": [
                    {
                        "candidate_id": item["candidate_id"],
                        "answer": item["payload"]["answer"],
                    }
                    for item in candidates
                ],
            },
            ensure_ascii=False,
        )
        + "\n</context>\n<evaluation_principles>\n"
        "1. 문항에 직접 답했는가.\n"
        "2. 지원자만의 장면·판단·행동이 보이는가.\n"
        "3. 판단→행동→결과의 인과가 자연스러운가.\n"
        "4. 기관 홍보문이나 업무 매뉴얼처럼 읽히지 않는가.\n"
        "5. 실제 사람이 말할 법한 한국어 호흡인가.\n"
        "6. 사실성과 문항 충족도가 동등할 때만 학습된 문체 선호를 우선한다.\n"
        "</evaluation_principles>\n<task>\n"
        "모델명·작성전략을 추측하지 말고 candidate_id만 사용해 좋은 순서대로 전 후보를 순위화한다. JSON만 반환한다.\n"
        "</task>"
    )


def _validate_ranking(payload: Mapping[str, Any], candidate_ids: set[str]) -> list[dict[str, Any]]:
    rows = payload.get("ranking")
    if not isinstance(rows, list):
        raise NarrativeCompilerError("preference ranking missing")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise NarrativeCompilerError("invalid preference ranking row")
        candidate_id = str(row.get("candidate_id", ""))
        score = row.get("score")
        if candidate_id not in candidate_ids or candidate_id in seen:
            raise NarrativeCompilerError("preference ranking candidate mismatch")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise NarrativeCompilerError("preference ranking score mismatch")
        seen.add(candidate_id)
        result.append(
            {
                "candidate_id": candidate_id,
                "score": score,
                "reason": str(row.get("reason", "")),
            }
        )
    if seen != candidate_ids or len(result) != len(candidate_ids):
        raise NarrativeCompilerError("preference ranking set mismatch")
    return result


def _blind_tournament(
    *,
    blueprint: Mapping[str, Any],
    candidates: list[dict[str, Any]],
    preference_profile: Mapping[str, Any] | None,
    model_id: str,
    timeout_ms: int,
    runner: ModelRunner,
    calls: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(candidates) == 1:
        return candidates[0], {
            "selected_candidate_id": candidates[0]["candidate_id"],
            "rankings": [],
            "position_consistent": True,
        }
    candidate_ids = {item["candidate_id"] for item in candidates}
    rankings: list[list[dict[str, Any]]] = []
    orders = (candidates, list(reversed(candidates)))
    for permutation, order in enumerate(orders, start=1):
        stage = f"preference_rank_{blueprint['question_index']}_{permutation}"
        payload = _coerce(
            runner(
                stage,
                _ranking_prompt(blueprint, order, preference_profile),
                model_id,
                timeout_ms,
            ),
            stage,
        )
        ranking = _validate_ranking(payload, candidate_ids)
        rankings.append(ranking)
        calls.append({"stage": stage, "model_id": model_id, "role": "blind_preference_judge"})
    points = {candidate_id: 0 for candidate_id in candidate_ids}
    score_sum = {candidate_id: 0 for candidate_id in candidate_ids}
    for ranking in rankings:
        size = len(ranking)
        for position, row in enumerate(ranking):
            points[row["candidate_id"]] += size - position
            score_sum[row["candidate_id"]] += row["score"]
    by_id = {item["candidate_id"]: item for item in candidates}
    selected_id = min(
        candidate_ids,
        key=lambda candidate_id: (
            -points[candidate_id],
            -score_sum[candidate_id],
            preference_distance(
                str(by_id[candidate_id]["payload"]["answer"]), preference_profile
            ),
            diagnose_text(str(by_id[candidate_id]["payload"]["answer"])).style_risk_score,
            candidate_id,
        ),
    )
    top_choices = [ranking[0]["candidate_id"] for ranking in rankings]
    return by_id[selected_id], {
        "selected_candidate_id": selected_id,
        "rankings": rankings,
        "rank_points": points,
        "score_sums": score_sum,
        "top_choices_by_permutation": top_choices,
        "position_consistent": len(set(top_choices)) == 1,
    }


def _critic_prompt(
    packet: Mapping[str, Any],
    payloads: list[dict[str, Any]],
    preference_profile: Mapping[str, Any] | None,
) -> str:
    return (
        "<context>\n"
        + json.dumps(
            {
                "portfolio": packet.get("portfolio"),
                "blueprints": [
                    _compact_blueprint(item, packet)
                    for item in packet.get("questions", [])
                    if isinstance(item, Mapping)
                ],
                "drafts": payloads,
                "learned_style_preferences": preference_directives(preference_profile),
            },
            ensure_ascii=False,
        )
        + "\n</context>\n<task>\n"
        "전체 지원서를 적대적으로 검토한다. polished generic prose에는 점수를 주지 않는다. 문항 직접성, 약한 thesis, "
        "장면의 일반성, 행동 흐림, 인과 공백, 억지 직무 연결, 기관 홍보문, 관공서 체크리스트, 인공적 문체, "
        "문항 간 경험·동사 반복, 이슈 문항의 trade-off 누락을 찾는다. 사실 범위를 벗어나면 evidence_risk다. "
        "MINOR는 정보용이고 MATERIAL/HARD만 최소 수정 지시를 준다. JSON만 반환한다.\n</task>"
    )


def _validate_critic(payload: Mapping[str, Any], question_indexes: set[int]) -> list[dict[str, Any]]:
    rows = payload.get("issues")
    if not isinstance(rows, list):
        raise NarrativeCompilerError("preference critic issues missing")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise NarrativeCompilerError("invalid preference critic issue")
        index = row.get("question_index")
        code = row.get("code")
        severity = row.get("severity")
        if not isinstance(index, int) or index not in question_indexes:
            raise NarrativeCompilerError("preference critic question mismatch")
        if code not in _CRITIC_CODES or severity not in {"MINOR", "MATERIAL", "HARD"}:
            raise NarrativeCompilerError("preference critic classification mismatch")
        result.append(
            {
                "question_index": index,
                "code": str(code),
                "severity": str(severity),
                "message": str(row.get("message", "")),
                "repair_instruction": str(row.get("repair_instruction", "")),
            }
        )
    return result


def generate_preference_optimized_draft(
    run_dir: Path,
    *,
    packet: dict[str, Any] | None = None,
    model_id: str | None = None,
    candidates_per_question: int = 3,
    max_repairs: int = 1,
    timeout_ms: int = 300_000,
    preference_profile_path: Path | None = None,
    runner: ModelRunner = subprocess_model_runner,
) -> tuple[list[DraftResponse], dict[str, Any]]:
    run_dir = run_dir.resolve()
    state = _state(run_dir)
    packet = packet or compile_run_blueprint(run_dir)
    model = model_id or resolve_model("sol").model_id
    if not model:
        raise NarrativeCompilerError("generation requires --model-id or CAREER_MODEL_SOL")
    if not 1 <= candidates_per_question <= len(REALISATION_MODES):
        raise ValueError(
            f"candidates_per_question must be 1..{len(REALISATION_MODES)}"
        )
    preference_profile = _preference_profile(run_dir, state, preference_profile_path)
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
    schema_version = ledger.schema_version
    blueprints = [
        item for item in packet.get("questions", []) if isinstance(item, Mapping)
    ]
    calls: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    selected_payloads: list[dict[str, Any]] = []
    prior_answers: list[dict[str, Any]] = []

    for blueprint in blueprints:
        valid: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        seen_answers: set[str] = set()
        for candidate_number, mode in enumerate(
            REALISATION_MODES[:candidates_per_question], start=1
        ):
            stage = f"preference_generate_q{blueprint['question_index']}_{candidate_number}"
            raw = _coerce(
                runner(
                    stage,
                    _draft_prompt(
                        blueprint,
                        packet,
                        prior_answers=prior_answers,
                        mode=mode,
                        preference_profile=preference_profile,
                    ),
                    model,
                    timeout_ms,
                ),
                stage,
            )
            calls.append({"stage": stage, "model_id": model, "role": "prose_realisation"})
            try:
                payload = _validate_generated_payload(raw, blueprint, stage)
            except NarrativeCompilerError as error:
                failures.append({"stage": stage, "codes": ["payload_contract"], "message": str(error)})
                continue
            normalized_answer = " ".join(payload["answer"].split())
            if normalized_answer in seen_answers:
                failures.append({"stage": stage, "codes": ["duplicate_realisation"]})
                continue
            seen_answers.add(normalized_answer)
            response = _to_response(payload, blueprint, ledger_schema_version=schema_version)
            issues = _candidate_issues(run_dir, state, response)
            if issues:
                failures.append({"stage": stage, "codes": [item.code for item in issues]})
                continue
            candidate_id = _candidate_id(payload)
            valid.append(
                {
                    "candidate_id": candidate_id,
                    "payload": payload,
                    "realisation_mode": mode[0],
                }
            )
        if not valid:
            raise NarrativeCompilerError(
                f"every prose realisation failed for question {blueprint['question_index']}"
            )
        winner, tournament = _blind_tournament(
            blueprint=blueprint,
            candidates=valid,
            preference_profile=preference_profile,
            model_id=model,
            timeout_ms=timeout_ms,
            runner=runner,
            calls=calls,
        )
        selected_payloads.append(winner["payload"])
        prior_answers.append(
            {
                "question_index": winner["payload"]["question_index"],
                "answer": winner["payload"]["answer"],
            }
        )
        selections.append(
            {
                "question_index": int(blueprint["question_index"]),
                "candidate_failures": failures,
                "candidates": [
                    {
                        "candidate_id": item["candidate_id"],
                        "realisation_mode": item["realisation_mode"],
                        "preference_distance": preference_distance(
                            str(item["payload"]["answer"]), preference_profile
                        ),
                        "style_risk_score": diagnose_text(
                            str(item["payload"]["answer"])
                        ).style_risk_score,
                    }
                    for item in valid
                ],
                **tournament,
            }
        )

    by_blueprint = {
        int(item["question_index"]): item for item in blueprints
    }
    by_payload = {
        int(item["question_index"]): item for item in selected_payloads
    }

    def critic(stage: str) -> list[dict[str, Any]]:
        current = [by_payload[int(item["question_index"])] for item in blueprints]
        raw = _coerce(
            runner(
                stage,
                _critic_prompt(packet, current, preference_profile),
                model,
                timeout_ms,
            ),
            stage,
        )
        calls.append({"stage": stage, "model_id": model, "role": "portfolio_critic"})
        return _validate_critic(
            raw, {int(item["question_index"]) for item in current}
        )

    critic_history: list[dict[str, Any]] = []
    critic_issues = critic("preference_critic")
    critic_history.append({"stage": "preference_critic", "issues": critic_issues})
    repaired_questions: list[int] = []
    for attempt in range(1, max(0, max_repairs) + 1):
        targets = sorted(
            {
                int(item["question_index"])
                for item in critic_issues
                if item["severity"] in {"MATERIAL", "HARD"}
            }
        )
        if not targets:
            break
        for index in targets:
            blueprint = by_blueprint[index]
            original = by_payload[index]
            issues = [
                item
                for item in critic_issues
                if item["question_index"] == index
                and item["severity"] in {"MATERIAL", "HARD"}
            ]
            stage = f"preference_repair_{attempt}_q{index}"
            raw = _coerce(
                runner(
                    stage,
                    _draft_prompt(
                        blueprint,
                        packet,
                        prior_answers=[
                            {"question_index": q, "answer": payload["answer"]}
                            for q, payload in sorted(by_payload.items())
                            if q != index
                        ],
                        mode=(
                            "targeted_repair",
                            "지적된 문제의 최소 범위만 고치고 선택 답변의 좋은 문장과 자연스러운 목소리는 보존한다.",
                        ),
                        preference_profile=preference_profile,
                        original=original,
                        repair_issues=issues,
                    ),
                    model,
                    timeout_ms,
                ),
                stage,
            )
            calls.append({"stage": stage, "model_id": model, "role": "targeted_repair"})
            try:
                repaired = _validate_generated_payload(raw, blueprint, stage)
            except NarrativeCompilerError:
                continue
            repaired_response = _to_response(
                repaired, blueprint, ledger_schema_version=schema_version
            )
            if _candidate_issues(run_dir, state, repaired_response):
                continue
            by_payload[index] = repaired
            repaired_questions.append(index)
        critic_issues = critic(f"preference_critic_after_repair_{attempt}")
        critic_history.append(
            {
                "stage": f"preference_critic_after_repair_{attempt}",
                "issues": critic_issues,
            }
        )

    final_payloads = [by_payload[int(item["question_index"])] for item in blueprints]
    responses = [
        _to_response(
            payload,
            by_blueprint[int(payload["question_index"])],
            ledger_schema_version=schema_version,
        )
        for payload in final_payloads
    ]
    deterministic_issues = _portfolio_issues(run_dir, state, responses)
    material = [
        item for item in critic_issues if item["severity"] in {"MATERIAL", "HARD"}
    ]
    report = {
        "schema_version": 1,
        "architecture": "preference_optimized_multi_realisation_v1",
        "packet_id": packet.get("packet_id"),
        "model_id": model,
        "candidates_per_question": candidates_per_question,
        "preference_profile": {
            "loaded": preference_profile is not None,
            "comparison_count": (
                int(preference_profile.get("comparison_count", 0))
                if preference_profile
                else 0
            ),
            "directives": preference_directives(preference_profile),
            "stores_source_text": False,
        },
        "candidate_selection": selections,
        "calls": calls,
        "critic_history": critic_history,
        "repaired_questions": sorted(set(repaired_questions)),
        "semantic_validation": {
            "status": "passed" if not material else "needs_review",
            "material_or_hard_issues": material,
        },
        "deterministic_validation": {
            "status": "passed" if not deterministic_issues else "failed",
            "issues": [asdict(item) for item in deterministic_issues],
        },
    }
    return responses, report


def write_preference_optimized_draft(
    run_dir: Path,
    *,
    output: Path | None = None,
    force: bool = False,
    **kwargs: Any,
) -> tuple[Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    packet = compile_run_blueprint(run_dir)
    responses, report = generate_preference_optimized_draft(
        run_dir, packet=packet, **kwargs
    )
    output = (output or (run_dir / "draft.json"))
    if not output.is_absolute():
        output = run_dir / output
    output = output.resolve()
    if output.exists() and not force:
        raise NarrativeCompilerError(
            f"output already exists: {output}; use --force to replace"
        )
    write_json(output, [asdict(item) for item in responses])
    write_json(run_dir / "05_선호최적화_검증.json", report)
    return output, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate preference-optimized evidence-grounded self-introduction prose"
    )
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--model-id")
    parser.add_argument("--candidates-per-question", type=int, default=3)
    parser.add_argument("--max-repairs", type=int, default=1)
    parser.add_argument("--timeout-ms", type=int, default=300_000)
    parser.add_argument("--preference-profile", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output, report = write_preference_optimized_draft(
        args.run,
        output=args.output,
        force=args.force,
        model_id=args.model_id,
        candidates_per_question=args.candidates_per_question,
        max_repairs=args.max_repairs,
        timeout_ms=args.timeout_ms,
        preference_profile_path=args.preference_profile,
    )
    print(output)
    print(args.run.resolve() / "05_선호최적화_검증.json")
    if (
        report["deterministic_validation"]["status"] != "passed"
        or report["semantic_validation"]["status"] != "passed"
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
