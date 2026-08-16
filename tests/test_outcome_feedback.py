import json
from pathlib import Path

import pytest

from career_pipeline.__main__ import build_parser, main
from career_pipeline.outcome_feedback import (
    OutcomeFeedbackError,
    build_outcome_feedback_context,
    load_outcome_ledger,
    merge_outcome_feedback,
    record_outcome_case,
    validate_outcome_ledger,
)
from career_pipeline.question_requirements import build_question_requirement_map
from career_pipeline.question_requirements import validate_question_requirement_map
from career_pipeline.models import DraftResponse, ExperienceClaimRef, Question
from tests.test_v2_prepare import run_v2, setup_sources, write_profile


def _case(
    evidence_ref: str,
    *,
    case_id: str = "hf-2026-intern",
    organization: str = "한국주택금융공사",
    verification_status: str = "confirmed",
    feedback_source: str = "official",
    scope: str = "cross_target",
):
    return {
        "case_id": case_id,
        "organization": organization,
        "target_role": "체험형 인턴",
        "decision": "rejected",
        "verification_status": verification_status,
        "feedback_source": feedback_source,
        "scope": scope,
        "recorded_at": "2026-08-01T12:00:00+09:00",
        "evidence_refs": [evidence_ref],
        "signals": [
            {"dimension": "job_competency", "direction": "weakness"},
            {"dimension": "product_understanding", "direction": "strength"},
        ],
        "metrics": {
            "applicant_score": 76,
            "cutoff_score": 85.5,
            "rank": 35,
            "pool_size": 62,
        },
    }


def test_outcome_ledger_is_strict_and_does_not_accept_raw_application_text(tmp_path: Path):
    evidence = tmp_path / "feedback.md"
    evidence.write_text("verified feedback metadata", encoding="utf-8")
    valid = {"schema_version": 1, "cases": [_case("feedback.md")]}

    assert validate_outcome_ledger(valid, root=tmp_path)["cases"][0]["case_id"] == "hf-2026-intern"

    invalid = json.loads(json.dumps(valid))
    invalid["cases"][0]["raw_application_text"] = "지원서 원문"
    with pytest.raises(OutcomeFeedbackError, match="shape"):
        validate_outcome_ledger(invalid, root=tmp_path)

    escaped = json.loads(json.dumps(valid))
    escaped["cases"][0]["evidence_refs"] = ["../outside.md"]
    with pytest.raises(OutcomeFeedbackError, match="workspace-relative"):
        validate_outcome_ledger(escaped, root=tmp_path)


def test_confirmed_exact_feedback_becomes_a_requirement_but_cross_target_is_review_only(tmp_path: Path):
    evidence = tmp_path / "feedback.md"
    evidence.write_text("verified feedback metadata", encoding="utf-8")
    ledger = {"schema_version": 1, "cases": [_case("feedback.md")]}

    exact = build_outcome_feedback_context(ledger, target="한국주택금융공사 체험형 인턴")
    cross_target = build_outcome_feedback_context(ledger, target="다른 공공기관 사무")

    exact_job = next(item for item in exact["requirements"] if item["dimension"] == "job_competency")
    cross_job = next(item for item in cross_target["requirements"] if item["dimension"] == "job_competency")
    strength = next(item for item in exact["requirements"] if item["direction"] == "strength")
    assert exact_job["enforcement"] == "hard_requirement"
    assert cross_job["enforcement"] == "review_required"
    assert strength["enforcement"] == "preserve_strength"
    assert exact["metric_semantics"] == "historical outcomes, not hire probability"


def test_feedback_merges_into_only_applicable_question_contracts(tmp_path: Path):
    evidence = tmp_path / "feedback.md"
    evidence.write_text("verified feedback metadata", encoding="utf-8")
    ledger = {"schema_version": 1, "cases": [_case("feedback.md")]}
    context = build_outcome_feedback_context(ledger, target="한국주택금융공사")
    requirement_map = build_question_requirement_map(
        [
            Question(1, "지원동기를 작성해 주십시오.", 600),
            Question(2, "직무능력을 보여 준 경험을 작성해 주십시오.", 600),
        ],
        target="한국주택금융공사",
    )

    merged = merge_outcome_feedback(requirement_map, context)

    assert merged["historical_outcome_feedback"]["status"] == "applied"
    assert any(
        item["dimension"] == "product_understanding"
        for item in merged["questions"][0]["historical_feedback_requirements"]
    )
    assert any(
        item["dimension"] == "job_competency"
        for item in merged["questions"][1]["historical_feedback_requirements"]
    )
    assert merged["question_set_sha256"] != requirement_map["question_set_sha256"]


def test_confirmed_historical_hard_requirement_is_deterministically_enforced(tmp_path: Path):
    evidence = tmp_path / "feedback.md"
    evidence.write_text("verified feedback metadata", encoding="utf-8")
    context = build_outcome_feedback_context(
        {"schema_version": 1, "cases": [_case("feedback.md")]},
        target="한국주택금융공사",
    )
    requirement_map = merge_outcome_feedback(
        build_question_requirement_map(
            [Question(1, "직무능력을 보여 준 경험을 작성해 주십시오.", 600)],
            target="한국주택금융공사",
            posting={"duties": ["신청 자료 확인"], "competencies": ["정확성"]},
        ),
        context,
    )
    reference = ExperienceClaimRef("exp-1", claim_ids=("claim-1",))
    weak = DraftResponse(
        1,
        "저는 꼼꼼한 사람입니다. 맡은 일에 최선을 다했습니다.",
        (),
        (reference,),
    )
    strong = DraftResponse(
        1,
        "신청 자료를 직접 확인하고 기준표와 대조했습니다. 누락 건을 분류해 담당자에게 전달했고 처리를 마쳤습니다.",
        (),
        (reference,),
    )

    weak_codes = {
        item.code
        for item in validate_question_requirement_map(
            [weak], requirement_map, target="한국주택금융공사"
        )
    }
    strong_codes = {
        item.code
        for item in validate_question_requirement_map(
            [strong], requirement_map, target="한국주택금융공사"
        )
    }

    assert "historical_requirement_job_competency" in weak_codes
    assert "historical_requirement_job_competency" not in strong_codes


def test_direct_answer_requirement_applies_to_first_two_sentences():
    requirement_map = build_question_requirement_map(
        [Question(1, "지원동기를 작성해 주십시오.", 600)],
        target="테스트기관",
    )
    late_answer = DraftResponse(
        1,
        "기관은 중요한 역할을 합니다. 관련 사업도 잘 알고 있습니다. 이 경험 때문에 지원했습니다.",
        (),
    )

    codes = {
        item.code
        for item in validate_question_requirement_map(
            [late_answer], requirement_map, target="테스트기관"
        )
    }

    assert "missing_direct_answer" in codes


def test_record_and_cli_validate_use_workspace_relative_evidence(tmp_path: Path, capsys):
    evidence = tmp_path / "feedback.md"
    evidence.write_text("verified feedback metadata", encoding="utf-8")
    ledger_path = tmp_path / ".career_profile" / "application_outcomes.json"

    record_outcome_case(tmp_path, ledger_path, _case("feedback.md"))
    loaded = load_outcome_ledger(ledger_path, root=tmp_path)

    assert len(loaded["cases"]) == 1
    assert not ledger_path.with_name(ledger_path.name + ".lock").exists()
    assert main(
        [
            "outcome",
            "validate",
            "--root",
            str(tmp_path),
            "--ledger",
            ".career_profile/application_outcomes.json",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["confirmed_case_count"] == 1

    parser = build_parser()
    parsed = parser.parse_args(
        [
            "outcome",
            "summary",
            "--root",
            str(tmp_path),
            "--target",
            "한국주택금융공사",
        ]
    )
    assert parsed.outcome_command == "summary"


def test_v2_prepare_injects_validated_outcome_feedback_into_question_strategy(tmp_path: Path):
    career, posting, draft = setup_sources(tmp_path)
    profile = write_profile(tmp_path, career)
    evidence = tmp_path / "feedback.md"
    evidence.write_text("verified feedback metadata", encoding="utf-8")
    record_outcome_case(
        tmp_path,
        tmp_path / ".career_profile" / "application_outcomes.json",
        _case("feedback.md", organization="HUG", scope="target_only"),
    )

    state = run_v2(tmp_path, profile, posting, draft, "outcome-feedback")
    run_dir = Path(state["run_dir"])
    feedback = json.loads(
        (run_dir / "05_전형결과피드백.json").read_text(encoding="utf-8")
    )
    strategy = json.loads(
        (run_dir / "05_문항전략.json").read_text(encoding="utf-8")
    )

    assert state["status"] == "ready_for_research"
    assert feedback["status"] == "applied"
    assert feedback["hard_requirement_count"] == 1
    assert state["outcome_feedback"]["artifact"] == "05_전형결과피드백.json"
    assert strategy["historical_outcome_feedback"]["requirements"]
