"""Shadow-mode provenance observations for final assertions.

The report deliberately does not decide semantic entailment. It compares the
existing assertion compiler's support IDs with atomic ClaimGraph propositions
and records widening risks without changing production control flow.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping

from .authority_contract import lexical_tokens, metric_values
from .claim_graph import ClaimGraph, claim_graph_to_dict

SHADOW_JSON = "12_주장증명섀도우.json"
SHADOW_MD = "12_주장증명섀도우.md"
SCHEMA_VERSION = 1
ATOMIC_SUPPORT_THRESHOLD = 0.18


def _atomic_score(assertion_text: str, proposition: str) -> float:
    assertion_tokens = lexical_tokens(assertion_text)
    proposition_tokens = lexical_tokens(proposition)
    if not assertion_tokens or not proposition_tokens:
        return 0.0
    return round(
        len(assertion_tokens & proposition_tokens)
        / max(1, min(len(assertion_tokens), 8)),
        4,
    )


def _observe_assertion(
    assertion: Mapping[str, Any],
    graph: ClaimGraph,
) -> dict[str, Any]:
    by_id = graph.by_id()
    support_ids = tuple(
        str(value) for value in assertion.get("supported_by", []) if value
    )
    nodes = [by_id[value] for value in support_ids if value in by_id]
    missing = sorted(value for value in support_ids if value not in by_id)
    text = str(assertion.get("atomic_text", ""))
    assertion_tokens = lexical_tokens(text)

    support_rows = []
    authorised_metrics: set[str] = set()
    any_atomic_overlap = False
    any_context_only_overlap = False
    for node in nodes:
        proposition_tokens = lexical_tokens(node.proposition)
        context_tokens = lexical_tokens(" ".join(node.context))
        context_only_tokens = context_tokens - proposition_tokens
        atomic_overlap = sorted(assertion_tokens & proposition_tokens)
        context_only_overlap = sorted(assertion_tokens & context_only_tokens)
        any_atomic_overlap = any_atomic_overlap or bool(atomic_overlap)
        any_context_only_overlap = any_context_only_overlap or bool(
            context_only_overlap
        )
        if node.label.factual_authority:
            authorised_metrics.update(node.label.metric_values)
        support_rows.append(
            {
                "node_id": node.node_id,
                "factual_authority": node.label.factual_authority,
                "atomic_score": _atomic_score(text, node.proposition),
                "atomic_token_overlap": atomic_overlap,
                "context_only_token_overlap": context_only_overlap,
                "proposition_metrics": list(node.label.metric_values),
            }
        )

    assertion_metrics = set(metric_values(text))
    unsupported_atomic_metrics = sorted(
        assertion_metrics - authorised_metrics
    )
    warnings: list[str] = []
    if missing:
        warnings.append("support_id_missing_from_claim_graph")
    if unsupported_atomic_metrics:
        warnings.append("unsupported_atomic_metric")
    if not any_atomic_overlap and any_context_only_overlap:
        warnings.append("context_only_support_risk")
    current_status = str(assertion.get("authority_status", ""))
    if (
        current_status in {"supported", "bounded_interpretation"}
        and nodes
        and all(
            float(row["atomic_score"]) < ATOMIC_SUPPORT_THRESHOLD
            for row in support_rows
        )
    ):
        warnings.append("weak_atomic_proposition_support")
    if any(not node.label.factual_authority for node in nodes):
        warnings.append("non_factual_graph_support")

    if missing:
        shadow_status = "missing_graph_support"
    elif unsupported_atomic_metrics:
        shadow_status = "atomic_metric_review_required"
    elif warnings:
        shadow_status = "review_required"
    elif nodes:
        shadow_status = "observed_atomic_support"
    else:
        shadow_status = "no_graph_support"

    return {
        "assertion_id": str(assertion.get("assertion_id", "")),
        "question_index": int(assertion.get("question_index", 0) or 0),
        "atomic_text": text,
        "existing_authority_status": current_status,
        "existing_supported_by": list(support_ids),
        "graph_support": support_rows,
        "missing_graph_support_ids": missing,
        "assertion_metrics": sorted(assertion_metrics),
        "atomic_authorised_metrics": sorted(authorised_metrics),
        "unsupported_atomic_metrics": unsupported_atomic_metrics,
        "warnings": warnings,
        "provenance_closed": not missing and bool(nodes),
        "semantic_proof_closed": False,
        "shadow_status": shadow_status,
    }


def build_proof_shadow_report(
    assertion_report: Mapping[str, Any],
    graph: ClaimGraph,
) -> dict[str, Any]:
    assertions = [
        _observe_assertion(row, graph)
        for row in assertion_report.get("assertions", [])
        if isinstance(row, Mapping)
    ]
    warning_counts = Counter(
        warning for row in assertions for warning in row["warnings"]
    )
    status_counts = Counter(row["shadow_status"] for row in assertions)
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": "proof_carrying_claim_graph_shadow_v1",
        "decision_effect": "none_shadow_mode",
        "semantic_entailment_policy": (
            "observational_only_lexical_signals_are_not_semantic_proof"
        ),
        "claim_graph": claim_graph_to_dict(graph),
        "assertions": assertions,
        "summary": {
            "total_assertions": len(assertions),
            "provenance_closed": sum(
                bool(row["provenance_closed"]) for row in assertions
            ),
            "semantic_proof_closed": 0,
            "by_shadow_status": dict(sorted(status_counts.items())),
            "warnings": dict(sorted(warning_counts.items())),
            "atomic_metric_review_required": sum(
                row["shadow_status"] == "atomic_metric_review_required"
                for row in assertions
            ),
            "context_only_support_risk": warning_counts.get(
                "context_only_support_risk", 0
            ),
            "weak_atomic_proposition_support": warning_counts.get(
                "weak_atomic_proposition_support", 0
            ),
        },
    }


def render_proof_shadow(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# 주장 증명 섀도우",
        "",
        "- 모드: `shadow` — 기존 판정과 Golden Path 제어에 영향을 주지 않음",
        f"- 총 주장: {summary.get('total_assertions', 0)}",
        f"- provenance ID 연결 완료: {summary.get('provenance_closed', 0)}",
        "- semantic proof 완료: 0 (현재 버전은 의미 증명을 주장하지 않음)",
        (
            "- atomic metric 검토 필요: "
            f"{summary.get('atomic_metric_review_required', 0)}"
        ),
        (
            "- context-only support 위험: "
            f"{summary.get('context_only_support_risk', 0)}"
        ),
        "",
    ]
    for row in report.get("assertions", []):
        if not isinstance(row, Mapping):
            continue
        lines.extend(
            [
                (
                    f"## {row.get('assertion_id', '')} · "
                    f"문항 {row.get('question_index', 0)}"
                ),
                f"- shadow 상태: `{row.get('shadow_status', '')}`",
                f"- 주장: {row.get('atomic_text', '')}",
                (
                    "- 기존 근거: "
                    + (", ".join(row.get("existing_supported_by", [])) or "-")
                ),
                (
                    "- 경고: "
                    + (", ".join(row.get("warnings", [])) or "-")
                ),
                (
                    "- atomic metric 불일치: "
                    + (
                        ", ".join(row.get("unsupported_atomic_metrics", []))
                        or "-"
                    )
                ),
                "- semantic_proof_closed: `false`",
                "",
            ]
        )
    return "\n".join(lines)


def write_proof_shadow_artifacts(
    run_dir: Path,
    assertion_report: Mapping[str, Any],
    graph: ClaimGraph,
) -> tuple[Path, Path, dict[str, Any]]:
    report = build_proof_shadow_report(assertion_report, graph)
    json_path = run_dir / SHADOW_JSON
    markdown_path = run_dir / SHADOW_MD
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_proof_shadow(report),
        encoding="utf-8",
    )
    return json_path, markdown_path, report
