import pytest
from career_pipeline.argument_search import (
    ArgumentSearchError, SEMANTIC_DIMENSIONS, aggregate_judgements,
    build_story_kernel, pareto_frontier, select_portfolio_routes,
    short_partial_duplicate_pairs, validate_route_packet,
)

def blueprint():
    return {
        "blueprint_id":"bp1","question_index":1,"intent":"problem_solving",
        "logic_contract":{"experience_mode":"required","research_mode":"none"},
        "experience":{
            "experience_id":"exp1","role":"담당",
            "situation":"입력 자료에 오류와 누락이 반복되었습니다.",
            "actions":["원자료와 입력값을 비교해 오류 유형을 나누고 먼저 수정할 대상을 판단했습니다."],
            "outcomes":["누락 항목을 수정했습니다."],
            "selected_claims":[{"claim_id":"c1","normalized_value":"오류를 찾아 수정함"}],
        },"research_claims":[],
    }

def route(rid="r1", posture="diagnosis"):
    return {
        "route_id":rid,"argument_posture":posture,
        "thesis":"오류를 바로 고치기보다 유형을 먼저 나눴습니다.",
        "thesis_support_refs":["experience:action:0"],
        "proof_chain":[
            {"kind":"friction","text":"오류 반복","support_refs":["experience:situation"]},
            {"kind":"judgment","text":"유형 우선","support_refs":["experience:action:0"]},
            {"kind":"action","text":"원자료 비교","support_refs":["experience:action:0"]},
            {"kind":"outcome","text":"누락 수정","support_refs":["experience:outcome:0"]},
        ],
        "closing_move":"같은 기준 재사용","evidence_gaps":[],
        "distinctive_anchor_refs":["experience:action:0"],
    }

def test_story_kernel_keeps_addressable_support():
    refs={x["ref"] for x in build_story_kernel(blueprint())["support"]}
    assert {"experience:situation","experience:action:0","claim:c1"} <= refs

def test_route_rejects_unsupported_ref():
    p={"blueprint_id":"bp1","question_index":1,"routes":[route("r1"),route("r2","scene")]}
    p["routes"][0]["proof_chain"][0]["support_refs"]=["experience:invented"]
    with pytest.raises(ArgumentSearchError):
        validate_route_packet(p, blueprint(), minimum_routes=2, maximum_routes=2)

def test_route_marks_missing_critical_judgment():
    rows=[route("r1"),route("r2","scene")]
    for r in rows:
        r["proof_chain"]=[x for x in r["proof_chain"] if x["kind"]!="judgment"]
    packet=validate_route_packet({"blueprint_id":"bp1","question_index":1,"routes":rows},blueprint(),minimum_routes=2,maximum_routes=2)
    assert all(x["critical_gap"] for x in packet["routes"])

def test_judge_median_and_pareto():
    rows=[route("r1"),route("r2","scene")]
    routes=validate_route_packet({"blueprint_id":"bp1","question_index":1,"routes":rows},blueprint(),minimum_routes=2,maximum_routes=2)["routes"]
    def j(rid,n): return {"route_id":rid,"scores":{d:n for d in SEMANTIC_DIMENSIONS},"fatal_issue":False}
    scored=aggregate_judgements(routes,[[j("r1",4),j("r2",2)],[j("r1",3),j("r2",3)],[j("r1",4),j("r2",2)]])
    assert scored[0]["route_id"]=="r1"
    assert [x["route_id"] for x in pareto_frontier(scored)]==["r1"]

def test_portfolio_jointly_penalizes_repeated_posture():
    dims={d:3.0 for d in SEMANTIC_DIMENSIONS}
    sets={
        1:[{"route_id":"a1","aggregate_score":90,"argument_posture":"same","experience_id":"","thesis":"오류 분류","proof_chain":[],"dimension_medians":dims},
           {"route_id":"a2","aggregate_score":84,"argument_posture":"other","experience_id":"","thesis":"원인 축소","proof_chain":[],"dimension_medians":dims}],
        2:[{"route_id":"b1","aggregate_score":90,"argument_posture":"same","experience_id":"","thesis":"오류 분류","proof_chain":[],"dimension_medians":dims},
           {"route_id":"b2","aggregate_score":88,"argument_posture":"different","experience_id":"","thesis":"상대 기준 확인","proof_chain":[],"dimension_medians":dims}],
    }
    result=select_portfolio_routes(sets)
    assert result["selected"][1]=="a1" and result["selected"][2]=="b2"

def test_qwen_exact_short_substring_case_is_caught_before_80_floor():
    copied="특히 A동작을 통해 B결과를 도출했습니다."
    long=("저는 데이터 분석 과정에서 원자료를 비교했습니다."*5)+copied
    pairs=short_partial_duplicate_pairs([(1,long),(2,copied)])
    assert pairs and pairs[0]["kind"]=="substring"
