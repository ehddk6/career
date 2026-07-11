from datetime import datetime
"""전체 파이프라인 조정. prepare와 finalize로 나뉘며, profile/posting/matching/research/finalize 흐름을 제어합니다."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import re

import yaml

from .conflicts import (
    apply_overrides,
    conflict_override_key,
    detect_conflicts,
)
from .extractors import extract_path
from .facts import METRIC, _normalize, extract_fact_claims
from .inventory import build_inventory
from .candidate_selection import generate_and_select_candidates
from .artifacts import write_final_artifact_manifest
from .character_count import count_characters
from .matching import match_questions, render_matches_markdown
from .posting_loader import (
    PostingSourceError,
    load_posting_source,
    write_posting_snapshot,
)
from .copyeditor_adapter import copyedit_responses
from .cost_limit import CostLimitExceeded, CostTracker
from .model_policy import ModelTier, choose_tier
from .posting_parser import parse_posting, reconcile_questions, render_posting_analysis
from .profile_refresh import refresh_profile
from .profile_schema import (
    ExperienceLedger,
    ProfileValidationError,
    ledger_to_dict,
    load_ledger,
)
from .quality import (
    STRICT_MIN_ANSWER_SCORE,
    STRICT_MIN_AVERAGE_SCORE,
    QualityIssue,
    score_answer_quality,
    validate_answer_quality,
    validate_interview_pack,
    validate_matching_gate,
    validate_posting_gate,
    validate_profile_gate,
)
from .questions import extract_questions
from .models import DraftResponse, ExperienceClaimRef, Question, ValidationIssue
from .patina_adapter import (
    HumanizationResult,
    PatinaScoreResult,
    humanize_text,
    score_text,
)
from .research_evidence import (
    REQUIRED_RESEARCH_POLICY,
    REQUIRED_RESEARCH_SKILL,
    load_research_execution,
    load_research_claims,
    official_domains_for_target,
    validate_research_execution,
    validate_research_evidence,
)
from .rendering import render_draft_docx, render_draft_markdown
from .state import resolve_run_dir, write_json, write_state
from .style_diagnostics import diagnose_responses
from .source_policy import is_evidence_path
from .validation import referenced_claim_values, validate_draft
from .writing_guidance import attach_writing_guidance


def _inventory_markdown(records) -> str:
    lines = ["# 자료 목록", "", "| 상태 | 파일 | 사유 |", "|---|---|---|"]
    lines.extend(
        f"| {item.status} | {item.relative_path} | {item.reason} |"
        for item in records
    )
    return "\n".join(lines) + "\n"


def _conflict_markdown(conflicts, claims) -> str:
    lines = ["# 충돌 검사", ""]
    if not conflicts:
        lines.append("- 충돌 없음")
    for number, conflict in enumerate(conflicts, 1):
        lines.extend(
            [
                f"## 충돌 {number}: {conflict.field}",
                f"값: {', '.join(conflict.values)}",
            ]
        )
        for index in conflict.claim_indexes:
            claim = claims[index]
            lines.append(f"- `{claim.source_path}`: {claim.context}")
        lines.append(
            f"- override key: `{conflict_override_key(conflict, claims)}`"
        )
        lines.append(
            "- 확인 질문: 실제 제출에 사용할 값과 근거 파일을 지정해 주세요."
        )
    return "\n".join(lines) + "\n"


def _load_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload.items()
    ):
        raise ValueError("fact_overrides.yaml must be a string-to-string mapping")
    return payload


def _load_draft_responses(path: Path) -> tuple[list[DraftResponse], list[ValidationIssue]]:
    """Load the externally authored draft contract without leaking parser errors."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return [], [
            ValidationIssue("invalid_draft_json", 0, f"draft.json을 읽을 수 없습니다: {error}")
        ]
    if not isinstance(payload, list):
        return [], [
            ValidationIssue("invalid_draft_shape", 0, "draft.json 최상위 값은 배열이어야 합니다.")
        ]

    responses: list[DraftResponse] = []
    issues: list[ValidationIssue] = []
    for position, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            issues.append(
                ValidationIssue("invalid_draft_entry", 0, f"{position}번 항목은 객체여야 합니다.")
            )
            continue
        question_index = item.get("question_index")
        answer = item.get("answer")
        evidence_paths = item.get("evidence_paths", [])
        experience_refs = item.get("experience_refs", [])
        research_refs = item.get("research_refs", [])
        if isinstance(question_index, bool) or not isinstance(question_index, int):
            issues.append(
                ValidationIssue("invalid_question_index", 0, f"{position}번 항목의 question_index는 정수여야 합니다.")
            )
            continue
        if not isinstance(answer, str):
            issues.append(
                ValidationIssue("invalid_answer", question_index, "answer는 문자열이어야 합니다.")
            )
            continue
        if not isinstance(evidence_paths, list) or not all(
            isinstance(value, str) for value in evidence_paths
        ):
            issues.append(
                ValidationIssue("invalid_evidence_paths", question_index, "evidence_paths는 문자열 배열이어야 합니다.")
            )
            continue
        if not isinstance(research_refs, list) or not all(
            isinstance(value, str) for value in research_refs
        ):
            issues.append(
                ValidationIssue("invalid_research_refs", question_index, "research_refs는 문자열 배열이어야 합니다.")
            )
            continue
        if not isinstance(experience_refs, list):
            issues.append(
                ValidationIssue("invalid_experience_refs", question_index, "experience_refs는 배열이어야 합니다.")
            )
            continue
        parsed_refs: list[ExperienceClaimRef] = []
        for reference in experience_refs:
            if not isinstance(reference, dict):
                issues.append(
                    ValidationIssue("invalid_experience_ref", question_index, "experience_refs 항목은 객체여야 합니다.")
                )
                break
            experience_id = reference.get("experience_id")
            claim_fields = reference.get("claim_fields", [])
            if not isinstance(experience_id, str) or not isinstance(claim_fields, list) or not all(
                isinstance(field, str) for field in claim_fields
            ):
                issues.append(
                    ValidationIssue("invalid_experience_ref", question_index, "experience_refs 항목 형식이 올바르지 않습니다.")
                )
                break
            parsed_refs.append(ExperienceClaimRef(experience_id, tuple(claim_fields)))
        else:
            responses.append(
                DraftResponse(
                    question_index,
                    answer,
                    tuple(evidence_paths),
                    tuple(parsed_refs),
                    tuple(research_refs),
                )
            )
    return responses, issues


def _write_research_execution_template(run_dir: Path) -> None:
    path = run_dir / "04_리서치실행.json"
    if path.exists():
        return
    write_json(
        path,
        {
            "policy": REQUIRED_RESEARCH_POLICY,
            "skill_name": REQUIRED_RESEARCH_SKILL,
            "mode": "ordinary-online",
            "searched_at": "",
            "status": "pending",
            "queries": [],
            "source_families": [],
            "verified_claim_ids": [],
        },
    )


def _resolve_voice_sample(
    explicit: Path | None,
    state: dict,
    run_dir: Path,
) -> Path | None:
    candidates = [
        explicit,
        Path(state["patina_voice_sample"]) if state.get("patina_voice_sample") else None,
        Path(state["root"]) / ".career_profile" / "voice_sample.txt"
        if state.get("root")
        else None,
        run_dir / "voice_sample.txt",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        path = candidate.resolve()
        if path.is_file():
            if path.stat().st_size > 20_000:
                raise ValueError("Patina voice sample must be 20KB or smaller")
            paragraphs = [
                item.strip()
                for item in re.split(r"\r?\n\s*\r?\n", path.read_text(encoding="utf-8"))
                if item.strip()
            ]
            if not 1 <= len(paragraphs) <= 3:
                raise ValueError("Patina voice sample must contain 1-3 paragraphs")
            return path
        if explicit is not None and path == explicit.resolve():
            raise FileNotFoundError(f"Patina voice sample not found: {path}")
    return None


def _confirmed_ledger(ledger: ExperienceLedger) -> ExperienceLedger:
    experiences = tuple(
        replace(
            experience,
            claims=tuple(
                claim for claim in experience.claims if claim.status == "confirmed"
            ),
        )
        for experience in ledger.experiences
        if experience.status == "confirmed"
    )
    return replace(ledger, experiences=experiences)


def _blocked_v2_state(
    run_dir: Path,
    root: Path,
    target: str,
    draft: Path,
    posting: str | None,
    status: str,
    stage: str,
    issues: list[QualityIssue],
    questions: list[Question] | tuple[Question, ...] = (),
) -> dict:
    state = {
        "status": status,
        "quality_mode": "v2",
        "strict_quality": True,
        "blocked_stage": stage,
        "issues": [asdict(issue) for issue in issues],
        "run_dir": str(run_dir),
        "root": str(root),
        "target": target,
        "draft": str(draft),
        "posting": posting,
        "questions": [asdict(question) for question in questions],
        "conflict_count": sum(
            issue.code == "conflicting_profile_claim" for issue in issues
        ),
    }
    attach_writing_guidance(root, run_dir, state)
    write_state(run_dir, state)
    return state


def _prepare_v2(
    *,
    root: Path,
    target: str,
    draft: Path,
    posting: str | None,
    run_dir: Path,
    profile: Path,
    official_domains: tuple[str, ...],
    research_domains: tuple[str, ...],
    official_source: bool,
    questions: list[Question],
) -> dict:
    try:
        ledger = load_ledger(profile)
    except (OSError, ProfileValidationError) as error:
        return _blocked_v2_state(
            run_dir,
            root,
            target,
            draft,
            posting,
            "blocked_profile",
            "profile",
            [QualityIssue("invalid_profile", str(error), str(profile))],
            questions,
        )

    review = refresh_profile(root, ledger)
    review_issues = [
        QualityIssue(
            "stale_profile_evidence" if item.status == "stale" else "missing_profile_evidence",
            f"{item.experience_id}: {item.reason}",
            item.source_path,
        )
        for item in review.items
        if item.status != "unchanged"
    ]
    selected_ids = {
        item.experience_id
        for item in ledger.experiences
        if item.status == "confirmed"
    }
    profile_issues = validate_profile_gate(
        ledger, selected_experience_ids=selected_ids
    )
    all_profile_issues = review_issues + profile_issues
    if all_profile_issues:
        status = (
            "blocked_conflict"
            if any(issue.code == "conflicting_profile_claim" for issue in all_profile_issues)
            else "blocked_profile"
        )
        return _blocked_v2_state(
            run_dir,
            root,
            target,
            draft,
            posting,
            status,
            "profile",
            all_profile_issues,
            questions,
        )

    confirmed = _confirmed_ledger(ledger)
    write_json(run_dir / "02_확정경험원장.json", ledger_to_dict(confirmed))

    if not posting:
        return _blocked_v2_state(
            run_dir,
            root,
            target,
            draft,
            posting,
            "blocked_posting",
            "posting",
            [QualityIssue("missing_posting", "채용공고 입력이 필요합니다.")],
            questions,
        )
    try:
        loaded = load_posting_source(
            posting,
            official_source=official_source,
            official_domains=official_domains,
        )
        write_posting_snapshot(run_dir, loaded)
        analysis = parse_posting(loaded, target=target)
    except (OSError, PostingSourceError) as error:
        return _blocked_v2_state(
            run_dir,
            root,
            target,
            draft,
            posting,
            "blocked_posting",
            "posting",
            [QualityIssue("invalid_posting_source", str(error))],
            questions,
        )

    write_json(run_dir / "00_채용공고분석.json", asdict(analysis))
    (run_dir / "00_채용공고분석.md").write_text(
        render_posting_analysis(analysis), encoding="utf-8"
    )
    posting_issues = validate_posting_gate(analysis)
    reconciliation = reconcile_questions(analysis.questions, tuple(questions))
    posting_issues.extend(
        QualityIssue(
            f"question_{item.reason}",
            f"문항 {item.index}: 공고={item.posting_value!r}, 초안={item.draft_value!r}",
            "00_채용공고분석.md",
        )
        for item in reconciliation.mismatches
    )
    if posting_issues:
        return _blocked_v2_state(
            run_dir,
            root,
            target,
            draft,
            posting,
            "blocked_posting",
            "posting",
            posting_issues,
            questions,
        )

    matches = match_questions(confirmed, analysis, reconciliation.questions)
    write_json(
        run_dir / "03_경험직무매칭.json",
        [asdict(item) for item in matches],
    )
    (run_dir / "03_경험직무매칭.md").write_text(
        render_matches_markdown(matches), encoding="utf-8"
    )
    matching_issues = validate_matching_gate(matches)
    if matching_issues:
        return _blocked_v2_state(
            run_dir,
            root,
            target,
            draft,
            posting,
            "blocked_profile",
            "matching",
            matching_issues,
            questions,
        )
    research_domains = official_domains_for_target(
        target, official_domains + research_domains
    )
    official_evidence_path = run_dir / "04_공식근거.json"
    if not official_evidence_path.exists():
        write_json(official_evidence_path, [])
    _write_research_execution_template(run_dir)
    state = {
        "status": "ready_for_research",
        "quality_mode": "v2",
        "strict_quality": True,
        "run_dir": str(run_dir),
        "root": str(root),
        "target": target,
        "draft": str(draft),
        "posting": posting,
        "profile": str(profile),
        "posting_snapshot_id": analysis.source.content_sha256,
        "official_research_domains": list(research_domains),
        "research_policy": REQUIRED_RESEARCH_POLICY,
        "required_research_skill": REQUIRED_RESEARCH_SKILL,
        "questions": [asdict(question) for question in reconciliation.questions],
        "selected_experience_ids": [
            item.recommended.experience_id
            for item in matches
            if item.recommended is not None
        ],
        "conflict_count": 0,
    }
    attach_writing_guidance(root, run_dir, state)
    write_state(run_dir, state)
    return state


def prepare_run(
    root: Path,
    target: str,
    draft: Path,
    posting: str | None,
    run_name: str | None,
    resume: Path | None = None,
    *,
    profile: Path | None = None,
    official_domains: tuple[str, ...] = (),
    research_domains: tuple[str, ...] = (),
    official_source: bool = False,
) -> dict:
    root = root.resolve()
    draft = draft.resolve()
    run_dir = resolve_run_dir(root, target, run_name, resume)
    inventory = build_inventory(root)
    draft_record = next(
        item for item in inventory if item.path.resolve() == draft
    )
    if draft_record.status == "failed":
        raise PermissionError(
            "대상 초안을 읽을 수 없습니다. 초안 파일을 닫고 다시 실행해 주세요. "
            f"원인: {draft_record.reason}"
        )
    documents = []
    for index, source in enumerate(inventory):
        if source.status != "use":
            continue
        try:
            documents.append(extract_path(source))
        except Exception as error:
            inventory[index] = replace(
                source, status="failed", reason=f"{type(error).__name__}: {error}"
            )

    questions = extract_questions(extract_path(draft_record).paragraphs)
    (run_dir / "01_자료목록.md").write_text(
        _inventory_markdown(inventory), encoding="utf-8"
    )
    if profile is not None:
        return _prepare_v2(
            root=root,
            target=target,
            draft=draft,
            posting=posting,
            run_dir=run_dir,
            profile=profile.resolve(),
            official_domains=official_domains,
            research_domains=research_domains,
            official_source=official_source,
            questions=questions,
        )

    fact_documents = [
        document
        for document in documents
        if is_evidence_path(document.source.relative_path)
    ]
    claims = extract_fact_claims(fact_documents)
    overrides = _load_overrides(run_dir / "fact_overrides.yaml")
    accepted = apply_overrides(claims, overrides)
    conflicts = detect_conflicts(accepted)

    fact_payload = []
    for claim in claims:
        item = asdict(claim)
        item["tokens"] = sorted(claim.tokens)
        fact_payload.append(item)
    write_json(run_dir / "02_사실원장.json", fact_payload)
    (run_dir / "03_충돌검사.md").write_text(
        _conflict_markdown(conflicts, accepted), encoding="utf-8"
    )

    state = {
        "status": "blocked_conflict" if conflicts else "ready_for_research",
        "quality_mode": "legacy",
        "run_dir": str(run_dir),
        "root": str(root),
        "target": target,
        "draft": str(draft),
        "posting": posting,
        "research_policy": REQUIRED_RESEARCH_POLICY,
        "required_research_skill": REQUIRED_RESEARCH_SKILL,
        "questions": [asdict(question) for question in questions],
        "conflict_count": len(conflicts),
    }
    _write_research_execution_template(run_dir)
    attach_writing_guidance(root, run_dir, state)
    write_state(run_dir, state)
    return state


def _write_review_report(
    run_dir: Path,
    questions: list[Question],
    responses: list[DraftResponse],
    *,
    v2: bool,
    issues: list[ValidationIssue],
) -> None:
    response_by_index = {item.question_index: item for item in responses}
    review_lines = ["# 자기소개서 검토보고서", ""]
    if v2:
        status = "통과" if not issues else "실패"
        review_lines.extend(
            [
                f"- 경험 원장: {status}",
                f"- 공고 공식성: {status}",
                f"- 경험·문항 매칭: {status}",
                f"- stale 근거: {'없음' if not issues else '검토 필요'}",
            ]
        )
    for question in questions:
        response = response_by_index.get(question.index)
        if response is None:
            continue
        review_lines.append(
            f"- 문항 {question.index}: {count_characters(response.answer, question.count_mode)}/"
            f"{question.character_limit or '미지정'}자 "
            f"({'공백 제외' if question.count_mode == 'spaces_excluded' else '공백 포함'}), "
            f"근거 {len(response.evidence_paths)}개"
        )
    if issues:
        review_lines.extend(["", "## 검증 이슈", ""])
        review_lines.extend(
            f"- `{issue.code}` 문항 {issue.question_index}: {issue.message}"
            for issue in issues
        )
    else:
        review_lines.extend(
            ["- 블라인드: 통과", "- 타기관명: 통과", "- 빈 답변: 없음"]
        )
    (run_dir / "07_자기소개서_검토보고서.md").write_text(
        "\n".join(review_lines) + "\n", encoding="utf-8"
    )


def finalize_run(
    run_dir: Path,
    *,
    copyedit: bool = False,
    copyeditor_timeout_ms: int = 180_000,
    humanize: bool = False,
    patina_backend: str = "codex-cli",
    patina_timeout_ms: int = 180_000,
    patina_max_retries: int = 1,
    patina_voice_sample: Path | None = None,
    patina_ai_threshold: int = 30,
    patina_score: bool = True,
    postprocess: str | None = None,
    postprocess_tier: ModelTier | None = None,
    postprocess_timeout_ms: int | None = None,
    postprocess_runner=None,
    max_model_calls: int | None = None,
    max_postprocess_calls: int = 1,
    max_stage_seconds: float | None = None,
) -> dict:
    run_dir = run_dir.resolve()
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    legacy_copyedit = postprocess is None and copyedit
    effective_postprocess = postprocess
    if effective_postprocess is None:
        effective_postprocess = "always" if copyedit else "never"
    if effective_postprocess not in {"auto", "always", "never"}:
        raise ValueError("postprocess must be auto, always, or never")
    state["postprocess_policy"] = effective_postprocess
    state["max_model_calls"] = max_model_calls
    state["max_postprocess_calls"] = max_postprocess_calls
    state["max_stage_seconds"] = max_stage_seconds
    if state.get("status") in {
        "blocked",
        "blocked_profile",
        "blocked_posting",
        "blocked_conflict",
    }:
        raise ValueError("준비 단계의 차단 이슈를 먼저 해결해야 합니다.")
    # Prevent a previous successful run from remaining falsely complete if a
    # rerun fails before its new final manifest is committed.
    state["status"] = "finalizing"
    state["final_artifact"] = None
    write_state(run_dir, state)

    v2 = state.get("quality_mode") == "v2"
    required = [
        "04_기업직무조사.md",
        "05_문항전략.md",
        "08_면접대비팩.md",
        "draft.json",
    ]
    required.extend(
        [
            "00_채용공고분석.json",
            "02_확정경험원장.json",
            "03_경험직무매칭.json",
        ]
        if v2
        else ["02_사실원장.json"]
    )
    if v2 and state.get("strict_quality", False):
        required.append("04_공식근거.json")
    if state.get("research_policy") == REQUIRED_RESEARCH_POLICY:
        required.append("04_리서치실행.json")
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"missing synthesis artifacts: {', '.join(missing)}"
        )

    questions = [Question(**item) for item in state["questions"]]
    responses, draft_issues = _load_draft_responses(run_dir / "draft.json")
    if draft_issues:
        _write_review_report(run_dir, questions, responses, v2=v2, issues=draft_issues)
        state.update(
            status="blocked_validation",
            validation_issues=[asdict(item) for item in draft_issues],
        )
        if v2:
            state["blocked_stage"] = "finalize"
            state["issues"] = [asdict(item) for item in draft_issues]
        write_state(run_dir, state)
        return state

    ledger = None
    research_claims = ()
    job_terms: tuple[str, ...] = ()
    if v2:
        ledger = load_ledger(run_dir / "02_확정경험원장.json")
        posting_payload = json.loads(
            (run_dir / "00_채용공고분석.json").read_text(encoding="utf-8")
        )
        job_terms = tuple(
            posting_payload.get("duties", []) + posting_payload.get("competencies", [])
        )
        known_sources = {
            evidence.source_path
            for experience in ledger.experiences
            for claim in experience.claims
            for evidence in claim.evidence
        }
    else:
        fact_data = json.loads(
            (run_dir / "02_사실원장.json").read_text(encoding="utf-8")
        )
        known_sources = {item["source_path"] for item in fact_data}
    issues = validate_draft(
        questions,
        responses,
        state["target"],
        known_sources,
        profile_ledger=ledger,
        require_experience_refs=v2,
    )
    if v2 and state.get("strict_quality", False):
        write_json(
            run_dir / "10_품질점수.json",
            [
                {
                    "question_index": question.index,
                    "score": asdict(
                        score_answer_quality(
                            question,
                            next(
                                response.answer
                                for response in responses
                                if response.question_index == question.index
                            ),
                            state["target"],
                            job_terms=job_terms,
                        )
                    ),
                }
                for question in questions
                if any(
                    response.question_index == question.index
                    for response in responses
                )
            ],
        )
        issues.extend(
            validate_answer_quality(
                questions,
                responses,
                state["target"],
                job_terms=job_terms,
                minimum_score=STRICT_MIN_ANSWER_SCORE,
                average_minimum_score=STRICT_MIN_AVERAGE_SCORE,
            )
        )
        try:
            research_claims = load_research_claims(run_dir / "04_공식근거.json")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            issues.append(
                ValidationIssue(
                    "invalid_research_evidence",
                    0,
                    f"공식 근거 JSON을 읽을 수 없습니다: {error}",
                )
            )
        else:
            issues.extend(
                validate_research_evidence(
                    questions,
                    responses,
                    research_claims,
                    allowed_domains=tuple(
                        state.get("official_research_domains", [])
                    ),
                )
            )

    if state.get("research_policy") == REQUIRED_RESEARCH_POLICY:
        try:
            research_execution = load_research_execution(
                run_dir / "04_리서치실행.json"
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            issues.append(
                ValidationIssue(
                    "invalid_research_execution",
                    0,
                    f"기업조사 실행 기록을 읽을 수 없습니다: {error}",
                )
            )
        else:
            issues.extend(
                validate_research_execution(research_execution, research_claims)
            )

    research = (run_dir / "04_기업직무조사.md").read_text(encoding="utf-8")
    if "http://" not in research and "https://" not in research:
        issues.append(
            ValidationIssue(
                "missing_research_link", 0, "공식 조사 링크가 없습니다."
            )
        )

    interview = (run_dir / "08_면접대비팩.md").read_text(encoding="utf-8")
    for section in ("1분 자기소개", "꼬리질문", "압박질문", "근거"):
        if section not in interview:
            issues.append(
                ValidationIssue(
                    "missing_interview_section",
                    0,
                    f"면접팩 누락: {section}",
                )
            )
    if v2 and ledger is not None:
        allowed_values = referenced_claim_values(responses, ledger)
        for match in METRIC.finditer(interview):
            normalized, _ = _normalize(match.group("number"), match.group("unit"))
            if normalized not in allowed_values:
                issues.append(
                    ValidationIssue(
                        "unapproved_interview_metric",
                        0,
                        f"면접팩의 승인되지 않은 수치: {match.group(0)}",
                    )
                )
        if state.get("strict_quality", False):
            issues.extend(
                validate_interview_pack(
                    interview,
                    questions,
                    responses,
                    allowed_metric_values=allowed_values,
                )
            )

    _write_review_report(
        run_dir, questions, responses, v2=v2, issues=issues
    )
    if issues:
        state.update(
            status="blocked_validation",
            validation_issues=[asdict(item) for item in issues],
        )
        if v2:
            state["blocked_stage"] = "finalize"
            state["issues"] = [asdict(item) for item in issues]
        write_state(run_dir, state)
        return state

    if legacy_copyedit:
        copyedited, copyeditor_report = copyedit_responses(
            responses,
            target_org=state["target"],
            job_terms=job_terms,
            timeout_ms=copyeditor_timeout_ms,
        )
        copyedit_issues = validate_draft(
            questions,
            copyedited,
            state["target"],
            known_sources,
            profile_ledger=ledger,
            require_experience_refs=v2,
        )
        if v2 and state.get("strict_quality", False):
            copyedit_issues.extend(
                validate_answer_quality(
                    questions,
                    copyedited,
                    state["target"],
                    job_terms=job_terms,
                    minimum_score=STRICT_MIN_ANSWER_SCORE,
                    average_minimum_score=STRICT_MIN_AVERAGE_SCORE,
                )
            )
            copyedit_issues.extend(
                validate_research_evidence(
                    questions,
                    copyedited,
                    research_claims,
                    allowed_domains=tuple(
                        state.get("official_research_domains", [])
                    ),
                )
            )
        if copyedit_issues:
            copyeditor_report.append(
                {
                    "question_index": 0,
                    "status": "fallback_validation",
                    "message": "; ".join(
                        issue.code for issue in copyedit_issues
                    ),
                }
            )
            state["copyeditor_status"] = "fallback_validation"
            state["copyeditor_applied"] = False
        else:
            responses = copyedited
            state["copyeditor_applied"] = any(
                item.get("status") == "copyedited"
                for item in copyeditor_report
            )
            copyeditor_fallback = any(
                str(item.get("status", "")).startswith("fallback_")
                for item in copyeditor_report
            )
            state["copyeditor_status"] = (
                "copyedited"
                if state["copyeditor_applied"]
                else "fallback" if copyeditor_fallback else "unchanged"
            )
            write_json(
                run_dir / "draft_copyedited.json",
                [asdict(response) for response in responses],
            )
        state["copyeditor_attempted"] = True
        write_json(run_dir / "09_copyeditor_report.json", copyeditor_report)
    else:
        # Record explicit disablement so a stale fallback report cannot affect
        # a later audit of the same run directory.
        write_json(
            run_dir / "09_copyeditor_report.json",
            [
                {
                    "question_index": question.index,
                    "status": "disabled",
                    "message": "copyeditor disabled by explicit finalize option",
                    "applied_rules": [],
                    "change_ratio": 0.0,
                }
                for question in questions
            ],
        )
        state["copyeditor_attempted"] = False
        state["copyeditor_applied"] = False
        state["copyeditor_status"] = "disabled"

    postprocess_attempted = False
    postprocess_applied = False
    postprocess_tier: str | None = None
    postprocess_model_id: str | None = None
    postprocess_budget_blocked = False
    model_unconfigured = False
    selected_source = "draft"
    postprocess_report: list[dict[str, object]] = []
    call_tracker = CostTracker(
        max_model_calls
        if max_model_calls is not None
        else 1_000_000 if humanize else max_postprocess_calls,
        max_postprocess_calls=max_postprocess_calls,
        max_stage_seconds=max_stage_seconds,
    )
    if not legacy_copyedit and not humanize:
        diagnostics = diagnose_responses(responses)
        write_json(
            run_dir / "09_style_diagnostics.json",
            [item.to_dict() for item in diagnostics],
        )
        target_responses = (
            responses
            if effective_postprocess == "always"
            else [
                response
                for response, diagnostic in zip(responses, diagnostics)
                if effective_postprocess == "auto" and diagnostic.should_rewrite
            ]
        )
        should_call = bool(target_responses)
        if effective_postprocess == "never":
            postprocess_report = [
                {
                    "question_index": item.question_index,
                    "status": "disabled",
                    "style_risk_score": diagnostic.style_risk_score,
                    "style_reasons": list(diagnostic.style_reasons),
                }
                for item, diagnostic in zip(responses, diagnostics)
            ]
        elif not should_call:
            postprocess_report = [
                {
                    "question_index": item.question_index,
                    "status": "skipped_style_pass",
                    "style_risk_score": diagnostic.style_risk_score,
                    "style_reasons": list(diagnostic.style_reasons),
                }
                for item, diagnostic in zip(responses, diagnostics)
            ]
        else:
            selected_diagnostics = [
                diagnostic
                for diagnostic in diagnostics
                if effective_postprocess == "always" or diagnostic.should_rewrite
            ]
            model = choose_tier(selected_diagnostics, postprocess_tier)
            postprocess_tier = model.tier
            postprocess_model_id = model.model_id
            model_unconfigured = postprocess_runner is None and model.model_id is None
            if model_unconfigured:
                # Never let the CLI silently select an unspecified external model.
                call_tracker.budget = 0
            try:
                call_tracker.record_call(
                    "copyeditor",
                    stage="postprocess",
                    model_tier=model.tier,
                    model_id=model.model_id,
                )
            except CostLimitExceeded as error:
                postprocess_budget_blocked = not model_unconfigured
                postprocess_report = [
                    {
                        "question_index": item.question_index,
                        "status": "skipped_model_unconfigured" if model_unconfigured else "fallback_budget_exceeded",
                        "message": "실제 모델 ID가 설정되지 않아 외부 호출을 건너뛰었습니다." if model_unconfigured else str(error),
                    }
                    for item in target_responses
                ]
            else:
                postprocess_attempted = True
                effective_timeout_ms = postprocess_timeout_ms or copyeditor_timeout_ms
                if max_stage_seconds is not None:
                    effective_timeout_ms = min(
                        effective_timeout_ms,
                        max(1, int(max_stage_seconds * 1000)),
                    )
                kwargs = {
                    "target_org": state["target"],
                    "job_terms": job_terms,
                    "timeout_ms": effective_timeout_ms,
                    "model_tier": model.tier,
                    "model_id": model.model_id,
                }
                if postprocess_runner is not None:
                    kwargs["runner"] = postprocess_runner
                within_stage_limit = True
                try:
                    edited, postprocess_report = copyedit_responses(
                        target_responses,
                        **kwargs,
                    )
                    call_status = "complete"
                except Exception as error:  # external runner failures are safe fallbacks
                    edited = target_responses
                    postprocess_report = [
                        {
                            "question_index": item.question_index,
                            "status": "fallback_backend_error",
                            "message": str(error),
                        }
                        for item in target_responses
                    ]
                    call_status = "failed"
                finally:
                    within_stage_limit = call_tracker.finish_call(status=call_status)
                if not within_stage_limit:
                    edited = target_responses
                    postprocess_report.append(
                        {
                            "question_index": 0,
                            "status": "fallback_stage_timeout",
                            "message": f"max_stage_seconds={max_stage_seconds}",
                        }
                    )
                elif any(
                    str(item.get("status", "")).startswith("fallback")
                    for item in postprocess_report
                    if isinstance(item, dict)
                ):
                    call_tracker.set_last_status("fallback")
                edited_by_index = {item.question_index: item for item in edited}
                target_indexes = {response.question_index for response in target_responses}
                original_responses = responses
                candidate = [
                    edited_by_index.get(item.question_index, item)
                    if item.question_index in target_indexes else item
                    for item in responses
                ]
                changed = any(
                    candidate_item.answer != original_item.answer
                    for candidate_item, original_item in zip(candidate, original_responses)
                )
                candidate_issues = []
                if changed:
                    candidate_issues.extend(
                        validate_draft(
                            questions,
                            candidate,
                            state["target"],
                            known_sources,
                            profile_ledger=ledger,
                            require_experience_refs=v2,
                        )
                    )
                    if v2 and state.get("strict_quality", False):
                        candidate_issues.extend(
                            validate_answer_quality(
                                questions,
                                candidate,
                                state["target"],
                                job_terms=job_terms,
                                minimum_score=STRICT_MIN_ANSWER_SCORE,
                                average_minimum_score=STRICT_MIN_AVERAGE_SCORE,
                            )
                        )
                        candidate_issues.extend(
                            validate_research_evidence(
                                questions,
                                candidate,
                                research_claims,
                                allowed_domains=tuple(state.get("official_research_domains", [])),
                            )
                        )
                bad_indexes = {
                    issue.question_index
                    for issue in candidate_issues
                    if issue.question_index in target_indexes
                }
                if any(issue.question_index == 0 for issue in candidate_issues):
                    bad_indexes = set(target_indexes)
                if bad_indexes:
                    messages: dict[int, list[str]] = {
                        question_index: [] for question_index in bad_indexes
                    }
                    for issue in candidate_issues:
                        for question_index in bad_indexes:
                            if issue.question_index in {0, question_index}:
                                messages[question_index].append(issue.code)
                    candidate = [
                        original if item.question_index in bad_indexes else item
                        for item, original in zip(candidate, original_responses)
                    ]
                    for question_index, codes in messages.items():
                        postprocess_report.append(
                            {
                                "question_index": question_index,
                                "status": "fallback_validation",
                                "message": "; ".join(codes),
                            }
                        )
                    call_tracker.set_last_status("fallback_validation")
                responses = candidate
                postprocess_applied = any(
                    item.answer != original.answer
                    for item, original in zip(responses, original_responses)
                )
                selected_source = "copyedited" if postprocess_applied else "draft"
                if postprocess_applied:
                    write_json(
                        run_dir / "draft_copyedited.json",
                        [asdict(response) for response in responses],
                    )
            state["postprocess_attempted"] = postprocess_attempted
            state["postprocess_applied"] = postprocess_applied
            state["postprocess_status"] = (
                "copyedited" if postprocess_applied
                else "fallback" if postprocess_attempted
                else "model_unconfigured" if model_unconfigured
                else "budget_exceeded" if postprocess_budget_blocked else "not_needed"
            )
            state["copyeditor_attempted"] = postprocess_attempted
            state["copyeditor_applied"] = postprocess_applied
            state["copyeditor_status"] = state["postprocess_status"]
            write_json(run_dir / "09_copyeditor_report.json", postprocess_report)
            state["postprocess_tier"] = postprocess_tier
            state["postprocess_model_id"] = postprocess_model_id
        if not should_call:
            state["postprocess_attempted"] = False
            state["postprocess_applied"] = False
            state["postprocess_status"] = (
                "model_unconfigured" if model_unconfigured
                else "budget_exceeded" if postprocess_budget_blocked
                else "not_needed" if effective_postprocess == "auto" else "disabled"
            )
            state["copyeditor_attempted"] = False
            state["copyeditor_applied"] = False
            state["copyeditor_status"] = state["postprocess_status"]
            write_json(run_dir / "09_copyeditor_report.json", postprocess_report)
        if model_unconfigured:
            call_tracker.budget = (
                max_model_calls
                if max_model_calls is not None
                else max_postprocess_calls
            )
        state["model_calls"] = call_tracker.to_dict()

    if humanize:
        state["legacy_patina"] = True
        legacy_timeout_ms = patina_timeout_ms
        if max_stage_seconds is not None:
            legacy_timeout_ms = min(
                legacy_timeout_ms,
                max(1, int(max_stage_seconds * 1000)),
            )

        def tracked_humanize(text: str, **kwargs) -> HumanizationResult:
            try:
                call_tracker.record_call("patina", stage="legacy_patina")
            except CostLimitExceeded:
                return HumanizationResult(text, "fallback_budget_exceeded", "model call budget exceeded")
            kwargs["timeout_ms"] = legacy_timeout_ms
            if postprocess_runner is not None:
                kwargs["runner"] = postprocess_runner
            try:
                result = humanize_text(text, **kwargs)
                call_tracker.finish_call(
                    status="fallback" if result.status.startswith("fallback") else "complete"
                )
                return result
            except Exception:
                call_tracker.finish_call(status="failed")
                raise

        def tracked_score(text: str, **kwargs) -> PatinaScoreResult:
            try:
                call_tracker.record_call("patina", stage="legacy_patina")
            except CostLimitExceeded:
                return PatinaScoreResult(None, "score_unavailable", "model call budget exceeded")
            kwargs["timeout_ms"] = legacy_timeout_ms
            if postprocess_runner is not None:
                kwargs["runner"] = postprocess_runner
            try:
                result = score_text(text, **kwargs)
                call_tracker.finish_call(
                    status="fallback" if result.score is None else "complete"
                )
                return result
            except Exception:
                call_tracker.finish_call(status="failed")
                raise

        voice_sample = _resolve_voice_sample(patina_voice_sample, state, run_dir)
        state["patina_backend"] = patina_backend
        state["patina_max_retries"] = patina_max_retries
        state["patina_ai_threshold"] = patina_ai_threshold
        state["patina_score_enabled"] = patina_score
        state["patina_voice_sample_used"] = str(voice_sample) if voice_sample else None
        humanized, patina_report = generate_and_select_candidates(
            responses,
            questions,
            state["target"],
            job_terms=job_terms,
            backend=patina_backend,
            timeout_ms=legacy_timeout_ms,
            voice_sample=voice_sample,
            max_retries=patina_max_retries,
            scorer=tracked_score if patina_score else None,
            ai_score_threshold=patina_ai_threshold,
            conditional_rewrite=patina_score,
            rewriter=tracked_humanize,
        )
        state["patina_attempted"] = any(
            bool(item.get("patina_attempted")) for item in patina_report
        )
        state["patina_score_attempted"] = any(
            bool(item.get("patina_score_attempted"))
            for item in patina_report
        )
        post_issues = validate_draft(
            questions,
            humanized,
            state["target"],
            known_sources,
            profile_ledger=ledger,
            require_experience_refs=v2,
        )
        if v2 and state.get("strict_quality", False):
            post_issues.extend(
                validate_answer_quality(
                    questions,
                    humanized,
                    state["target"],
                    job_terms=job_terms,
                    minimum_score=STRICT_MIN_ANSWER_SCORE,
                    average_minimum_score=STRICT_MIN_AVERAGE_SCORE,
                )
            )
            post_issues.extend(
                validate_research_evidence(
                    questions,
                    humanized,
                    research_claims,
                    allowed_domains=tuple(
                        state.get("official_research_domains", [])
                    ),
                )
            )
        if post_issues:
            patina_report.append(
                {
                    "question_index": 0,
                    "status": "fallback_validation",
                    "message": "; ".join(issue.code for issue in post_issues),
                    "backend": patina_backend,
                }
            )
            state["patina_status"] = "fallback_validation"
            state["patina_applied"] = False
        else:
            responses = humanized
            selected_variants = {
                str(item["selected_variant"]) for item in patina_report
            }
            fallback_count = sum(
                str(candidate["status"]).startswith("fallback_")
                for item in patina_report
                for candidate in item["candidates"]
            )
            if selected_variants.difference({"original", "copyedited"}):
                state["patina_status"] = "humanized"
            elif selected_variants == {"copyedited"} and all(
                item.get("ai_score_gate") == "passed"
                for item in patina_report
            ):
                state["patina_status"] = "not_needed"
            elif any(
                item.get("ai_score_gate") in {"failed", "unavailable"}
                for item in patina_report
            ):
                state["patina_status"] = "fallback_score_gate"
            elif fallback_count:
                state["patina_status"] = "fallback"
            else:
                state["patina_status"] = "unchanged"
            applied_count = sum(
                str(item["selected_variant"]) not in {"original", "copyedited"}
                for item in patina_report
            )
            state["patina_attempted"] = any(
                bool(
                    item.get(
                        "patina_attempted",
                        item.get("selected_variant") not in {"original", "copyedited"},
                    )
                )
                for item in patina_report
            )
            state["patina_score_attempted"] = any(
                bool(item.get("patina_score_attempted"))
                for item in patina_report
            )
            state["patina_applied"] = applied_count > 0
            state["patina_summary"] = {
                "attempted_questions": sum(
                    bool(
                        item.get(
                            "patina_attempted",
                            item.get("selected_variant")
                            not in {"original", "copyedited"},
                        )
                    )
                    for item in patina_report
                ),
                "applied_questions": applied_count,
                "baseline_selected_questions": len(patina_report) - applied_count,
                "fallback_candidates": fallback_count,
                "score_passed_questions": sum(
                    item.get("ai_score_gate") == "passed"
                    for item in patina_report
                ),
                "score_unavailable_questions": sum(
                    item.get("ai_score_gate") == "unavailable"
                    for item in patina_report
                ),
                "headroom_met_questions": sum(
                    bool(item.get("headroom_target_met"))
                    for item in patina_report
                ),
            }
            write_json(
                run_dir / "draft_humanized.json",
                [asdict(response) for response in responses],
            )
        write_json(run_dir / "09_patina_report.json", patina_report)
        write_json(run_dir / "09_초안후보평가.json", patina_report)
        write_json(
            run_dir / "10_품질점수.json",
            [
                {
                    "question_index": item["question_index"],
                    "selected_variant": item["selected_variant"],
                    "score": item["selected_score"],
                }
                for item in patina_report
                if "selected_score" in item
            ],
        )
        _write_review_report(run_dir, questions, responses, v2=v2, issues=[])

    state["model_calls"] = call_tracker.to_dict()
    output_paths = (
        run_dir / "06_자기소개서.md",
        run_dir / "06_자기소개서.docx",
        run_dir / "draft_final.json",
    )
    if any(path.is_symlink() for path in output_paths):
        raise ValueError("최종 산출물 경로에 심볼릭 링크가 있어 안전하게 저장할 수 없습니다.")
    markdown = render_draft_markdown(questions, responses)
    (run_dir / "06_자기소개서.md").write_text(markdown, encoding="utf-8")
    render_draft_docx(
        questions, responses, run_dir / "06_자기소개서.docx"
    )
    write_json(
        run_dir / "draft_final.json",
        [asdict(response) for response in responses],
    )
    state["status"] = "complete"
    state["finished_at"] = datetime.now().isoformat()
    state["run_duration_seconds"] = round(
        (datetime.fromisoformat(state["finished_at"])
         - datetime.fromisoformat(state.get("started_at", state["finished_at"]))).total_seconds(),
        2,
    )
    state.pop("validation_issues", None)
    state.pop("issues", None)
    state.pop("blocked_stage", None)
    state["final_artifact"] = write_final_artifact_manifest(
        run_dir,
        selected_source=(
            "legacy_patina" if humanize and state.get("patina_applied")
            else "copyedited" if state.get("copyeditor_applied") else selected_source
        ),
        postprocess_attempted=bool(state.get("postprocess_attempted", False)),
        postprocess_applied=bool(state.get("postprocess_applied", False)),
        model_tier=state.get("postprocess_tier"),
        model_id=state.get("postprocess_model_id"),
        validation={"status": "passed", "issues": []},
    )
    write_state(run_dir, state)
    return state
