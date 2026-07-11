import json
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.portfolio import build_portfolio


def _seed_review(tmp_path: Path, *, score: float = 100.0, recommendation: str = "제출권장") -> Path:
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
                        "average_score": score,
                        "recommendation": recommendation,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return review


def test_portfolio_build_marks_candidates_pending_without_official_posting(tmp_path: Path):
    _seed_review(tmp_path)
    output = tmp_path / "portfolio"

    assert main(["portfolio", "build", "--root", str(tmp_path), "--output-dir", str(output)]) == 0

    payload = json.loads((output / "application_portfolio.json").read_text(encoding="utf-8"))
    assert len(payload["applications"]) == 1
    entry = payload["applications"][0]
    assert entry["posting_status"] == "pending_official_posting"
    assert entry["submission_status"] == "not_ready"
    assert entry["is_active"] is False
    assert payload["active_posting_count"] == 0


def test_portfolio_separates_legacy_internal_score_from_submission_status(tmp_path: Path):
    _seed_review(tmp_path, score=100.0, recommendation="제출권장")
    output = tmp_path / "portfolio"

    assert main(["portfolio", "build", "--root", str(tmp_path), "--output-dir", str(output)]) == 0

    payload = json.loads((output / "application_portfolio.json").read_text(encoding="utf-8"))
    entry = payload["applications"][0]
    # 과거 내부 평가는 100점 제출권장이지만, 공식 공고가 없으면 제출 불가
    assert entry["legacy_internal_score"] == 100.0
    assert entry["legacy_recommendation"] == "제출권장"
    assert entry["submission_status"] == "not_ready"
    assert entry["is_active"] is False

    md = (output / "application_portfolio.md").read_text(encoding="utf-8")
    assert "과거 내부 평가" in md
    assert "100.0" in md


def test_portfolio_does_not_mark_submittable_without_official_url_and_confirmed_profile(tmp_path: Path):
    _seed_review(tmp_path)
    root = tmp_path
    # 확정 원장이 없는 상태에서는 활성/준비 완료 될 수 없음
    payload = build_portfolio(root)
    entry = payload["applications"][0]
    assert entry["official_posting_url"] == ""
    assert entry["is_active"] is False
    assert entry["submission_status"] == "not_ready"
    assert payload["active_posting_count"] == 0


def test_portfolio_csv_includes_legacy_score_and_active_columns(tmp_path: Path):
    _seed_review(tmp_path, score=88.0, recommendation="보류")
    output = tmp_path / "portfolio"

    main(["portfolio", "build", "--root", str(tmp_path), "--output-dir", str(output)])

    csv_text = (output / "application_portfolio.csv").read_text(encoding="utf-8-sig")
    header = csv_text.splitlines()[0]
    assert "legacy_internal_score" in header
    assert "is_active" in header
    assert "legacy_recommendation" in header
    row = csv_text.splitlines()[1]
    assert "88.0" in row
    assert "보류" in row


def test_portfolio_applies_verified_target_but_requires_audit_for_ready(tmp_path: Path):
    _seed_review(tmp_path)
    (tmp_path / ".career_profile").mkdir()
    (tmp_path / ".career_profile" / "experience_ledger.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".career_profile" / "application_targets.json").write_text(
        json.dumps({"targets": [{
            "organization": "테스트기관",
            "official_posting_url": "https://example.or.kr/posting",
            "posting_status": "active",
            "deadline": "2026-07-23T16:00:00+09:00",
            "audit_passed": False,
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = build_portfolio(tmp_path)
    entry = payload["applications"][0]
    assert entry["is_active"] is True
    assert entry["submission_status"] == "not_ready"
    assert payload["active_posting_count"] == 1
