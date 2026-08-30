from pathlib import Path

import career_pipeline.nrs_paired_reconstruction as paired_reconstruction

from career_pipeline.fluent_korean_shadow import (
    apply_fluent_korean_shadow_prompt,
    fluent_korean_realization_constraints,
)
from career_pipeline.nrs_paired_reconstruction import (
    _benchmark_protocol,
    _generate_shared_route,
    _source_complete_fallback_route,
    _required_research_reference_instruction,
    _route_bound_reference_ids,
    _shadow_actor_attribution_codes,
    _validate_route_bound_payload,
    _writer_contract,
    _writer_contract_hash,
    evaluate_v2_production_opt_in,
)
from career_pipeline.nrs_paired_reconstruction import _preflight
from career_pipeline.models import ValidationIssue


def test_shadow_guard_blocks_unsupported_supervisor_confirmation(tmp_path: Path):
    (tmp_path / "02_확정경험원장.json").write_text(
        '{"actions":["세 조건을 본인이 다시 확인했다."]}', encoding="utf-8"
    )
    assert _shadow_actor_attribution_codes(
        tmp_path, "담당 직원의 사전 확인 후 안내했습니다."
    ) == ["shadow_unsupported_actor_attribution"]


def test_shadow_guard_allows_supported_supervisor_confirmation(tmp_path: Path):
    (tmp_path / "02_확정경험원장.json").write_text(
        '{"actions":["담당 직원의 사전 확인 후 안내했다."]}', encoding="utf-8"
    )
    assert not _shadow_actor_attribution_codes(
        tmp_path, "담당 직원의 사전 확인 후 안내했습니다."
    )


def test_fluent_korean_constraints_apply_to_both_prose_arms_only():
    source = "원래 프롬프트"
    constraints = fluent_korean_realization_constraints()
    assert "영어식 소제목" in constraints
    assert "조사와 어미를 생략하지" in constraints
    assert apply_fluent_korean_shadow_prompt("deep_prose_generate_q1_1", source).endswith(constraints)
    assert apply_fluent_korean_shadow_prompt("nrs_shadow_generate_q1_1", source).endswith(constraints)
    assert apply_fluent_korean_shadow_prompt("deep_route_plan_q1", source) == source


def test_fluent_korean_constraints_are_not_duplicated_on_retry():
    once = apply_fluent_korean_shadow_prompt("nrs_shadow_generate_q1_1", "원래 프롬프트")
    assert apply_fluent_korean_shadow_prompt("nrs_shadow_generate_q1_1", once) == once


def test_twelve_question_preflight_uses_explicit_benchmark_size():
    rows = [{
        "question_resolvable": True,
        "route_id": "R",
        "blueprint_id": "B",
        "proof_chain": ["proof"],
        "claim_evidence_resolvable": True,
        "research_evidence_resolvable": True,
        "same_writer_config": True,
        "validator_available": True,
    }] * 12
    result = _preflight(rows, {"writer_backend": "test"}, expected_question_count=12)
    assert result["passed"] is True
    assert result["checks"]["question_count_matches_expected"] is True


def test_research_required_control_prompt_assigns_reference_binding_to_program():
    blueprint = {
        "logic_contract": {"research_mode": "required"},
        "research_claims": [{"claim_id": "R-1"}, {"claim_id": "R-2"}],
    }
    instruction = _required_research_reference_instruction(blueprint)
    assert "program, not the model" in instruction
    assert "R-1" not in instruction


def test_research_reference_instruction_is_empty_when_research_is_not_required():
    assert _required_research_reference_instruction(
        {"logic_contract": {"research_mode": "forbidden"}}
    ) == ""


def _route_bound_fixture():
    blueprint = {
        "blueprint_id": "BP-1",
        "question_index": 1,
        "logic_contract": {"experience_mode": "required", "research_mode": "required"},
        "experience": {"selected_claims": [{"claim_id": "C-1"}]},
        "research_claims": [{"claim_id": "R-1"}],
    }
    route = {
        "thesis_support_refs": ["claim:C-1"],
        "proof_chain": [
            {"support_refs": ["research:R-1", "claim:C-1"]},
        ],
    }
    raw = {
        "blueprint_id": "BP-1",
        "question_index": 1,
        "answer": "근거에 맞춰 답변을 작성했습니다.",
        "used_claim_ids": [],
        "used_research_ids": ["invented-id"],
    }
    return blueprint, route, raw


def test_route_bound_validator_ignores_model_declared_ids_and_attaches_route_ids():
    blueprint, route, raw = _route_bound_fixture()
    payload = _validate_route_bound_payload(raw, blueprint, "test", route)
    assert payload["used_claim_ids"] == ["C-1"]
    assert payload["used_research_ids"] == ["R-1"]


def test_route_bound_validator_attaches_visible_selected_metric_claims():
    blueprint = {
        "blueprint_id": "BP-METRIC",
        "question_index": 1,
        "logic_contract": {"experience_mode": "required", "research_mode": "none"},
        "experience": {
            "selected_claims": [
                {"claim_id": "C-1", "normalized_value": "검토 기준을 정리했습니다."},
                {"claim_id": "C-2", "normalized_value": "3주에서 2주"},
            ],
        },
        "research_claims": [],
    }
    route = {
        "thesis_support_refs": ["claim:C-1"],
        "proof_chain": [{"support_refs": ["claim:C-1"]}],
    }
    raw = {
        "blueprint_id": "BP-METRIC",
        "question_index": 1,
        "answer": "팀 전체 업무 기간은 3주에서 2주로 단축되었습니다.",
        "used_claim_ids": ["invented-id"],
        "used_research_ids": [],
    }

    payload = _validate_route_bound_payload(raw, blueprint, "test", route)

    assert payload["used_claim_ids"] == ["C-1", "C-2"]
    assert payload["used_research_ids"] == []


def test_route_bound_validator_drops_unrendered_optional_research():
    blueprint = {
        "blueprint_id": "BP-OPTIONAL-RESEARCH",
        "question_index": 1,
        "logic_contract": {"experience_mode": "required", "research_mode": "preferred"},
        "experience": {"selected_claims": [{"claim_id": "C-1"}]},
        "research_claims": [{
            "claim_id": "R-1",
            "claim": "한국남동발전은 실행형 인재를 명확한 목표를 향해 행동하는 인재로 설명한다.",
        }],
    }
    route = {
        "thesis_support_refs": ["claim:C-1", "research:R-1"],
        "proof_chain": [{"support_refs": ["claim:C-1", "research:R-1"]}],
    }
    raw = {
        "blueprint_id": "BP-OPTIONAL-RESEARCH",
        "question_index": 1,
        "answer": "자료를 검토하는 기준을 세워 적용했습니다.",
        "used_claim_ids": ["C-1"],
        "used_research_ids": ["R-1"],
    }

    payload = _validate_route_bound_payload(raw, blueprint, "test", route)

    assert payload["used_claim_ids"] == ["C-1"]
    assert payload["used_research_ids"] == []


def test_route_bound_references_reject_unapproved_ids():
    blueprint, route, _ = _route_bound_fixture()
    route["proof_chain"][0]["support_refs"] = ["research:unknown"]
    try:
        _route_bound_reference_ids(blueprint, route)
    except ValueError as error:
        assert "not approved" in str(error)
    else:
        raise AssertionError("unapproved route reference must fail")


def test_route_bound_references_resolve_approved_experience_field_to_claims():
    blueprint, route, _ = _route_bound_fixture()
    route["thesis_support_refs"] = ["experience:action:0"]
    route["proof_chain"][0]["support_refs"] = ["experience:outcome:0", "research:R-1"]
    claim_ids, research_ids = _route_bound_reference_ids(blueprint, route)
    assert claim_ids == ["C-1"]
    assert research_ids == ["R-1"]


def test_v2_protocol_has_equal_candidate_and_retry_budgets():
    protocol = _benchmark_protocol(
        experiment_id="v2", selections=[("run", 1)], expected_question_count=1,
        control_generation_mode="same_prompt_route_order_candidates",
        protocol_version=2, evaluation_role="regression_only",
    )
    assert protocol["arms"]["fresh_control"]["candidate_count"] == 3
    assert protocol["arms"]["nrs"]["candidate_count"] == 3
    assert protocol["arms"]["fresh_control"]["retry_budget_per_candidate"] == 2
    assert "audit_meta_leakage" in protocol["shared_exclusion_gates"]
    assert protocol["evaluation_role"] == "regression_only"


def test_v2_writer_contract_hash_is_calculated_from_common_config():
    backend = {"writer_backend": "test-backend", "resolved_model": None, "reasoning_effort": "medium"}
    control = _writer_contract(backend)
    nrs = _writer_contract(backend)
    assert control == nrs
    assert _writer_contract_hash(control) == _writer_contract_hash(nrs)
    assert control["candidate_count"] == 3
    assert control["reasoning_effort"] == "medium"
    assert len(control["common_prompt_hash"]) == 64


def test_source_complete_fallback_route_keeps_both_arms_on_authorized_evidence():
    blueprint = {
        "blueprint_id": "BP-FALLBACK",
        "question_index": 4,
        "intent": "motivation",
        "logic_contract": {"experience_mode": "required", "research_mode": "required"},
        "experience": {
            "selected_claims": [{"claim_id": "C-1", "normalized_value": "Verified experience fact."}],
            "actions": ["Compared eligibility and settlement conditions."],
        },
        "research_claims": [{"claim_id": "R-1", "claim": "Verified organization fact."}],
    }

    route = _source_complete_fallback_route(blueprint)

    assert route["route_id"] == "fallback-source-complete-4"
    assert route["critical_gap"] is False
    assert [step["kind"] for step in route["proof_chain"]] == [
        "criterion", "organization_fact", "action", "fit_bridge",
    ]
    references = {
        ref
        for step in route["proof_chain"]
        for ref in step["support_refs"]
    }
    assert references <= {"claim:C-1", "experience:action:0", "research:R-1"}


def test_source_complete_fallback_route_supports_experience_only_adaptation():
    blueprint = {
        "blueprint_id": "BP-FALLBACK-ADAPT",
        "question_index": 2,
        "intent": "adaptation",
        "logic_contract": {"experience_mode": "preferred", "research_mode": "none"},
        "experience": {
            "selected_claims": [{"claim_id": "C-1", "normalized_value": "Verified experience fact."}],
            "actions": ["Reorganized the attendance process."],
        },
        "research_claims": [],
    }

    route = _source_complete_fallback_route(blueprint)

    assert route["route_id"] == "fallback-source-complete-2"
    assert route["critical_gap"] is False
    assert [step["kind"] for step in route["proof_chain"]] == [
        "context", "judgment", "action", "outcome",
    ]
    references = {
        ref
        for step in route["proof_chain"]
        for ref in step["support_refs"]
    }
    assert references <= {"claim:C-1", "experience:action:0"}


def test_source_complete_fallback_route_omits_unverified_preferred_experience():
    blueprint = {
        "blueprint_id": "BP-FALLBACK-RESEARCH-ONLY",
        "question_index": 3,
        "intent": "job_plan",
        "logic_contract": {"experience_mode": "preferred", "research_mode": "required"},
        "experience": {
            "selected_claims": [],
            "actions": ["Raw 3,000-page experience excerpt without an approved claim."],
        },
        "research_claims": [{"claim_id": "R-1", "claim": "Verified job duty."}],
    }

    route = _source_complete_fallback_route(blueprint)

    assert route["route_id"] == "fallback-source-complete-3"
    references = {
        ref
        for step in route["proof_chain"]
        for ref in step["support_refs"]
    }
    assert references == {"research:R-1"}
    assert "experience:action:0" not in route["thesis_support_refs"]


def test_source_complete_fallback_route_supports_research_only_issue_analysis():
    blueprint = {
        "blueprint_id": "BP-FALLBACK-RESEARCH-ONLY-ISSUE",
        "question_index": 4,
        "intent": "issue_analysis",
        "logic_contract": {"experience_mode": "none", "research_mode": "required"},
        "experience": None,
        "research_claims": [{"claim_id": "R-1", "claim": "Verified issue evidence."}],
    }

    route = _source_complete_fallback_route(blueprint)

    assert route["route_id"] == "fallback-source-complete-4"
    assert route["thesis_support_refs"] == ["research:R-1"]
    assert {
        ref for step in route["proof_chain"] for ref in step["support_refs"]
    } == {"research:R-1"}


def test_optional_experience_gate_keeps_research_validation_but_drops_legacy_requirement(tmp_path: Path):
    class Response:
        answer = "직무 수행계획입니다."
        research_refs = ("R-1",)

    original = paired_reconstruction._candidate_issues
    (tmp_path / "02_확정경험원장.json").write_text("{}", encoding="utf-8")
    paired_reconstruction._candidate_issues = lambda *_args: [
        ValidationIssue("missing_evidence", 1, "legacy"),
        ValidationIssue("missing_experience_ref", 1, "legacy"),
        ValidationIssue("other_organization", 1, "keep"),
    ]
    try:
        issues = paired_reconstruction._shadow_candidate_issues(
            tmp_path, {}, Response(), allow_research_only=True
        )
    finally:
        paired_reconstruction._candidate_issues = original

    assert [issue.code for issue in issues] == ["other_organization"]


def test_shared_route_uses_source_complete_fallback_for_invalid_planner_support():
    blueprint = {
        "blueprint_id": "BP-INVALID-PLANNER", "question_index": 1, "intent": "motivation",
        "logic_contract": {"experience_mode": "required", "research_mode": "required"},
        "experience": {
            "selected_claims": [{"claim_id": "C-1", "normalized_value": "Verified experience fact."}],
            "actions": ["Compared supporting documents."],
        },
        "research_claims": [{"claim_id": "R-1", "claim": "Verified organization fact."}],
    }

    def runner(*_args):
        return {
            "blueprint_id": "BP-INVALID-PLANNER", "question_index": 1,
            "routes": [{
                "route_id": "unsupported-plan", "thesis": "지원 후 수행할 행동을 설명합니다.",
                "thesis_support_refs": ["claim:C-1"],
                "proof_chain": [
                    {"kind": "criterion", "text": "기준", "support_refs": ["claim:C-1"]},
                    {"kind": "organization_fact", "text": "기관", "support_refs": ["research:R-1"]},
                    {"kind": "action", "text": "근거 없는 미래 행동", "support_refs": []},
                    {"kind": "fit_bridge", "text": "연결", "support_refs": ["research:R-1"]},
                ],
                "closing_move": "마무리", "evidence_gaps": [], "distinctive_anchor_refs": ["claim:C-1"],
            }],
        }

    route = _generate_shared_route(blueprint=blueprint, packet={}, runner=runner, timeout_ms=100)

    assert route["route_id"] == "fallback-source-complete-1"
    assert route["critical_gap"] is False


def test_default_backend_runner_recovers_transient_transport_failure(monkeypatch):
    calls = []

    def flaky_runner(stage, prompt, model_id, timeout_ms):
        calls.append((stage, prompt, model_id, timeout_ms))
        if len(calls) == 1:
            raise RuntimeError("temporary CLI session failure")
        return {"ok": True}

    monkeypatch.setattr(paired_reconstruction, "subprocess_model_runner", flaky_runner)
    monkeypatch.setattr(paired_reconstruction.time, "sleep", lambda _: None)
    assert paired_reconstruction.default_backend_runner(
        "nrs_shadow_generate_control_q1_1", "본문", "__codex_default_backend__", 1000
    ) == {"ok": True}
    assert len(calls) == 2


def test_v2_production_opt_in_reports_eligibility_but_never_changes_default():
    rows = [
        {
            "question_id": f"q{index}", "selected_material_factual_issue_count": 0,
            "audit_meta_leakage_count": 0,
        }
        for index in range(1, 10)
    ]
    key = [
        {"question_id": f"q{index}", "A_source": "NRS", "B_source": "BASELINE"}
        for index in range(1, 10)
    ]
    reviews = {
        f"q{index}": {
            "preferred": "A", "more_natural_korean": "A",
            "question_fit": "A", "more_interview_speakable": "A",
        }
        for index in range(1, 10)
    }
    result = evaluate_v2_production_opt_in(rows=rows, answer_key=key, reviews=reviews)
    assert result["status"] == "eligible_for_user_approval"
    assert result["production_default_changed"] is False
