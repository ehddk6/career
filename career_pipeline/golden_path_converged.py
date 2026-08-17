"""Evidence-to-Signal convergence layer for the Career Pipeline Golden Path."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from . import golden_path as gp
from .assertion_compiler import ASSERTION_JSON, write_assertion_artifacts
from .authority_contract import (
    canonical_metric_values_by_question,
    canonical_metric_values_for_responses,
    metric_values,
    research_is_submission_authority,
)
from .evidence_portfolio import (
    build_evidence_portfolio,
    portfolio_for_stage,
    write_evidence_portfolio,
)
from .research_contract import ensure_canonical_research_pack
from .reliable_deep_writer import REPORT_JSON as RELIABLE_JUDGE_REPORT, reliable_generate_prose

CONVERGENCE_VERSION = "evidence_to_signal_contract_v2"
_BASE_DEFAULT_SERVICES = gp.default_services
_BASE_RUN_AUTHORITY_VIEW = gp._run_authority_view


def _hash_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode()).hexdigest()


def _authority_view(run: Path) -> dict[str, Any]:
    value = dict(_BASE_RUN_AUTHORITY_VIEW(run))
    value["contract_convergence_version"] = CONVERGENCE_VERSION
    return value


def _raw_research(run: Path) -> dict[str, dict[str, Any]]:
    path = run / "04_공식근거.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    return {
        str(row.get("claim_id")): dict(row)
        for row in payload
        if isinstance(row, Mapping) and row.get("claim_id")
    }


def _compat_research_score(run: Path, audit_module: Any, original: Any):
    raw = _raw_research(run)
    submission = {
        claim_id
        for claim_id, row in raw.items()
        if research_is_submission_authority(row, row)
    }
    stable = {
        claim_id
        for claim_id, row in raw.items()
        if claim_id in submission
        and str(row.get("freshness_class", "")) in {"stable", "posting_bound"}
    }

    def wrapped(run_dir, state, questions, responses):
        _, issues = original(run_dir, state, questions, responses)
        filtered = []
        for issue in issues:
            message = str(getattr(issue, "message", ""))
            code = str(getattr(issue, "code", ""))
            if code == "weak_source_type" and any(claim_id in message for claim_id in submission):
                continue
            if code == "missing_source_date" and any(claim_id in message for claim_id in stable):
                continue
            filtered.append(issue)
        return audit_module._deduct(25, filtered), filtered

    return wrapped


def _augment_audit(run: Path, audit_module: Any, payload: dict[str, Any]) -> dict[str, Any]:
    path = run / ASSERTION_JSON
    if not path.is_file():
        return payload
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return payload
    summary = report.get("summary", {}) if isinstance(report, Mapping) else {}
    unsupported = int(summary.get("unsupported", 0) or 0) if isinstance(summary, Mapping) else 0
    needs_review = int(summary.get("needs_review", 0) or 0) if isinstance(summary, Mapping) else 0
    issues = list(payload.get("issues", [])) if isinstance(payload.get("issues"), list) else []
    sections = payload.get("sections", {}) if isinstance(payload.get("sections"), Mapping) else {}
    cover = sections.get("cover_letter", {}) if isinstance(sections, Mapping) else {}
    penalty = 0
    if unsupported:
        issues.append(
            {
                "category": "assertion",
                "code": "unsupported_final_assertion",
                "severity": "high",
                "message": f"최종 답변에 authority contract가 지지하지 못한 주장이 {unsupported}개 있습니다.",
                "question_index": 0,
            }
        )
        penalty += 8
    if needs_review:
        issues.append(
            {
                "category": "assertion",
                "code": "causal_scope_review_required",
                "severity": "medium",
                "message": f"근거 연결 또는 인과·기여 범위를 추가 확인해야 하는 주장이 {needs_review}개 있습니다.",
                "question_index": 0,
            }
        )
        penalty += 4
    if penalty and isinstance(cover, dict):
        cover["score"] = max(0, int(cover.get("score", 0)) - penalty)
    total = sum(
        int(section.get("score", 0))
        for section in sections.values()
        if isinstance(section, Mapping)
    )
    payload.update(
        issues=issues,
        score=total,
        internal_validation_score=total,
        quality_gate=(
            "fail"
            if any(isinstance(row, Mapping) and row.get("severity") == "high" for row in issues)
            else "pass"
        ),
        human_review_recommended=bool(issues),
        recommendation=(
            "내부검증 우수"
            if total >= 95
            else "내부검증 통과"
            if total >= 90
            else "내부검증 보완 필요"
        ),
        assertion_compiler={
            "unsupported": unsupported,
            "needs_review": needs_review,
            "artifact": ASSERTION_JSON,
        },
        reliable_judge={
            "artifact": RELIABLE_JUDGE_REPORT,
            "present": (run / RELIABLE_JUDGE_REPORT).is_file(),
            "factual_authority_granted": False,
        },
    )
    (run / "11_최종품질감사.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run / "11_최종품질감사.md").write_text(
        audit_module.render_quality_audit(payload), encoding="utf-8"
    )
    return payload


def _canonical_interview_gate(base_gate, run: Path, draft_path: Path):
    issues = list(base_gate(run, draft_path))
    pack = run / "08_면접대비팩.md"
    if not pack.is_file():
        return issues
    from .orchestrator import _load_draft_responses
    from .profile_schema import load_ledger
    from .quality import _find_interview_question_marker

    responses, parse_issues = _load_draft_responses(draft_path)
    if parse_issues:
        return issues + [
            {
                "code": getattr(item, "code", "invalid_draft"),
                "question_index": getattr(item, "question_index", 0),
                "message": getattr(item, "message", str(item)),
            }
            for item in parse_issues
        ]
    ledger = load_ledger(run / "02_확정경험원장.json")
    allowed = canonical_metric_values_by_question(run, responses, ledger)
    text = pack.read_text(encoding="utf-8")
    visible = sorted(
        (
            (
                response.question_index,
                _find_interview_question_marker(text, response.question_index),
            )
            for response in responses
        ),
        key=lambda row: row[1],
    )
    visible = [row for row in visible if row[1] >= 0]
    seen = {
        (
            str(item.get("code")),
            int(item.get("question_index", 0)),
            str(item.get("message")),
        )
        for item in issues
        if isinstance(item, Mapping)
    }
    for offset, (question_index, start) in enumerate(visible):
        end = visible[offset + 1][1] if offset + 1 < len(visible) else len(text)
        for metric in metric_values(text[start:end]):
            if metric in allowed.get(question_index, set()):
                continue
            row = {
                "code": "unapproved_interview_metric_scope",
                "question_index": question_index,
                "message": (
                    f"문항 {question_index} 면접 블록에서 이 문항 근거가 승인하지 않은 "
                    f"수치를 사용했습니다: {metric}"
                ),
            }
            key = (row["code"], question_index, row["message"])
            if key not in seen:
                seen.add(key)
                issues.append(row)
    return issues


def converged_services() -> gp.GoldenPathServices:
    base = _BASE_DEFAULT_SERVICES()

    def research_gate(run):
        report = dict(base.research_gate(run))
        ensure_canonical_research_pack(run)
        report["contract_convergence"] = CONVERGENCE_VERSION
        return report

    def strategy_fingerprint(run):
        return _hash_json(
            {
                "base": base.strategy_fingerprint(run),
                "evidence_portfolio": build_evidence_portfolio(run),
                "contract": CONVERGENCE_VERSION,
                "reliable_prose_selection": "v1",
            }
        )

    def write_draft(run, config):
        _, _, portfolio = write_evidence_portfolio(run)
        import career_pipeline.deep_writer as deep_writer
        import career_pipeline.integrated_writer as integrated_writer

        original_prior = integrated_writer.strategy_prior_for_stage
        original_generate = deep_writer._generate_prose

        def with_portfolio(packet, stage):
            result = dict(original_prior(packet, stage))
            result["evidence_portfolio"] = portfolio_for_stage(portfolio, stage)
            return result

        integrated_writer.strategy_prior_for_stage = with_portfolio
        deep_writer._generate_prose = reliable_generate_prose
        try:
            report = dict(base.write_draft(run, config))
        finally:
            integrated_writer.strategy_prior_for_stage = original_prior
            deep_writer._generate_prose = original_generate
        report["evidence_portfolio"] = {
            "artifact": "05_근거포트폴리오.json",
            "weighted_signal_coverage": portfolio.get("summary", {}).get(
                "weighted_signal_coverage"
            ),
            "factual_authority_granted": False,
        }
        report["reliable_judge"] = {
            "artifact": RELIABLE_JUDGE_REPORT,
            "protocol": "position_swapped_score_schema_v1",
            "unstable_selection_policy": "deterministic_fallback",
            "factual_authority_granted": False,
        }
        return report

    def finalize(run, config):
        import career_pipeline.orchestrator as orchestrator

        original = orchestrator.referenced_claim_values
        orchestrator.referenced_claim_values = (
            lambda responses, ledger: canonical_metric_values_for_responses(
                run, responses, ledger
            )
        )
        try:
            return base.finalize(run, config)
        finally:
            orchestrator.referenced_claim_values = original

    def compile_interview(run):
        _, _, assertions = write_assertion_artifacts(run)
        plan = dict(base.compile_interview(run))
        plan["assertion_compiler"] = {
            "artifact": ASSERTION_JSON,
            "summary": assertions.get("summary", {}),
            "policy": "diagnostic_and_audit_gate_never_factual_authority",
        }
        path = run / "08_면접지능설계.json"
        if path.is_file():
            path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return plan

    def audit(run):
        ensure_canonical_research_pack(run)
        if not (run / ASSERTION_JSON).is_file():
            write_assertion_artifacts(run)
        import career_pipeline.audit as audit_module

        original_values = audit_module.referenced_claim_values
        original_research_score = audit_module._research_score
        audit_module.referenced_claim_values = (
            lambda responses, ledger: canonical_metric_values_for_responses(
                run, responses, ledger
            )
        )
        audit_module._research_score = _compat_research_score(
            run, audit_module, original_research_score
        )
        try:
            payload = dict(base.audit(run))
        finally:
            audit_module.referenced_claim_values = original_values
            audit_module._research_score = original_research_score
        return _augment_audit(run, audit_module, payload)

    return gp.GoldenPathServices(
        research_gate=research_gate,
        strategy_fingerprint=strategy_fingerprint,
        write_draft=write_draft,
        interview_gate=lambda run, draft: _canonical_interview_gate(
            base.interview_gate, run, draft
        ),
        finalize=finalize,
        resolve_final_draft=base.resolve_final_draft,
        compile_interview=compile_interview,
        audit=audit,
    )


def main(argv: list[str] | None = None) -> int:
    original_services = gp.default_services
    original_authority_view = gp._run_authority_view
    gp.default_services = converged_services
    gp._run_authority_view = _authority_view
    try:
        return gp.main(argv)
    finally:
        gp.default_services = original_services
        gp._run_authority_view = original_authority_view


if __name__ == "__main__":
    raise SystemExit(main())
