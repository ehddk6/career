import json
from pathlib import Path

from career_pipeline.narrative_realization_shadow import (
    build_narrative_kernel,
    generate_realization_plans,
)
from career_pipeline.nrs_shadow_benchmark import (
    blind_pair,
    build_private_report,
    generate_nrs_candidates,
    render_blind_packet,
    select_blind_candidate,
    write_private_artifacts,
)
from career_pipeline.self_introduction_genre import blocking_genre_issues
from career_pipeline.deep_writer import _schema

def _blueprint():
    return {
        "blueprint_id": "B1",
        "question_index": 1,
        "prompt": "문제를 해결한 경험을 작성하세요.",
        "intent": "problem_solving",
        "experience": {
            "selected_claims": [
                {"claim_id": "C1", "normalized_value": "문의 내용을 메모함"}
            ]
        },
        "research_claims": [],
    }

def _route():
    return {
        "route_id": "R1",
        "question_index": 1,
        "thesis": "반복 문의를 구조화했다.",
        "thesis_support_refs": ["claim:C1"],
        "proof_chain": [
            {"kind": "friction", "text": "반복 문의가 있었다.", "support_refs": ["claim:C1"]},
            {"kind": "judgment", "text": "질문 구조가 필요하다고 판단했다.", "support_refs": ["claim:C1"]},
            {"kind": "action", "text": "문의를 메모했다.", "support_refs": ["claim:C1"]},
        ],
        "evidence_gaps": [],
        "distinctive_anchor_refs": ["claim:C1"],
    }

def _validate(payload, blueprint, stage):
    required = {"blueprint_id", "question_index", "answer", "used_claim_ids", "used_research_ids"}
    assert required <= set(payload)
    assert payload["blueprint_id"] == blueprint["blueprint_id"]
    assert payload["question_index"] == blueprint["question_index"]
    return dict(payload)

def test_generate_candidates_uses_injected_validator_and_keeps_plans():
    blueprint = _blueprint()
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plans = generate_realization_plans(kernel, max_plans=3)

    def runner(stage, prompt, model, timeout):
        number = int(stage.rsplit("_", 1)[1])
        return {
            "blueprint_id": "B1",
            "question_index": 1,
            "answer": f"{number}번째 구조로 문의를 메모한 경험을 작성했습니다.",
            "used_claim_ids": ["C1"],
            "used_research_ids": [],
        }

    valid, failures = generate_nrs_candidates(
        blueprint=blueprint,
        packet={"target": "role"},
        route=route,
        kernel=kernel,
        plans=plans,
        runner=runner,
        model_id="test-model",
        timeout_ms=1000,
        validate_payload=_validate,
        anchor_texts=["문의 메모"],
    )
    assert not failures
    assert len(valid) == len(plans)
    assert len({row["plan_id"] for row in valid}) == len(plans)

def test_duplicate_answers_are_rejected():
    blueprint = _blueprint()
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plans = generate_realization_plans(kernel, max_plans=3)

    def runner(stage, prompt, model, timeout):
        return {
            "blueprint_id": "B1",
            "question_index": 1,
            "answer": "항상 같은 답변",
            "used_claim_ids": ["C1"],
            "used_research_ids": [],
        }

    valid, failures = generate_nrs_candidates(
        blueprint=blueprint, packet={}, route=route, kernel=kernel, plans=plans,
        runner=runner, model_id="x", timeout_ms=100, validate_payload=_validate,
    )
    assert len(valid) == 1
    assert any("duplicate_realisation" in row["codes"] for row in failures)


def test_genre_gate_retries_without_exposing_a_banned_word_list():
    blueprint = _blueprint()
    blueprint["character_plan"] = {"quality_minimum": 42, "hard_maximum": 60}
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plan = generate_realization_plans(kernel, max_plans=1)
    prompts = []

    def runner(stage, prompt, model, timeout):
        prompts.append(prompt)
        answer = (
            "문의 내용을 메모했습니다. 결과를 제 단독 성과로 확대해 말할 수는 없습니다."
            if stage.endswith("_1") else
            "문의 내용을 메모해 공통 질문을 정리했습니다."
        )
        return {
            "blueprint_id": "B1", "question_index": 1, "answer": answer,
            "used_claim_ids": ["C1"], "used_research_ids": [],
        }

    valid, failures = generate_nrs_candidates(
        blueprint=blueprint, packet={}, route=route, kernel=kernel, plans=plan,
        runner=runner, model_id="x", timeout_ms=100, validate_payload=_validate,
        genre_issues=blocking_genre_issues,
    )
    assert len(valid) == 1
    assert not failures
    assert "본인이 직접 한 행동은 분석·정리·제안처럼 근거에 있는 행동으로" in prompts[1]
    assert "운영상 변화는 이후 확인된 변화로 별도 문장에 표현하십시오" in prompts[1]
    assert "허용 사실 한 가지를 본문에 정확히 포함하십시오" in prompts[1]
    assert "selected_claims가 직접 허용하는 값만 남기고" in prompts[1]
    assert "확신할 수 없으면 기관명 없이 경험을 설명하십시오" in prompts[1]
    assert "공백 포함 42자 이상 60자 이하를 지키고" in prompts[1]
    assert "향상시켰습니다" not in prompts[1]


def test_selected_metric_must_survive_realization():
    blueprint = _blueprint()
    blueprint["experience"]["selected_claims"] = [
        {"claim_id": "C1", "normalized_value": "3,000페이지", "is_metric": True}
    ]
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plan = generate_realization_plans(kernel, max_plans=1)
    prompts = []

    def runner(stage, prompt, model, timeout):
        prompts.append(prompt)
        answer = (
            "자료를 분류해 문의 유형을 정리했습니다."
            if stage.endswith("_1")
            else "3,000페이지의 자료를 분류해 문의 유형을 정리했습니다."
        )
        return {
            "blueprint_id": "B1", "question_index": 1, "answer": answer,
            "used_claim_ids": ["C1"], "used_research_ids": [],
        }

    valid, failures = generate_nrs_candidates(
        blueprint=blueprint, packet={}, route=route, kernel=kernel, plans=plan,
        runner=runner, model_id="x", timeout_ms=100, validate_payload=_validate,
    )

    assert len(valid) == 1
    assert "3,000페이지" in valid[0]["payload"]["answer"]
    assert "is_metric=true 수치" in prompts[1]


def test_required_metric_bundle_requires_every_metric():
    blueprint = _blueprint()
    blueprint["experience"]["selected_claims"] = [
        {"claim_id": "duration", "normalized_value": "2일", "is_metric": True},
        {"claim_id": "scale", "normalized_value": "3,000페이지", "is_metric": True},
    ]
    blueprint["experience"]["required_metric_claim_ids"] = ["duration", "scale"]
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plan = generate_realization_plans(kernel, max_plans=1)

    def runner(stage, prompt, model, timeout):
        answer = (
            "2일 안에 자료를 분류했습니다."
            if stage.endswith("_1")
            else "3,000페이지의 자료를 2일 안에 분류했습니다."
        )
        return {
            "blueprint_id": "B1", "question_index": 1, "answer": answer,
            "used_claim_ids": ["duration", "scale"], "used_research_ids": [],
        }

    valid, failures = generate_nrs_candidates(
        blueprint=blueprint, packet={}, route=route, kernel=kernel, plans=plan,
        runner=runner, model_id="x", timeout_ms=100, validate_payload=_validate,
    )

    assert not failures
    assert valid[0]["payload"]["answer"] == "3,000페이지의 자료를 2일 안에 분류했습니다."

def test_blind_packet_never_exposes_arm_identity():
    row = blind_pair(
        question_index=1,
        baseline_answer="baseline text",
        nrs_answer="nrs text",
        salt="pilot",
    )
    rendered = render_blind_packet([row])
    assert "baseline text" in rendered
    assert "nrs text" in rendered
    assert "source_by_label" not in rendered
    assert "baseline/NRS identity is intentionally hidden" in rendered
    assert row["human_review"]["preferred"] is None

def test_private_report_marks_no_decision_effect():
    blueprint = _blueprint()
    route = _route()
    kernel = build_narrative_kernel(blueprint, route)
    plans = generate_realization_plans(kernel, max_plans=2)
    report = build_private_report(
        question_index=1,
        kernel=kernel,
        plans=plans,
        baseline_candidate_id="BASE",
        nrs_candidates=[],
    )
    assert report["private"] is True
    assert report["decision_effect"] == "none_shadow_mode"
    assert report["factual_authority_granted"] is False
    assert report["human_labels_performed"] is False

def test_private_writer_outputs_keep_human_fields_null(tmp_path: Path):
    row = blind_pair(
        question_index=1,
        baseline_answer="A",
        nrs_answer="B",
        salt="x",
    )
    detail, blind = write_private_artifacts(tmp_path, reports=[], blind_rows=[row])
    payload = json.loads(detail.read_text(encoding="utf-8"))
    assert payload["private"] is True
    assert payload["human_labels_performed"] is False
    assert payload["blind_pairs"][0]["human_review"]["preferred"] is None
    assert "source_by_label" not in blind.read_text(encoding="utf-8")


def test_blind_candidate_selection_uses_both_counterbalanced_presentations():
    candidates = [
        {"candidate_id": "C1", "payload": {"answer": "첫 번째 문안"}},
        {"candidate_id": "C2", "payload": {"answer": "두 번째 문안"}},
        {"candidate_id": "C3", "payload": {"answer": "세 번째 문안"}},
    ]

    def runner(stage, prompt, model, timeout):
        assert "후보의 순서, ID, 작성 경로에서 우열을 추정하지 않습니다" in prompt
        # The same content ranking must be accepted in either presentation.
        return {"ranking": [
            {"candidate_id": "C2", "rank": 1},
            {"candidate_id": "C3", "rank": 2},
            {"candidate_id": "C1", "rank": 3},
        ]}

    selected, record = select_blind_candidate(
        blueprint={"question_index": 1, "prompt": "지원 동기"},
        candidates=candidates,
        runner=runner,
        model_id="test",
        timeout_ms=1000,
    )
    assert selected["candidate_id"] == "C2"
    assert record["method"] == "counterbalanced_blind_rank_v1"
    assert len(record["rounds"]) == 2
    assert record["rounds"][0]["presented_candidate_ids"] == ["C1", "C2", "C3"]
    assert record["rounds"][1]["presented_candidate_ids"] == ["C3", "C2", "C1"]


def test_candidate_selection_stage_uses_ranking_output_schema():
    schema = _schema("nrs_shadow_candidate_select_q1_1")
    assert schema["required"] == ["ranking"]
    assert set(schema["properties"]["ranking"]["items"]["required"]) == {"candidate_id", "rank"}


def test_blind_packet_asks_for_question_fit_without_arm_identity():
    row = blind_pair(question_index=1, baseline_answer="A", nrs_answer="B", salt="v2")
    row["question"] = "문항 원문"
    packet = render_blind_packet([row])
    assert "| question_fit |" in packet
    assert "문항 원문" in packet
    assert "source_by_label" not in packet


def test_blind_packet_marks_question_fit_unavailable_without_prompt():
    row = blind_pair(question_index=1, baseline_answer="A", nrs_answer="B", salt="v2")

    packet = render_blind_packet([row])

    assert "문항 원문이 제공되지 않았습니다" in packet
    assert "source_by_label" not in packet
