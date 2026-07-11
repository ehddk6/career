"""Create a project-wide, evidence-bound reassessment of the job-search workspace."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any


REVIEW_DIR = "jasoseo_all_review_20260705"
EVALUATION_FILES = (
    "submission_ready_re_evaluation_20260705.json",
    "supplemental_submission_ready_re_evaluation_20260705.json",
    "legacy_submission_ready_re_evaluation_20260705.json",
)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _ensure_portfolio(root: Path) -> dict[str, Any]:
    """Build the portfolio board on the fly so the reassessment stays self-contained."""
    from career_pipeline.portfolio import build_portfolio, write_portfolio

    payload = build_portfolio(root)
    review_dir = root / REVIEW_DIR
    if review_dir.exists():
        write_portfolio(payload, review_dir)
    return payload


def _profile_status(root: Path) -> dict[str, Any]:
    profile_dir = root / ".career_profile"
    confirmed = profile_dir / "experience_ledger.json"
    proposed = profile_dir / "experience_ledger.proposed.json"
    if confirmed.exists():
        return {"status": "confirmed", "path": str(confirmed.relative_to(root))}
    if proposed.exists():
        payload = _load_json(proposed, {})
        experiences = payload.get("experiences", []) if isinstance(payload, dict) else []
        return {
            "status": "proposed",
            "path": str(proposed.relative_to(root)),
            "experience_count": len(experiences) if isinstance(experiences, list) else 0,
        }
    return {"status": "missing"}


def _run_summary(root: Path) -> dict[str, Any]:
    runs: list[dict[str, str]] = []
    for run_dir in sorted((root / "career_runs").glob("*")):
        state = _load_json(run_dir / "run.json", {})
        if not isinstance(state, dict):
            continue
        runs.append(
            {
                "run": run_dir.name,
                "status": str(state.get("status", "unknown")),
                "target": str(state.get("target", "")),
                "quality_mode": str(state.get("quality_mode", "legacy")),
            }
        )
    complete = [item for item in runs if item["status"] == "complete"]
    v2_complete = [item for item in complete if item["quality_mode"] == "v2"]
    legacy_complete = [item for item in complete if item["quality_mode"] != "v2"]
    return {
        "total_runs": len(runs),
        "status_counts": dict(Counter(item["status"] for item in runs)),
        "complete_runs": complete,
        "v2_complete_count": len(v2_complete),
        "legacy_complete_count": len(legacy_complete),
    }


def _evaluation_summary(review_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    for name in EVALUATION_FILES:
        payload = _load_json(review_dir / name, [])
        entries = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        source_counts[name] = len(entries)
        records.extend(entries)

    scores = [
        float(item["average_score"])
        for item in records
        if isinstance(item.get("average_score"), (int, float))
    ]
    recommendations = Counter(str(item.get("recommendation", "")) for item in records)
    organizations = Counter(str(item.get("organization", "")) for item in records)
    uniform = bool(scores) and len(set(scores)) == 1
    return {
        "candidate_count": len(records),
        "source_counts": source_counts,
        "recommendation_counts": dict(recommendations),
        "organization_counts": dict(organizations.most_common()),
        "score_summary": {
            "count": len(scores),
            "minimum": min(scores) if scores else None,
            "maximum": max(scores) if scores else None,
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "unique_score_count": len(set(scores)),
            "uniform_scores": uniform,
        },
    }


def _portfolio_summary(root: Path) -> dict[str, Any]:
    payload = _ensure_portfolio(root)
    applications = (
        payload.get("applications", [])
        if isinstance(payload, dict) and isinstance(payload.get("applications"), list)
        else []
    )
    active = [item for item in applications if isinstance(item, dict) and item.get("is_active")]
    ready = [item for item in applications if isinstance(item, dict) and item.get("submission_status") == "ready"]
    posting_counts = Counter(
        str(item.get("posting_status", "")) for item in applications if isinstance(item, dict)
    )
    block_reasons: list[dict[str, str]] = []
    for item in applications:
        if not isinstance(item, dict):
            continue
        if item.get("submission_status") == "ready":
            continue
        org = str(item.get("organization", ""))
        reasons: list[str] = []
        if not item.get("official_posting_url"):
            reasons.append("공식 공고 URL 없음")
        if not item.get("is_active"):
            reasons.append("활성 공고 아님")
        if isinstance(payload, dict) and not payload.get("confirmed_profile"):
            reasons.append("확정 경험 원장 없음")
        if not item.get("candidate_drafts"):
            reasons.append("후보 초안 없음")
        block_reasons.append(
            {"organization": org, "reasons": ", ".join(reasons) or "미확인"}
        )
    return {
        "confirmed_profile": payload.get("confirmed_profile") if isinstance(payload, dict) else False,
        "total_organizations": len(applications),
        "active_posting_count": len(active),
        "ready_count": len(ready),
        "posting_status_counts": dict(posting_counts),
        "block_reasons": block_reasons,
    }


def build_reassessment(root: Path) -> dict[str, Any]:
    review_dir = root / REVIEW_DIR
    profile = _profile_status(root)
    runs = _run_summary(root)
    evaluations = _evaluation_summary(review_dir)
    portfolio = _portfolio_summary(root)
    application_queue = [
        {
            "organization": organization,
            "candidate_drafts": count,
            "status": "공고 확인 필요",
            "next_gate": "최신 공식 공고와 확정 경험 원장 확인",
        }
        for organization, count in evaluations["organization_counts"].items()
        if organization
    ]
    blockers: list[dict[str, str]] = []

    if profile["status"] != "confirmed":
        blockers.append(
            {
                "priority": "P0",
                "area": "경험 근거",
                "finding": "확정 경험 원장이 없어 사실·수치 검증을 완료할 수 없습니다.",
                "action": "후보 원장을 검토해 사실인 경험과 수치만 confirmed 원장으로 확정합니다.",
            }
        )
    if evaluations["score_summary"]["uniform_scores"]:
        blockers.append(
            {
                "priority": "P0",
                "area": "자기소개서 평가",
                "finding": "모든 후보가 같은 점수를 받아 제출 우선순위를 판별할 수 없습니다.",
                "action": "최신 공고 문항·글자 수·직무 연결·근거 상태를 반영한 상대 평가로 다시 선별합니다.",
            }
        )
    if runs["v2_complete_count"] == 0:
        blockers.append(
            {
                "priority": "P1",
                "area": "지원 실행",
                "finding": "확정 경험 원장과 공식 공고를 함께 사용한 완료 V2 실행 기록이 없습니다.",
                "action": "지원할 기업을 정한 뒤 공식 공고 기준으로 V2 prepare → research → finalize를 실행합니다.",
            }
        )
    blockers.append(
        {
            "priority": "P1",
            "area": "지원 전략",
            "finding": "기존 후보는 과거 공고 기반 자료가 섞여 있어 현재 접수 중인 채용과 직접 연결되지 않습니다.",
            "action": "이번 주 공고별로 지원 여부, 마감일, 직무, 사용할 초안을 한 표로 관리합니다.",
        }
    )
    blockers.append(
        {
            "priority": "P2",
            "area": "면접 준비",
            "finding": "완료된 면접팩은 HUG 중심이며, 다른 우선 기업용 검증된 면접팩이 부족합니다.",
            "action": "확정 경험 원장을 기준으로 우선 지원 기업별 1분 소개·꼬리질문·반박질문을 생성합니다.",
        }
    )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "assessment_date": date.today().isoformat(),
        "scope": "workspace-wide job-search project reassessment",
        "profile": profile,
        "pipeline_runs": runs,
        "cover_letter_corpus": evaluations,
        "portfolio": portfolio,
        "application_queue": application_queue,
        "priority_actions": blockers,
        "verification_boundary": (
            "이 보고서는 로컬 작업공간의 파일과 실행 기록을 평가합니다. "
            "현재 접수 중인 채용공고, 마감일, 최신 기업 정보는 별도 공식 출처 확인이 필요합니다."
        ),
    }


def render_reassessment(payload: dict[str, Any]) -> str:
    profile = payload["profile"]
    runs = payload["pipeline_runs"]
    corpus = payload["cover_letter_corpus"]
    portfolio = payload["portfolio"]
    scores = corpus["score_summary"]
    lines = [
        "# 취업 프로젝트 전체 재평가",
        "",
        f"- 평가일: {payload['assessment_date']}",
        "- 범위: 경험 근거, 자기소개서 후보군, 지원 파이프라인, 면접 준비, 운영 관리",
        "",
        "## 현재 상태",
        "",
        f"- 경험 원장: {profile['status']}",
        f"- 자기소개서 후보: {corpus['candidate_count']}개",
        f"- 후보 평가 점수: {scores['minimum']}~{scores['maximum']}점, 고유 점수 {scores['unique_score_count']}개",
        f"- 파이프라인 실행: {runs['total_runs']}개, 완료 {len(runs['complete_runs'])}개, V2 완료 {runs['v2_complete_count']}개",
        f"- 49개 기관 상태판: 활성 공고 {portfolio['active_posting_count']}개, 제출 준비 완료 {portfolio['ready_count']}개",
        "",
        "## 우선 개선",
        "",
    ]
    for item in payload["priority_actions"]:
        lines.extend(
            [
                f"### {item['priority']} · {item['area']}",
                "",
                f"- 진단: {item['finding']}",
                f"- 개선: {item['action']}",
                "",
            ]
        )
    lines.extend(["## 지원 준비 큐", ""])
    for item in payload["application_queue"]:
        lines.append(
            f"- {item['organization']}: 기존 후보 {item['candidate_drafts']}개 · "
            f"{item['status']} · {item['next_gate']}"
        )
    if portfolio["block_reasons"]:
        lines.extend(["", "## 차단 사유 요약", ""])
        for item in portfolio["block_reasons"][:10]:
            lines.append(f"- {item['organization']}: {item['reasons']}")
        if len(portfolio["block_reasons"]) > 10:
            lines.append(f"- 외 {len(portfolio['block_reasons']) - 10}개 기관")
    lines.extend(
        [
            "",
            "## 운영 원칙",
            "",
            "1. 기존 초안은 참고 후보로만 두고, 실제 지원본은 최신 공식 공고와 확정 경험 원장을 통과한 경우에만 사용합니다.",
            "2. '제출 권장' 표시는 상대 우선순위와 근거 검증이 끝난 경우에만 사용합니다.",
            "3. 기업 조사에서 로컬 자료와 공식 출처를 구분해 기록합니다.",
            "",
            "## 검증 범위",
            "",
            payload["verification_boundary"],
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = (args.output_dir or root / REVIEW_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_reassessment(root)
    stamp = date.today().strftime("%Y%m%d")
    json_path = output_dir / f"project_reassessment_{stamp}.json"
    md_path = output_dir / f"project_reassessment_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_reassessment(payload), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
