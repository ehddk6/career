import re
from pathlib import Path

import career_pipeline.deep_writer as dw
from career_pipeline.argument_search import SEMANTIC_DIMENSIONS


def _blueprint():
    return {
        "blueprint_id": "bp1",
        "question_index": 1,
        "prompt": "문제를 해결한 경험과 그 과정에서의 판단을 작성해 주세요",
        "intent": "problem_solving",
        "logic_contract": {"experience_mode": "required", "research_mode": "none"},
        "character_plan": {"maximum": 500, "count_mode": "spaces_included"},
        "experience": {
            "experience_id": "exp1",
            "role": "담당",
            "situation": "입력 자료에 오류와 누락이 반복되어 마감이 지연될 위험이 있었습니다.",
            "actions": [
                "원자료와 입력값을 비교해 오류 유형을 나누고 영향이 큰 항목부터 수정하기로 판단했습니다."
            ],
            "outcomes": ["누락 항목을 수정하고 제출 전 오류를 정리했습니다."],
            "selected_claims": [],
        },
        "research_claims": [],
        "beats": [],
        "portfolio_constraints": {},
        "risk_controls": [],
    }


def _packet():
    return {
        "packet_id": "pkt1",
        "target": "테스트기관",
        "portfolio": {},
        "questions": [_blueprint()],
    }


def _routes():
    common = [
        {"kind": "friction", "text": "반복 오류와 마감 위험을 문제로 좁힌다.", "support_refs": ["experience:situation"]},
        {"kind": "judgment", "text": "영향이 큰 오류부터 고치는 기준을 선택한다.", "support_refs": ["experience:action:0"]},
        {"kind": "action", "text": "원자료와 입력값을 비교해 오류 유형을 나눈다.", "support_refs": ["experience:action:0"]},
        {"kind": "outcome", "text": "누락 항목을 수정하고 제출 전 오류를 정리한다.", "support_refs": ["experience:outcome:0"]},
    ]
    return [
        {
            "route_id": "r1",
            "argument_posture": "risk_first",
            "thesis": "오류 자체보다 마감에 영향을 주는 오류를 먼저 좁혀 해결한 경험이다.",
            "thesis_support_refs": ["experience:situation", "experience:action:0"],
            "proof_chain": common,
            "closing_move": "직무에서도 영향 기준으로 우선순위를 세운다.",
            "evidence_gaps": [],
            "distinctive_anchor_refs": ["experience:action:0"],
        },
        {
            "route_id": "r2",
            "argument_posture": "diagnosis_first",
            "thesis": "증상보다 오류 유형을 분리해 원인을 좁히는 방식으로 문제를 풀었다.",
            "thesis_support_refs": ["experience:action:0"],
            "proof_chain": common,
            "closing_move": "문제를 유형화한 뒤 해결 순서를 정하는 방식을 적용한다.",
            "evidence_gaps": [],
            "distinctive_anchor_refs": ["experience:situation", "experience:action:0"],
        },
        {
            "route_id": "r3",
            "argument_posture": "decision_first",
            "thesis": "모든 오류를 동시에 고치기보다 영향이 큰 항목부터 처리하는 판단이 핵심이었다.",
            "thesis_support_refs": ["experience:action:0"],
            "proof_chain": common,
            "closing_move": "제한된 시간에는 영향과 검증 가능성을 기준으로 결정한다.",
            "evidence_gaps": [],
            "distinctive_anchor_refs": ["experience:action:0"],
        },
    ]


def _ids(prompt):
    result = []
    for value in re.findall(r'"route_id"\s*:\s*"([^"]+)"', prompt):
        if value not in result:
            result.append(value)
    return result


def _judge_payload(route_ids):
    rows = []
    for route_id in route_ids:
        rows.append(
            {
                "route_id": route_id,
                "scores": {dimension: 3 for dimension in SEMANTIC_DIMENSIONS},
                "fatal_issue": False,
            }
        )
    return {"routes": rows}


def _runner_factory(structural_issue=False):
    critic_calls = {"count": 0}

    def runner(stage, prompt, model_id, timeout_ms):
        if stage.startswith("deep_route_plan"):
            return {
                "blueprint_id": "bp1",
                "question_index": 1,
                "routes": _routes(),
            }
        if stage.startswith("deep_route_judge"):
            return _judge_payload(_ids(prompt))
        if stage.startswith("deep_prose_generate"):
            suffix = " 판단 기준을 먼저 세웠습니다." if stage.endswith("_1") else " 문제를 유형별로 좁혔습니다."
            return {
                "blueprint_id": "bp1",
                "question_index": 1,
                "answer": (
                    "반복되는 오류를 모두 같은 순서로 처리하지 않았습니다. "
                    "원자료와 입력값을 비교해 오류 유형을 나누고 영향이 큰 항목부터 수정했습니다."
                    + suffix
                ),
                "used_claim_ids": [],
                "used_research_ids": [],
            }
        if stage.startswith("deep_prose_judge"):
            candidate_ids = [value for value in _ids(prompt) if value.startswith("P")]
            return _judge_payload(candidate_ids)
        if stage.startswith("deep_portfolio_critic"):
            critic_calls["count"] += 1
            if structural_issue and critic_calls["count"] == 1:
                return {
                    "issues": [
                        {
                            "question_index": 1,
                            "code": "weak_thesis",
                            "severity": "MATERIAL",
                            "message": "판단의 핵심이 약하다.",
                            "repair_instruction": "다른 논증 경로를 선택한다.",
                        }
                    ]
                }
            return {"issues": []}
        raise AssertionError(stage)

    return runner


def test_deep_writer_searches_argument_routes_before_prose(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setattr(dw, "_state", lambda _: {"target": "테스트기관", "root": str(tmp_path)})
    responses, report = dw.generate_deep_draft(
        run,
        packet=_packet(),
        writer_model_id="writer",
        judge_model_ids=("judge-a", "judge-b"),
        route_count=3,
        prose_realisations=2,
        runner=_runner_factory(),
    )
    assert len(responses) == 1
    assert report["architecture"] == "evidence_to_argument_search_v1"
    assert report["judge_independence"] == "heterogeneous_model_ids"
    assert report["semantic_validation"]["status"] == "passed"
    assert report["deterministic_validation"]["status"] == "passed"
    roles = {call["role"] for call in report["calls"]}
    assert "argument_route_planner" in roles
    assert "blind_prose_judge" in roles
    route_judges = [call for call in report["calls"] if call["stage"].startswith("deep_route_judge")]
    assert len(route_judges) == 12


def test_structural_critic_triggers_route_substitution_not_surface_rewrite(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setattr(dw, "_state", lambda _: {"target": "테스트기관", "root": str(tmp_path)})
    responses, report = dw.generate_deep_draft(
        run,
        packet=_packet(),
        writer_model_id="writer",
        judge_model_ids=("judge",),
        route_count=3,
        prose_realisations=1,
        runner=_runner_factory(structural_issue=True),
    )
    assert responses
    assert report["route_substitutions"], "weak_thesis should try a different argument route"
    assert report["route_substitutions"][0]["from_route_id"] != report["route_substitutions"][0]["to_route_id"]
    assert report["semantic_validation"]["status"] == "passed"
    assert not any(call["stage"].startswith("deep_surface_repair") for call in report["calls"])
