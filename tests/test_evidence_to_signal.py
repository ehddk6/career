import json
from pathlib import Path
from types import SimpleNamespace

from career_pipeline.argument_search import SEMANTIC_DIMENSIONS
from career_pipeline.authority_contract import build_authority_context
from career_pipeline.assertion_compiler import compile_assertion_report
from career_pipeline.evidence_portfolio import build_evidence_portfolio
from career_pipeline.reliable_deep_writer import _preference_from_judgement
from career_pipeline.reliable_judge import (
    compare_candidates,
    resolve_comparison_graph,
    summarize_canonical_preferences,
)
from career_pipeline.research_contract import ensure_canonical_research_pack
from career_pipeline.system_benchmark import run_case


def _ledger():
    verification = SimpleNamespace(
        method="before_after",
        contribution="caused",
        scope="문의 처리",
        measurement_period="1개월",
    )
    claim = SimpleNamespace(
        status="confirmed",
        claim_id="c1",
        field="metric:time",
        normalized_value="20%",
        verification=verification,
    )
    experience = SimpleNamespace(
        status="confirmed",
        experience_id="e1",
        role="고객문의 담당",
        situation="반복 문의",
        actions=("유형별 분석",),
        outcomes=("처리 시간 20% 감소",),
        claims=(claim,),
    )
    return SimpleNamespace(experiences=(experience,))


def _response():
    ref = SimpleNamespace(experience_id="e1", claim_ids=("c1",), claim_fields=())
    return SimpleNamespace(
        question_index=1,
        answer="문의를 유형별로 분석해 처리 시간을 20% 줄였습니다.",
        experience_refs=(ref,),
        research_refs=("r1",),
    )


def _research():
    return SimpleNamespace(
        claim_id="r1",
        claim="공식 사업 규모는 5조원입니다.",
        evidence_excerpt="5조원",
        source_type="annual_report",
        verification_status="confirmed",
        claim_type="program_or_service",
        application_use="문항 1",
        source_url="https://example.go.kr",
    )


def _context():
    return build_authority_context(
        [_response()],
        _ledger(),
        [_research()],
        research_raw={"r1": {"source_tier": 1, "submission_authority": True}},
    )


def test_authority_contract_scopes_applicant_and_research_metrics():
    context = _context()
    assert context.metric_values(1) == {"20%", "5조원"}
    assert context.metric_values(2) == set()


def test_assertion_compiler_blocks_unsupported_metric():
    assert compile_assertion_report([_response()], _context())["summary"]["unsupported"] == 0
    bad = SimpleNamespace(
        **{**_response().__dict__, "answer": "문의 처리량을 999건 개선했습니다."}
    )
    assert compile_assertion_report([bad], _context())["summary"]["unsupported"] >= 1


def test_assertion_compiler_lexical_gap_is_review_not_hard_fail():
    vague = SimpleNamespace(
        **{**_response().__dict__, "answer": "새로운 방식으로 접근했습니다."}
    )
    summary = compile_assertion_report([vague], _context())["summary"]
    assert summary["unsupported"] == 0
    assert summary["needs_review"] >= 1


def test_causal_contribution_does_not_authorize_solo_ownership():
    bad = SimpleNamespace(
        **{
            **_response().__dict__,
            "answer": "제가 단독으로 문의 절차를 개선해 처리 시간을 20% 줄였습니다.",
        }
    )
    report = compile_assertion_report([bad], _context())
    assert report["summary"]["unsupported"] >= 1
    assert any(
        "ownership_overclaim_risk" in row["contradicts"]
        for row in report["assertions"]
    )


def test_reliable_judge_detects_position_bias_and_cycle():
    def runner(stage, prompt, model_id, timeout_ms):
        return {"preference": "A", "reason": "position-biased", "confidence": 0.8}

    result = compare_candidates(
        "alpha",
        "beta",
        rubric={"evidence": 1, "fit": 1},
        model_ids=["m1"],
        runner=runner,
    )
    assert result["status"] == "evaluation_uncertain"
    assert result["summary"]["position_flip_rate"] > 0
    graph = resolve_comparison_graph(
        [
            {"candidate_a": "A", "candidate_b": "B", "winner": "A"},
            {"candidate_a": "B", "candidate_b": "C", "winner": "B"},
            {"candidate_a": "C", "candidate_b": "A", "winner": "C"},
        ]
    )
    assert graph["status"] == "evaluation_uncertain"
    assert graph["cycles"]


def test_score_schema_reliable_selector_supports_tie_and_position_flip():
    high = {dimension: 4 for dimension in SEMANTIC_DIMENSIONS}
    low = {dimension: 2 for dimension in SEMANTIC_DIMENSIONS}
    tie = {dimension: 3 for dimension in SEMANTIC_DIMENSIONS}
    assert _preference_from_judgement(
        [
            {"route_id": "A", "scores": high, "fatal_issue": False},
            {"route_id": "B", "scores": low, "fatal_issue": False},
        ],
        "A",
        "B",
        {},
    ) == "A"
    assert _preference_from_judgement(
        [
            {"route_id": "A", "scores": tie, "fatal_issue": False},
            {"route_id": "B", "scores": tie, "fatal_issue": False},
        ],
        "A",
        "B",
        {},
    ) == "TIE"
    summary = summarize_canonical_preferences(
        [
            {
                "model_id": "m1",
                "rubric_variant": "evidence_first",
                "role": "structured_reviewer",
                "orientation": "AB",
                "canonical_preference": "A",
            },
            {
                "model_id": "m1",
                "rubric_variant": "evidence_first",
                "role": "structured_reviewer",
                "orientation": "BA",
                "canonical_preference": "B",
            },
        ]
    )
    assert summary["position_flip_rate"] == 1.0
    assert summary["stable"] is False


def test_system_benchmark_detects_unsafe_mutations():
    result = run_case(
        {"case_id": "x", "question_index": 1, "answer": _response().answer},
        _context(),
    )
    assert result["metrics"]["unsafe_detection_rate"] == 1.0
    assert result["metrics"]["benign_invariance_rate"] >= 0.5


def test_research_contract_adds_compat_sections_without_new_fact(tmp_path: Path):
    (tmp_path / "04_기업직무조사.md").write_text("# 기업·직무 조사팩\n", encoding="utf-8")
    (tmp_path / "04_공식근거.json").write_text(
        json.dumps(
            [
                {
                    "claim_id": "r1",
                    "claim": "공식 역할",
                    "source_url": "https://example.go.kr",
                    "source_type": "annual_report",
                    "source_tier": 1,
                    "verification_status": "confirmed",
                    "submission_authority": True,
                    "argument_role": "organization_differentiator",
                    "application_use": "문항 1",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "04_근거커버리지.json").write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_index": 1,
                        "slots": [
                            {
                                "required": True,
                                "status": "pass",
                                "accepted_claim_ids": ["r1"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "04_근거충돌.json").write_text(
        '{"unresolved_groups":[]}', encoding="utf-8"
    )
    ensure_canonical_research_pack(tmp_path)
    text = (tmp_path / "04_기업직무조사.md").read_text(encoding="utf-8")
    assert all(section in text for section in ("확인된 사실", "해석", "확인 필요", "문항·면접 활용 맵"))
    assert "r1" in text and "문항 1" in text


def test_evidence_portfolio_is_planning_only(tmp_path: Path):
    (tmp_path / "run.json").write_text(
        json.dumps({"questions": [{"index": 1, "prompt": "고객 대응과 분석 역량을 설명"}]}),
        encoding="utf-8",
    )
    (tmp_path / "00_채용공고분석.json").write_text(
        json.dumps(
            {"duties": ["고객 문의 분석"], "competencies": ["정확한 고객 대응"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "02_확정경험원장.json").write_text(
        json.dumps(
            {
                "experiences": [
                    {
                        "status": "confirmed",
                        "experience_id": "e1",
                        "title": "상담",
                        "role": "고객 대응",
                        "situation": "문의",
                        "actions": ["문의 분석"],
                        "outcomes": ["정확도 개선"],
                        "competencies": ["분석"],
                        "claims": [
                            {
                                "status": "confirmed",
                                "claim_id": "c1",
                                "field": "action",
                                "normalized_value": "문의 분석",
                                "verification": {
                                    "method": "direct_source",
                                    "contribution": "contributed",
                                },
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "04_공식근거.json").write_text("[]", encoding="utf-8")
    plan = build_evidence_portfolio(tmp_path)
    assert plan["factual_authority_granted"] is False
    assert plan["assignments"][0]["preferred_evidence"]
    assert plan["summary"]["weighted_signal_coverage"] > 0
