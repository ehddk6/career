from __future__ import annotations

from pathlib import Path

import pytest

from career_pipeline.quality_benchmark import (
    BENCHMARK_SECTIONS,
    benchmark_template,
    evaluate_benchmark,
    run_blind_benchmark,
    write_benchmark_template,
)


def completed_payload(choice: str = "B"):
    payload = benchmark_template(
        data_package_id="CAREER-DATA-TEST",
        baseline_label="external-six",
        challenger_label="career-pipeline",
    )
    for section in BENCHMARK_SECTIONS:
        for item in payload["sections"][section].values():
            item.update(
                choice=choice,
                reason="익명 산출물의 구체적인 근거를 비교했습니다.",
                decisive_difference="검증 가능한 사실과 직접 행동의 연결",
                evidence_refs=["artifact:q1"],
            )
    return payload


def test_all_dimensions_ahead_requires_every_dimension_to_win():
    payload = completed_payload()
    result = evaluate_benchmark(payload)
    assert result.verdict == "ALL_DIMENSIONS_AHEAD"
    assert result.challenger_wins == sum(map(len, BENCHMARK_SECTIONS.values()))

    payload["sections"]["self_intro"]["natural_korean"]["choice"] = "A"
    mixed = evaluate_benchmark(payload)
    assert mixed.verdict != "ALL_DIMENSIONS_AHEAD"


def test_challenger_hard_fail_is_excluded_before_quality_comparison():
    payload = completed_payload()
    payload["hard_fail"]["B"] = ["contribution_overstatement"]
    assert evaluate_benchmark(payload).verdict == "HARD_FAIL"


def test_pending_or_non_blind_benchmark_cannot_be_claimed():
    pending = benchmark_template(
        data_package_id="CAREER-DATA-TEST",
        baseline_label="external-six",
        challenger_label="career-pipeline",
    )
    with pytest.raises(ValueError, match="pending"):
        evaluate_benchmark(pending)
    pending["blind_protocol"]["system_labels_hidden"] = False
    with pytest.raises(ValueError, match="blind protocol"):
        evaluate_benchmark(pending)


def test_benchmark_template_does_not_overwrite(tmp_path: Path):
    output = tmp_path / "benchmark.json"
    write_benchmark_template(
        output,
        data_package_id="CAREER-DATA-TEST",
        baseline_label="external-six",
        challenger_label="career-pipeline",
    )
    with pytest.raises(FileExistsError):
        write_benchmark_template(
            output,
            data_package_id="CAREER-DATA-TEST",
            baseline_label="external-six",
            challenger_label="career-pipeline",
        )


def test_blind_benchmark_randomizes_sides_and_maps_challenger_back_to_b(
    tmp_path: Path, monkeypatch
):
    baseline = tmp_path / "external_named.json"
    challenger = tmp_path / "pipeline_named.json"
    baseline.write_text('{"answer":"일반론"}', encoding="utf-8")
    challenger.write_text('{"answer":"근거 연결"}', encoding="utf-8")
    captured = {}

    def fake_judge(prompt, *, model_id, timeout_ms):
        captured["prompt"] = prompt
        data = __import__("json").loads(prompt.split("\n", 1)[1])
        challenger_side = next(
            side
            for side, rows in data["artifacts"].items()
            if rows[0]["artifact_id"].startswith("C")
        )
        return {
            "hard_fail": {"X": [], "Y": []},
            "sections": {
                section: {
                    dimension: {
                        "choice": challenger_side,
                        "reason": "근거와 결과의 연결이 더 구체적입니다.",
                        "decisive_difference": "검증 가능한 근거 ID",
                        "evidence_refs": [f"{challenger_side}1:answer"],
                    }
                    for dimension in dimensions
                }
                for section, dimensions in BENCHMARK_SECTIONS.items()
            },
        }

    monkeypatch.setattr(
        "career_pipeline.quality_benchmark.subprocess_benchmark_judge", fake_judge
    )
    output = tmp_path / "result.json"
    result = run_blind_benchmark(
        output,
        data_package_id="CAREER-DATA-TEST",
        baseline_label="external-six",
        challenger_label="career-pipeline",
        baseline_files=[baseline],
        challenger_files=[challenger],
        model_id="judge-model",
    )

    assert result.verdict == "ALL_DIMENSIONS_AHEAD"
    assert str(baseline) not in captured["prompt"]
    assert str(challenger) not in captured["prompt"]
    assert "must not earn an advantage" in captured["prompt"]
    assert output.is_file()
