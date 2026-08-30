from career_pipeline.system_benchmark import ownership_escalation, run_benchmark, run_case


def _validator(_question_index, text, _context):
    unsafe = "987654건" in text or "제가 단독으로" in text
    return {"safe": not unsafe}


def test_system_benchmark_detects_unsafe_mutations_and_preserves_benign_variants():
    case = {"case_id": "q1", "question_index": 1, "answer": "팀이 검토를 완료했습니다. 결과를 공유했습니다."}

    result = run_case(case, None, validator=_validator)

    assert result["baseline_safe"] is True
    assert result["metrics"] == {"unsafe_detection_rate": 1.0, "benign_invariance_rate": 1.0}
    rows = {row["mutation"]: row for row in result["mutations"]}
    assert rows["unsupported_metric"]["safe"] is False
    assert rows["ownership_escalation"]["safe"] is False
    assert rows["whitespace"]["invariant_to_baseline"] is True
    assert rows["sentence_order"]["invariant_to_baseline"] is True


def test_system_benchmark_summarizes_multiple_cases_deterministically():
    cases = [
        {"case_id": "q1", "question_index": 1, "answer": "팀이 검토했습니다."},
        {"case_id": "q2", "question_index": 2, "answer": "팀이 안내했습니다."},
    ]

    report = run_benchmark(cases, {"q1": None, "q2": None}, validator=_validator)

    assert report["summary"] == {
        "case_count": 2,
        "mean_unsafe_detection_rate": 1.0,
        "mean_benign_invariance_rate": 1.0,
    }


def test_ownership_mutation_does_not_rewrite_a_future_team_benefit_as_past_ownership():
    text = "요청을 정리해 팀이 본 업무에 집중하도록 돕겠습니다."

    mutated = ownership_escalation(text)

    assert "제가 단독으로 본 업무에 집중하도록" not in mutated
    assert mutated.endswith("이 성과는 제가 단독으로 달성했습니다.")
