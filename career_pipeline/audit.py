"""Final run audit for submission-quality career pipeline artifacts."""
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .models import DraftResponse, ExperienceClaimRef, Question, ValidationIssue
from .quality import (
    STRICT_MIN_ANSWER_SCORE,
    STRICT_MIN_AVERAGE_SCORE,
    score_answer_quality,
    validate_answer_quality,
    validate_interview_pack,
)
from .research_evidence import (
    contains_prompt_injection,
    load_research_claims,
    load_research_execution,
    validate_research_evidence,
    validate_research_execution,
)
from .state import write_json
from .validation import referenced_claim_values, validate_draft
from .profile_schema import load_ledger


@dataclass(frozen=True)
class AuditIssue:
    category: str
    code: str
    severity: str
    message: str
    question_index: int = 0


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _questions(state: dict[str, Any]) -> list[Question]:
    return [Question(**item) for item in state.get("questions", [])]


def _responses_from_payload(payload: Any) -> list[DraftResponse]:
    responses: list[DraftResponse] = []
    if not isinstance(payload, list):
        return responses
    for item in payload:
        if not isinstance(item, dict):
            continue
        responses.append(
            DraftResponse(
                int(item.get("question_index", 0)),
                str(item.get("answer", "")),
                tuple(str(path) for path in item.get("evidence_paths", [])),
                tuple(
                    ExperienceClaimRef(
                        str(reference.get("experience_id", "")),
                        tuple(str(field) for field in reference.get("claim_fields", [])),
                    )
                    for reference in item.get("experience_refs", [])
                    if isinstance(reference, dict)
                ),
                tuple(str(ref) for ref in item.get("research_refs", [])),
            )
        )
    return responses


def _final_responses(run_dir: Path) -> list[DraftResponse]:
    for name in ("draft_humanized.json", "draft_copyedited.json", "draft.json"):
        path = run_dir / name
        if path.exists():
            return _responses_from_payload(_read_json(path, []))
    return []


def _issue_from_validation(category: str, issue: ValidationIssue) -> AuditIssue:
    critical = {
        "empty_answer",
        "over_limit",
        "unapproved_metric",
        "unapproved_interview_metric",
        "unknown_experience_ref",
        "unconfirmed_claim_ref",
        "research_prompt_injection",
    }
    severity = "high" if issue.code in critical else "medium"
    return AuditIssue(category, issue.code, severity, issue.message, issue.question_index)


def _deduct(base: int, issues: list[AuditIssue]) -> int:
    penalty = 0
    for issue in issues:
        penalty += 8 if issue.severity == "high" else 4
    return max(0, base - penalty)


def _job_terms(run_dir: Path) -> tuple[str, ...]:
    posting = _read_json(run_dir / "00_채용공고분석.json", {})
    if not isinstance(posting, dict):
        return ()
    return tuple(
        str(item)
        for item in posting.get("duties", []) + posting.get("competencies", [])
    )


def _cover_letter_score(
    run_dir: Path,
    state: dict[str, Any],
    questions: list[Question],
    responses: list[DraftResponse],
) -> tuple[int, list[AuditIssue], list[dict[str, Any]]]:
    issues: list[AuditIssue] = []
    score_rows: list[dict[str, Any]] = []
    target = str(state.get("target", ""))
    terms = _job_terms(run_dir)
    ledger = None
    known_sources: set[str] = set()
    if (run_dir / "02_확정경험원장.json").exists():
        try:
            ledger = load_ledger(run_dir / "02_확정경험원장.json")
            known_sources = {
                evidence.source_path
                for experience in ledger.experiences
                for claim in experience.claims
                for evidence in claim.evidence
            }
        except Exception as error:
            issues.append(
                AuditIssue(
                    "cover_letter",
                    "invalid_profile_ledger",
                    "high",
                    f"확정 경험 원장을 읽을 수 없습니다: {error}",
                )
            )
    else:
        facts = _read_json(run_dir / "02_사실원장.json", [])
        if isinstance(facts, list):
            known_sources = {
                str(item.get("source_path"))
                for item in facts
                if isinstance(item, dict) and isinstance(item.get("source_path"), str)
            }
    draft_issues = validate_draft(
        questions,
        responses,
        target,
        known_sources,
        profile_ledger=ledger,
        require_experience_refs=bool(ledger),
    )
    quality_issues = validate_answer_quality(
        questions,
        responses,
        target,
        job_terms=terms,
        minimum_score=STRICT_MIN_ANSWER_SCORE,
        average_minimum_score=STRICT_MIN_AVERAGE_SCORE,
    )
    issues.extend(_issue_from_validation("cover_letter", item) for item in draft_issues)
    issues.extend(_issue_from_validation("cover_letter", item) for item in quality_issues)
    for question in questions:
        response = next(
            (item for item in responses if item.question_index == question.index),
            None,
        )
        if response is None:
            continue
        row = score_answer_quality(question, response.answer, target, job_terms=terms)
        score_rows.append({"question_index": question.index, "score": asdict(row)})
    if not score_rows:
        issues.append(
            AuditIssue("cover_letter", "missing_draft", "high", "감사할 답변이 없습니다.")
        )
        return 0, issues, score_rows
    average = sum(row["score"]["total"] for row in score_rows) / len(score_rows)
    base = round(min(40, average * 0.4))
    return _deduct(base, issues), issues, score_rows


def _research_score(
    run_dir: Path,
    state: dict[str, Any],
    questions: list[Question],
    responses: list[DraftResponse],
) -> tuple[int, list[AuditIssue]]:
    issues: list[AuditIssue] = []
    claims = ()
    try:
        claims = load_research_claims(run_dir / "04_공식근거.json")
    except Exception as error:
        issues.append(
            AuditIssue(
                "research",
                "invalid_research_evidence",
                "high",
                f"공식 근거를 읽을 수 없습니다: {error}",
            )
        )
    if claims:
        validation = validate_research_evidence(
            questions,
            responses,
            claims,
            allowed_domains=tuple(state.get("official_research_domains", [])),
        )
        issues.extend(_issue_from_validation("research", item) for item in validation)
        for claim in claims:
            if not claim.source_type:
                issues.append(
                    AuditIssue(
                        "research",
                        "missing_source_type",
                        "medium",
                        f"출처 유형이 없습니다: {claim.claim_id}",
                    )
                )
            elif claim.source_type not in {"official", "primary", "regulatory", "official_posting"}:
                issues.append(
                    AuditIssue(
                        "research",
                        "weak_source_type",
                        "medium",
                        f"권위 출처로 분류되지 않은 근거입니다: {claim.claim_id}",
                    )
                )
            if not (claim.published_at or claim.basis_date):
                issues.append(
                    AuditIssue(
                        "research",
                        "missing_source_date",
                        "medium",
                        f"게시일 또는 기준일이 없습니다: {claim.claim_id}",
                    )
                )
            if contains_prompt_injection(claim.claim) or contains_prompt_injection(
                claim.evidence_excerpt
            ):
                issues.append(
                    AuditIssue(
                        "research",
                        "research_prompt_injection",
                        "high",
                        f"외부 지시문으로 보이는 문장이 있습니다: {claim.claim_id}",
                    )
                )
    if (run_dir / "04_리서치실행.json").exists():
        try:
            execution = load_research_execution(run_dir / "04_리서치실행.json")
            execution_issues = validate_research_execution(execution, claims)
            issues.extend(
                _issue_from_validation("research", item) for item in execution_issues
            )
        except Exception as error:
            issues.append(
                AuditIssue(
                    "research",
                    "invalid_research_execution",
                    "high",
                    f"리서치 실행 기록을 읽을 수 없습니다: {error}",
                )
            )
    research_md = (run_dir / "04_기업직무조사.md")
    if not research_md.exists() or "https://" not in research_md.read_text(
        encoding="utf-8"
    ):
        issues.append(
            AuditIssue(
                "research",
                "missing_research_link",
                "medium",
                "기업조사 문서에 공식 HTTPS 링크가 없습니다.",
            )
        )
    return _deduct(25, issues), issues


def _interview_score(
    run_dir: Path,
    questions: list[Question],
    responses: list[DraftResponse],
) -> tuple[int, list[AuditIssue]]:
    issues: list[AuditIssue] = []
    path = run_dir / "08_면접대비팩.md"
    if not path.exists():
        return 0, [
            AuditIssue("interview", "missing_interview_pack", "high", "면접팩이 없습니다.")
        ]
    allowed_values: set[str] | None = None
    if (run_dir / "02_확정경험원장.json").exists():
        try:
            allowed_values = referenced_claim_values(
                responses, load_ledger(run_dir / "02_확정경험원장.json")
            )
        except Exception:
            allowed_values = set()
    validation = validate_interview_pack(
        path.read_text(encoding="utf-8"),
        questions,
        responses,
        allowed_metric_values=allowed_values,
    )
    issues.extend(_issue_from_validation("interview", item) for item in validation)
    return _deduct(20, issues), issues


def _voice_sample_status(run_dir: Path, state: dict[str, Any]) -> tuple[str, AuditIssue | None]:
    candidates = []
    if state.get("patina_voice_sample_used"):
        candidates.append(Path(str(state["patina_voice_sample_used"])))
    if state.get("root"):
        candidates.append(Path(str(state["root"])) / ".career_profile" / "voice_sample.txt")
    candidates.append(run_dir / "voice_sample.txt")
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return "unreadable", AuditIssue(
                "style", "invalid_voice_sample", "medium", "voice_sample을 읽을 수 없습니다."
            )
        paragraphs = [item for item in text.splitlines() if item.strip()]
        if len(text.encode("utf-8")) > 20_000 or not (1 <= len(paragraphs) <= 3):
            return "invalid", AuditIssue(
                "style",
                "invalid_voice_sample",
                "medium",
                "voice_sample은 1-3단락, 20KB 이하여야 합니다.",
            )
        return "valid", None
    return "missing", None


def _style_score(run_dir: Path, state: dict[str, Any]) -> tuple[int, list[AuditIssue], dict[str, Any]]:
    issues: list[AuditIssue] = []
    score = 0
    copy_report = _read_json(run_dir / "09_copyeditor_report.json", None)
    patina_report = _read_json(run_dir / "09_patina_report.json", None)
    if isinstance(copy_report, list):
        if any(str(item.get("status", "")).startswith("fallback") for item in copy_report if isinstance(item, dict)):
            issues.append(AuditIssue("style", "copyeditor_fallback", "medium", "copyeditor가 fallback 되었습니다."))
            score += 2
        else:
            score += 5
    else:
        issues.append(AuditIssue("style", "copyeditor_not_verified", "medium", "copyeditor 보고서가 없습니다."))
        score += 2
    if isinstance(patina_report, list):
        gates = {
            str(item.get("ai_score_gate", "not_requested"))
            for item in patina_report
            if isinstance(item, dict)
        }
        if "failed" in gates or "unavailable" in gates:
            issues.append(AuditIssue("style", "patina_score_not_verified", "medium", "Patina 점수 게이트가 통과되지 않았습니다."))
            score += 2
        else:
            score += 5
    else:
        issues.append(AuditIssue("style", "patina_not_verified", "medium", "Patina 보고서가 없습니다."))
        score += 2
    voice_status, voice_issue = _voice_sample_status(run_dir, state)
    if voice_issue is not None:
        issues.append(voice_issue)
    score += 3 if voice_status == "valid" else 2 if voice_status == "missing" else 0
    if state.get("status") == "complete" and not str(state.get("patina_status", "")).startswith("fallback"):
        score += 2
    return min(15, score), issues, {"voice_sample_status": voice_status}


def run_quality_audit(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = _read_json(run_dir / "run.json", {})
    questions = _questions(state)
    responses = _final_responses(run_dir)
    cover_score, cover_issues, score_rows = _cover_letter_score(
        run_dir, state, questions, responses
    )
    research_score, research_issues = _research_score(
        run_dir, state, questions, responses
    )
    interview_score, interview_issues = _interview_score(run_dir, questions, responses)
    style_score, style_issues, style_meta = _style_score(run_dir, state)
    total = cover_score + research_score + interview_score + style_score
    recommendation = (
        "제출권장"
        if total >= 95
        else "보완 후 제출권장" if total >= 90 else "보완 필요"
    )
    issues = cover_issues + research_issues + interview_issues + style_issues
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "run_dir": str(run_dir),
        "score": total,
        "recommendation": recommendation,
        "sections": {
            "cover_letter": {"score": cover_score, "max": 40},
            "research": {"score": research_score, "max": 25},
            "interview": {"score": interview_score, "max": 20},
            "style_safety": {"score": style_score, "max": 15, **style_meta},
        },
        "question_scores": score_rows,
        "issues": [asdict(item) for item in issues],
    }
    write_json(run_dir / "11_최종품질감사.json", payload)
    (run_dir / "11_최종품질감사.md").write_text(
        render_quality_audit(payload), encoding="utf-8"
    )
    return payload


def render_quality_audit(payload: dict[str, Any]) -> str:
    lines = [
        "# 최종품질감사",
        "",
        f"- 총점: {payload['score']}/100",
        f"- 판정: {payload['recommendation']}",
        "",
        "## 영역별 점수",
        "",
    ]
    for name, section in payload["sections"].items():
        lines.append(f"- {name}: {section['score']}/{section['max']}")
    lines.extend(["", "## 보완 항목", ""])
    if payload["issues"]:
        for item in payload["issues"]:
            target = f" 문항 {item['question_index']}" if item["question_index"] else ""
            lines.append(
                f"- `{item['severity']}` `{item['code']}`{target}: {item['message']}"
            )
    else:
        lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"
