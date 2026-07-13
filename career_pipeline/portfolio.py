"""Workspace-wide application portfolio board."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .application_quality import assess_application_quality


EVALUATION_FILES = (
    "submission_ready_re_evaluation_20260705.json",
    "supplemental_submission_ready_re_evaluation_20260705.json",
    "legacy_submission_ready_re_evaluation_20260705.json",
)


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _legacy_score(records: list[dict[str, Any]]) -> dict[str, Any]:
    """과거 내부 평가 점수와 제출 권장 표시를 현재 상태와 분리해 기록합니다."""
    if not records:
        return {"average_score": None, "recommendation": "", "source": ""}
    scores = [
        float(item["average_score"])
        for item in records
        if isinstance(item.get("average_score"), (int, float))
    ]
    recommendation = next(
        (str(item.get("recommendation", "")) for item in records if item.get("recommendation")),
        "",
    )
    return {
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "recommendation": recommendation,
        "source": "legacy internal evaluation",
    }


def _target_overrides(root: Path) -> dict[str, dict[str, Any]]:
    path = root / ".career_profile" / "application_targets.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("targets", []) if isinstance(payload, dict) else []
    return {
        str(row["organization"]): row
        for row in rows
        if isinstance(row, dict) and row.get("organization")
    }


def build_portfolio(root: Path) -> dict[str, Any]:
    review = root / "jasoseo_all_review_20260705"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    legacy_by_org: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name in EVALUATION_FILES:
        for item in _load(review / name):
            organization = str(item.get("organization") or "미분류")
            grouped[organization].append(
                {
                    "source": name,
                    "file": str(item.get("file", "")),
                    "question_count": item.get("question_count"),
                }
            )
            legacy_by_org[organization].append(item)
    confirmed_profile = (root / ".career_profile" / "experience_ledger.json").exists()
    overrides = _target_overrides(root)
    applications: list[dict[str, Any]] = []
    for organization, items in sorted(grouped.items()):
        legacy = _legacy_score(legacy_by_org.get(organization, []))
        target = overrides.get(organization, {})
        official_url = str(target.get("official_posting_url", ""))
        posting_status = str(target.get("posting_status", "pending_official_posting"))
        quality = assess_application_quality(
            root,
            target,
            confirmed_profile=confirmed_profile,
            has_candidates=bool(items),
        )
        is_active = quality["dimensions"]["posting"]
        applications.append(
            {
                "organization": organization,
                "candidate_drafts": len(items),
                "drafts": items,
                "target_role": str(target.get("target_role", "")),
                "official_posting_url": official_url,
                "posting_status": posting_status,
                "is_active": is_active,
                "deadline": str(target.get("deadline", "")),
                "last_checked": str(target.get("last_checked", "")),
                "selected_draft": str(target.get("selected_draft", "")),
                "v2_run_dir": str(target.get("v2_run_dir", "")),
                "legacy_internal_score": legacy["average_score"],
                "legacy_recommendation": legacy["recommendation"],
                "legacy_score_source": legacy["source"],
                "quality_readiness": quality,
                "submission_status": quality["status"],
            }
        )
    active_count = sum(1 for item in applications if item["is_active"])
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "confirmed_profile": confirmed_profile,
        "active_posting_count": active_count,
        "applications": applications,
    }


def write_portfolio(payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "application_portfolio.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fields = (
        "organization",
        "candidate_drafts",
        "target_role",
        "official_posting_url",
        "posting_status",
        "is_active",
        "deadline",
        "last_checked",
        "selected_draft",
        "v2_run_dir",
        "legacy_internal_score",
        "legacy_recommendation",
        "quality_gates",
        "quality_blockers",
        "submission_status",
    )
    with (output_dir / "application_portfolio.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {
                **{field: item.get(field, "") for field in fields},
                "quality_gates": (
                    f"{item['quality_readiness']['passed_gate_count']}/"
                    f"{item['quality_readiness']['total_gate_count']}"
                ),
                "quality_blockers": ";".join(item["quality_readiness"]["blocker_codes"]),
            }
            for item in payload["applications"]
        )
    lines = [
        "# 지원 상태판",
        "",
        f"- 확정 경험 원장: {'있음' if payload['confirmed_profile'] else '없음'}",
        f"- 활성 공고: {payload['active_posting_count']}개",
        "",
        "과거 내부 평가(100점)는 참고용입니다. 현재 품질은 경험·공고·지원자격·공식조사·최종 자기소개서·면접팩의 6개 독립 게이트로 판정합니다.",
        "",
        "| 기관 | 후보 초안 | 공고 상태 | 활성 | 과거 내부 평가 | 품질 게이트 | 제출 상태 |",
        "|---|---:|---|:---:|---:|---:|---|",
    ]
    for item in payload["applications"]:
        legacy = item.get("legacy_internal_score")
        legacy_cell = f"{legacy}" if legacy is not None else "-"
        lines.append(
            f"| {item['organization']} | {item['candidate_drafts']} | {item['posting_status']} | "
            f"{'O' if item.get('is_active') else 'X'} | {legacy_cell} | "
            f"{item['quality_readiness']['passed_gate_count']}/{item['quality_readiness']['total_gate_count']} | "
            f"{item['submission_status']} |"
        )
    (output_dir / "application_portfolio.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
