import json
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.application_quality import assess_application_quality
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
            "deadline": "2099-07-23T16:00:00+09:00",
            "last_checked": date.today().isoformat(),
            "audit_passed": False,
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = build_portfolio(tmp_path)
    entry = payload["applications"][0]
    assert entry["is_active"] is True
    assert entry["submission_status"] == "review_required"
    assert payload["active_posting_count"] == 1


def test_portfolio_ready_requires_all_six_quality_gates(tmp_path: Path):
    review = _seed_review(tmp_path)
    profile = tmp_path / ".career_profile"
    profile.mkdir()
    (profile / "experience_ledger.json").write_text("{}", encoding="utf-8")
    run = tmp_path / "career_runs" / "verified"
    run.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps({"status": "complete", "quality_mode": "v2"}), encoding="utf-8"
    )
    (run / "04_공식근거.json").write_text('[{"verified": true}]', encoding="utf-8")
    (run / "04_리서치실행.json").write_text(
        json.dumps({"status": "verified", "searched_at": date.today().isoformat()}),
        encoding="utf-8",
    )
    final_files = {
        "answer_json": run / "draft_final.json",
        "markdown": run / "06_자기소개서.md",
        "docx": run / "06_자기소개서.docx",
    }
    for name, path in final_files.items():
        path.write_bytes(name.encode("utf-8"))
    (run / "12_최종산출물.json").write_text(
        json.dumps(
                {
                    "answer_json_path": "draft_final.json",
                "markdown_path": "06_자기소개서.md",
                "docx_path": "06_자기소개서.docx",
                    "sha256": {
                    name: sha256(path.read_bytes()).hexdigest()
                    for name, path in final_files.items()
                    },
                    "selection": {
                        "selection_mode": "rigorous",
                        "status": "passed",
                        "hard_fail": False,
                    },
                },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run / "08_면접대비팩.md").write_text("# 면접팩", encoding="utf-8")
    (run / "11_최종품질감사.json").write_text(
        json.dumps(
            {
                "internal_validation_score": 99,
                "quality_gate": "pass",
                "issues": [],
                "sections": {
                    "research": {"score": 25, "max": 25},
                    "interview": {"score": 20, "max": 20},
                },
            }
        ),
        encoding="utf-8",
    )
    (profile / "application_targets.json").write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "organization": "테스트기관",
                        "official_posting_url": "https://example.or.kr/posting",
                        "posting_status": "active",
                        "eligibility_status": "eligible",
                        "deadline": "2099-07-23T16:00:00+09:00",
                        "last_checked": date.today().isoformat(),
                        "selected_draft": "career_runs/verified/06_자기소개서.docx",
                        "v2_run_dir": "career_runs/verified",
                        "audit_passed": True,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    entry = build_portfolio(tmp_path)["applications"][0]
    assert entry["submission_status"] == "ready"
    assert entry["quality_readiness"]["passed_gate_count"] == 6
    assert entry["quality_readiness"]["blocker_codes"] == []
    assert (
        entry["quality_readiness"]["selected_artifact_quality"]["metric"]
        == "internal_validation_not_hire_probability"
    )

    final_files["docx"].write_bytes(b"tampered")
    tampered = build_portfolio(tmp_path)["applications"][0]
    assert tampered["submission_status"] == "review_required"
    assert "FINAL_ARTIFACT_VALIDATION_FAILED" in tampered["quality_readiness"]["blocker_codes"]


def test_portfolio_research_gate_requires_full_research_audit_section(tmp_path: Path):
    _seed_review(tmp_path)
    profile = tmp_path / ".career_profile"
    profile.mkdir()
    (profile / "experience_ledger.json").write_text("{}", encoding="utf-8")
    run = tmp_path / "career_runs" / "research-gap"
    run.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps({"status": "complete", "quality_mode": "v2"}),
        encoding="utf-8",
    )
    (run / "04_공식근거.json").write_text('[{"verified": true}]', encoding="utf-8")
    (run / "04_리서치실행.json").write_text(
        json.dumps({"status": "verified", "searched_at": date.today().isoformat()}),
        encoding="utf-8",
    )
    (run / "11_최종품질감사.json").write_text(
        json.dumps(
            {
                "internal_validation_score": 96,
                "quality_gate": "pass",
                "issues": [],
                "sections": {
                    "research": {"score": 21, "max": 25},
                    "interview": {"score": 20, "max": 20},
                },
            }
        ),
        encoding="utf-8",
    )
    target = {
        "v2_run_dir": "career_runs/research-gap",
        "official_posting_url": "https://example.or.kr/posting",
        "posting_status": "active",
        "last_checked": date.today().isoformat(),
        "deadline": "2099-07-23T16:00:00+09:00",
        "eligibility_status": "eligible",
    }

    quality = assess_application_quality(
        tmp_path,
        target,
        confirmed_profile=True,
        has_candidates=True,
    )

    assert quality["dimensions"]["research"] is False
    assert "OFFICIAL_RESEARCH_NOT_VERIFIED" in quality["blocker_codes"]


def test_portfolio_stale_posting_is_not_active(tmp_path: Path):
    _seed_review(tmp_path)
    profile = tmp_path / ".career_profile"
    profile.mkdir()
    (profile / "experience_ledger.json").write_text("{}", encoding="utf-8")
    (profile / "application_targets.json").write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "organization": "테스트기관",
                        "official_posting_url": "https://example.or.kr/posting",
                        "posting_status": "active",
                        "last_checked": "2020-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    entry = build_portfolio(tmp_path)["applications"][0]
    assert entry["is_active"] is False
    assert entry["submission_status"] == "not_ready"
    assert "POSTING_CHECK_STALE" in entry["quality_readiness"]["blocker_codes"]


def test_quality_gate_expires_at_exact_deadline_time(tmp_path: Path):
    target = {
        "official_posting_url": "https://example.or.kr/posting",
        "posting_status": "active",
        "last_checked": "2026-07-23",
        "deadline": "2026-07-23T16:00:00+00:00",
        "eligibility_status": "manual_review",
    }

    before = assess_application_quality(
        tmp_path,
        target,
        confirmed_profile=True,
        has_candidates=False,
        evaluation_date=datetime(2026, 7, 23, 15, 59, tzinfo=timezone.utc),
    )
    after = assess_application_quality(
        tmp_path,
        target,
        confirmed_profile=True,
        has_candidates=False,
        evaluation_date=datetime(2026, 7, 23, 16, 1, tzinfo=timezone.utc),
    )

    assert before["dimensions"]["posting"] is True
    assert after["dimensions"]["posting"] is False
    assert "POSTING_EXPIRED" in after["blocker_codes"]
