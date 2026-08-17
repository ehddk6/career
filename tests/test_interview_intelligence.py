import json
from pathlib import Path

import pytest

import career_pipeline.interview_intelligence as ii


def _write_run(tmp_path: Path) -> Path:
    run = tmp_path / "career_runs" / "sample"
    run.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps(
            {
                "root": str(tmp_path),
                "target": "테스트기관 행정직",
                "questions": [
                    {
                        "index": 1,
                        "prompt": "협업 과정에서 문제를 해결한 경험과 지원 직무에 어떻게 활용할지 설명하세요.",
                        "character_limit": 800,
                        "count_mode": "spaces_included",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger = {
        "schema_version": 1,
        "generated_at": "2026-08-17T00:00:00+00:00",
        "workspace_root": str(tmp_path),
        "experiences": [
            {
                "experience_id": "exp_alpha",
                "title": "고객 문의 분류 개선",
                "organization_alias": "기관A",
                "period": None,
                "role": "인턴",
                "situation": "반복 문의가 누적되어 응답이 지연되는 상황이었다.",
                "actions": ["문의 유형을 분류하고 담당자와 기준을 정리했다."],
                "outcomes": ["확인된 처리 건수는 20건이었다."],
                "competencies": ["문제해결", "협업"],
                "claims": [
                    {
                        "field": "metric:case_count",
                        "normalized_value": "20건",
                        "status": "confirmed",
                        "evidence": [
                            {
                                "source_path": "evidence.docx",
                                "paragraph_index": 0,
                                "source_sha256": "a" * 64,
                                "excerpt_sha256": "b" * 64,
                            }
                        ],
                        "claim_id": "clm_case20",
                    }
                ],
                "status": "confirmed",
                "confirmed_at": "2026-08-16T10:00:00+09:00",
            }
        ],
    }
    (run / "02_확정경험원장.json").write_text(
        json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
    )
    research = [
        {
            "claim_id": "res_job1",
            "claim": "테스트기관은 민원 접수 및 처리 지원 업무를 수행한다.",
            "source_url": "https://example.go.kr/job",
            "checked_at": "2026-08-17T09:00:00+09:00",
            "evidence_excerpt": "민원 접수 및 처리 지원",
            "source_type": "official_job_description",
            "published_at": "2026-08-01",
            "basis_date": "2026-08-01",
            "verification_status": "confirmed",
            "claim_type": "job_duty",
            "application_use": "문항1 직무 연결",
            "freshness_class": "stable",
            "source_tier": 1,
            "argument_role": "job_reality",
        }
    ]
    (run / "04_공식근거.json").write_text(
        json.dumps(research, ensure_ascii=False), encoding="utf-8"
    )
    draft = [
        {
            "question_index": 1,
            "answer": "반복 문의를 유형별로 정리하고 담당자와 기준을 맞춰 20건의 처리를 확인했습니다. 이 경험을 민원 처리 지원 업무에 활용하겠습니다.",
            "evidence_paths": ["evidence.docx"],
            "experience_refs": [
                {
                    "experience_id": "exp_alpha",
                    "claim_fields": ["metric:case_count"],
                    "claim_ids": ["clm_case20"],
                }
            ],
            "research_refs": ["res_job1"],
        }
    ]
    (run / "draft_final.json").write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8"
    )
    return run


def test_compile_builds_claim_defense_graph_and_structured_adaptive_bank(tmp_path: Path):
    run = _write_run(tmp_path)
    plan = ii.compile_interview_plan(run)

    assert plan["architecture"] == "structured_adaptive_claim_defense_v1"
    assert plan["authority"]["applicant_facts"].startswith("02_확정경험원장.json")
    assert plan["design_contract"]["hiring_probability_estimation"] is False
    assert len(plan["claim_graph"]["nodes"]) == 2
    families = {item["family"] for item in plan["question_bank"]}
    assert "core_intro" in families
    assert "core_past_behavior" in families
    assert "metric_probe" in families
    assert "ownership_probe" in families
    assert "causality_probe" in families
    assert "organization_probe" in families
    assert "situational_job_probe" in families
    assert plan["recommended_sequence"][:2] == ["core:intro:60", "core:q1"]


def test_compile_fails_closed_on_unconfirmed_or_unknown_claim_reference(tmp_path: Path):
    run = _write_run(tmp_path)
    draft_path = run / "draft_final.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft[0]["experience_refs"][0]["claim_ids"] = ["clm_missing"]
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ii.InterviewIntelligenceError, match="unknown or unconfirmed claim"):
        ii.compile_interview_plan(run)


def test_adaptive_selector_uses_fixed_backbone_then_weakness_and_risk(tmp_path: Path):
    run = _write_run(tmp_path)
    plan = ii.compile_interview_plan(run)
    assert ii.select_next_question(plan, {})["question_id"] == "core:intro:60"
    session = {
        "turns": [{"question_id": "core:intro:60"}, {"question_id": "core:q1"}],
        "weak_dimensions": ["ownership_precision", "causal_precision"],
    }
    next_question = ii.select_next_question(plan, session)
    assert next_question is not None
    assert next_question["standardized"] is False
    assert next_question["selection_reason"] == "expected_diagnostic_utility"
    assert {"ownership_precision", "causal_precision"}.intersection(next_question["dimensions"])


def test_evaluation_blocks_question_scoped_unsupported_metric(tmp_path: Path):
    run = _write_run(tmp_path)
    plan = ii.compile_interview_plan(run)
    metric_question = next(item for item in plan["question_bank"] if item["family"] == "metric_probe")
    evaluation = ii.evaluate_transcript(
        plan,
        [
            {
                "question_id": metric_question["question_id"],
                "answer": "제가 직접 개선해서 30건을 달성했습니다.",
                "elapsed_seconds": 20,
            }
        ],
    )
    deterministic = evaluation["turns"][0]["deterministic"]
    assert "unsupported_metric" in deterministic["flags"]
    assert "30건" in deterministic["unsupported_metrics"]
    assert "ownership_precision" in evaluation["summary"]["weak_dimensions"]


def test_semantic_judges_are_median_aggregated_and_capped_by_hard_fact_gate(tmp_path: Path):
    run = _write_run(tmp_path)
    plan = ii.compile_interview_plan(run)

    def runner(stage, prompt, model_id, timeout_ms):
        assert "Do not estimate hiring probability" in prompt
        question = json.loads(prompt)["context"]["question"]
        return {
            "scores": {dim: 4 for dim in question["dimensions"]},
            "evidence": {dim: "answer evidence" for dim in question["dimensions"]},
            "risks": [],
            "probe_focus": [],
        }

    evaluation = ii.evaluate_transcript(
        plan,
        [
            {
                "question_id": "core:q1",
                "answer": "제가 직접 30건을 달성했고 그 방법을 선택한 이유는 처리 속도 때문입니다.",
                "elapsed_seconds": 55,
            }
        ],
        judge_model_ids=("judge-a", "judge-b"),
        runner=runner,
    )
    scores = evaluation["turns"][0]["semantic"]["aggregate_scores"]
    assert scores["evidence_defensibility"] == 1.0
    assert scores["causal_precision"] == 1.0


def test_weakness_profile_persists_only_aggregates_not_raw_answers(tmp_path: Path):
    evaluation = {
        "summary": {
            "dimension_scores": {"ownership_precision": 1.5},
            "observed_dimensions": ["ownership_precision", "causal_precision"],
            "weak_dimension_hits": {"ownership_precision": 2, "causal_precision": 1},
            "deterministic_flags": {"ownership_overclaim_risk": 2},
        }
    }
    path = ii.update_weakness_profile(tmp_path, evaluation)
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["policy"]["stores_raw_answers"] is False
    assert payload["dimensions"]["ownership_precision"]["ema_score"] == 1.5
    assert payload["dimensions"]["ownership_precision"]["weak_signal_ema"] == 1.0
    assert payload["dimensions"]["causal_precision"]["weak_signal_ema"] == 0.5
    assert payload["flags"]["ownership_overclaim_risk"] == 2
    assert "turns" not in payload
    assert "raw_answers" not in payload
    assert "이 문장은 저장되면 안 됨" not in serialized


def test_official_research_metric_is_allowed_only_for_linked_research_claim(tmp_path: Path):
    run = _write_run(tmp_path)
    research_path = run / "04_공식근거.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    research[0]["claim"] = "테스트기관은 120건의 민원 처리 지원 실적을 공식적으로 공시했다."
    research_path.write_text(json.dumps(research, ensure_ascii=False), encoding="utf-8")
    plan = ii.compile_interview_plan(run)
    question = next(item for item in plan["question_bank"] if item["family"] == "organization_probe")
    ok = ii.evaluate_transcript(plan, [{"question_id": question["question_id"], "answer": "공식 근거상 120건이며, 그 의미는 민원 처리 지원의 운영 규모를 보여준다는 점입니다."}])
    assert "unsupported_metric" not in ok["turns"][0]["deterministic"]["flags"]
    bad = ii.evaluate_transcript(plan, [{"question_id": question["question_id"], "answer": "공식 실적은 999건입니다."}])
    assert "unsupported_metric" in bad["turns"][0]["deterministic"]["flags"]
