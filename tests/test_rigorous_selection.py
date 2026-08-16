import json
import re
import subprocess
from pathlib import Path

import pytest

from career_pipeline.models import DraftResponse, Question, ValidationIssue
from career_pipeline.rigorous_selection import (
    JUDGES,
    WEIGHTS,
    RigorousSelectionError,
    _compact_judge_packet,
    _reset_rigorous_directory,
    _deduplicate_judge_evaluations,
    _coerce_payload,
    _validate_judge,
    _candidate_hard_fail,
    subprocess_model_runner,
    run_rigorous_selection,
)
from career_pipeline.quality_profiles import get_quality_profile


def _candidate(text: str):
    return {"responses": [{
        "question_index": 1, "answer": text, "evidence_paths": [],
        "experience_refs": [], "research_refs": [],
    }]}


class FakeRunner:
    def __init__(self, *, bad_total: bool = False, omit_candidate: bool = False, weaknesses=()):
        self.calls = []
        self.bad_total = bad_total
        self.omit_candidate = omit_candidate
        self.weaknesses = list(weaknesses)

    def __call__(self, stage, prompt, model_id, timeout_ms):
        self.calls.append((stage, prompt))
        package_id = re.search(r'"data_package_id"\s*:\s*"([^"]+)"', prompt).group(1)
        package = {"data_package_id": package_id, "data_package_version": "2.0"}
        if stage.startswith("candidate_"):
            return {**package, **_candidate(f"후보 {stage[-1]}의 답변입니다.")}
        if stage.startswith("judge_"):
            ids = sorted(set(re.findall(r'"(C[A-F0-9]{8})"\s*:', prompt)))
            if self.omit_candidate:
                ids = ids[:-1]
            mode = next(item for item in JUDGES if stage == f"judge_{item.lower()}")
            scores = dict(WEIGHTS)
            total = sum(scores.values()) - (1 if self.bad_total else 0)
            return {
                **package,
                "judge_mode": mode,
                "evaluations": [{
                    "candidate_id": candidate_id, "hard_fail": False,
                    "hard_fail_reasons": [], "hard_fail_status": "NONE",
                    "hard_fail_type": None, "review_required": [],
                    "scores": scores, "total": total,
                    "weakness_codes": self.weaknesses,
                    "transferable_elements": [],
                } for candidate_id in ids],
            }
        if stage == "synthesis":
            return {
                **package,
                **_candidate(
                    "현장에서 고객이 한참 머뭇거리는 모습을 보았습니다. "
                    "처음에는 안내문만 건네면 된다고 생각했지만, 직접 동작을 보여 드리자 표정이 풀렸습니다. "
                    "그때 설명은 전달보다 상대의 반응을 살피는 일임을 배웠습니다."
                ),
            }
        return {
            **package,
            "choice": "X", "hard_fail": {"X": [], "Y": []},
            "reason": "baseline safer", "comparison_ready": True,
            "question_choices": {
                "q1": {
                    "choice": "X",
                    "reason": "기존 답변의 사실 경계가 더 안정적입니다.",
                    "decisive_difference": "새로운 인과관계가 없습니다.",
                }
            },
            "risk_audit": {
                category: {"X": [], "Y": []}
                for category in (
                    "remaining_fact_risks",
                    "interview_defense_risks",
                    "spoken_answer_risks",
                    "company_specificity_regression",
                    "applicant_voice_regression",
                    "experience_duplication",
                    "style_regression",
                )
            },
            "remaining_risks": [],
        }


def test_rigorous_selection_hides_strategies_and_writes_hashes(tmp_path: Path):
    runner = FakeRunner()
    result = run_rigorous_selection(
        tmp_path, questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={"ledger": "frozen"}, model_id="gpt-5.6-sol",
        validate_candidate=lambda _: [], runner=runner, max_calls=9,
    )

    judge_prompts = "\n".join(prompt for stage, prompt in runner.calls if stage.startswith("judge_"))
    assert "FACT_FIRST" not in judge_prompts
    assert result.metadata["status"] == "passed"
    assert result.metadata["artifact_sha256"]
    assert result.metadata["data_package"]["data_package_version"] == "2.0"
    assert result.metadata["data_package"]["data_package_id"].startswith("CAREER-DATA-")
    assert result.metadata["candidate_count"] == 5
    assert (tmp_path / "rigorous" / "private_mapping.json").exists()
    assert len([stage for stage, _ in runner.calls if stage.startswith("judge_")]) == 3


def test_subprocess_model_timeout_becomes_resumable_selection_error(tmp_path: Path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr("career_pipeline.rigorous_selection.subprocess.run", timeout)

    with pytest.raises(RigorousSelectionError, match="timed out at candidate_2"):
        subprocess_model_runner("candidate_2", "prompt", "model", 1234)


def test_rigorous_reset_clears_stale_files_without_requiring_directory_deletion(
    tmp_path: Path, monkeypatch
):
    rigorous = tmp_path / "rigorous"
    candidates = rigorous / "candidates"
    candidates.mkdir(parents=True)
    stale = candidates / "stale.json"
    stale.write_text("{}", encoding="utf-8")
    original_rmdir = Path.rmdir

    def deny_candidate_rmdir(path):
        if path.name == "candidates":
            raise PermissionError("synced directory delete denied")
        return original_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", deny_candidate_rmdir)
    _reset_rigorous_directory(tmp_path, rigorous)

    assert not stale.exists()
    assert candidates.exists()


@pytest.mark.parametrize("runner", [FakeRunner(bad_total=True), FakeRunner(omit_candidate=True)])
def test_rigorous_selection_fails_closed_on_invalid_judge_output(tmp_path: Path, runner):
    with pytest.raises(RigorousSelectionError):
        run_rigorous_selection(
            tmp_path, questions=[Question(1, "질문", 1000)],
            incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
            frozen_packet={}, model_id="gpt-5.6-sol",
            validate_candidate=lambda _: [], runner=runner, max_calls=9,
        )


def test_rigorous_selection_is_model_name_agnostic_and_enforces_profile_budget(tmp_path: Path):
    base = dict(
        run_dir=tmp_path, questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),), frozen_packet={},
        validate_candidate=lambda _: [], runner=FakeRunner(),
    )
    result = run_rigorous_selection(**base, model_id="custom-quality-model", max_calls=9)
    assert result.metadata["model_id"] == "custom-quality-model"
    with pytest.raises(RigorousSelectionError):
        run_rigorous_selection(
            **base,
            model_id="custom-quality-model",
            max_calls=12,
            quality_profile=get_quality_profile("max_quality"),
        )


def test_synthesis_is_discarded_when_blind_comparison_prefers_winner(tmp_path: Path):
    runner = FakeRunner(weaknesses=("korean_style",))
    result = run_rigorous_selection(
        tmp_path, questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),), frozen_packet={},
        model_id="gpt-5.6-sol", validate_candidate=lambda _: [],
        runner=runner, max_calls=9,
    )
    assert result.responses[0].answer != "합성 답변입니다."
    assert result.metadata["call_count"] == 9


def test_semantic_hard_fail_requires_independent_confirmation():
    rows = [
        {
            "judge_mode": "RECRUITER",
            "hard_fail": True,
            "hard_fail_status": "CONFIRMED",
            "hard_fail_type": "SEMANTIC",
            "review_required": [],
        },
        {
            "judge_mode": "KOREAN_EDITOR",
            "hard_fail": False,
            "hard_fail_status": "NONE",
            "hard_fail_type": None,
            "review_required": [],
        },
    ]

    assert _candidate_hard_fail(rows) == (False, False)
    rows.append({
        "judge_mode": "JOB_FACT_AUDITOR",
        "hard_fail": True,
        "hard_fail_status": "CONFIRMED",
        "hard_fail_type": "SEMANTIC",
        "review_required": [],
    })
    assert _candidate_hard_fail(rows) == (True, False)


def test_deterministic_format_alias_is_normalized():
    candidate_id = "C12345678"
    payload = {
        "data_package_id": "CAREER-DATA-TEST",
        "data_package_version": "2.0",
        "judge_mode": "JOB_FACT_AUDITOR",
        "evaluations": [{
            "candidate_id": candidate_id,
            "hard_fail": True,
            "hard_fail_reasons": ["format"],
            "hard_fail_status": "CONFIRMED",
            "hard_fail_type": "DETERMINISTIC_FORMAT",
            "review_required": [],
            "scores": dict(WEIGHTS),
            "total": sum(WEIGHTS.values()),
            "weakness_codes": [],
            "transferable_elements": [],
        }],
    }
    rows = _validate_judge(
        payload,
        "JOB_FACT_AUDITOR",
        {candidate_id},
        {"data_package_id": "CAREER-DATA-TEST", "data_package_version": "2.0"},
    )
    assert rows[0]["hard_fail_type"] == "DETERMINISTIC"
    assert rows[0]["hard_fail"] is False
    assert rows[0]["hard_fail_status"] == "REVIEW_REQUIRED"


def test_deterministic_hard_fail_prefix_is_normalized():
    candidate_id = "C12345678"
    payload = {
        "data_package_id": "CAREER-DATA-TEST",
        "data_package_version": "2.0",
        "judge_mode": "RECRUITER",
        "evaluations": [{
            "candidate_id": candidate_id,
            "hard_fail": True,
            "hard_fail_reasons": ["문항 길이 초과"],
            "hard_fail_status": "CONFIRMED",
            "hard_fail_type": "DETERMINISTIC_LENGTH_LIMIT_EXCEEDED",
            "review_required": [],
            "scores": dict(WEIGHTS),
            "total": sum(WEIGHTS.values()),
            "weakness_codes": [],
            "transferable_elements": [],
        }],
    }

    rows = _validate_judge(
        payload,
        "RECRUITER",
        {candidate_id},
        {"data_package_id": "CAREER-DATA-TEST", "data_package_version": "2.0"},
    )
    assert rows[0]["hard_fail_type"] == "DETERMINISTIC"


def test_rigorous_rerun_removes_stale_json_artifacts(tmp_path: Path):
    stale = tmp_path / "rigorous" / "candidate_failures.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("[]", encoding="utf-8")

    run_rigorous_selection(
        tmp_path,
        questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="gpt-5.6-sol",
        validate_candidate=lambda _: [],
        runner=FakeRunner(),
        max_calls=9,
    )

    assert not stale.exists()


def test_blocked_selection_can_resume_validated_candidates_and_judges(tmp_path: Path):
    base = dict(
        run_dir=tmp_path,
        questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="gpt-5.6-sol",
        validate_candidate=lambda _: [],
        max_calls=9,
    )
    run_rigorous_selection(**base, runner=FakeRunner())

    class ResumeRunner(FakeRunner):
        def __call__(self, stage, prompt, model_id, timeout_ms):
            if stage.startswith("candidate_") or stage.startswith("judge_"):
                raise AssertionError(f"checkpoint stage was called again: {stage}")
            return super().__call__(stage, prompt, model_id, timeout_ms)

    runner = ResumeRunner()
    result = run_rigorous_selection(
        **base,
        runner=runner,
        resume_from_checkpoint=True,
    )

    assert all(
        not stage.startswith(("candidate_", "judge_")) for stage, _ in runner.calls
    )
    assert set(result.metadata["resumed_stages"]) >= {
        "generated_1",
        "generated_2",
        "generated_3",
        "generated_4",
        "judge_recruiter",
        "judge_job_fact_auditor",
        "judge_korean_editor",
    }


def test_invalid_incumbent_is_excluded_before_blind_judging(tmp_path: Path):
    def validate(candidate):
        if candidate[0].answer == "기존 답변입니다.":
            return [ValidationIssue("over_limit", 1, "상한 초과")]
        return []

    result = run_rigorous_selection(
        tmp_path,
        questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="gpt-5.6-sol",
        validate_candidate=validate,
        runner=FakeRunner(),
        max_calls=9,
    )

    assert result.metadata["candidate_count"] == 4
    failures = json.loads(
        (tmp_path / "rigorous" / "candidate_failures.json").read_text(encoding="utf-8")
    )
    assert failures[0]["stage"] == "incumbent"


def test_judge_packet_keeps_only_candidate_reachable_evidence():
    frozen = {
        "target": "테스트기관",
        "posting": {"duties": ["자료 심사"]},
        "question_requirement_map": {"questions": []},
        "research_claims": [
            {"claim_id": "r-used", "claim": "사용 근거"},
            {"claim_id": "r-unused", "claim": "미사용 근거"},
        ],
        "experience_ledger": {
            "schema_version": 2,
            "experiences": [
                {
                    "experience_id": "exp-used",
                    "claims": [
                        {"claim_id": "c-used"},
                        {"claim_id": "c-unused"},
                    ],
                },
                {"experience_id": "exp-unused", "claims": []},
            ],
        },
        "prompt_contracts": {
            "contract_version": "v",
            "data_package_id": "p",
            "data_package_version": "2.0",
            "company_research": {
                "safe_claims": [{"claim_id": "r-used"}],
                "prohibited_claim_ids": ["r-blocked"],
            },
            "interview_defense": {
                "defensible_experience_ids": ["exp-used", "exp-unused"],
                "experience_defense": [
                    {"experience_id": "exp-used"},
                    {"experience_id": "exp-unused"},
                ],
                "questions": ["large unused section"],
                "probes": ["large unused section"],
            },
        },
    }
    blind = {
        "C12345678": [
            {
                "question_index": 1,
                "research_refs": ["r-used"],
                "experience_refs": [
                    {"experience_id": "exp-used", "claim_ids": ["c-used"]}
                ],
            }
        ]
    }

    compact = _compact_judge_packet(frozen, blind)

    assert [row["claim_id"] for row in compact["research_claims"]] == ["r-used"]
    assert [row["experience_id"] for row in compact["experience_ledger"]["experiences"]] == ["exp-used"]
    assert compact["experience_ledger"]["experiences"][0]["claims"] == [
        {"claim_id": "c-used"}
    ]
    defense = compact["prompt_contracts"]["interview_defense"]
    assert defense["defensible_experience_ids"] == ["exp-used"]
    assert "questions" not in defense
    assert "probes" not in defense


def test_judge_duplicate_with_same_decision_is_merged_but_conflict_fails():
    base = {
        "candidate_id": "C12345678",
        "hard_fail": False,
        "hard_fail_reasons": [],
        "hard_fail_status": "NONE",
        "hard_fail_type": None,
        "review_required": ["첫 검토"],
        "scores": dict(WEIGHTS),
        "total": sum(WEIGHTS.values()),
        "weakness_codes": [],
        "transferable_elements": [],
    }
    duplicate = {**base, "review_required": ["추가 검토"]}

    rows = _deduplicate_judge_evaluations([base, duplicate], "RECRUITER")

    assert len(rows) == 1
    assert rows[0]["review_required"] == ["첫 검토", "추가 검토"]
    with pytest.raises(RigorousSelectionError, match="conflicting duplicate"):
        _deduplicate_judge_evaluations(
            [base, {**duplicate, "total": 99}], "RECRUITER"
        )


def test_final_comparison_question_choice_array_is_normalized():
    payload = {
        "question_choices": [{
            "question_index": 3,
            "choice": "Y",
            "reason": "직접성이 높습니다.",
            "decisive_difference": "직무 연결이 구체적입니다.",
        }]
    }
    normalized = _coerce_payload(payload, "final_comparison")
    assert normalized["question_choices"]["q3"]["choice"] == "Y"
    assert "question_index" not in normalized["question_choices"]["q3"]


def test_final_comparison_supports_non_four_question_posting(tmp_path: Path):
    class ThreeQuestionRunner(FakeRunner):
        def __call__(self, stage, prompt, model_id, timeout_ms):
            payload = super().__call__(stage, prompt, model_id, timeout_ms)
            if stage.startswith("candidate_") or stage == "synthesis":
                package = {
                    key: payload[key]
                    for key in ("data_package_id", "data_package_version")
                }
                payload = {
                    **package,
                    "responses": [
                        {
                            "question_index": index,
                            "answer": f"문항 {index} 답변입니다.",
                            "evidence_paths": [],
                            "experience_refs": [],
                            "research_refs": [],
                        }
                        for index in (1, 2, 3)
                    ],
                }
            if stage == "final_comparison":
                payload["question_choices"] = {
                    f"q{index}": {
                        "choice": "X",
                        "reason": f"문항 {index}의 사실 경계를 유지합니다.",
                        "decisive_difference": "새 사실 추가 여부",
                    }
                    for index in (1, 2, 3)
                }
            return payload

    questions = [Question(index, f"질문 {index}", 1000) for index in (1, 2, 3)]
    incumbent = tuple(
        DraftResponse(index, f"기존 문항 {index} 답변입니다.", ())
        for index in (1, 2, 3)
    )
    result = run_rigorous_selection(
        tmp_path,
        questions=questions,
        incumbent=incumbent,
        frozen_packet={},
        model_id="gpt-5.6-sol",
        validate_candidate=lambda _: [],
        runner=ThreeQuestionRunner(),
        max_calls=9,
    )
    assert len(result.responses) == 3


def test_max_quality_adds_natural_voice_and_interview_defense_candidates(tmp_path: Path):
    runner = FakeRunner()
    result = run_rigorous_selection(
        tmp_path,
        questions=[Question(1, "지원동기를 작성해 주십시오.", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="capability-based-model",
        validate_candidate=lambda _: [],
        runner=runner,
        max_calls=40,
        quality_profile=get_quality_profile("max_quality"),
    )

    candidate_prompts = "\n".join(
        prompt for stage, prompt in runner.calls if stage.startswith("candidate_")
    )
    assert "NATURAL_VOICE" in candidate_prompts
    assert "INTERVIEW_DEFENSE" in candidate_prompts
    assert result.metadata["quality_profile"] == "max_quality"
    assert result.metadata["candidate_count"] == 7
    assert result.metadata["judge_count"] == 4


def test_max_quality_applies_project_editor_contract_to_every_quality_stage(tmp_path: Path):
    runner = FakeRunner()
    run_rigorous_selection(
        tmp_path,
        questions=[Question(1, "지원동기를 작성해 주십시오.", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="capability-based-model",
        validate_candidate=lambda _: [],
        runner=runner,
        max_calls=40,
        quality_profile=get_quality_profile("max_quality"),
    )

    required_stages = [
        prompt
        for stage, prompt in runner.calls
        if stage.startswith("candidate_")
        or stage.startswith("judge_")
        or stage == "synthesis"
        or stage == "final_comparison"
    ]
    assert required_stages
    assert all("PROJECT_WRITING_EDITOR_CONTRACT" in prompt for prompt in required_stages)
    assert all("저자의 목소리 보존" in prompt for prompt in required_stages)
    assert WEIGHTS["korean_readability"] + WEIGHTS["applicant_distinctiveness"] == 25


def test_max_quality_repairs_deterministic_final_style_risks(tmp_path: Path):
    class StyleRepairRunner(FakeRunner):
        def __call__(self, stage, prompt, model_id, timeout_ms):
            if stage == "synthesis":
                self.calls.append((stage, prompt))
                package_id = re.search(
                    r'"data_package_id"\s*:\s*"([^"]+)"', prompt
                ).group(1)
                return {
                    "data_package_id": package_id,
                    "data_package_version": "2.0",
                    **_candidate(
                        "자료를 확인하겠습니다. 기준을 확인하겠습니다. "
                        "결과를 확인하겠습니다. 다시 확인하겠습니다. "
                        "끝까지 확인하겠습니다."
                    ),
                }
            if stage.startswith("synthesis_repair_"):
                self.calls.append((stage, prompt))
                package_id = re.search(
                    r'"data_package_id"\s*:\s*"([^"]+)"', prompt
                ).group(1)
                return {
                    "data_package_id": package_id,
                    "data_package_version": "2.0",
                    **_candidate(
                        "현장에서 고객이 한참 머뭇거리는 모습을 보았습니다. "
                        "처음에는 안내문만 건네면 된다고 생각했지만, 직접 동작을 보여 드리자 표정이 풀렸습니다. "
                        "그때 설명은 전달보다 상대의 반응을 살피는 일임을 배웠습니다."
                    ),
                }
            return super().__call__(stage, prompt, model_id, timeout_ms)

    runner = StyleRepairRunner()
    run_rigorous_selection(
        tmp_path,
        questions=[Question(1, "지원동기를 작성해 주십시오.", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
        frozen_packet={},
        model_id="capability-based-model",
        validate_candidate=lambda _: [],
        runner=runner,
        max_calls=40,
        quality_profile=get_quality_profile("max_quality"),
    )

    assert any(stage.startswith("synthesis_repair_") for stage, _ in runner.calls)


def test_unconfirmed_judge_role_in_hard_fail_type_is_treated_as_review_metadata():
    package = {"data_package_id": "CAREER-DATA-test", "data_package_version": "2.0"}
    scores = {key: value for key, value in WEIGHTS.items()}
    payload = {
        **package,
        "judge_mode": "KOREAN_EDITOR",
        "evaluations": [
            {
                "candidate_id": "A",
                "hard_fail": False,
                "hard_fail_reasons": [],
                "hard_fail_status": "REVIEW_REQUIRED",
                "hard_fail_type": "KOREAN_EDITOR",
                "review_required": ["사람다운 문체 보완"],
                "scores": scores,
                "total": sum(scores.values()),
                "weakness_codes": ["korean_style"],
                "transferable_elements": [],
            }
        ],
    }

    rows = _validate_judge(payload, "KOREAN_EDITOR", {"A"}, package)

    assert rows[0]["hard_fail_type"] is None
    assert rows[0]["review_required"] == ["사람다운 문체 보완"]
