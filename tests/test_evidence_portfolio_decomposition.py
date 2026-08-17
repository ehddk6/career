"""Evidence Portfolio planning_score decomposition invariants.

The decomposition must be additive and must never change the production
selection (same preferred evidence ids, same ordering, same final scores).
"""
from __future__ import annotations

import json
from pathlib import Path

from career_pipeline.evidence_portfolio import (
    build_evidence_portfolio,
    score_candidate,
)


def _write_run(root: Path, posting: dict, ledger: dict, questions: list[dict]) -> None:
    (root / "run.json").write_text(
        json.dumps({"target": posting["target"], "questions": questions}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "00_채용공고분석.json").write_text(
        json.dumps(posting, ensure_ascii=False), encoding="utf-8"
    )
    (root / "02_확정경험원장.json").write_text(
        json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
    )
    (root / "04_공식근거.json").write_text("[]", encoding="utf-8")


def _claim(cid: str, value: str, method: str = "direct_source", contribution: str = "caused") -> dict:
    return {
        "claim_id": cid,
        "field": "action",
        "normalized_value": value,
        "status": "confirmed",
        "verification": {"method": method, "contribution": contribution},
    }


def _fixture(tmp_path: Path) -> Path:
    posting = {
        "target": "테스트공사 행정",
        "duties": ["신청서류를 공식 기준과 대조해 오류와 누락을 확인한다"],
        "competencies": [],
        "requirements": [],
        "preferred": [],
        "constraints": [],
    }
    ledger = {
        "experiences": [
            {
                "experience_id": "exp-1",
                "status": "confirmed",
                "title": "행정지원",
                "role": "담당",
                "situation": "신청서류 처리",
                "actions": ["신청서류를 대조했다"],
                "outcomes": [],
                "competencies": [],
                "claims": [
                    _claim("clm-strong", "신청서류를 공식 기준과 대조해 오류를 확인했습니다."),
                    _claim("clm-metric", "오류율이 30% 감소했습니다.", method="before_after"),
                ],
            },
            {
                "experience_id": "exp-2",
                "status": "confirmed",
                "title": "고객응대",
                "role": "담당",
                "situation": "",
                "actions": [],
                "outcomes": [],
                "competencies": [],
                "claims": [_claim("clm-weak", "성실하게 업무에 참여했습니다.", contribution="contributed")],
            },
        ]
    }
    questions = [{"index": 1, "prompt": "신청 서류 검토 직무에서 본인의 강점을 설명해 주십시오."}]
    _write_run(tmp_path, posting, ledger, questions)
    return tmp_path


def test_decomposition_parts_sum_to_final_score(tmp_path: Path) -> None:
    portfolio = build_evidence_portfolio(_fixture(tmp_path))
    rows = [
        row
        for assignment in portfolio["assignments"]
        for row in assignment["preferred_evidence"]
    ]
    assert rows, "fixture must select at least one evidence row"
    for row in rows:
        total = (
            float(row["signal_relevance_contribution"])
            + float(row["question_overlap_contribution"])
            + float(row["defensibility_contribution"])
            - float(row["risk_penalty"])
            - float(row["reuse_penalty"])
        )
        assert abs(total - float(row["planning_score"])) <= 0.003, row


def test_decomposition_flags_are_consistent(tmp_path: Path) -> None:
    portfolio = build_evidence_portfolio(_fixture(tmp_path))
    for assignment in portfolio["assignments"]:
        for row in assignment["preferred_evidence"]:
            zero = (
                float(row["signal_relevance_contribution"]) == 0.0
                and float(row["question_overlap_contribution"]) == 0.0
            )
            assert row["zero_signal_selection"] is zero, row
            assert row["selected_due_to_defensibility_only"] is zero, row
            assert row["positive_relevance_contribution"] is not zero, row
            assert row["covered_signal_count"] == len(row["covered_signal_ids"]), row


def test_selection_identity_snapshot(tmp_path: Path) -> None:
    run = _fixture(tmp_path)
    portfolio = build_evidence_portfolio(run)
    selected = [
        (assignment["question_index"], [row["evidence_id"] for row in assignment["preferred_evidence"]])
        for assignment in portfolio["assignments"]
    ]
    expected = [
        (1, ["applicant:exp-1:clm-strong", "applicant:exp-1:clm-metric"])
    ]
    assert selected == expected


def test_assignment_order_matches_sort_key(tmp_path: Path) -> None:
    portfolio = build_evidence_portfolio(_fixture(tmp_path), max_per_question=3)
    for assignment in portfolio["assignments"]:
        rows = assignment["preferred_evidence"]
        keys = [(float(row["planning_score"]), row["evidence_id"]) for row in rows]
        assert keys == sorted(keys, reverse=True), rows


def test_score_candidate_zero_signal_detection() -> None:
    candidate = {
        "evidence_id": "applicant:exp-1:clm-1",
        "tokens": ["성실", "참여"],
        "defensibility": 1.7,
        "risk": 0.0,
    }
    signals: list[dict] = [
        {"signal_id": "sig_1", "weight": 1.0, "tokens": ["신청서류", "대조"]}
    ]
    part = score_candidate(candidate, signals, set(), 0)
    assert part["signal_relevance_contribution"] == 0.0
    assert part["question_overlap_contribution"] == 0.0
    assert part["zero_signal_selection"] is True
    assert part["selected_due_to_defensibility_only"] is True
    assert abs(part["score"] - 1.7 * 0.75) < 1e-9
