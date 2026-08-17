"""Evidence × Construct shadow portfolio.

This module compares confirmed applicant evidence with behavioral indicators
from the target TaskConstructGraph. It is diagnostic only and never grants
factual or construct authority.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .job_analysis_schema import (
    JobAnalysisGraph,
    job_analysis_graph_to_dict,
)

CONSTRUCT_PORTFOLIO_JSON = "05_구성개념근거매트릭스.json"
CONSTRUCT_PORTFOLIO_MD = "05_구성개념근거매트릭스.md"
SCHEMA_VERSION = 1
ARCHITECTURE = "evidence_construct_shadow_matrix_v1"

_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = {
    "지원", "직무", "업무", "기관", "회사", "관련", "경험", "역량", "필요",
    "통해", "대한", "문항", "설명", "수행", "담당", "및", "등",
}


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _tokens(text: str) -> set[str]:
    return {
        item.casefold()
        for item in _WORD.findall(text or "")
        if item.casefold() not in _STOP
    }


def _score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return round(len(left & right) / max(1, min(len(right), 8)), 4)


def _evidence_candidates(ledger: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for experience in ledger.get("experiences", []) or []:
        if (
            not isinstance(experience, Mapping)
            or experience.get("status") != "confirmed"
        ):
            continue
        experience_id = str(experience.get("experience_id", ""))
        context = " ".join(
            [
                str(experience.get("title", "")),
                str(experience.get("role", "")),
                str(experience.get("situation", "")),
                *[str(item) for item in experience.get("actions", []) or []],
                *[str(item) for item in experience.get("outcomes", []) or []],
            ]
        ).strip()
        for claim in experience.get("claims", []) or []:
            if (
                not isinstance(claim, Mapping)
                or claim.get("status") != "confirmed"
            ):
                continue
            claim_id = str(
                claim.get("claim_id") or claim.get("field") or ""
            )
            if not claim_id:
                continue
            atomic = str(claim.get("normalized_value", "")).strip()
            verification = (
                claim.get("verification", {})
                if isinstance(claim.get("verification"), Mapping)
                else {}
            )
            rows.append(
                {
                    "evidence_id": f"applicant:{experience_id}:{claim_id}",
                    "source_kind": "applicant",
                    "experience_id": experience_id,
                    "claim_id": claim_id,
                    "atomic_text": atomic,
                    "context_text": context,
                    "atomic_tokens": _tokens(atomic),
                    "context_tokens": _tokens(context),
                    "contribution_scope": str(
                        verification.get("contribution", "unknown")
                    ),
                    "factual_authority_granted": False,
                }
            )
    return rows


def _indicator_map(graph: JobAnalysisGraph) -> dict[str, list[str]]:
    indicators = {
        item.indicator_id: item.behavior
        for item in graph.behavioral_indicators
    }
    return {
        construct.construct_id: [
            indicators[item]
            for item in construct.behavioral_indicator_ids
            if item in indicators
        ]
        for construct in graph.constructs
    }


def _relation(
    candidate: Mapping[str, Any],
    construct_label: str,
    indicators: Sequence[str],
) -> dict[str, Any]:
    atomic_tokens = set(candidate.get("atomic_tokens", set()))
    context_tokens = set(candidate.get("context_tokens", set()))
    label_tokens = _tokens(construct_label)

    best_atomic = 0.0
    best_context = 0.0
    best_atomic_overlap: list[str] = []
    best_context_overlap: list[str] = []
    for indicator in indicators:
        indicator_tokens = _tokens(indicator)
        atomic_overlap = sorted(atomic_tokens & indicator_tokens)
        context_overlap = sorted(context_tokens & indicator_tokens)
        atomic_score = _score(atomic_tokens, indicator_tokens)
        context_score = _score(context_tokens, indicator_tokens)
        if atomic_score > best_atomic:
            best_atomic = atomic_score
            best_atomic_overlap = atomic_overlap
        if context_score > best_context:
            best_context = context_score
            best_context_overlap = context_overlap

    label_overlap = sorted(atomic_tokens & label_tokens)
    if best_atomic >= 0.34 and len(best_atomic_overlap) >= 2:
        relation = "direct"
    elif best_atomic > 0 or (
        best_context >= 0.25 and len(best_context_overlap) >= 2
    ):
        relation = "partial"
    elif label_overlap or best_context_overlap:
        relation = "inferred"
    else:
        relation = "none"

    return {
        "relation": relation,
        "atomic_score": best_atomic,
        "context_score": best_context,
        "atomic_indicator_overlap": best_atomic_overlap,
        "context_indicator_overlap": best_context_overlap,
        "construct_label_overlap": label_overlap,
        "atomic_match": bool(best_atomic_overlap),
        "context_match": bool(best_context_overlap),
    }


def _question_constructs(
    question: Mapping[str, Any],
    graph: JobAnalysisGraph,
) -> set[str]:
    prompt_tokens = _tokens(str(question.get("prompt", "")))
    by_indicator = _indicator_map(graph)
    scored: list[tuple[float, str]] = []
    for construct in graph.constructs:
        if construct.construct_id not in graph.core_construct_ids:
            continue
        surface = _tokens(construct.label)
        for indicator in by_indicator.get(construct.construct_id, []):
            surface |= _tokens(indicator)
        score = _score(prompt_tokens, surface)
        scored.append((score, construct.construct_id))
    positive = {construct_id for score, construct_id in scored if score > 0}
    return positive or set(graph.core_construct_ids)


def build_construct_portfolio(
    graph: JobAnalysisGraph,
    ledger: Mapping[str, Any],
    *,
    evidence_portfolio: Mapping[str, Any] | None = None,
    run_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = _evidence_candidates(
        ledger if isinstance(ledger, Mapping) else {}
    )
    indicator_map = _indicator_map(graph)
    links: list[dict[str, Any]] = []

    for candidate in candidates:
        for construct in graph.constructs:
            if construct.status not in {
                "target_explicit",
                "target_supported",
            }:
                continue
            observed = _relation(
                candidate,
                construct.label,
                indicator_map.get(construct.construct_id, []),
            )
            if observed["relation"] == "none":
                continue
            link_id = "ecl_" + sha256(
                (
                    str(candidate["evidence_id"])
                    + "\0"
                    + construct.construct_id
                    + "\0"
                    + observed["relation"]
                ).encode("utf-8")
            ).hexdigest()[:18]
            links.append(
                {
                    "link_id": link_id,
                    "evidence_id": candidate["evidence_id"],
                    "experience_id": candidate["experience_id"],
                    "claim_id": candidate["claim_id"],
                    "construct_id": construct.construct_id,
                    "relation": observed["relation"],
                    "atomic_score": observed["atomic_score"],
                    "context_score": observed["context_score"],
                    "atomic_indicator_overlap": observed[
                        "atomic_indicator_overlap"
                    ],
                    "context_indicator_overlap": observed[
                        "context_indicator_overlap"
                    ],
                    "construct_label_overlap": observed[
                        "construct_label_overlap"
                    ],
                    "atomic_match": observed["atomic_match"],
                    "context_match": observed["context_match"],
                    "contribution_scope": candidate[
                        "contribution_scope"
                    ],
                    "factual_authority_granted": False,
                    "construct_authority_added": False,
                }
            )

    links.sort(
        key=lambda row: (
            row["construct_id"],
            {"direct": 0, "partial": 1, "inferred": 2}.get(
                row["relation"], 3
            ),
            -float(row["atomic_score"]),
            row["evidence_id"],
        )
    )

    covered = {
        row["construct_id"]
        for row in links
        if row["relation"] in {"direct", "partial"}
    }
    uncovered_core = sorted(
        set(graph.core_construct_ids) - covered
    )

    by_evidence: dict[str, list[dict[str, Any]]] = {}
    for row in links:
        by_evidence.setdefault(str(row["evidence_id"]), []).append(row)

    current = (
        evidence_portfolio
        if isinstance(evidence_portfolio, Mapping)
        else {}
    )
    state = run_state if isinstance(run_state, Mapping) else {}
    question_by_index = {
        int(row["index"]): row
        for row in state.get("questions", []) or []
        if isinstance(row, Mapping) and isinstance(row.get("index"), int)
    }
    disagreements: list[dict[str, Any]] = []
    selected_by_question: dict[int, set[str]] = {}
    for assignment in current.get("assignments", []) or []:
        if not isinstance(assignment, Mapping):
            continue
        question_index = int(assignment.get("question_index", 0) or 0)
        selected: set[str] = set()
        for preferred in assignment.get("preferred_evidence", []) or []:
            if not isinstance(preferred, Mapping):
                continue
            evidence_id = str(preferred.get("evidence_id", ""))
            if not evidence_id:
                continue
            selected.add(evidence_id)
            relevant_links = [
                row
                for row in by_evidence.get(evidence_id, [])
                if row["construct_id"] in set(graph.core_construct_ids)
                and row["relation"] in {"direct", "partial"}
            ]
            if not relevant_links and str(
                preferred.get("source_kind", "")
            ) == "applicant":
                disagreements.append(
                    {
                        "kind": "lexical_high_construct_weak",
                        "question_index": question_index,
                        "evidence_id": evidence_id,
                        "planning_score": preferred.get(
                            "planning_score"
                        ),
                    }
                )
        selected_by_question[question_index] = selected

    for question_index, question in question_by_index.items():
        relevant_constructs = _question_constructs(question, graph)
        selected = selected_by_question.get(question_index, set())
        direct_candidates = sorted(
            {
                row["evidence_id"]
                for row in links
                if row["relation"] == "direct"
                and row["construct_id"] in relevant_constructs
            }
        )
        for evidence_id in direct_candidates:
            if evidence_id not in selected:
                disagreements.append(
                    {
                        "kind": "construct_direct_not_selected",
                        "question_index": question_index,
                        "evidence_id": evidence_id,
                        "construct_ids": sorted(
                            {
                                row["construct_id"]
                                for row in links
                                if row["evidence_id"] == evidence_id
                                and row["relation"] == "direct"
                                and row["construct_id"]
                                in relevant_constructs
                            }
                        ),
                    }
                )

    disagreement_counts: dict[str, int] = {}
    for row in disagreements:
        key = str(row["kind"])
        disagreement_counts[key] = disagreement_counts.get(key, 0) + 1

    payload = {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "decision_effect": "none_shadow_mode",
        "graph_id": graph.graph_id,
        "job_analysis": {
            "artifact": "04_직무구성개념.json",
            "core_construct_ids": list(graph.core_construct_ids),
        },
        "links": links,
        "uncovered_core_construct_ids": uncovered_core,
        "disagreements": disagreements,
        "summary": {
            "candidate_count": len(candidates),
            "link_count": len(links),
            "direct_link_count": sum(
                row["relation"] == "direct" for row in links
            ),
            "partial_link_count": sum(
                row["relation"] == "partial" for row in links
            ),
            "inferred_link_count": sum(
                row["relation"] == "inferred" for row in links
            ),
            "core_construct_count": len(graph.core_construct_ids),
            "covered_core_construct_count": len(
                set(graph.core_construct_ids) - set(uncovered_core)
            ),
            "uncovered_core_construct_count": len(uncovered_core),
            "disagreement_counts": dict(
                sorted(disagreement_counts.items())
            ),
        },
        "policy": {
            "factual_authority_granted": False,
            "construct_authority_added": False,
            "research_is_not_applicant_evidence": True,
            "keyword_only_match_is_not_direct": True,
            "context_only_match_is_not_direct": True,
        },
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["matrix_id"] = sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]
    return payload


def render_construct_portfolio(
    payload: Mapping[str, Any],
    graph: JobAnalysisGraph,
) -> str:
    by_construct = {
        item.construct_id: item for item in graph.constructs
    }
    lines = [
        "# 구성개념 × 지원자 근거 섀도우",
        "",
        "> 기존 Evidence Portfolio와 writer 판정을 바꾸지 않는 shadow 분석이다.",
        "",
        f"- graph_id: `{payload.get('graph_id', '')}`",
        f"- matrix_id: `{payload.get('matrix_id', '')}`",
        f"- direct links: {payload.get('summary', {}).get('direct_link_count', 0)}",
        f"- uncovered core constructs: {payload.get('summary', {}).get('uncovered_core_construct_count', 0)}",
        "",
        "## 핵심 구성개념별 근거",
        "",
    ]
    core = list(payload.get("job_analysis", {}).get("core_construct_ids", []))
    for construct_id in core:
        construct = by_construct.get(str(construct_id))
        label = construct.label if construct else str(construct_id)
        lines.append(f"### {label} · `{construct_id}`")
        rows = [
            row
            for row in payload.get("links", [])
            if isinstance(row, Mapping)
            and row.get("construct_id") == construct_id
        ]
        if not rows:
            lines.append("- 직접/부분 근거 없음")
        else:
            for row in rows[:8]:
                lines.append(
                    f"- `{row.get('evidence_id')}` → "
                    f"`{row.get('relation')}` "
                    f"(atomic={row.get('atomic_score')}, "
                    f"context={row.get('context_score')})"
                )
        lines.append("")
    lines += ["## 기존 포트폴리오와 불일치", ""]
    disagreements = payload.get("disagreements", [])
    if not disagreements:
        lines.append("- 없음")
    else:
        for row in disagreements:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"- `{row.get('kind')}` · 문항 "
                f"{row.get('question_index', 0)} · "
                f"`{row.get('evidence_id', '')}`"
            )
    lines += [
        "",
        "## 정책",
        "",
        "- 회사/연구 근거는 지원자 능력 근거로 사용하지 않는다.",
        "- construct 명칭 단어만 겹치는 경우 direct로 판정하지 않는다.",
        "- context-only 행동 일치는 direct로 판정하지 않는다.",
        "- 이 산출물은 사실 권한이나 construct 권한을 추가하지 않는다.",
    ]
    return "\n".join(lines)


def write_construct_portfolio(
    run_dir: Path,
    *,
    job_graph: JobAnalysisGraph,
    evidence_portfolio: Mapping[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    run = run_dir.resolve()
    ledger = _read(run / "02_확정경험원장.json", {})
    state = _read(run / "run.json", {})
    if not isinstance(ledger, Mapping):
        ledger = {}
    if not isinstance(state, Mapping):
        state = {}
    current = (
        evidence_portfolio
        if isinstance(evidence_portfolio, Mapping)
        else _read(run / "05_근거포트폴리오.json", {})
    )
    if not isinstance(current, Mapping):
        current = {}
    payload = build_construct_portfolio(
        job_graph,
        ledger,
        evidence_portfolio=current,
        run_state=state,
    )
    json_path = run / CONSTRUCT_PORTFOLIO_JSON
    markdown_path = run / CONSTRUCT_PORTFOLIO_MD
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_construct_portfolio(payload, job_graph),
        encoding="utf-8",
    )
    return json_path, markdown_path, payload
