"""Materialize and refresh the Evidence-First Company Research workspace.

The workspace is deliberately separate from browsing. Agents or humans may use
any retrieval tool, but only claims that satisfy this deterministic contract are
allowed to feed the writing pipeline.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from .research_conflicts import resolve_research_conflicts
from .research_coverage import build_research_coverage
from .research_planner import compile_research_plan
from .research_source_registry import build_source_registry, tier_for_source_type

PLAN_FILE = "04_리서치계획.json"
SOURCE_FILE = "04_리서치출처.json"
CLAIM_FILE = "04_공식근거.json"
CONFLICT_FILE = "04_근거충돌.json"
COVERAGE_FILE = "04_근거커버리지.json"
PACK_FILE = "04_기업직무조사.md"

ROLE_FROM_TYPE = {
    "organization_role": "organization_differentiator",
    "job_duty": "real_operating_role",
    "industry_issue": "issue_mechanism",
    "program_or_service": "institution_response",
    "risk_or_limit": "operating_constraint",
    "selection_criteria": "operating_constraint",
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _question_role_map(plan: Mapping[str, Any]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for question in plan.get("questions", []) or []:
        if not isinstance(question, Mapping):
            continue
        index = int(question.get("question_index", 0))
        for slot in question.get("slots", []) or []:
            if not isinstance(slot, Mapping):
                continue
            role = str(slot.get("argument_role", "")).strip()
            if role:
                result.setdefault(role, []).append(index)
    return result


def _infer_role(claim: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    explicit = str(claim.get("argument_role", "")).strip()
    if explicit:
        return explicit
    claim_type = str(claim.get("claim_type", "unspecified"))
    base = ROLE_FROM_TYPE.get(claim_type, "")
    if claim_type == "program_or_service":
        wanted = _question_role_map(plan)
        for role in (
            "current_priority", "institution_response", "real_operating_role",
            "organization_differentiator", "stakeholder_problem",
        ):
            if role in wanted:
                return role
    return base


def _default_freshness(claim: Mapping[str, Any]) -> str:
    explicit = str(claim.get("freshness_class", "")).strip()
    if explicit:
        return explicit
    if str(claim.get("published_at", "")).strip() or str(claim.get("basis_date", "")).strip():
        return "current"
    if str(claim.get("claim_type", "")) in {"organization_role", "eligibility", "selection_criteria"}:
        return "stable"
    return "unknown"


def enrich_claim_metadata(claims: list[dict[str, Any]], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    role_questions = _question_role_map(plan)
    enriched: list[dict[str, Any]] = []
    for raw in claims:
        item = dict(raw)
        role = _infer_role(item, plan)
        if role:
            item["argument_role"] = role
        item.setdefault("source_tier", 1 if item.get("source_type") else 2)
        item.setdefault(
            "support_strength",
            "direct" if str(item.get("evidence_excerpt", "")).strip() else "unknown",
        )
        item["freshness_class"] = _default_freshness(item)
        if role and not str(item.get("application_use", "")).strip():
            questions = sorted(set(role_questions.get(role, [])))
            if questions:
                item["application_use"] = " · ".join(f"문항 {index}" for index in questions)
        enriched.append(item)
    return enriched


def _render_pack(
    plan: Mapping[str, Any],
    registry: Mapping[str, Any],
    claims: list[Mapping[str, Any]],
    conflicts: Mapping[str, Any],
    coverage: Mapping[str, Any],
) -> str:
    lines = [
        "# 기업·직무 조사팩",
        "",
        f"- 대상: {plan.get('target', '')}",
        f"- 조사 상태: {coverage.get('status', 'needs_research')}",
        f"- 필수 슬롯: {coverage.get('covered_required_slots', 0)}/{coverage.get('required_slots', 0)}",
        f"- 미해결 충돌: {len(conflicts.get('unresolved_groups', []))}",
        "",
        "## 공식 도메인",
        "",
    ]
    domains = registry.get("official_domains", []) or []
    if domains:
        lines.extend(f"- https://{domain}" for domain in domains)
    else:
        lines.append("- 아직 등록된 공식 도메인 없음")
    lines.extend(["", "## 문항별 조사 커버리지", ""])
    for question in coverage.get("questions", []) or []:
        lines.append(f"### 문항 {question.get('question_index')} · {question.get('intent')}")
        for slot in question.get("slots", []) or []:
            mark = "PASS" if slot.get("status") == "pass" else str(slot.get("status", "missing")).upper()
            refs = ", ".join(slot.get("accepted_claim_ids", []) or []) or "-"
            lines.append(f"- [{mark}] {slot.get('argument_role')}: {refs}")
        lines.append("")
    lines.extend(["## 검증된 회사 근거", ""])
    if not claims:
        lines.append("- 아직 등록된 근거 없음")
    for claim in claims:
        lines.extend(
            [
                f"### {claim.get('claim_id', '(no id)')}",
                f"- 주장: {claim.get('claim', '')}",
                f"- 역할: {claim.get('argument_role', '')}",
                f"- 분류: {claim.get('claim_type', '')}",
                f"- 출처등급: Tier {claim.get('source_tier', '')}",
                f"- 시점: {claim.get('freshness_class', '')} / basis={claim.get('basis_date', '')} / published={claim.get('published_at', '')}",
                f"- 근거: {claim.get('evidence_excerpt', '')}",
                f"- 출처: {claim.get('source_url', '')}",
                "",
            ]
        )
    if coverage.get("next_queries"):
        lines.extend(["## 다음 조사 질의", ""])
        lines.extend(f"- {query}" for query in coverage.get("next_queries", []))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def initialize_research_workspace(run_dir: Path, *, force_plan: bool = False) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = _read_json(run_dir / "run.json", {})
    if not isinstance(state, Mapping):
        raise ValueError("run.json must be an object")
    questions = state.get("questions", []) or []
    posting = _read_json(run_dir / "00_채용공고분석.json", {})
    plan_path = run_dir / PLAN_FILE
    if force_plan or not plan_path.is_file():
        plan = compile_research_plan(
            questions,
            target=str(state.get("target", "")),
            posting=posting if isinstance(posting, Mapping) else {},
        )
        _write_json(plan_path, plan)
    else:
        plan = _read_json(plan_path, {})

    registry_path = run_dir / SOURCE_FILE
    existing_registry = _read_json(registry_path, {})
    discovered = existing_registry.get("sources", []) if isinstance(existing_registry, Mapping) else []
    registry = build_source_registry(
        str(state.get("target", "")),
        explicit_domains=state.get("official_research_domains", []) or [],
        discovered_sources=discovered if isinstance(discovered, list) else [],
    )
    _write_json(registry_path, registry)

    updated_state = dict(state)
    updated_state["official_research_domains"] = list(registry.get("official_domains", []))
    updated_state["research_intelligence_enabled"] = True
    updated_state["research_plan_id"] = plan.get("plan_id")
    _write_json(run_dir / "run.json", updated_state)

    claim_path = run_dir / CLAIM_FILE
    if not claim_path.is_file():
        _write_json(claim_path, [])
    raw_claims = _read_json(claim_path, [])
    if not isinstance(raw_claims, list):
        raise ValueError(f"{CLAIM_FILE} must be an array")
    claims = enrich_claim_metadata(
        [dict(item) for item in raw_claims if isinstance(item, Mapping)], plan
    )
    _write_json(claim_path, claims)

    conflicts = resolve_research_conflicts(claims)
    coverage = build_research_coverage(plan, claims, conflicts)
    _write_json(run_dir / CONFLICT_FILE, conflicts)
    _write_json(run_dir / COVERAGE_FILE, coverage)
    (run_dir / PACK_FILE).write_text(
        _render_pack(plan, registry, claims, conflicts, coverage), encoding="utf-8"
    )
    return {
        "plan": plan,
        "registry": registry,
        "claims": claims,
        "conflicts": conflicts,
        "coverage": coverage,
    }


def assert_research_ready(run_dir: Path) -> dict[str, Any]:
    report = initialize_research_workspace(run_dir)
    coverage = report["coverage"]
    if not coverage.get("stop_research", False):
        missing: list[str] = []
        for question in coverage.get("questions", []) or []:
            for slot in question.get("slots", []) or []:
                if slot.get("required") and slot.get("status") != "pass":
                    missing.append(
                        f"문항 {question.get('question_index')}:{slot.get('argument_role')}({slot.get('status')})"
                    )
        detail = ", ".join(missing) or "required research coverage is incomplete"
        raise ValueError("company research is not ready: " + detail)
    if report["conflicts"].get("unresolved_groups"):
        raise ValueError(
            "company research has unresolved conflicts: "
            + ", ".join(report["conflicts"]["unresolved_groups"])
        )
    return report


def register_research_source(
    run_dir: Path,
    *,
    url: str,
    source_type: str,
    publisher: str = "",
    official: bool = False,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    initialize_research_workspace(run_dir)
    registry = _read_json(run_dir / SOURCE_FILE, {})
    sources = list(registry.get("sources", []) or []) if isinstance(registry, Mapping) else []
    if not any(
        isinstance(item, Mapping) and str(item.get("url", "")) == url for item in sources
    ):
        sources.append(
            {
                "url": url,
                "publisher": publisher,
                "source_type": source_type,
                "source_tier": tier_for_source_type(source_type),
                "official": official,
            }
        )
    state = _read_json(run_dir / "run.json", {})
    rebuilt = build_source_registry(
        str(state.get("target", "")),
        explicit_domains=state.get("official_research_domains", []) or [],
        discovered_sources=sources,
    )
    _write_json(run_dir / SOURCE_FILE, rebuilt)
    return initialize_research_workspace(run_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile and refresh evidence-first company research artifacts"
    )
    parser.add_argument("command", choices=("init", "refresh", "status", "source-add"))
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--force-plan", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--source-type", default="unknown")
    parser.add_argument("--publisher", default="")
    parser.add_argument("--official", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "source-add":
        if not args.url:
            raise SystemExit("--url is required for source-add")
        report = register_research_source(
            args.run,
            url=args.url,
            source_type=args.source_type,
            publisher=args.publisher,
            official=args.official,
        )
    else:
        report = initialize_research_workspace(args.run, force_plan=args.force_plan)
    coverage = report["coverage"]
    if args.command == "status":
        print(
            json.dumps(
                {
                    "status": coverage.get("status"),
                    "coverage_ratio": coverage.get("coverage_ratio"),
                    "next_queries": coverage.get("next_queries"),
                    "unresolved_conflicts": report["conflicts"].get("unresolved_groups", []),
                    "refreshed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(args.run.resolve() / PLAN_FILE)
        print(args.run.resolve() / COVERAGE_FILE)
        print(args.run.resolve() / PACK_FILE)
    return 0 if coverage.get("stop_research") and not report["conflicts"].get("unresolved_groups") else 3


if __name__ == "__main__":
    raise SystemExit(main())
