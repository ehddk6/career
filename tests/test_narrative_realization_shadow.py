from career_pipeline.narrative_realization_shadow import (
    NarrativeRealizationError,
    answer_latency_contract,
    build_narrative_kernel,
    build_nrs_prompt,
    generate_realization_plans,
    realization_diagnostics,
)

def _blueprint(intent="problem_solving"):
    return {
        "blueprint_id": "B1",
        "question_index": 1,
        "prompt": "문제를 해결한 경험을 작성하세요.",
        "intent": intent,
        "logic_contract": {"experience_mode": "required", "research_mode": "forbidden"},
        "experience": {
            "experience_id": "E1",
            "selected_claims": [
                {"claim_id": "C1", "normalized_value": "반복 문의를 메모하고 공통 질문으로 분류함"},
                {"claim_id": "C2", "normalized_value": "안내 초안을 작성함"},
            ],
        },
        "research_claims": [],
    }

def _route():
    return {
        "route_id": "R1",
        "question_index": 1,
        "intent": "problem_solving",
        "thesis": "반복 문의를 구조화해 안내 초안으로 연결했다.",
        "thesis_support_refs": ["claim:C1", "claim:C2"],
        "proof_chain": [
            {"kind": "friction", "text": "반복 문의가 이어졌다.", "support_refs": ["claim:C1"]},
            {"kind": "judgment", "text": "공통 질문 구조가 필요하다고 판단했다.", "support_refs": ["claim:C1"]},
            {"kind": "action", "text": "문의를 메모하고 분류했다.", "support_refs": ["claim:C1"]},
            {"kind": "outcome", "text": "안내 초안을 작성했다.", "support_refs": ["claim:C2"]},
        ],
        "closing_move": "판단 기준을 직무 수행 방식으로 연결",
        "evidence_gaps": [],
        "distinctive_anchor_refs": ["claim:C2"],
    }

def test_kernel_preserves_route_proof_without_inventing_missing_kinds():
    kernel = build_narrative_kernel(_blueprint(), _route())
    assert [item.kind for item in kernel.proof_items] == [
        "friction", "judgment", "action", "outcome"
    ]
    assert all(item.kind != "criterion" for item in kernel.proof_items)
    assert kernel.distinctive_anchor_refs == ("claim:C2",)

def test_plans_are_structurally_distinct_by_opening_proof():
    kernel = build_narrative_kernel(_blueprint(), _route())
    plans = generate_realization_plans(kernel, max_plans=4)
    assert len(plans) >= 3
    first_indexes = [plan.ordered_proof_indexes[0] for plan in plans]
    assert len(first_indexes) == len(set(first_indexes))
    assert len({plan.move_sequence for plan in plans}) == len(plans)

def test_problem_solving_latency_is_not_global_two_sentence_rule():
    contract = answer_latency_contract("problem_solving")
    assert contract["max_sentence"] == 3
    assert "friction" in contract["required_signal"]

def test_prompt_contains_structural_plan_and_hard_authority_boundaries():
    blueprint = _blueprint()
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plan = generate_realization_plans(kernel)[0]
    prompt = build_nrs_prompt(blueprint, {"target": "role"}, route, kernel, plan)
    assert "move_sequence" in prompt
    assert "새로운 사실 권한을 만들지 않는다" in prompt
    assert "단독 인과" in prompt
    assert "used_claim_ids" in prompt

def test_unknown_proof_kind_fails_closed():
    route = _route()
    route["proof_chain"] = [
        {"kind": "invented_kind", "text": "x", "support_refs": ["claim:C1"]}
    ]
    try:
        build_narrative_kernel(_blueprint(), route)
    except NarrativeRealizationError as exc:
        assert "unsupported proof kind" in str(exc)
    else:
        raise AssertionError("expected fail-closed behavior")

def test_genericity_heuristic_improves_when_anchor_is_present():
    generic = realization_diagnostics(
        "업무를 원활하게 수행했습니다. 이를 통해 역량을 키웠습니다.",
        anchor_texts=["안내 초안"],
    )
    specific = realization_diagnostics(
        "병원용 안내 초안을 작성했습니다. 미확정 사항은 따로 표시했습니다.",
        anchor_texts=["안내 초안"],
    )
    assert specific["genericity_risk"] < generic["genericity_risk"]
    assert specific["distinctive_anchor_coverage"] > generic["distinctive_anchor_coverage"]

def test_no_supported_family_falls_back_to_route_order_control():
    route = _route()
    route["proof_chain"] = [
        {"kind": "action", "text": "기록했다.", "support_refs": ["claim:C1"]},
        {"kind": "outcome", "text": "초안을 만들었다.", "support_refs": ["claim:C2"]},
    ]
    route["distinctive_anchor_refs"] = []
    kernel = build_narrative_kernel(_blueprint(), route)
    plans = generate_realization_plans(kernel)
    assert [plan.family for plan in plans] == ["route_order_control"]
