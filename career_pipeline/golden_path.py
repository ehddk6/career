"""Authority-preserving, content-addressed golden path for Career Pipeline."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

MANIFEST = "13_골든패스.json"
SCHEMA_VERSION = 1


class GoldenPathError(ValueError):
    pass


@dataclass(frozen=True)
class GoldenPathConfig:
    writer_model_id: str | None = None
    judge_model_ids: tuple[str, ...] = ()
    route_count: int = 3
    prose_realisations: int = 2
    writer_timeout_ms: int = 300_000
    surface_preference_profile: str | None = None
    semantic_preference_profile: str | None = None
    postprocess: str = "auto"
    postprocess_tier: str | None = None
    postprocess_timeout_ms: int | None = None
    max_model_calls: int | None = None
    max_postprocess_calls: int = 1
    max_stage_seconds: float | None = None
    selection_mode: str = "single"
    incumbent: str | None = None
    rigorous_timeout_ms: int = 300_000
    reuse_cache: bool = True


@dataclass(frozen=True)
class GoldenPathServices:
    research_gate: Callable[[Path], Mapping[str, Any]]
    strategy_fingerprint: Callable[[Path], str]
    write_draft: Callable[[Path, GoldenPathConfig], Mapping[str, Any]]
    interview_gate: Callable[[Path, Path], Sequence[Mapping[str, Any]]]
    finalize: Callable[[Path, GoldenPathConfig], Mapping[str, Any]]
    resolve_final_draft: Callable[[Path], Path]
    compile_interview: Callable[[Path], Mapping[str, Any]]
    audit: Callable[[Path], Mapping[str, Any]]


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise GoldenPathError(f"cannot read JSON: {path}: {e}") from e


def _write_json(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _snapshot(run: Path, names: Sequence[str]) -> dict[str, str | None]:
    return {name: _file_sha(run / name) for name in names}


def _run_authority_view(run: Path) -> dict[str, Any]:
    state = _read_json(run / "run.json", {})
    if not isinstance(state, Mapping):
        raise GoldenPathError("run.json must be an object")
    keys = (
        "quality_mode", "strict_quality", "root", "target", "posting", "profile",
        "posting_snapshot_id", "official_research_domains", "research_policy",
        "questions", "selected_experience_ids",
    )
    return {key: state.get(key) for key in keys}


def _authority_snapshot(run: Path) -> dict[str, str | None]:
    value = _snapshot(run, (
        "00_채용공고분석.json", "02_확정경험원장.json", "03_경험직무매칭.json",
        "04_리서치계획.json", "04_리서치출처.json", "04_공식근거.json",
        "04_근거충돌.json", "04_근거커버리지.json", "04_리서치실행.json",
    ))
    value["run_authority_contract"] = _json_hash(_run_authority_view(run))
    return value


def _manifest(run: Path) -> dict[str, Any]:
    value = _read_json(run / MANIFEST, {})
    if not isinstance(value, dict):
        raise GoldenPathError(f"{MANIFEST} must be an object")
    value.setdefault("schema_version", SCHEMA_VERSION)
    value.setdefault("run_dir", str(run))
    value.setdefault("stages", {})
    return value


def _save(run: Path, value: Mapping[str, Any]) -> None:
    _write_json(run / MANIFEST, dict(value))


def _status(run: Path, m: dict[str, Any], status: str, next_action: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    m["status"] = status
    m["next_action"] = next_action
    if details is None:
        m.pop("status_details", None)
    else:
        m["status_details"] = dict(details)
    _save(run, m)
    return m


def _record(run: Path, m: dict[str, Any], name: str, fp: str, *, status: str = "passed", outputs: Mapping[str, str | None] | None = None, details: Mapping[str, Any] | None = None) -> None:
    row: dict[str, Any] = {"status": status, "input_fingerprint": fp, "outputs": dict(outputs or {})}
    if details:
        row["details"] = dict(details)
    m.setdefault("stages", {})[name] = row
    _save(run, m)


def _cache_ok(run: Path, m: Mapping[str, Any], stage: str, fp: str) -> bool:
    row = m.get("stages", {}).get(stage, {}) if isinstance(m.get("stages"), Mapping) else {}
    if not isinstance(row, Mapping) or row.get("status") != "passed" or row.get("input_fingerprint") != fp:
        return False
    outputs = row.get("outputs", {})
    if not isinstance(outputs, Mapping):
        return False
    return all(expected is None or _file_sha(run / str(name)) == expected for name, expected in outputs.items())


def _config_hash(config: GoldenPathConfig, fields: Sequence[str]) -> str:
    raw = asdict(config)
    return _json_hash({key: raw.get(key) for key in fields})


def _default_research_gate(run: Path) -> Mapping[str, Any]:
    from .research_evidence import load_research_claims, load_research_execution, validate_research_execution
    from .research_workspace import initialize_research_workspace

    report = initialize_research_workspace(run)
    coverage = report.get("coverage", {}) if isinstance(report, Mapping) else {}
    conflicts = report.get("conflicts", {}) if isinstance(report, Mapping) else {}
    reasons: list[str] = []
    if not isinstance(coverage, Mapping) or not coverage.get("stop_research", False):
        reasons.append("required_research_coverage_incomplete")
    unresolved = conflicts.get("unresolved_groups", []) if isinstance(conflicts, Mapping) else []
    if unresolved:
        reasons.append("unresolved_research_conflicts")
    try:
        claims = load_research_claims(run / "04_공식근거.json")
        execution = load_research_execution(run / "04_리서치실행.json")
        execution_issues = [asdict(x) for x in validate_research_execution(execution, claims)]
    except Exception as e:
        execution_issues = [{"code": "invalid_research_execution", "question_index": 0, "message": str(e)}]
    if execution_issues:
        reasons.append("research_execution_not_verified")
    return {
        "ready": not reasons,
        "reasons": reasons,
        "coverage": dict(coverage) if isinstance(coverage, Mapping) else {},
        "conflicts": dict(conflicts) if isinstance(conflicts, Mapping) else {},
        "execution_issues": execution_issues,
        "next_queries": list(coverage.get("next_queries", [])) if isinstance(coverage, Mapping) else [],
    }


def _default_strategy_fingerprint(run: Path) -> str:
    from .strategy_prior import build_strategy_prior
    return _json_hash(build_strategy_prior(run))


def _default_write(run: Path, config: GoldenPathConfig) -> Mapping[str, Any]:
    from .integrated_writer import write_integrated_draft
    _, report = write_integrated_draft(
        run,
        force=True,
        writer_model_id=config.writer_model_id,
        judge_model_ids=config.judge_model_ids,
        route_count=config.route_count,
        prose_realisations=config.prose_realisations,
        timeout_ms=config.writer_timeout_ms,
        surface_preference_profile_path=Path(config.surface_preference_profile).resolve() if config.surface_preference_profile else None,
        semantic_preference_profile_path=Path(config.semantic_preference_profile).resolve() if config.semantic_preference_profile else None,
    )
    return report


def _research_metrics(responses: Sequence[Any], claims: Sequence[Any]) -> set[str]:
    from .facts import METRIC, _normalize
    by_id = {c.claim_id: c for c in claims if getattr(c, "claim_id", "")}
    result: set[str] = set()
    for response in responses:
        for claim_id in getattr(response, "research_refs", ()):
            claim = by_id.get(claim_id)
            if claim is None or getattr(claim, "verification_status", "") not in {"confirmed", "verified"}:
                continue
            for match in METRIC.finditer(getattr(claim, "claim", "")):
                normalized, _ = _normalize(match.group("number"), match.group("unit"))
                result.add(normalized)
    return result


def _default_interview_gate(run: Path, draft_path: Path) -> Sequence[Mapping[str, Any]]:
    from .facts import METRIC, _normalize
    from .models import Question, ValidationIssue
    from .orchestrator import _load_draft_responses
    from .profile_schema import load_ledger
    from .quality import _find_interview_question_marker, validate_interview_pack
    from .research_evidence import load_research_claims
    from .validation import referenced_claim_values

    pack = run / "08_면접대비팩.md"
    if not pack.is_file():
        return [{"code": "missing_interview_pack", "question_index": 0, "message": "08_면접대비팩.md is required before finalize"}]
    state = _read_json(run / "run.json", {})
    questions = [Question(**row) for row in state.get("questions", [])]
    responses, parse_issues = _load_draft_responses(draft_path)
    if parse_issues:
        return [asdict(x) for x in parse_issues]
    ledger = load_ledger(run / "02_확정경험원장.json")
    claims = load_research_claims(run / "04_공식근거.json")
    text = pack.read_text(encoding="utf-8")
    global_allowed = referenced_claim_values(responses, ledger) | _research_metrics(responses, claims)
    issues = validate_interview_pack(text, questions, responses, allowed_metric_values=global_allowed, strict=True)

    visible = sorted(
        ((r.question_index, _find_interview_question_marker(text, r.question_index)) for r in responses),
        key=lambda item: item[1],
    )
    visible = [row for row in visible if row[1] >= 0]
    by_index = {r.question_index: r for r in responses}
    for offset, (index, start) in enumerate(visible):
        end = visible[offset + 1][1] if offset + 1 < len(visible) else len(text)
        local = referenced_claim_values([by_index[index]], ledger) | _research_metrics([by_index[index]], claims)
        for match in METRIC.finditer(text[start:end]):
            normalized, _ = _normalize(match.group("number"), match.group("unit"))
            if normalized not in local:
                issues.append(ValidationIssue(
                    "unapproved_interview_metric_scope", index,
                    f"문항 {index} 면접 블록에서 이 문항 근거가 승인하지 않은 수치를 사용했습니다: {match.group(0)}",
                ))
    return [asdict(x) for x in issues]


def _default_finalize(run: Path, config: GoldenPathConfig) -> Mapping[str, Any]:
    from .orchestrator import finalize_run
    return finalize_run(
        run,
        copyedit=False,
        humanize=False,
        postprocess=config.postprocess,
        postprocess_tier=config.postprocess_tier,
        postprocess_timeout_ms=config.postprocess_timeout_ms,
        max_model_calls=config.max_model_calls,
        max_postprocess_calls=config.max_postprocess_calls,
        max_stage_seconds=config.max_stage_seconds,
        selection_mode=config.selection_mode,
        incumbent_path=Path(config.incumbent).resolve() if config.incumbent else None,
        rigorous_timeout_ms=config.rigorous_timeout_ms,
    )


def _default_resolve(run: Path) -> Path:
    from .interview_intelligence.schema import _resolve_draft_path
    return _resolve_draft_path(run)


def _default_compile_interview(run: Path) -> Mapping[str, Any]:
    from .interview_intelligence.core import write_interview_plan
    _, _, plan = write_interview_plan(run)
    return plan


def _default_audit(run: Path) -> Mapping[str, Any]:
    from .audit import run_quality_audit
    return run_quality_audit(run)


def default_services() -> GoldenPathServices:
    return GoldenPathServices(
        _default_research_gate, _default_strategy_fingerprint, _default_write,
        _default_interview_gate, _default_finalize, _default_resolve,
        _default_compile_interview, _default_audit,
    )


def _weakness_sha(run: Path) -> str | None:
    state = _read_json(run / "run.json", {})
    root = state.get("root") if isinstance(state, Mapping) else None
    return _file_sha(Path(root).resolve() / ".career_profile" / "interview_weakness_profile.json") if isinstance(root, str) and root else None


def advance_golden_path(run_dir: Path, *, config: GoldenPathConfig | None = None, services: GoldenPathServices | None = None) -> dict[str, Any]:
    run = run_dir.resolve()
    config = config or GoldenPathConfig()
    svc = services or default_services()
    state = _read_json(run / "run.json", {})
    if not isinstance(state, Mapping) or state.get("quality_mode") != "v2" or not state.get("strict_quality", False):
        raise GoldenPathError("golden path requires a V2 strict-quality run")
    m = _manifest(run)
    m["contract"] = {
        "architecture": "authority_preserving_content_addressed_golden_path_v1",
        "factual_authority": "never_expands_downstream",
        "research_execution_must_be_verified": True,
        "legacy_interview_validation": "strict_true_question_scoped_metrics",
        "final_draft_drives_interview_intelligence": True,
        "stale_downstream_reuse": "blocked_by_sha_fingerprint",
    }

    research = dict(svc.research_gate(run))
    rfp = _json_hash(_authority_snapshot(run))
    _record(run, m, "research", rfp, status="passed" if research.get("ready") else "waiting",
            outputs=_snapshot(run, ("04_리서치계획.json", "04_리서치출처.json", "04_공식근거.json", "04_근거충돌.json", "04_근거커버리지.json", "04_리서치실행.json")),
            details=research)
    if not research.get("ready"):
        return _status(run, m, "waiting_for_research", "complete official research, resolve conflicts, verify 04_리서치실행.json, then resume",
                       {"reasons": research.get("reasons", []), "next_queries": research.get("next_queries", [])})

    writer_fp = _json_hash({
        "authority": _authority_snapshot(run),
        "strategy": svc.strategy_fingerprint(run),
        "config": _config_hash(config, ("writer_model_id", "judge_model_ids", "route_count", "prose_realisations", "writer_timeout_ms", "surface_preference_profile", "semantic_preference_profile")),
    })
    if not (config.reuse_cache and _cache_ok(run, m, "writing", writer_fp)):
        report = dict(svc.write_draft(run, config))
        bad = [
            name for name in ("deterministic_validation", "semantic_validation")
            if isinstance(report.get(name), Mapping) and report[name].get("status") not in {None, "passed"}
        ]
        if bad:
            _record(run, m, "writing", writer_fp, status="blocked", details=report)
            return _status(run, m, "blocked_writing", "resolve integrated-writer validation failures", report)
        _record(run, m, "writing", writer_fp, outputs=_snapshot(run, ("draft.json", "05_통합전략선행정보.json", "05_통합논증검색_검증.json")))

    draft = run / "draft.json"
    if not draft.is_file():
        return _status(run, m, "blocked_writing", "generate draft.json through Integrated Writer")
    pack = run / "08_면접대비팩.md"
    if not pack.is_file():
        return _status(run, m, "waiting_for_interview_pack", "author 08_면접대비팩.md from current draft and authoritative refs, then resume", {"draft_sha256": _file_sha(draft)})

    pack_sha = _file_sha(pack)
    pre_issues = list(svc.interview_gate(run, draft))
    _record(run, m, "legacy_interview_prefinal", _json_hash((_file_sha(draft), pack_sha)), status="passed" if not pre_issues else "blocked",
            outputs={"08_면접대비팩.md": pack_sha}, details={"issues": pre_issues, "strict": True})
    if pre_issues:
        return _status(run, m, "waiting_for_interview_pack_fix", "fix legacy interview pack against strict contract, then resume", {"issues": pre_issues})

    finalize_fp = _json_hash({
        "draft": _file_sha(draft),
        "authority": _authority_snapshot(run),
        "config": _config_hash(config, ("postprocess", "postprocess_tier", "postprocess_timeout_ms", "max_model_calls", "max_postprocess_calls", "max_stage_seconds", "selection_mode", "incumbent", "rigorous_timeout_ms")),
    })
    if not (config.reuse_cache and _cache_ok(run, m, "finalize", finalize_fp)):
        final_state = dict(svc.finalize(run, config))
        if final_state.get("status") != "complete":
            _record(run, m, "finalize", finalize_fp, status="blocked", details=final_state)
            return _status(run, m, "blocked_finalize", "resolve finalize validation issues", final_state)
        final_path = svc.resolve_final_draft(run)
        _record(run, m, "finalize", finalize_fp,
                outputs={str(final_path.relative_to(run)): _file_sha(final_path), "12_최종산출물.json": _file_sha(run / "12_최종산출물.json")},
                details={"prefinal_draft_sha256": _file_sha(draft), "prefinal_pack_sha256": pack_sha, "selection_mode": config.selection_mode})

    final_path = svc.resolve_final_draft(run)
    final_sha = _file_sha(final_path)
    fin = m.get("stages", {}).get("finalize", {})
    details = fin.get("details", {}) if isinstance(fin, Mapping) else {}
    pre_draft_sha = details.get("prefinal_draft_sha256") if isinstance(details, Mapping) else None
    pre_pack_sha = details.get("prefinal_pack_sha256") if isinstance(details, Mapping) else None
    current_pack_sha = _file_sha(pack)
    if pre_draft_sha and final_sha != pre_draft_sha and current_pack_sha == pre_pack_sha:
        return _status(run, m, "waiting_for_interview_pack_refresh", "refresh 08_면접대비팩.md from final selected draft, then resume",
                       {"prefinal_draft_sha256": pre_draft_sha, "final_draft_sha256": final_sha, "pack_sha256": current_pack_sha})

    final_issues = list(svc.interview_gate(run, final_path))
    _record(run, m, "legacy_interview_final", _json_hash((final_sha, current_pack_sha)), status="passed" if not final_issues else "blocked",
            outputs={"08_면접대비팩.md": current_pack_sha}, details={"issues": final_issues, "strict": True, "draft": str(final_path)})
    if final_issues:
        return _status(run, m, "waiting_for_interview_pack_refresh", "realign legacy interview pack to final selected draft and authoritative refs, then resume", {"issues": final_issues})

    interview_fp = _json_hash({
        "final": final_sha,
        "authority": _snapshot(run, ("02_확정경험원장.json", "04_공식근거.json")),
        "run_contract": _run_authority_view(run),
        "weakness_profile": _weakness_sha(run),
    })
    if not (config.reuse_cache and _cache_ok(run, m, "interview_intelligence", interview_fp)):
        plan = dict(svc.compile_interview(run))
        _record(run, m, "interview_intelligence", interview_fp,
                outputs=_snapshot(run, ("08_면접지능설계.json", "08_면접질문은행.md")),
                details={"architecture": plan.get("architecture"), "source_final_draft_sha256": final_sha})

    audit_fp = _json_hash({
        "final": final_sha,
        "inputs": _snapshot(run, ("04_공식근거.json", "04_리서치실행.json", "04_기업직무조사.md", "08_면접대비팩.md", "08_면접지능설계.json", "12_최종산출물.json")),
    })
    if config.reuse_cache and _cache_ok(run, m, "audit", audit_fp):
        audit = _read_json(run / "11_최종품질감사.json", {})
    else:
        audit = dict(svc.audit(run))
        _record(run, m, "audit", audit_fp, status="passed" if audit.get("quality_gate") == "pass" else "blocked",
                outputs=_snapshot(run, ("11_최종품질감사.json", "11_최종품질감사.md")),
                details={"quality_gate": audit.get("quality_gate"), "internal_validation_score": audit.get("internal_validation_score", audit.get("score"))})
    score = int(audit.get("internal_validation_score", audit.get("score", 0)) or 0)
    if audit.get("quality_gate") != "pass" or score < 90:
        return _status(run, m, "review_required", "resolve audit issues; complete requires quality_gate=pass and score>=90",
                       {"quality_gate": audit.get("quality_gate"), "score": score, "issues": audit.get("issues", [])})

    m["final"] = {"draft_path": str(final_path), "draft_sha256": final_sha, "audit_score": score,
                  "quality_gate": audit.get("quality_gate"), "interview_plan_sha256": _file_sha(run / "08_면접지능설계.json")}
    return _status(run, m, "complete", "human review, then optional application package/review/authorization workflow")


def start_golden_path(*, root: Path, target: str, draft: Path, posting: str, profile: Path, run_name: str | None = None,
                      official_domains: Sequence[str] = (), research_domains: Sequence[str] = (), official_source: bool = False,
                      config: GoldenPathConfig | None = None) -> dict[str, Any]:
    from .orchestrator import prepare_run
    from .research_workspace import initialize_research_workspace
    state = prepare_run(root, target, draft, posting, run_name, profile=profile,
                        official_domains=tuple(official_domains), research_domains=tuple(research_domains), official_source=official_source)
    run = Path(str(state["run_dir"])).resolve()
    if str(state.get("status", "")).startswith("blocked_"):
        return _status(run, _manifest(run), "blocked_prepare", "resolve prepare/profile/posting/matching issues", state)
    initialize_research_workspace(run)
    return advance_golden_path(run, config=config)


def _add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--writer-model-id")
    p.add_argument("--judge-model-id", action="append", default=[])
    p.add_argument("--routes", type=int, default=3)
    p.add_argument("--prose-realisations", type=int, default=2)
    p.add_argument("--writer-timeout-ms", type=int, default=300_000)
    p.add_argument("--surface-preference-profile")
    p.add_argument("--semantic-preference-profile")
    p.add_argument("--postprocess", choices=("auto", "always", "never"), default="auto")
    p.add_argument("--postprocess-tier", choices=("luna", "terra", "sol"))
    p.add_argument("--postprocess-timeout-ms", type=int)
    p.add_argument("--max-model-calls", type=int)
    p.add_argument("--max-postprocess-calls", type=int, default=1)
    p.add_argument("--max-stage-seconds", type=float)
    p.add_argument("--selection-mode", choices=("single", "rigorous"), default="single")
    p.add_argument("--incumbent")
    p.add_argument("--rigorous-timeout-ms", type=int, default=300_000)
    p.add_argument("--no-cache", action="store_true")


def _cfg(a: argparse.Namespace) -> GoldenPathConfig:
    return GoldenPathConfig(
        writer_model_id=a.writer_model_id, judge_model_ids=tuple(a.judge_model_id), route_count=a.routes,
        prose_realisations=a.prose_realisations, writer_timeout_ms=a.writer_timeout_ms,
        surface_preference_profile=a.surface_preference_profile, semantic_preference_profile=a.semantic_preference_profile,
        postprocess=a.postprocess, postprocess_tier=a.postprocess_tier, postprocess_timeout_ms=a.postprocess_timeout_ms,
        max_model_calls=a.max_model_calls, max_postprocess_calls=a.max_postprocess_calls, max_stage_seconds=a.max_stage_seconds,
        selection_mode=a.selection_mode, incumbent=a.incumbent, rigorous_timeout_ms=a.rigorous_timeout_ms,
        reuse_cache=not a.no_cache,
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Career Pipeline content-addressed golden path")
    sub = p.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--root", required=True, type=Path)
    start.add_argument("--target", required=True)
    start.add_argument("--draft", required=True, type=Path)
    start.add_argument("--posting", required=True)
    start.add_argument("--profile", required=True, type=Path)
    start.add_argument("--run-name")
    start.add_argument("--official-domain", action="append", default=[])
    start.add_argument("--research-domain", action="append", default=[])
    start.add_argument("--official-source", action="store_true")
    _add_args(start)
    resume = sub.add_parser("resume")
    resume.add_argument("--run", required=True, type=Path)
    _add_args(resume)
    status = sub.add_parser("status")
    status.add_argument("--run", required=True, type=Path)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    if a.command == "status":
        value = _manifest(a.run.resolve())
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value.get("status") == "complete" else 2
    config = _cfg(a)
    result = (
        start_golden_path(root=a.root.resolve(), target=a.target, draft=a.draft.resolve(), posting=a.posting,
                          profile=a.profile.resolve(), run_name=a.run_name, official_domains=a.official_domain,
                          research_domains=a.research_domain, official_source=a.official_source, config=config)
        if a.command == "start" else advance_golden_path(a.run.resolve(), config=config)
    )
    print(json.dumps({"status": result.get("status"), "next_action": result.get("next_action"), "run_dir": result.get("run_dir")}, ensure_ascii=False, indent=2))
    status = str(result.get("status", ""))
    return 0 if status == "complete" else 2 if status.startswith("waiting_") or status == "review_required" else 3


if __name__ == "__main__":
    raise SystemExit(main())
