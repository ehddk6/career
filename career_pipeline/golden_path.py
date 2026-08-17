"""Content-addressed golden-path orchestration for Career Pipeline.

This module does not create new factual authority. It coordinates the existing
V2 authority, research, writing, finalize, interview, and audit layers while
recording the exact upstream fingerprints used by every derived stage.

The ordinary workflow intentionally stops at human/agent boundaries instead of
silently skipping them:

prepare -> research gate -> integrated writer -> strict legacy interview gate
-> finalize -> final-draft/legacy-pack freshness gate -> interview intelligence
-> audit
"""
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
    """Raised when the golden-path contract itself is invalid."""


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


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash_json(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_snapshot(run_dir: Path, names: Sequence[str]) -> dict[str, str | None]:
    return {name: _file_sha(run_dir / name) for name in names}


def _fingerprint(*parts: Any) -> str:
    return _hash_json(parts)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GoldenPathError(f"cannot read JSON: {path}: {error}") from error


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    payload = _read_json(run_dir / MANIFEST, {})
    if not isinstance(payload, dict):
        raise GoldenPathError(f"{MANIFEST} must contain an object")
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("run_dir", str(run_dir))
    payload.setdefault("stages", {})
    return payload


def _save_manifest(run_dir: Path, manifest: Mapping[str, Any]) -> None:
    _write_json_atomic(run_dir / MANIFEST, dict(manifest))


def _set_status(
    run_dir: Path,
    manifest: dict[str, Any],
    status: str,
    *,
    next_action: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest["status"] = status
    manifest["next_action"] = next_action
    if details is not None:
        manifest["status_details"] = dict(details)
    else:
        manifest.pop("status_details", None)
    _save_manifest(run_dir, manifest)
    return manifest


def _record_stage(
    run_dir: Path,
    manifest: dict[str, Any],
    name: str,
    *,
    status: str,
    input_fingerprint: str,
    outputs: Mapping[str, str | None] | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    stage = {
        "status": status,
        "input_fingerprint": input_fingerprint,
        "outputs": dict(outputs or {}),
    }
    if details:
        stage["details"] = dict(details)
    manifest.setdefault("stages", {})[name] = stage
    _save_manifest(run_dir, manifest)


def _cache_valid(
    run_dir: Path,
    manifest: Mapping[str, Any],
    stage_name: str,
    input_fingerprint: str,
) -> bool:
    stage = manifest.get("stages", {}).get(stage_name, {}) if isinstance(manifest.get("stages"), Mapping) else {}
    if not isinstance(stage, Mapping):
        return False
    if stage.get("status") != "passed" or stage.get("input_fingerprint") != input_fingerprint:
        return False
    outputs = stage.get("outputs", {})
    if not isinstance(outputs, Mapping):
        return False
    for relative, expected in outputs.items():
        if expected is None:
            continue
        if _file_sha(run_dir / str(relative)) != expected:
            return False
    return True


def _config_fingerprint(config: GoldenPathConfig, fields: Sequence[str]) -> str:
    payload = asdict(config)
    return _hash_json({name: payload.get(name) for name in fields})


def _default_research_gate(run_dir: Path) -> Mapping[str, Any]:
    from .research_evidence import load_research_claims, load_research_execution, validate_research_execution
    from .research_workspace import initialize_research_workspace

    report = initialize_research_workspace(run_dir)
    coverage = report.get("coverage", {}) if isinstance(report, Mapping) else {}
    conflicts = report.get("conflicts", {}) if isinstance(report, Mapping) else {}
    reasons: list[str] = []
    if not isinstance(coverage, Mapping) or not coverage.get("stop_research", False):
        reasons.append("required_research_coverage_incomplete")
    unresolved = conflicts.get("unresolved_groups", []) if isinstance(conflicts, Mapping) else []
    if unresolved:
        reasons.append("unresolved_research_conflicts")

    execution_issues: list[dict[str, Any]] = []
    try:
        claims = load_research_claims(run_dir / "04_공식근거.json")
        execution = load_research_execution(run_dir / "04_리서치실행.json")
        execution_issues = [asdict(item) for item in validate_research_execution(execution, claims)]
    except Exception as error:
        execution_issues = [{"code": "invalid_research_execution", "question_index": 0, "message": str(error)}]
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


def _default_strategy_fingerprint(run_dir: Path) -> str:
    from .strategy_prior import build_strategy_prior

    return _hash_json(build_strategy_prior(run_dir))


def _default_write_draft(run_dir: Path, config: GoldenPathConfig) -> Mapping[str, Any]:
    from .integrated_writer import write_integrated_draft

    _, report = write_integrated_draft(
        run_dir,
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


def _referenced_research_metrics(responses: Sequence[Any], claims: Sequence[Any]) -> set[str]:
    from .facts import METRIC, _normalize

    by_id = {claim.claim_id: claim for claim in claims if getattr(claim, "claim_id", "")}
    allowed: set[str] = set()
    for response in responses:
        for claim_id in getattr(response, "research_refs", ()):
            claim = by_id.get(claim_id)
            if claim is None or getattr(claim, "verification_status", "") not in {"confirmed", "verified"}:
                continue
            for match in METRIC.finditer(getattr(claim, "claim", "")):
                normalized, _ = _normalize(match.group("number"), match.group("unit"))
                allowed.add(normalized)
    return allowed


def _default_interview_gate(run_dir: Path, draft_path: Path) -> Sequence[Mapping[str, Any]]:
    from .orchestrator import _load_draft_responses
    from .models import Question
    from .profile_schema import load_ledger
    from .quality import validate_interview_pack
    from .research_evidence import load_research_claims
    from .validation import referenced_claim_values

    pack_path = run_dir / "08_면접대비팩.md"
    if not pack_path.is_file():
        return [{
            "code": "missing_interview_pack",
            "question_index": 0,
            "message": "08_면접대비팩.md is required before finalize",
        }]
    state = _read_json(run_dir / "run.json", {})
    if not isinstance(state, Mapping):
        raise GoldenPathError("run.json must contain an object")
    questions = [Question(**item) for item in state.get("questions", [])]
    responses, parse_issues = _load_draft_responses(draft_path)
    if parse_issues:
        return [asdict(item) for item in parse_issues]
    ledger = load_ledger(run_dir / "02_확정경험원장.json")
    claims = load_research_claims(run_dir / "04_공식근거.json")
    allowed = referenced_claim_values(responses, ledger)
    allowed.update(_referenced_research_metrics(responses, claims))
    issues = validate_interview_pack(
        pack_path.read_text(encoding="utf-8"),
        questions,
        responses,
        allowed_metric_values=allowed,
        strict=True,
    )
    return [asdict(item) for item in issues]


def _default_finalize(run_dir: Path, config: GoldenPathConfig) -> Mapping[str, Any]:
    from .orchestrator import finalize_run

    return finalize_run(
        run_dir,
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


def _default_resolve_final_draft(run_dir: Path) -> Path:
    from .interview_intelligence.schema import _resolve_draft_path

    return _resolve_draft_path(run_dir)


def _default_compile_interview(run_dir: Path) -> Mapping[str, Any]:
    from .interview_intelligence.core import write_interview_plan

    _, _, plan = write_interview_plan(run_dir)
    return plan


def _default_audit(run_dir: Path) -> Mapping[str, Any]:
    from .audit import run_quality_audit

    return run_quality_audit(run_dir)


def default_services() -> GoldenPathServices:
    return GoldenPathServices(
        research_gate=_default_research_gate,
        strategy_fingerprint=_default_strategy_fingerprint,
        write_draft=_default_write_draft,
        interview_gate=_default_interview_gate,
        finalize=_default_finalize,
        resolve_final_draft=_default_resolve_final_draft,
        compile_interview=_default_compile_interview,
        audit=_default_audit,
    )


def _authority_snapshot(run_dir: Path) -> dict[str, str | None]:
    return _artifact_snapshot(
        run_dir,
        (
            "run.json",
            "00_채용공고분석.json",
            "02_확정경험원장.json",
            "03_경험직무매칭.json",
            "04_리서치계획.json",
            "04_리서치출처.json",
            "04_공식근거.json",
            "04_근거충돌.json",
            "04_근거커버리지.json",
            "04_리서치실행.json",
        ),
    )


def _weakness_profile_sha(run_dir: Path) -> str | None:
    state = _read_json(run_dir / "run.json", {})
    root = state.get("root") if isinstance(state, Mapping) else None
    if not isinstance(root, str) or not root:
        return None
    return _file_sha(Path(root).resolve() / ".career_profile" / "interview_weakness_profile.json")


def advance_golden_path(
    run_dir: Path,
    *,
    config: GoldenPathConfig | None = None,
    services: GoldenPathServices | None = None,
) -> dict[str, Any]:
    """Advance an existing run as far as deterministic gates allow.

    External research and the human-readable legacy interview pack remain
    explicit boundaries. Re-running this function resumes from the first stale
    or incomplete stage using content fingerprints rather than file existence.
    """
    run_dir = run_dir.resolve()
    config = config or GoldenPathConfig()
    services = services or default_services()
    state = _read_json(run_dir / "run.json", {})
    if not isinstance(state, Mapping):
        raise GoldenPathError("run.json must contain an object")
    if state.get("quality_mode") != "v2" or not state.get("strict_quality", False):
        raise GoldenPathError("golden path requires V2 strict-quality run with a confirmed profile")

    manifest = _load_manifest(run_dir)
    manifest["contract"] = {
        "architecture": "authority_preserving_content_addressed_golden_path_v1",
        "factual_authority": "never_expands_downstream",
        "research_execution_must_be_verified": True,
        "legacy_interview_validation": "strict_true",
        "final_draft_drives_interview_intelligence": True,
        "stale_downstream_reuse": "blocked_by_sha_fingerprint",
    }

    research = dict(services.research_gate(run_dir))
    research_input = _fingerprint(_authority_snapshot(run_dir))
    _record_stage(
        run_dir,
        manifest,
        "research",
        status="passed" if research.get("ready") else "waiting",
        input_fingerprint=research_input,
        outputs=_artifact_snapshot(
            run_dir,
            ("04_리서치계획.json", "04_리서치출처.json", "04_공식근거.json", "04_근거충돌.json", "04_근거커버리지.json", "04_리서치실행.json"),
        ),
        details=research,
    )
    if not research.get("ready"):
        return _set_status(
            run_dir,
            manifest,
            "waiting_for_research",
            next_action="complete official research claims, resolve conflicts, and mark 04_리서치실행.json verified; then resume",
            details={"reasons": research.get("reasons", []), "next_queries": research.get("next_queries", [])},
        )

    strategy_fp = services.strategy_fingerprint(run_dir)
    writer_fp = _fingerprint(
        _authority_snapshot(run_dir),
        strategy_fp,
        _config_fingerprint(
            config,
            ("writer_model_id", "judge_model_ids", "route_count", "prose_realisations", "writer_timeout_ms", "surface_preference_profile", "semantic_preference_profile"),
        ),
    )
    if not (config.reuse_cache and _cache_valid(run_dir, manifest, "writing", writer_fp)):
        report = dict(services.write_draft(run_dir, config))
        deterministic = report.get("deterministic_validation", {}) if isinstance(report, Mapping) else {}
        semantic = report.get("semantic_validation", {}) if isinstance(report, Mapping) else {}
        if isinstance(deterministic, Mapping) and deterministic.get("status") not in {None, "passed"}:
            _record_stage(run_dir, manifest, "writing", status="blocked", input_fingerprint=writer_fp, details=report)
            return _set_status(run_dir, manifest, "blocked_writing", next_action="resolve integrated writer deterministic validation failures", details=report)
        if isinstance(semantic, Mapping) and semantic.get("status") not in {None, "passed"}:
            _record_stage(run_dir, manifest, "writing", status="blocked", input_fingerprint=writer_fp, details=report)
            return _set_status(run_dir, manifest, "blocked_writing", next_action="resolve integrated writer semantic validation failures", details=report)
        _record_stage(
            run_dir,
            manifest,
            "writing",
            status="passed",
            input_fingerprint=writer_fp,
            outputs=_artifact_snapshot(run_dir, ("draft.json", "05_통합전략선행정보.json", "05_통합논증검색_검증.json")),
            details={"architecture": report.get("architecture") if isinstance(report, Mapping) else None},
        )

    draft_path = run_dir / "draft.json"
    if not draft_path.is_file():
        return _set_status(run_dir, manifest, "blocked_writing", next_action="generate draft.json through integrated writer")

    pack_path = run_dir / "08_면접대비팩.md"
    if not pack_path.is_file():
        return _set_status(
            run_dir,
            manifest,
            "waiting_for_interview_pack",
            next_action="author 08_면접대비팩.md from the current draft and authoritative refs; then resume",
            details={"draft_sha256": _file_sha(draft_path)},
        )
    prefinal_pack_sha = _file_sha(pack_path)
    prefinal_issues = list(services.interview_gate(run_dir, draft_path))
    pack_gate_fp = _fingerprint(_file_sha(draft_path), prefinal_pack_sha)
    _record_stage(
        run_dir,
        manifest,
        "legacy_interview_prefinal",
        status="passed" if not prefinal_issues else "blocked",
        input_fingerprint=pack_gate_fp,
        outputs={"08_면접대비팩.md": prefinal_pack_sha},
        details={"issues": prefinal_issues, "strict": True},
    )
    if prefinal_issues:
        return _set_status(
            run_dir,
            manifest,
            "waiting_for_interview_pack_fix",
            next_action="fix the legacy interview pack against strict finalization contract; then resume",
            details={"issues": prefinal_issues},
        )

    finalize_fp = _fingerprint(
        _file_sha(draft_path),
        _authority_snapshot(run_dir),
        _config_fingerprint(
            config,
            ("postprocess", "postprocess_tier", "postprocess_timeout_ms", "max_model_calls", "max_postprocess_calls", "max_stage_seconds", "selection_mode", "incumbent", "rigorous_timeout_ms"),
        ),
    )
    finalized_from_cache = config.reuse_cache and _cache_valid(run_dir, manifest, "finalize", finalize_fp)
    if not finalized_from_cache:
        final_state = dict(services.finalize(run_dir, config))
        if final_state.get("status") != "complete":
            _record_stage(run_dir, manifest, "finalize", status="blocked", input_fingerprint=finalize_fp, details=final_state)
            return _set_status(run_dir, manifest, "blocked_finalize", next_action="resolve finalize validation issues", details=final_state)
        final_draft_path = services.resolve_final_draft(run_dir)
        _record_stage(
            run_dir,
            manifest,
            "finalize",
            status="passed",
            input_fingerprint=finalize_fp,
            outputs={
                str(final_draft_path.relative_to(run_dir)): _file_sha(final_draft_path),
                "12_최종산출물.json": _file_sha(run_dir / "12_최종산출물.json"),
            },
            details={
                "prefinal_draft_sha256": _file_sha(draft_path),
                "prefinal_pack_sha256": prefinal_pack_sha,
                "selection_mode": config.selection_mode,
            },
        )
    final_draft_path = services.resolve_final_draft(run_dir)
    final_draft_sha = _file_sha(final_draft_path)
    finalize_stage = manifest.get("stages", {}).get("finalize", {})
    finalize_details = finalize_stage.get("details", {}) if isinstance(finalize_stage, Mapping) else {}
    original_pack_sha = finalize_details.get("prefinal_pack_sha256") if isinstance(finalize_details, Mapping) else None
    prefinal_draft_sha = finalize_details.get("prefinal_draft_sha256") if isinstance(finalize_details, Mapping) else None
    current_pack_sha = _file_sha(pack_path)

    if prefinal_draft_sha and final_draft_sha != prefinal_draft_sha and current_pack_sha == original_pack_sha:
        return _set_status(
            run_dir,
            manifest,
            "waiting_for_interview_pack_refresh",
            next_action="refresh 08_면접대비팩.md from the final selected draft; then resume",
            details={
                "prefinal_draft_sha256": prefinal_draft_sha,
                "final_draft_sha256": final_draft_sha,
                "pack_sha256": current_pack_sha,
            },
        )

    final_pack_issues = list(services.interview_gate(run_dir, final_draft_path))
    final_pack_fp = _fingerprint(final_draft_sha, current_pack_sha)
    _record_stage(
        run_dir,
        manifest,
        "legacy_interview_final",
        status="passed" if not final_pack_issues else "blocked",
        input_fingerprint=final_pack_fp,
        outputs={"08_면접대비팩.md": current_pack_sha},
        details={"issues": final_pack_issues, "strict": True, "draft": str(final_draft_path)},
    )
    if final_pack_issues:
        return _set_status(
            run_dir,
            manifest,
            "waiting_for_interview_pack_refresh",
            next_action="realign the legacy interview pack to the final selected draft and authoritative refs; then resume",
            details={"issues": final_pack_issues},
        )

    interview_fp = _fingerprint(
        final_draft_sha,
        _artifact_snapshot(run_dir, ("02_확정경험원장.json", "04_공식근거.json", "run.json")),
        _weakness_profile_sha(run_dir),
    )
    if not (config.reuse_cache and _cache_valid(run_dir, manifest, "interview_intelligence", interview_fp)):
        plan = dict(services.compile_interview(run_dir))
        _record_stage(
            run_dir,
            manifest,
            "interview_intelligence",
            status="passed",
            input_fingerprint=interview_fp,
            outputs=_artifact_snapshot(run_dir, ("08_면접지능설계.json", "08_면접질문은행.md")),
            details={"architecture": plan.get("architecture"), "source_final_draft_sha256": final_draft_sha},
        )

    audit_fp = _fingerprint(
        final_draft_sha,
        _artifact_snapshot(
            run_dir,
            (
                "04_공식근거.json",
                "04_리서치실행.json",
                "04_기업직무조사.md",
                "08_면접대비팩.md",
                "08_면접지능설계.json",
                "12_최종산출물.json",
            ),
        ),
    )
    if config.reuse_cache and _cache_valid(run_dir, manifest, "audit", audit_fp):
        audit = _read_json(run_dir / "11_최종품질감사.json", {})
    else:
        audit = dict(services.audit(run_dir))
        _record_stage(
            run_dir,
            manifest,
            "audit",
            status="passed" if audit.get("quality_gate") == "pass" else "blocked",
            input_fingerprint=audit_fp,
            outputs=_artifact_snapshot(run_dir, ("11_최종품질감사.json", "11_최종품질감사.md")),
            details={
                "quality_gate": audit.get("quality_gate"),
                "internal_validation_score": audit.get("internal_validation_score", audit.get("score")),
            },
        )

    score = int(audit.get("internal_validation_score", audit.get("score", 0)) or 0)
    if audit.get("quality_gate") != "pass" or score < 90:
        return _set_status(
            run_dir,
            manifest,
            "review_required",
            next_action="resolve audit issues; golden path is not complete until quality_gate=pass and score>=90",
            details={"quality_gate": audit.get("quality_gate"), "score": score, "issues": audit.get("issues", [])},
        )

    manifest["final"] = {
        "draft_path": str(final_draft_path),
        "draft_sha256": final_draft_sha,
        "audit_score": score,
        "quality_gate": audit.get("quality_gate"),
        "interview_plan_sha256": _file_sha(run_dir / "08_면접지능설계.json"),
    }
    return _set_status(
        run_dir,
        manifest,
        "complete",
        next_action="human review and, if desired, application-package/review/authorization workflow",
    )


def start_golden_path(
    *,
    root: Path,
    target: str,
    draft: Path,
    posting: str,
    profile: Path,
    run_name: str | None = None,
    official_domains: Sequence[str] = (),
    research_domains: Sequence[str] = (),
    official_source: bool = False,
    config: GoldenPathConfig | None = None,
) -> dict[str, Any]:
    from .orchestrator import prepare_run
    from .research_workspace import initialize_research_workspace

    state = prepare_run(
        root,
        target,
        draft,
        posting,
        run_name,
        profile=profile,
        official_domains=tuple(official_domains),
        research_domains=tuple(research_domains),
        official_source=official_source,
    )
    run_dir = Path(str(state["run_dir"])).resolve()
    if str(state.get("status", "")).startswith("blocked_"):
        manifest = _load_manifest(run_dir)
        return _set_status(run_dir, manifest, "blocked_prepare", next_action="resolve prepare/profile/posting/matching issues", details=state)
    initialize_research_workspace(run_dir)
    return advance_golden_path(run_dir, config=config)


def _add_execution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--writer-model-id")
    parser.add_argument("--judge-model-id", action="append", default=[])
    parser.add_argument("--routes", type=int, default=3)
    parser.add_argument("--prose-realisations", type=int, default=2)
    parser.add_argument("--writer-timeout-ms", type=int, default=300_000)
    parser.add_argument("--surface-preference-profile")
    parser.add_argument("--semantic-preference-profile")
    parser.add_argument("--postprocess", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--postprocess-tier", choices=("luna", "terra", "sol"))
    parser.add_argument("--postprocess-timeout-ms", type=int)
    parser.add_argument("--max-model-calls", type=int)
    parser.add_argument("--max-postprocess-calls", type=int, default=1)
    parser.add_argument("--max-stage-seconds", type=float)
    parser.add_argument("--selection-mode", choices=("single", "rigorous"), default="single")
    parser.add_argument("--incumbent")
    parser.add_argument("--rigorous-timeout-ms", type=int, default=300_000)
    parser.add_argument("--no-cache", action="store_true")


def _config_from_args(args: argparse.Namespace) -> GoldenPathConfig:
    return GoldenPathConfig(
        writer_model_id=args.writer_model_id,
        judge_model_ids=tuple(args.judge_model_id),
        route_count=args.routes,
        prose_realisations=args.prose_realisations,
        writer_timeout_ms=args.writer_timeout_ms,
        surface_preference_profile=args.surface_preference_profile,
        semantic_preference_profile=args.semantic_preference_profile,
        postprocess=args.postprocess,
        postprocess_tier=args.postprocess_tier,
        postprocess_timeout_ms=args.postprocess_timeout_ms,
        max_model_calls=args.max_model_calls,
        max_postprocess_calls=args.max_postprocess_calls,
        max_stage_seconds=args.max_stage_seconds,
        selection_mode=args.selection_mode,
        incumbent=args.incumbent,
        rigorous_timeout_ms=args.rigorous_timeout_ms,
        reuse_cache=not args.no_cache,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the content-addressed Career Pipeline golden path")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--root", required=True, type=Path)
    start.add_argument("--target", required=True)
    start.add_argument("--draft", required=True, type=Path)
    start.add_argument("--posting", required=True)
    start.add_argument("--profile", required=True, type=Path)
    start.add_argument("--run-name")
    start.add_argument("--official-domain", action="append", default=[])
    start.add_argument("--research-domain", action="append", default=[])
    start.add_argument("--official-source", action="store_true")
    _add_execution_args(start)
    resume = commands.add_parser("resume")
    resume.add_argument("--run", required=True, type=Path)
    _add_execution_args(resume)
    status = commands.add_parser("status")
    status.add_argument("--run", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "status":
        value = _load_manifest(args.run.resolve())
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value.get("status") == "complete" else 2
    config = _config_from_args(args)
    if args.command == "start":
        result = start_golden_path(
            root=args.root.resolve(),
            target=args.target,
            draft=args.draft.resolve(),
            posting=args.posting,
            profile=args.profile.resolve(),
            run_name=args.run_name,
            official_domains=args.official_domain,
            research_domains=args.research_domain,
            official_source=args.official_source,
            config=config,
        )
    else:
        result = advance_golden_path(args.run.resolve(), config=config)
    print(json.dumps({
        "status": result.get("status"),
        "next_action": result.get("next_action"),
        "run_dir": result.get("run_dir"),
    }, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "complete" else 2 if str(result.get("status", "")).startswith("waiting_") or result.get("status") == "review_required" else 3


if __name__ == "__main__":
    raise SystemExit(main())
