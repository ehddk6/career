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
    write_private_artifacts,
)

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
