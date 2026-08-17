"""Deterministic shadow audit of real career runs: JobAnalysis x Evidence x Construct.

Recomputes the JobAnalysisGraph, the lexical Evidence Portfolio, and the
Construct Portfolio entirely in memory for each eligible run directory and
reports:

* disagreement kind A (``lexical_high_construct_weak``): evidence the lexical
  portfolio preferred, but which has no direct/partial link to a core
  construct;
* disagreement kind B (``construct_direct_not_selected``): evidence with a
  direct link to a question-relevant core construct that the lexical
  portfolio did not select;
* uncovered core constructs (no direct/partial coverage at all);
* context-only matches (context tokens only, never direct);
* authority-boundary checks (taxonomy prior escalation, research factual
  authority, false-direct verdicts).

Classification rules (deterministic, no LLM, documented here so results are
reproducible):

A (lexical_high_construct_weak)
    - atomic core overlap exists  -> ``insufficient`` (threshold sensitivity)
    - context-only core overlap   -> ``construct_mapper_preferred``
    - no core grounding, but the evidence covers >=1 posting/question signal
                                   -> ``insufficient`` (lenses disagree on
                                      different axes; needs human judgment)
    - no core grounding and the run has uncovered core constructs
                                   -> ``insufficient`` (indicator coverage gap)
    - no core grounding otherwise -> ``construct_mapper_preferred``

B (construct_direct_not_selected)
    - direct candidate score > best selected applicant score
                                   -> ``construct_mapper_preferred``
    - no applicant evidence selected for the question (research only)
                                   -> ``construct_mapper_preferred``
    - direct candidate shares >=2 atomic tokens with the question prompt
                                   -> ``construct_mapper_preferred``
    - otherwise                   -> ``lexical_mapper_preferred``

The detailed per-disagreement report (which contains atomic claim text from
real runs) is only ever written below ``career_runs/_audit/``, which is
git-ignored.  The committed report must stay aggregate/anonymised.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .evidence_portfolio import (
    _candidates,
    _rel,
    _signals,
    build_evidence_portfolio,
)
from .job_analysis_compiler import build_job_analysis_graph
from .construct_portfolio import build_construct_portfolio

AUDIT_ROOT = "_audit"
GENERIC_TOKENS = {
    "업무", "처리", "수행", "관리", "지원", "작성", "검토", "조사", "분석",
    "수집", "정리", "확인", "점검", "대응", "운영", "개선", "작업", "기록",
    "진행", "참여", "활용", "보고",
}

_INPUT_FILES = (
    "run.json",
    "00_채용공고분석.json",
    "02_확정경험원장.json",
    "04_공식근거.json",
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _tokens(text: str) -> set[str]:
    return {
        item.casefold()
        for item in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or "")
    }


def _binding_families(graph: Any) -> dict[str, str]:
    return {
        binding.source_id: binding.source_family
        for binding in graph.source_bindings
    }


def _candidate_score(
    candidate: Mapping[str, Any],
    signals: list[dict[str, Any]],
    question_tokens: set[str],
) -> float:
    ss = {
        signal["signal_id"]: _rel(candidate, signal)
        for signal in signals
    }
    weighted = sum(ss[s["signal_id"]] * float(s["weight"]) for s in signals)
    qo = (
        len(question_tokens & set(candidate.get("tokens", [])))
        / max(1, min(len(question_tokens), 8))
        if question_tokens
        else 0.0
    )
    return (
        weighted
        + qo * 1.1
        + float(candidate.get("defensibility", 1.0)) * 0.75
        - float(candidate.get("risk", 0.0)) * 0.8
    )


def _question_tokens(state: Mapping[str, Any], question_index: int) -> set[str]:
    for question in state.get("questions", []) or []:
        if (
            isinstance(question, Mapping)
            and int(question.get("index", -1)) == question_index
        ):
            return _tokens(str(question.get("prompt", "")))
    return set()


def _classify_a(
    links: list[dict[str, Any]],
    core_ids: set[str],
    uncovered: list[str],
    signal_covered: bool,
) -> str:
    core_atomic = [
        row
        for row in links
        if row["atomic_match"] and row["construct_id"] in core_ids
    ]
    if core_atomic:
        return "insufficient"
    context_only_core = [
        row
        for row in links
        if row["construct_id"] in core_ids
        and row["context_match"]
        and not row["atomic_match"]
    ]
    if context_only_core:
        return "construct_mapper_preferred"
    if signal_covered:
        return "insufficient"
    if uncovered:
        return "insufficient"
    return "construct_mapper_preferred"


def _classify_b(
    direct: dict[str, Any],
    question_index: int,
    ep: Mapping[str, Any],
    candidates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    state: Mapping[str, Any],
) -> str:
    assignment = next(
        (
            row
            for row in ep.get("assignments", []) or []
            if isinstance(row, Mapping)
            and int(row.get("question_index", -1)) == question_index
        ),
        {},
    )
    selected = [
        row
        for row in assignment.get("preferred_evidence", []) or []
        if isinstance(row, Mapping)
    ]
    applicant_selected = [
        row for row in selected if row.get("source_kind") == "applicant"
    ]
    best_selected = max(
        (float(row.get("planning_score", 0.0) or 0.0) for row in applicant_selected),
        default=0.0,
    )
    direct_row = next(
        (
            c
            for c in candidates
            if str(c.get("evidence_id", "")) == str(direct["evidence_id"])
        ),
        None,
    )
    question_tokens = _question_tokens(state, question_index)
    if direct_row is None:
        return "insufficient"
    score = _candidate_score(direct_row, signals, question_tokens)
    if score > best_selected + 0.001:
        return "construct_mapper_preferred"
    if not applicant_selected:
        return "construct_mapper_preferred"
    if len(question_tokens & set(direct_row.get("tokens", []))) >= 2:
        return "construct_mapper_preferred"
    return "lexical_mapper_preferred"


def audit_run(run_dir: Path) -> dict[str, Any] | None:
    run = run_dir.resolve()
    if not all((run / name).is_file() for name in _INPUT_FILES):
        return None
    state = _read_json(run / "run.json", {})
    posting = _read_json(run / "00_채용공고분석.json", {})
    ledger = _read_json(run / "02_확정경험원장.json", {})
    research = _read_json(run / "04_공식근거.json", [])
    if not isinstance(state, Mapping) or not isinstance(posting, Mapping):
        return None
    if not isinstance(ledger, Mapping):
        ledger = {}
    if not isinstance(research, list):
        research = []

    graph = build_job_analysis_graph(
        posting,
        tuple(row for row in research if isinstance(row, Mapping)),
        target=str(state.get("target") or posting.get("target") or "").strip(),
    )
    ep = build_evidence_portfolio(run)
    cp = build_construct_portfolio(
        graph,
        ledger,
        evidence_portfolio=ep,
        run_state=state,
    )

    core_ids = set(graph.core_construct_ids)
    bindings = _binding_families(graph)
    links = [row for row in cp.get("links", []) or [] if isinstance(row, Mapping)]

    taxonomy_sourced_target = [
        construct.construct_id
        for construct in graph.constructs
        if construct.status in {"target_explicit", "target_supported"}
        and construct.source_binding_ids
        and all(
            "taxonomy" in bindings.get(sid, "")
            for sid in construct.source_binding_ids
        )
    ]
    context_only_direct = [
        row
        for row in links
        if row.get("relation") == "direct" and not row.get("atomic_match")
    ]
    false_direct = [
        row
        for row in links
        if row.get("relation") == "direct"
        and (float(row.get("atomic_score", 1.0) or 1.0) < 0.34)
    ]
    generic_direct = [
        row
        for row in links
        if row.get("relation") == "direct"
        and row.get("atomic_indicator_overlap")
        and all(
            token in GENERIC_TOKENS
            for token in row.get("atomic_indicator_overlap", [])
        )
    ]
    context_only_links = [
        row
        for row in links
        if row.get("context_match") and not row.get("atomic_match")
    ]

    disagreements = []
    for row in cp.get("disagreements", []) or []:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("kind", ""))
        evidence_id = str(row.get("evidence_id", ""))
        question_index = int(row.get("question_index", 0) or 0)
        evidence_links = [r for r in links if r["evidence_id"] == evidence_id]
        if kind == "lexical_high_construct_weak":
            assignment = next(
                (
                    item
                    for item in ep.get("assignments", []) or []
                    if isinstance(item, Mapping)
                    and int(item.get("question_index", -1)) == question_index
                ),
                {},
            )
            preferred = next(
                (
                    item
                    for item in assignment.get("preferred_evidence", []) or []
                    if isinstance(item, Mapping)
                    and str(item.get("evidence_id", "")) == evidence_id
                ),
                None,
            )
            signal_covered = bool(
                (preferred or {}).get("covered_signal_ids", []) or []
            )
            classification = _classify_a(
                evidence_links,
                core_ids,
                cp.get("uncovered_core_construct_ids", []) or [],
                signal_covered,
            )
            disagreements.append(
                {
                    "kind": kind,
                    "question_index": question_index,
                    "evidence_id": evidence_id,
                    "classification": classification,
                    "signal_covered": signal_covered,
                    "link_count": len(evidence_links),
                    "atomic_core_link_count": sum(
                        1
                        for r in evidence_links
                        if r["atomic_match"] and r["construct_id"] in core_ids
                    ),
                    "context_only_core_link_count": sum(
                        1
                        for r in evidence_links
                        if r["construct_id"] in core_ids
                        and r["context_match"]
                        and not r["atomic_match"]
                    ),
                }
            )
        elif kind == "construct_direct_not_selected":
            classification = _classify_b(
                row,
                question_index,
                ep,
                _candidates(ledger, research),
                _signals(posting, state),
                state,
            )
            disagreements.append(
                {
                    "kind": kind,
                    "question_index": question_index,
                    "evidence_id": evidence_id,
                    "construct_ids": row.get("construct_ids", []),
                    "classification": classification,
                }
            )

    claim_texts: dict[str, str] = {}
    for experience in ledger.get("experiences", []) or []:
        if not isinstance(experience, Mapping):
            continue
        eid = str(experience.get("experience_id", ""))
        for claim in experience.get("claims", []) or []:
            if not isinstance(claim, Mapping):
                continue
            claim_texts[f"applicant:{eid}:{str(claim.get('claim_id') or claim.get('field') or '')}"] = (
                str(claim.get("normalized_value", ""))
            )

    return {
        "run_name": run.name,
        "target": str(state.get("target", "")),
        "question_count": len(state.get("questions", []) or []),
        "core_construct_ids": list(core_ids),
        "uncovered_core_construct_ids": cp.get("uncovered_core_construct_ids", []) or [],
        "link_summary": {
            "direct": sum(r.get("relation") == "direct" for r in links),
            "partial": sum(r.get("relation") == "partial" for r in links),
            "inferred": sum(r.get("relation") == "inferred" for r in links),
            "context_only": len(context_only_links),
        },
        "authority_checks": {
            "taxonomy_escalation_candidates": taxonomy_sourced_target,
            "context_only_direct_violations": len(context_only_direct),
            "false_direct_violations": len(false_direct),
            "generic_direct_candidates": len(generic_direct),
        },
        "disagreements": disagreements,
        "claim_texts": claim_texts,
    }


def _render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# 실측 run 구성개념 불일치 감사 (로컬 전용)",
        "",
        "> 이 리포트는 `career_runs/`의 실제 데이터를 포함하므로 git에 커밋하지 않는다.",
        "",
        f"- audited runs: {report['real_run_count']}",
        f"- lexical_high_construct_weak (A): {report['lexical_high_construct_weak_count']}",
        f"- construct_direct_not_selected (B): {report['construct_direct_not_selected_count']}",
        f"- reviewed disagreements: {report['reviewed_disagreement_count']}",
        f"- construct_mapper_preferred: {report['construct_mapper_preferred_count']}",
        f"- lexical_mapper_preferred: {report['lexical_mapper_preferred_count']}",
        f"- unresolved (insufficient): {report['unresolved_count']}",
        f"- false_direct: {report['false_direct_count']}",
        f"- context_only_direct_violation: {report['context_only_direct_violation_count']}",
        f"- taxonomy_escalation_violation: {report['taxonomy_escalation_violation_count']}",
        f"- generic_direct_candidates: {report['generic_direct_candidate_count']}",
        f"- runs with uncovered core constructs: {report['uncovered_core_runs']} "
        f"(total {report['uncovered_core_construct_total']})",
        "",
    ]
    for record in report.get("runs", []) or []:
        if not isinstance(record, Mapping):
            continue
        lines.append(
            f"## {record['run_name']} (core {len(record['core_construct_ids'])}, "
            f"uncovered {len(record['uncovered_core_construct_ids'])}, "
            f"direct {record['link_summary']['direct']}, "
            f"partial {record['link_summary']['partial']}, "
            f"inferred {record['link_summary']['inferred']})"
        )
        for row in record.get("disagreements", []) or []:
            if not isinstance(row, Mapping):
                continue
            atomic = (record.get("claim_texts") or {}).get(
                str(row.get("evidence_id", "")), ""
            )
            lines.append(
                f"- Q{row['question_index']} [{row['kind']}] "
                f"`{row['evidence_id']}` -> {row['classification']} "
                f"(atomic: {str(atomic)[:70]})"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic shadow disagreement audit over real career runs."
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("career_runs"),
        help="root directory containing run directories",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory for the detailed report (default: <runs>/_audit)",
    )
    args = parser.parse_args()

    runs_root = args.runs.resolve()
    out_root = (args.out or (runs_root / AUDIT_ROOT)).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    records = []
    for directory in sorted(runs_root.iterdir()):
        if not directory.is_dir():
            continue
        record = audit_run(directory)
        if record is not None:
            records.append(record)

    counts: dict[str, int] = {}
    for record in records:
        for row in record["disagreements"]:
            key = row["classification"]
            counts[key] = counts.get(key, 0) + 1
    kind_counts: dict[str, int] = {}
    for record in records:
        for row in record["disagreements"]:
            kind_counts[row["kind"]] = kind_counts.get(row["kind"], 0) + 1
    violation_counts: dict[str, int] = {}
    for record in records:
        for key, value in record["authority_checks"].items():
            if isinstance(value, list):
                value = len(value)
            violation_counts[key] = violation_counts.get(key, 0) + int(value)
    uncovered_runs = sum(
        1 for record in records if record["uncovered_core_construct_ids"]
    )
    total_uncovered = sum(
        len(record["uncovered_core_construct_ids"]) for record in records
    )

    report = {
        "generated_at": "2026-08-17T00:00:00+09:00",
        "audit_script": "career_pipeline/real_run_disagreement_audit.py",
        "real_run_count": len(records),
        "lexical_high_construct_weak_count": kind_counts.get(
            "lexical_high_construct_weak", 0
        ),
        "construct_direct_not_selected_count": kind_counts.get(
            "construct_direct_not_selected", 0
        ),
        "reviewed_disagreement_count": sum(len(r["disagreements"]) for r in records),
        "construct_mapper_preferred_count": counts.get("construct_mapper_preferred", 0),
        "lexical_mapper_preferred_count": counts.get("lexical_mapper_preferred", 0),
        "unresolved_count": counts.get("insufficient", 0),
        "false_direct_count": violation_counts.get("false_direct_violations", 0),
        "context_only_direct_violation_count": violation_counts.get(
            "context_only_direct_violations", 0
        ),
        "taxonomy_escalation_violation_count": len(
            {
                cid
                for record in records
                for cid in record["authority_checks"][
                    "taxonomy_escalation_candidates"
                ]
            }
        ),
        "generic_direct_candidate_count": violation_counts.get(
            "generic_direct_candidates", 0
        ),
        "uncovered_core_runs": uncovered_runs,
        "uncovered_core_construct_total": total_uncovered,
        "runs": records,
    }
    detail_path = out_root / "2026-08-17-real-run-disagreement-audit.detailed.json"
    detail_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path = out_root / "2026-08-17-real-run-disagreement-audit.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(f"audited {len(records)} runs")
    print(f"detailed report: {detail_path}")
    print(f"markdown review: {md_path}")
    print(json.dumps(
        {
            key: value
            for key, value in report.items()
            if key not in {"runs"}
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()