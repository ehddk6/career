import json
import re
from pathlib import Path

import pytest

from career_pipeline.models import DraftResponse, Question
from career_pipeline.rigorous_selection import (
    JUDGES,
    WEIGHTS,
    RigorousSelectionError,
    _candidate_hard_fail,
    run_rigorous_selection,
)


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
        package = {"data_package_id": package_id, "data_package_version": "1.1"}
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
            return {**package, **_candidate("합성 답변입니다.")}
        return {
            **package,
            "choice": "X", "hard_fail": {"X": [], "Y": []},
            "reason": "baseline safer", "comparison_ready": True,
            "question_choices": {"q1": {"choice": "X", "reason": "safer"}},
            "risk_audit": {"X": {}, "Y": {}}, "remaining_risks": [],
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
    assert result.metadata["data_package"]["data_package_version"] == "1.1"
    assert result.metadata["candidate_count"] == 5
    assert (tmp_path / "rigorous" / "private_mapping.json").exists()
    assert len([stage for stage, _ in runner.calls if stage.startswith("judge_")]) == 3


@pytest.mark.parametrize("runner", [FakeRunner(bad_total=True), FakeRunner(omit_candidate=True)])
def test_rigorous_selection_fails_closed_on_invalid_judge_output(tmp_path: Path, runner):
    with pytest.raises(RigorousSelectionError):
        run_rigorous_selection(
            tmp_path, questions=[Question(1, "질문", 1000)],
            incumbent=(DraftResponse(1, "기존 답변입니다.", ()),),
            frozen_packet={}, model_id="gpt-5.6-sol",
            validate_candidate=lambda _: [], runner=runner, max_calls=9,
        )


def test_rigorous_selection_requires_sol_and_nine_call_budget(tmp_path: Path):
    base = dict(
        run_dir=tmp_path, questions=[Question(1, "질문", 1000)],
        incumbent=(DraftResponse(1, "기존 답변입니다.", ()),), frozen_packet={},
        validate_candidate=lambda _: [], runner=FakeRunner(),
    )
    with pytest.raises(RigorousSelectionError):
        run_rigorous_selection(**base, model_id="gpt-5.6-terra", max_calls=9)
    with pytest.raises(RigorousSelectionError):
        run_rigorous_selection(**base, model_id="gpt-5.6-sol", max_calls=8)


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
