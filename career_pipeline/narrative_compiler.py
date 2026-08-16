"""Compile career-pipeline evidence into a narrative blueprint and optional draft.

This module is intentionally additive.  It does not replace the existing final
validators.  It inserts a planning layer before prose so the model receives one
bounded argument blueprint per question instead of improvising from the entire
workspace packet.

Usage:
    python -m career_pipeline.narrative_compiler --run career_runs/<run>
    python -m career_pipeline.narrative_compiler --run career_runs/<run> --generate

Plan-only mode is deterministic and performs no model call.  Generation requires
an explicit model ID or CAREER_MODEL_SOL and writes ``draft_narrative.json`` by
default, never overwriting an existing file unless ``--force`` is given.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping

from .answer_blueprint import build_answer_blueprint_packet, render_blueprint_markdown
from .copyeditor_adapter import _resolved_codex_command
from .model_policy import resolve_model
from .models import DraftResponse, ExperienceClaimRef, Question, ValidationIssue
from .profile_schema import ExperienceLedger, load_ledger
from .research_evidence import load_research_claims, validate_research_evidence
from .state import write_json
from .validation import validate_draft


ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]


class NarrativeCompilerError(ValueError):
    pass


_GENERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "blueprint_id",
        "question_index",
        "answer",
        "used_claim_ids",
        "used_research_ids",
    ],
    "properties": {
        "blueprint_id": {"type": "string"},
        "question_index": {"type": "integer"},
        "answer": {"type": "string"},
        "used_claim_ids": {"type": "array", "items": {"type": "string"}},
        "used_research_ids": {"type": "array", "items": {"type": "string"}},
    },
}

_CRITIC_CODES = (
    "question_gap",
    "weak_thesis",
    "generic_scene",
    "action_blur",
    "causal_gap",
    "forced_job_bridge",
    "company_brochure",
    "generic_closing",
    "artificial_voice",
    "overloaded_answer",
    "portfolio_redundancy",
    "evidence_risk",
    "policy_tradeoff_gap",
)

_CRITIC_SCHEMA = {
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


def _subprocess_runner(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any]:
    schema_payload = _CRITIC_SCHEMA if stage == "narrative_critic" else _GENERATION_SCHEMA
    with tempfile.TemporaryDirectory(prefix="career-narrative-") as temp:
        root = Path(temp)
        schema = root / "schema.json"
        schema.write_text(json.dumps(schema_payload, ensure_ascii=False), encoding="utf-8")
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


def _coerce_payload(value: dict[str, Any] | str, stage: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise NarrativeCompilerError(f"invalid JSON at {stage}") from error
    if not isinstance(value, dict):
        raise NarrativeCompilerError(f"invalid object at {stage}")
    return value


def _question_objects(state: Mapping[str, Any]) -> list[Question]:
    result: list[Question] = []
    for row in state.get("questions", []) or []:
        if not isinstance(row, Mapping):
            continue
        result.append(
            Question(
                int(row["index"]),
                str(row.get("prompt", "")),
                row.get("character_limit"),
                str(row.get("count_mode", "spaces_included")),
                row.get("minimum_character_limit"),
            )
        )
    return sorted(result, key=lambda item: item.index)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def compile_run_blueprint(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state_path = run_dir / "run.json"
    if not state_path.is_file():
        raise NarrativeCompilerError(f"run.json not found: {state_path}")
    state = _read_json(state_path, {})
    if not isinstance(state, dict):
        raise NarrativeCompilerError("run.json must be an object")
    questions = _question_objects(state)
    if not questions:
        raise NarrativeCompilerError("run has no questions")
    posting = _read_json(run_dir / "00_채용공고분석.json", {})
    ledger = _read_json(run_dir / "02_확정경험원장.json", {})
    matches = _read_json(run_dir / "03_경험직무매칭.json", [])
    research_claims = _read_json(run_dir / "04_공식근거.json", [])
    if not isinstance(posting, dict) or not isinstance(ledger, dict):
        raise NarrativeCompilerError("posting and confirmed experience ledger must be JSON objects")
    if not isinstance(matches, list) or not isinstance(research_claims, list):
        raise NarrativeCompilerError("matching and research artifacts must be JSON arrays")
    packet = build_answer_blueprint_packet(
        questions,
        target=str(state.get("target", "")),
        posting=posting,
        ledger=ledger,
        matches=matches,
        research_claims=[item for item in research_claims if isinstance(item, Mapping)],
    )
    write_json(run_dir / "05_답변설계도.json", packet)
    (run_dir / "05_답변설계도.md").write_text(
        render_blueprint_markdown(packet), encoding="utf-8"
    )
    return packet


def _compact_blueprint(blueprint: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target": packet.get("target"),
        "portfolio_rules": packet.get("portfolio", {}).get("cross_answer_rules", []),
        "blueprint_id": blueprint.get("blueprint_id"),
        "question_index": blueprint.get("question_index"),
        "prompt": blueprint.get("prompt"),
        "intent": blueprint.get("intent"),
        "logic_contract": blueprint.get("logic_contract"),
        "character_plan": blueprint.get("character_plan"),
        "beats": blueprint.get("beats"),
        "experience": blueprint.get("experience"),
        "research_claims": blueprint.get("research_claims"),
        "portfolio_constraints": blueprint.get("portfolio_constraints"),
        "risk_controls": blueprint.get("risk_controls"),
        "interview_defense_questions": blueprint.get("interview_defense_questions"),
    }


def _generation_prompt(
    blueprint: Mapping[str, Any],
    packet: Mapping[str, Any],
    prior_answers: list[dict[str, Any]],
    *,
    repair_issues: list[dict[str, Any]] | None = None,
    original: Mapping[str, Any] | None = None,
) -> str:
    task = (
        "Repair the existing answer only for the typed issues below."
        if repair_issues
        else "Write one Korean self-introduction answer from the narrative blueprint."
    )
    return (
        task
        + " The blueprint is a writing contract, not factual evidence. Use only facts and numbers explicitly "
        "contained in experience.selected_claims or research_claims. Situation/actions/outcomes may shape scene "
        "and wording but do not authorize a number unless a selected claim contains that exact numeric value. "
        "Never strengthen contribution=observed into personal causation or contribution=contributed into sole causation. "
        "Follow the beat order as an argument, not as headings or a checklist. The final answer must be plain prose. "
        "Make the first two sentences answer the prompt, preserve the applicant's concrete scene and judgment, and "
        "avoid brochure copy, generic promises, template-like transitions, and repeated 확인/대조/기록/보고 chains. "
        "Use only claim/research IDs that are visibly reflected in the answer. Do not use all available evidence merely "
        "because it exists. Respect the exact character maximum and count mode. Return JSON only.\n"
        + json.dumps(
            {
                "blueprint": _compact_blueprint(blueprint, packet),
                "prior_answers_for_portfolio_diversity": prior_answers,
                "repair_issues": repair_issues or [],
                "original": original,
            },
            ensure_ascii=False,
        )
    )


def _allowed_claims(blueprint: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    experience = blueprint.get("experience")
    if not isinstance(experience, Mapping):
        return {}
    return {
        str(item.get("claim_id", "")): dict(item)
        for item in experience.get("selected_claims", []) or []
        if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
    }


def _allowed_research(blueprint: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("claim_id", "")): dict(item)
        for item in blueprint.get("research_claims", []) or []
        if isinstance(item, Mapping) and str(item.get("claim_id", "")).strip()
    }


def _validate_generated_payload(payload: Mapping[str, Any], blueprint: Mapping[str, Any], stage: str) -> dict[str, Any]:
    if payload.get("blueprint_id") != blueprint.get("blueprint_id"):
        raise NarrativeCompilerError(f"blueprint mismatch at {stage}")
    if payload.get("question_index") != blueprint.get("question_index"):
        raise NarrativeCompilerError(f"question mismatch at {stage}")
    answer = payload.get("answer")
    claim_ids = payload.get("used_claim_ids")
    research_ids = payload.get("used_research_ids")
    if not isinstance(answer, str) or not answer.strip():
        raise NarrativeCompilerError(f"empty answer at {stage}")
    if not isinstance(claim_ids, list) or not all(isinstance(item, str) for item in claim_ids):
        raise NarrativeCompilerError(f"invalid claim IDs at {stage}")
    if not isinstance(research_ids, list) or not all(isinstance(item, str) for item in research_ids):
        raise NarrativeCompilerError(f"invalid research IDs at {stage}")
    allowed_claim_ids = set(_allowed_claims(blueprint))
    allowed_research_ids = set(_allowed_research(blueprint))
    if not set(claim_ids).issubset(allowed_claim_ids):
        raise NarrativeCompilerError(f"unapproved claim ID at {stage}")
    if not set(research_ids).issubset(allowed_research_ids):
        raise NarrativeCompilerError(f"unapproved research ID at {stage}")
    logic = blueprint.get("logic_contract", {})
    if isinstance(logic, Mapping):
        if logic.get("experience_mode") == "required" and not claim_ids:
            raise NarrativeCompilerError(f"experience evidence required at {stage}")
        if logic.get("research_mode") == "required" and not research_ids:
            raise NarrativeCompilerError(f"research evidence required at {stage}")
    return {
        "blueprint_id": str(payload["blueprint_id"]),
        "question_index": int(payload["question_index"]),
        "answer": answer.strip(),
        "used_claim_ids": list(dict.fromkeys(claim_ids)),
        "used_research_ids": list(dict.fromkeys(research_ids)),
    }


def _to_response(
    payload: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    *,
    ledger_schema_version: int | None = None,
) -> DraftResponse:
    allowed_claims = _allowed_claims(blueprint)
    used_claims = [allowed_claims[item] for item in payload["used_claim_ids"]]
    experience = blueprint.get("experience")
    experience_refs: tuple[ExperienceClaimRef, ...]
    if used_claims and isinstance(experience, Mapping):
        experience_refs = (
            ExperienceClaimRef(
                str(experience.get("experience_id", "")),
                () if (ledger_schema_version or 0) >= 2 else tuple(
                    str(item.get("field", "")) for item in used_claims
                ),
                tuple(str(item.get("claim_id", "")) for item in used_claims)
                if (ledger_schema_version or 0) >= 2 else (),
            ),
        )
    else:
        experience_refs = ()
    evidence_paths = tuple(
        sorted(
            {
                str(path)
                for claim in used_claims
                for path in claim.get("evidence_paths", []) or []
                if str(path).strip()
            }
        )
    )
    return DraftResponse(
        int(payload["question_index"]),
        str(payload["answer"]),
        evidence_paths,
        experience_refs,
        tuple(str(item) for item in payload["used_research_ids"]),
    )


def _critic_prompt(packet: Mapping[str, Any], payloads: list[dict[str, Any]]) -> str:
    return (
        "Act as an adversarial Korean self-introduction argument editor. Do not rewrite. Identify only material "
        "weaknesses that prevent the set from being persuasive, specific, defensible, and question-faithful. "
        "Do not reward polished generic prose. Check whether each answer actually follows its narrative beats, whether "
        "a motivation answer starts from the applicant's criterion rather than company brochure copy, whether a job "
        "plan explains priority/failure/escalation rather than a manual-like checklist, whether an issue essay has one "
        "clear mechanism and a real tradeoff, and whether the whole portfolio repeats the same scene/action vocabulary. "
        "Facts/causality outside the blueprint are evidence_risk. MINOR issues are informational; MATERIAL/HARD issues "
        "must have a precise repair instruction that changes the smallest possible span. Return JSON only.\n"
        + json.dumps(
            {
                "portfolio": packet.get("portfolio"),
                "blueprints": [
                    _compact_blueprint(row, packet)
                    for row in packet.get("questions", []) or []
                    if isinstance(row, Mapping)
                ],
                "drafts": payloads,
            },
            ensure_ascii=False,
        )
    )


def _validate_critic(payload: Mapping[str, Any], question_indexes: set[int]) -> list[dict[str, Any]]:
    issues = payload.get("issues")
    if not isinstance(issues, list):
        raise NarrativeCompilerError("critic issues missing")
    result: list[dict[str, Any]] = []
    for raw in issues:
        if not isinstance(raw, Mapping):
            raise NarrativeCompilerError("invalid critic issue")
        index = raw.get("question_index")
        code = raw.get("code")
        severity = raw.get("severity")
        if not isinstance(index, int) or index not in question_indexes:
            raise NarrativeCompilerError("critic question mismatch")
        if code not in _CRITIC_CODES or severity not in {"MINOR", "MATERIAL", "HARD"}:
            raise NarrativeCompilerError("critic issue classification mismatch")
        result.append(
            {
                "question_index": index,
                "code": str(code),
                "severity": str(severity),
                "message": str(raw.get("message", "")),
                "repair_instruction": str(raw.get("repair_instruction", "")),
            }
        )
    return result


def _known_sources(ledger: ExperienceLedger) -> set[str]:
    return {
        evidence.source_path
        for experience in ledger.experiences
        for claim in experience.claims
        for evidence in claim.evidence
    }


def _deterministic_validation(
    run_dir: Path,
    state: Mapping[str, Any],
    responses: list[DraftResponse],
) -> list[ValidationIssue]:
    questions = _question_objects(state)
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
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
        research_claims = load_research_claims(research_path)
        issues.extend(
            validate_research_evidence(
                questions,
                responses,
                research_claims,
                allowed_domains=tuple(str(item) for item in state.get("official_research_domains", []) or []),
            )
        )
    return issues


def generate_run_draft(
    run_dir: Path,
    *,
    packet: dict[str, Any] | None = None,
    model_id: str | None = None,
    timeout_ms: int = 300_000,
    max_repairs: int = 1,
    runner: ModelRunner = _subprocess_runner,
) -> tuple[list[DraftResponse], dict[str, Any]]:
    run_dir = run_dir.resolve()
    state = _read_json(run_dir / "run.json", {})
    if not isinstance(state, dict):
        raise NarrativeCompilerError("run.json must be an object")
    packet = packet or compile_run_blueprint(run_dir)
    resolved_model = model_id or resolve_model("sol").model_id
    if not resolved_model:
        raise NarrativeCompilerError("generation requires --model-id or CAREER_MODEL_SOL")
    blueprints = [item for item in packet.get("questions", []) or [] if isinstance(item, Mapping)]
    payloads: list[dict[str, Any]] = []
    prior: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    for blueprint in blueprints:
        stage = f"narrative_generate_q{blueprint['question_index']}"
        value = _coerce_payload(
            runner(stage, _generation_prompt(blueprint, packet, prior), resolved_model, timeout_ms),
            stage,
        )
        payload = _validate_generated_payload(value, blueprint, stage)
        payloads.append(payload)
        prior.append({"question_index": payload["question_index"], "answer": payload["answer"]})
        calls.append({"stage": stage, "model_id": resolved_model})

    def run_critic(current_payloads: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
        raw = _coerce_payload(
            runner(stage, _critic_prompt(packet, current_payloads), resolved_model, timeout_ms),
            stage,
        )
        calls.append({"stage": stage, "model_id": resolved_model})
        return _validate_critic(
            raw, {int(item["question_index"]) for item in current_payloads}
        )

    critic_history: list[dict[str, Any]] = []
    critic_issues = run_critic(payloads, "narrative_critic")
    critic_history.append({"stage": "narrative_critic", "issues": critic_issues})

    by_blueprint = {int(item["question_index"]): item for item in blueprints}
    by_payload = {int(item["question_index"]): item for item in payloads}
    repaired_questions: list[int] = []
    for attempt in range(1, max(0, max_repairs) + 1):
        targets = sorted(
            {
                item["question_index"]
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
            stage = f"narrative_repair_{attempt}_q{index}"
            repaired_raw = _coerce_payload(
                runner(
                    stage,
                    _generation_prompt(
                        blueprint,
                        packet,
                        [
                            {
                                "question_index": q_index,
                                "answer": current["answer"],
                            }
                            for q_index, current in sorted(by_payload.items())
                            if q_index != index
                        ],
                        repair_issues=issues,
                        original=original,
                    ),
                    resolved_model,
                    timeout_ms,
                ),
                stage,
            )
            repaired = _validate_generated_payload(repaired_raw, blueprint, stage)
            by_payload[index] = repaired
            calls.append({"stage": stage, "model_id": resolved_model})
            repaired_questions.append(index)
        current_payloads = [
            by_payload[int(item["question_index"])] for item in blueprints
        ]
        critic_stage = f"narrative_critic_after_repair_{attempt}"
        critic_issues = run_critic(current_payloads, critic_stage)
        critic_history.append({"stage": critic_stage, "issues": critic_issues})

    final_payloads = [by_payload[int(item["question_index"])] for item in blueprints]
    ledger_schema_version = packet.get("experience_ledger_schema_version")
    responses = [
        _to_response(
            payload,
            by_blueprint[int(payload["question_index"])],
            ledger_schema_version=(
                int(ledger_schema_version)
                if isinstance(ledger_schema_version, int)
                else None
            ),
        )
        for payload in final_payloads
    ]
    deterministic_issues = _deterministic_validation(run_dir, state, responses)
    report = {
        "schema_version": 1,
        "packet_id": packet.get("packet_id"),
        "model_id": resolved_model,
        "calls": calls,
        "critic_history": critic_history,
        "critic_issues": critic_issues,
        "semantic_validation": {
            "status": (
                "passed"
                if not any(item["severity"] in {"MATERIAL", "HARD"} for item in critic_issues)
                else "needs_review"
            ),
            "material_or_hard_issues": [
                item for item in critic_issues if item["severity"] in {"MATERIAL", "HARD"}
            ],
        },
        "repaired_questions": sorted(set(repaired_questions)),
        "deterministic_validation": {
            "status": "passed" if not deterministic_issues else "failed",
            "issues": [asdict(item) for item in deterministic_issues],
        },
    }
    return responses, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile evidence into a self-introduction narrative plan")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--model-id")
    parser.add_argument("--timeout-ms", type=int, default=300_000)
    parser.add_argument("--max-repairs", type=int, default=1)
    parser.add_argument("--output")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_dir = args.run.resolve()
    packet = compile_run_blueprint(run_dir)
    print(str(run_dir / "05_답변설계도.json"))
    if not args.generate:
        return 0
    responses, report = generate_run_draft(
        run_dir,
        packet=packet,
        model_id=args.model_id,
        timeout_ms=args.timeout_ms,
        max_repairs=args.max_repairs,
    )
    output = Path(args.output) if args.output else run_dir / "draft_narrative.json"
    if not output.is_absolute():
        output = run_dir / output
    output = output.resolve()
    if output.exists() and not args.force:
        raise NarrativeCompilerError(f"output already exists: {output}; use --force to replace")
    write_json(output, [asdict(item) for item in responses])
    write_json(run_dir / "05_서사컴파일_검증.json", report)
    if (
        report["deterministic_validation"]["status"] != "passed"
        or report["semantic_validation"]["status"] != "passed"
    ):
        print(str(run_dir / "05_서사컴파일_검증.json"))
        return 3
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
