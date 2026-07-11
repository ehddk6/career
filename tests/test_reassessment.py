import json
import sys
from pathlib import Path

from scripts.reassess_job_project import build_reassessment, render_reassessment


def _seed(tmp_path: Path) -> Path:
    review = tmp_path / "jasoseo_all_review_20260705"
    review.mkdir()
    for name in (
        "submission_ready_re_evaluation_20260705.json",
        "supplemental_submission_ready_re_evaluation_20260705.json",
        "legacy_submission_ready_re_evaluation_20260705.json",
    ):
        (review / name).write_text(
            json.dumps(
                [
                    {
                        "organization": "테스트기관",
                        "file": name,
                        "question_count": 1,
                        "average_score": 100.0,
                        "recommendation": "제출권장",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return review


def test_reassessment_includes_active_posting_count_and_block_reasons(tmp_path: Path):
    _seed(tmp_path)
    profile_dir = tmp_path / ".career_profile"
    profile_dir.mkdir()
    (profile_dir / "experience_ledger.proposed.json").write_text(
        json.dumps({"experiences": [{"experience_id": "exp_1"}]}),
        encoding="utf-8",
    )
    payload = build_reassessment(tmp_path)

    assert payload["profile"]["status"] == "proposed"
    assert payload["pipeline_runs"]["v2_complete_count"] == 0
    portfolio = payload["portfolio"]
    assert portfolio["total_organizations"] == 1
    assert portfolio["active_posting_count"] == 0
    assert portfolio["ready_count"] == 0
    assert len(portfolio["block_reasons"]) == 1
    reasons = portfolio["block_reasons"][0]["reasons"]
    assert "공식 공고 URL 없음" in reasons
    assert "확정 경험 원장 없음" in reasons


def test_reassessment_render_includes_v2_complete_and_active_counts(tmp_path: Path):
    _seed(tmp_path)
    profile_dir = tmp_path / ".career_profile"
    profile_dir.mkdir()
    (profile_dir / "experience_ledger.proposed.json").write_text(
        json.dumps({"experiences": [{"experience_id": "exp_1"}]}),
        encoding="utf-8",
    )
    payload = build_reassessment(tmp_path)
    text = render_reassessment(payload)
    assert "V2 완료" in text
    assert "활성 공고" in text
    assert "차단 사유 요약" in text


def test_reassessment_picks_up_v2_complete_run(tmp_path: Path):
    _seed(tmp_path)
    profile_dir = tmp_path / ".career_profile"
    profile_dir.mkdir()
    (profile_dir / "experience_ledger.proposed.json").write_text(
        json.dumps({"experiences": [{"experience_id": "exp_1"}]}),
        encoding="utf-8",
    )
    runs = tmp_path / "career_runs"
    run_dir = runs / "v2-run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"status": "complete", "target": "테스트기관", "quality_mode": "v2"}),
        encoding="utf-8",
    )
    payload = build_reassessment(tmp_path)
    assert payload["pipeline_runs"]["v2_complete_count"] == 1
    assert payload["pipeline_runs"]["v2_complete_count"] == len(
        payload["pipeline_runs"]["complete_runs"]
    )
