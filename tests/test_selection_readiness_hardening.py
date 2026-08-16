import json
from pathlib import Path

from career_pipeline import application_quality
from career_pipeline.__main__ import main
from career_pipeline.models import DraftResponse, Question
from career_pipeline.rigorous_selection import WEIGHTS, run_rigorous_selection
from tests.test_rigorous_selection import FakeRunner


class LowReviewRunner(FakeRunner):
    def __call__(self, stage, prompt, model_id, timeout_ms):
        payload = super().__call__(stage, prompt, model_id, timeout_ms)
        if stage.startswith("judge_"):
            for row in payload["evaluations"]:
                row["scores"] = {key: 0 for key in WEIGHTS}
                row["total"] = 0
                row["hard_fail_status"] = "REVIEW_REQUIRED"
                row["review_required"] = ["직무 연결과 문항 직접성 재검토"]
                row["weakness_codes"] = ["question_gap", "job_gap"]
        return payload


def test_zero_score_and_unresolved_review_cannot_be_reported_as_rigorous_pass(tmp_path: Path):
    result = run_rigorous_selection(
        tmp_path,
        questions=[Question(1, "지원동기를 작성해 주십시오.", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="capability-model",
        validate_candidate=lambda _: [],
        runner=LowReviewRunner(),
        max_calls=9,
    )

    assert result.metadata["status"] == "review_required"
    assert result.metadata["review_required"] is True
    assert result.metadata["quality_floor"]["passed"] is False
    assert set(result.metadata["quality_floor"]["reason_codes"]) >= {
        "JUDGE_MEDIAN_TOTAL_BELOW_FLOOR",
        "JUDGE_MINIMUM_TOTAL_BELOW_FLOOR",
        "JUDGE_MEDIAN_CORE_BELOW_FLOOR",
        "SEMANTIC_REVIEW_UNRESOLVED",
    }


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _good_readiness_artifacts(run_dir: Path) -> None:
    _write_json(
        run_dir / "12_최종산출물.json",
        {
            "selection": {
                "selection_mode": "rigorous",
                "status": "passed",
                "hard_fail": False,
                "review_required": False,
                "quality_floor": {"passed": True},
            }
        },
    )
    _write_json(
        run_dir / "11_최종품질감사.json",
        {
            "quality_gate": "pass",
            "internal_validation_score": 99,
            "human_review_recommended": False,
            "issues": [],
            "question_scores": [
                {"question_index": 1, "score": {"total": 90}},
                {"question_index": 2, "score": {"total": 92}},
            ],
        },
    )
    _write_json(
        run_dir / "07_글자수검증.json",
        {
            "rows": [
                {
                    "question_index": 1,
                    "hard_limit_status": "PASS",
                    "target_status": "PASS",
                }
            ]
        },
    )


def test_submission_readiness_requires_selection_floor_question_floor_and_no_human_review(tmp_path: Path):
    _good_readiness_artifacts(tmp_path)
    assert application_quality._rigorous_selection_passed(tmp_path) is True
    assert application_quality._audit_passed(tmp_path) is True

    manifest = json.loads((tmp_path / "12_최종산출물.json").read_text(encoding="utf-8"))
    manifest["selection"]["quality_floor"]["passed"] = False
    _write_json(tmp_path / "12_최종산출물.json", manifest)
    assert application_quality._rigorous_selection_passed(tmp_path) is False

    _good_readiness_artifacts(tmp_path)
    audit = json.loads((tmp_path / "11_최종품질감사.json").read_text(encoding="utf-8"))
    audit["human_review_recommended"] = True
    _write_json(tmp_path / "11_최종품질감사.json", audit)
    assert application_quality._audit_passed(tmp_path) is False

    audit["human_review_recommended"] = False
    audit["question_scores"][0]["score"]["total"] = 84
    _write_json(tmp_path / "11_최종품질감사.json", audit)
    assert application_quality._audit_passed(tmp_path) is False

    _good_readiness_artifacts(tmp_path)
    length = json.loads((tmp_path / "07_글자수검증.json").read_text(encoding="utf-8"))
    length["rows"][0]["target_status"] = "REVIEW_REQUIRED"
    _write_json(tmp_path / "07_글자수검증.json", length)
    assert application_quality._audit_passed(tmp_path) is False


def test_audit_cli_uses_quality_gate_instead_of_score_only(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "career_pipeline.__main__.run_quality_audit",
        lambda _run: {
            "internal_validation_score": 99,
            "score": 99,
            "recommendation": "제출 전 검토",
            "quality_gate": "fail",
            "human_review_recommended": False,
        },
    )

    assert main(["audit", "--run", str(tmp_path)]) == 2
    assert "내부검증 99/100" in capsys.readouterr().out

    monkeypatch.setattr(
        "career_pipeline.__main__.run_quality_audit",
        lambda _run: {
            "internal_validation_score": 99,
            "score": 99,
            "recommendation": "사람 검토 필요",
            "quality_gate": "pass",
            "human_review_recommended": True,
        },
    )
    assert main(["audit", "--run", str(tmp_path)]) == 2
