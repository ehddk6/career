"""Compile and render interview intelligence plans."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..profile_schema import load_ledger
from ..research_evidence import load_research_claims
from ..state import write_json
from .schema import (
    BANK_MD, PLAN_JSON, SCHEMA_VERSION, InterviewIntelligenceError, _compact, _compile_claim_graph,
    _intent, _load_draft, _load_state, _now, _question_map, _read_json, _research_raw, _resolve_draft_path,
)
from .questions import _load_weakness_profile, _question_bank, _recommended_sequence

def compile_interview_plan(run_dir: Path, *, draft_path: Path | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = _load_state(run_dir)
    draft_file = _resolve_draft_path(run_dir, draft_path)
    draft = _load_draft(draft_file)
    ledger_path = run_dir / "02_확정경험원장.json"
    research_path = run_dir / "04_공식근거.json"
    if not ledger_path.is_file():
        raise InterviewIntelligenceError("02_확정경험원장.json is required")
    if not research_path.is_file():
        raise InterviewIntelligenceError("04_공식근거.json is required")
    ledger = load_ledger(ledger_path)
    research_claims = load_research_claims(research_path)
    raw_research = _research_raw(research_path)
    prompts = _question_map(state, draft)
    graph = _compile_claim_graph(draft, ledger, research_claims, raw_research)
    root_value = state.get("root")
    root = Path(root_value).resolve() if isinstance(root_value, str) and root_value else None
    weakness = _load_weakness_profile(root)
    target = str(state.get("target", "")).strip()
    bank = _question_bank(draft, prompts, graph, target)
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "architecture": "structured_adaptive_claim_defense_v1",
        "generated_at": _now(),
        "run_dir": str(run_dir),
        "target": target,
        "source_artifacts": {
            "final_draft": str(draft_file),
            "experience_ledger": str(ledger_path),
            "official_research": str(research_path),
            "posting_and_questions": str(run_dir / "run.json"),
        },
        "authority": {
            "applicant_facts": "02_확정경험원장.json confirmed claims only",
            "organization_facts": "04_공식근거.json confirmed official claims only",
            "final_draft": "assertion surface to defend; not new factual authority",
            "strategy_guidance": "may shape practice only; never factual authority",
            "semantic_judges": "diagnostic only; never factual authority",
        },
        "design_contract": {
            "standardized_backbone": True,
            "adaptive_probe_selection": "expected_diagnostic_utility",
            "question_selection_targets": "weak_dimensions + claim_risk + uncovered_dimensions + uncovered_claim_nodes",
            "scoring_scale": "0-4 behaviorally anchored semantic dimensions",
            "hard_fact_gate_precedes_semantic_scoring": True,
            "raw_answers_saved_to_weakness_profile": False,
            "hiring_probability_estimation": False,
        },
        "research_basis": [
            {"id": "campion_palmer_campion_1997", "role": "structured_interview_backbone"},
            {"id": "campion_pursell_brown_1988", "role": "job_related_questions_and_anchored_scoring"},
            {"id": "taylor_small_2002", "role": "past_behavior_questions_and_anchored_scoring"},
            {"id": "levashina_et_al_2014", "role": "structured_probing_and_followups"},
            {"id": "sparkme_2026", "role": "experimental_adaptive_semi_structured_interview_design"},
        ],
        "application_questions": [
            {
                "question_index": row.question_index,
                "prompt": prompts.get(row.question_index, ""),
                "intent": _intent(prompts.get(row.question_index, "")),
                "answer_excerpt": _compact(row.answer, 240),
            }
            for row in draft
        ],
        "claim_graph": graph,
        "question_bank": bank,
        "weakness_profile": weakness,
    }
    plan["recommended_sequence"] = _recommended_sequence(plan)
    plan["summary"] = {
        "claim_nodes": len(graph["nodes"]),
        "applicant_claim_nodes": sum(node.get("source_kind") == "applicant" for node in graph["nodes"]),
        "research_claim_nodes": sum(node.get("source_kind") == "research" for node in graph["nodes"]),
        "standardized_questions": sum(bool(item.get("standardized")) for item in bank),
        "adaptive_probes": sum(not bool(item.get("standardized")) for item in bank),
        "highest_risk_nodes": [
            node["node_id"]
            for node in sorted(graph["nodes"], key=lambda item: (-float(item.get("risk", 1.0)), str(item.get("node_id"))))[:8]
        ],
    }
    return plan


def render_question_bank_markdown(plan: Mapping[str, Any]) -> str:
    bank = [item for item in plan.get("question_bank", []) if isinstance(item, Mapping)]
    by_id = {str(item.get("question_id")): item for item in bank}
    lines = [
        "# 면접 질문은행 — Structured-Adaptive Interview Intelligence",
        "",
        "> 이 문서는 연습·진단용이다. 합격 확률을 추정하지 않으며, 개인 사실은 확정 경험원장, 기관 사실은 공식근거만 권한을 가진다.",
        "",
        "## 권장 순서",
        "",
    ]
    for position, qid in enumerate(plan.get("recommended_sequence", []), 1):
        item = by_id.get(str(qid), {})
        lines.append(f"{position}. **{qid}** — {item.get('prompt', '')}")
    lines.extend(("", "## 고정 코어 질문", ""))
    for item in bank:
        if not item.get("standardized"):
            continue
        lines.extend(
            (
                f"### {item.get('question_id')}",
                str(item.get("prompt", "")),
                f"- 평가 차원: {', '.join(item.get('dimensions', []))}",
                f"- 권장 시간: {item.get('expected_seconds')}초",
                f"- 목적: {item.get('rationale', '')}",
                "",
            )
        )
    lines.extend(("## 적응형 꼬리·압박 질문", ""))
    for item in bank:
        if item.get("standardized"):
            continue
        lines.extend(
            (
                f"### {item.get('question_id')} · {item.get('family')}",
                str(item.get("prompt", "")),
                f"- 평가 차원: {', '.join(item.get('dimensions', []))}",
                f"- 위험도: {item.get('risk')} / 난도: {item.get('difficulty')}",
                f"- 목적: {item.get('rationale', '')}",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def write_interview_plan(run_dir: Path, *, draft_path: Path | None = None) -> tuple[Path, Path, dict[str, Any]]:
    plan = compile_interview_plan(run_dir, draft_path=draft_path)
    run_dir = run_dir.resolve()
    json_path = run_dir / PLAN_JSON
    md_path = run_dir / BANK_MD
    write_json(json_path, plan)
    md_path.write_text(render_question_bank_markdown(plan), encoding="utf-8")
    return json_path, md_path, plan

def _load_plan(run_dir: Path, plan_path: Path | None = None) -> dict[str, Any]:
    path = plan_path or (run_dir / PLAN_JSON)
    if not path.is_absolute():
        path = run_dir / path
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise InterviewIntelligenceError("interview plan must be an object")
    return payload
