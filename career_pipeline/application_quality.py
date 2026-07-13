"""Evidence-bound quality readiness for an application target.

This module deliberately avoids a synthetic "hire probability" score.  It
reports independent gates so a legacy internal score cannot hide a missing
posting, stale research, an unfinalized cover letter, or an unverified
interview pack.
"""

from __future__ import annotations

import json
from hashlib import sha256
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


POSTING_FRESHNESS_DAYS = 7
QUALITY_DIMENSIONS = (
    "profile",
    "posting",
    "eligibility",
    "research",
    "cover_letter",
    "interview",
)
BLOCKER_MESSAGES = {
    "CONFIRMED_PROFILE_MISSING": "확정 경험 원장 없음",
    "OFFICIAL_POSTING_URL_MISSING_OR_INVALID": "공식 공고 URL 없음 또는 형식 오류",
    "POSTING_NOT_ACTIVE": "활성 공고 아님",
    "POSTING_CHECK_DATE_MISSING_OR_INVALID": "공고 확인일 없음 또는 형식 오류",
    "POSTING_CHECK_STALE": "공고 확인 결과가 오래됨",
    "POSTING_DEADLINE_MISSING_OR_INVALID": "공고 마감일 없음 또는 형식 오류",
    "POSTING_EXPIRED": "공고 마감일 경과",
    "ELIGIBILITY_NOT_CONFIRMED": "지원 자격이 eligible로 확정되지 않음",
    "ELIGIBILITY_INELIGIBLE": "필수 지원 자격 미충족",
    "CANDIDATE_DRAFT_MISSING": "후보 초안 없음",
    "V2_RUN_MISSING_OR_UNSAFE": "안전한 V2 실행 없음",
    "OFFICIAL_RESEARCH_NOT_VERIFIED": "공식 회사·직무 조사 미검증",
    "FINAL_ARTIFACT_MANIFEST_MISSING": "최종 자기소개서 manifest 없음",
    "FINAL_ARTIFACT_VALIDATION_FAILED": "최종 자기소개서 경로 또는 SHA-256 검증 실패",
    "INTERVIEW_PACK_NOT_VERIFIED": "면접팩 미검증",
    "FINAL_AUDIT_NOT_PASSED": "최종 품질 감사 미통과",
    "SELECTED_DRAFT_PATH_UNSAFE": "선택 자기소개서 경로가 안전하지 않음",
    "SELECTED_DRAFT_MISSING": "선택 자기소개서 없음",
}


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _has_json_content(path: Path) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value, (dict, list)) and bool(value)


def _safe_workspace_path(root: Path, raw: object) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    candidate = root / path
    try:
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None


def _parse_deadline(value: object, local_timezone) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.max, local_timezone)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=local_timezone) if parsed.tzinfo is None else parsed


def _official_https_url(value: object) -> bool:
    parsed = urlsplit(str(value or "").strip())
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username


def research_artifacts_ready(run_dir: Path | None, today: date | None = None) -> bool:
    if run_dir is None or not run_dir.is_dir():
        return False
    state = _load_object(run_dir / "run.json")
    if state.get("status") != "complete" or state.get("quality_mode") != "v2":
        return False
    evaluation_date = today or date.today()
    execution = _load_object(run_dir / "04_리서치실행.json")
    searched_at = _parse_date(execution.get("searched_at"))
    research_fresh = bool(
        searched_at
        and 0 <= (evaluation_date - searched_at).days <= POSTING_FRESHNESS_DAYS
    )
    return bool(
        _has_json_content(run_dir / "04_공식근거.json")
        and execution.get("status") == "verified"
        and research_fresh
    )


def _manifest_file(run_dir: Path, value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    try:
        candidate = run_dir / path
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(run_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() and not resolved.is_symlink() else None


def _final_artifact_valid(root: Path, run_dir: Path | None, target: dict[str, Any]) -> bool:
    selected = _safe_workspace_path(root, target.get("selected_draft"))
    if selected is None or not selected.is_file() or run_dir is None:
        return False
    final_manifest = _load_object(run_dir / "12_최종산출물.json")
    hashes = final_manifest.get("sha256", {}) if final_manifest else {}
    files = {
        "answer_json": _manifest_file(run_dir, final_manifest.get("answer_json_path")),
        "markdown": _manifest_file(run_dir, final_manifest.get("markdown_path")),
        "docx": _manifest_file(run_dir, final_manifest.get("docx_path")),
    }
    if not all(files.values()) or not isinstance(hashes, dict):
        return False
    if selected.resolve() != files["docx"]:
        return False
    hashes_valid = all(
        isinstance(hashes.get(name), str)
        and sha256(path.read_bytes()).hexdigest() == hashes[name]
        for name, path in files.items()
        if path is not None
    )
    return hashes_valid


def _interview_ready(run_dir: Path | None) -> bool:
    if run_dir is None or not run_dir.is_dir():
        return False
    pack = run_dir / "08_면접대비팩.md"
    if not pack.is_file() or pack.stat().st_size == 0:
        return False
    audit = _load_object(run_dir / "11_최종품질감사.json")
    section = audit.get("sections", {}).get("interview", {}) if audit else {}
    score = section.get("score")
    maximum = section.get("max")
    return isinstance(score, (int, float)) and score == maximum and maximum > 0


def _audit_passed(run_dir: Path | None) -> bool:
    if run_dir is None:
        return False
    audit = _load_object(run_dir / "11_최종품질감사.json")
    score = audit.get("internal_validation_score", audit.get("score"))
    high_issues = [
        item
        for item in audit.get("issues", [])
        if isinstance(item, dict) and item.get("severity") == "high"
    ]
    return bool(
        audit.get("quality_gate") == "pass"
        and isinstance(score, (int, float))
        and score >= 90
        and not high_issues
    )


def _selected_quality_summary(run_dir: Path | None) -> dict[str, Any] | None:
    if run_dir is None:
        return None
    audit = _load_object(run_dir / "11_최종품질감사.json")
    manifest_path = run_dir / "12_최종산출물.json"
    if not audit or not manifest_path.is_file():
        return None
    question_totals = [
        item.get("score", {}).get("total")
        for item in audit.get("question_scores", [])
        if isinstance(item, dict) and isinstance(item.get("score"), dict)
    ]
    numeric_totals = [value for value in question_totals if isinstance(value, (int, float))]
    return {
        "metric": "internal_validation_not_hire_probability",
        "internal_validation_score": audit.get("internal_validation_score", audit.get("score")),
        "quality_gate": audit.get("quality_gate"),
        "human_review_recommended": audit.get("human_review_recommended", True),
        "question_score_min": min(numeric_totals) if numeric_totals else None,
        "question_score_max": max(numeric_totals) if numeric_totals else None,
        "sections": audit.get("sections", {}),
        "issue_codes": sorted(
            {
                str(item.get("code"))
                for item in audit.get("issues", [])
                if isinstance(item, dict) and item.get("code")
            }
        ),
        "final_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
    }


def assess_application_quality(
    root: Path,
    target: dict[str, Any],
    *,
    confirmed_profile: bool,
    has_candidates: bool,
    evaluation_date: date | datetime | None = None,
) -> dict[str, Any]:
    """Return explainable readiness gates for one application target."""

    if isinstance(evaluation_date, datetime):
        now = evaluation_date
        if now.tzinfo is None:
            now = now.astimezone()
    elif isinstance(evaluation_date, date):
        now = datetime.combine(evaluation_date, time.min).astimezone()
    else:
        now = datetime.now().astimezone()
    today = now.date()
    run_dir = _safe_workspace_path(root, target.get("v2_run_dir"))
    last_checked = _parse_date(target.get("last_checked"))
    deadline_at = _parse_deadline(target.get("deadline"), now.tzinfo)
    posting_fresh = bool(
        last_checked
        and 0 <= (today - last_checked).days <= POSTING_FRESHNESS_DAYS
    )
    posting_passed = bool(
        _official_https_url(target.get("official_posting_url"))
        and target.get("posting_status") == "active"
        and posting_fresh
        and deadline_at is not None
        and deadline_at >= now
    )

    dimensions = {
        "profile": bool(confirmed_profile),
        "posting": posting_passed,
        "eligibility": target.get("eligibility_status") == "eligible",
        "research": research_artifacts_ready(run_dir, today),
        "cover_letter": bool(
            has_candidates
            and _final_artifact_valid(root, run_dir, target)
            and _audit_passed(run_dir)
        ),
        "interview": _interview_ready(run_dir),
    }
    blockers: list[str] = []
    if not confirmed_profile:
        blockers.append("CONFIRMED_PROFILE_MISSING")
    if not _official_https_url(target.get("official_posting_url")):
        blockers.append("OFFICIAL_POSTING_URL_MISSING_OR_INVALID")
    if target.get("posting_status") != "active":
        blockers.append("POSTING_NOT_ACTIVE")
    if not last_checked:
        blockers.append("POSTING_CHECK_DATE_MISSING_OR_INVALID")
    elif not posting_fresh:
        blockers.append("POSTING_CHECK_STALE")
    if deadline_at and deadline_at < now:
        blockers.append("POSTING_EXPIRED")
    elif deadline_at is None:
        blockers.append("POSTING_DEADLINE_MISSING_OR_INVALID")
    if target.get("eligibility_status") == "ineligible":
        blockers.append("ELIGIBILITY_INELIGIBLE")
    elif not dimensions["eligibility"]:
        blockers.append("ELIGIBILITY_NOT_CONFIRMED")
    if not has_candidates:
        blockers.append("CANDIDATE_DRAFT_MISSING")
    if run_dir is None or not run_dir.is_dir():
        blockers.append("V2_RUN_MISSING_OR_UNSAFE")
    else:
        if not dimensions["research"]:
            blockers.append("OFFICIAL_RESEARCH_NOT_VERIFIED")
        if not _load_object(run_dir / "12_최종산출물.json"):
            blockers.append("FINAL_ARTIFACT_MANIFEST_MISSING")
        elif not _final_artifact_valid(root, run_dir, target):
            blockers.append("FINAL_ARTIFACT_VALIDATION_FAILED")
        if not dimensions["interview"]:
            blockers.append("INTERVIEW_PACK_NOT_VERIFIED")
    if not _audit_passed(run_dir):
        blockers.append("FINAL_AUDIT_NOT_PASSED")
    if target.get("selected_draft") and _safe_workspace_path(root, target.get("selected_draft")) is None:
        blockers.append("SELECTED_DRAFT_PATH_UNSAFE")
    elif not target.get("selected_draft"):
        blockers.append("SELECTED_DRAFT_MISSING")

    passed = sum(1 for name in QUALITY_DIMENSIONS if dimensions[name])
    if passed == len(QUALITY_DIMENSIONS):
        status = "ready"
    elif posting_passed and target.get("eligibility_status") != "ineligible":
        status = "review_required"
    else:
        status = "not_ready"
    blocker_codes = sorted(set(blockers))
    return {
        "status": status,
        "dimensions": dimensions,
        "passed_gate_count": passed,
        "total_gate_count": len(QUALITY_DIMENSIONS),
        "blocker_codes": blocker_codes,
        "blocker_messages": [BLOCKER_MESSAGES[code] for code in blocker_codes],
        "posting_freshness_days": POSTING_FRESHNESS_DAYS,
        "evidence": {
            "posting_checked_at": str(target.get("last_checked", "")),
            "deadline": str(target.get("deadline", "")),
            "eligibility_status": str(target.get("eligibility_status", "manual_review")),
            "v2_run_dir": str(target.get("v2_run_dir", "")),
            "selected_draft": str(target.get("selected_draft", "")),
        },
        "selected_artifact_quality": _selected_quality_summary(run_dir),
    }
