"""BehaviorAtom typed IR extraction rules (deterministic, fail-closed)."""
from __future__ import annotations

from career_pipeline.behavior_ir import build_behavior_atoms


def _ledger(claims: list[dict], actions: list[str] = ()) -> dict:
    return {
        "experiences": [
            {
                "experience_id": "exp-1",
                "status": "confirmed",
                "title": "행정지원",
                "role": "담당",
                "situation": "신청서류 처리",
                "actions": list(actions),
                "outcomes": [],
                "competencies": [],
                "claims": claims,
            }
        ]
    }


def _claim(
    value: str,
    cid: str = "clm-1",
    status: str = "confirmed",
    evidence: bool = True,
    field: str = "action",
) -> dict:
    claim = {
        "claim_id": cid,
        "field": field,
        "normalized_value": value,
        "status": status,
        "verification": {"method": "direct_source", "contribution": "caused"},
    }
    if evidence:
        claim["evidence"] = [
            {
                "source_path": "exp1/evidence.txt",
                "paragraph_index": 0,
                "source_sha256": "0" * 64,
                "excerpt_sha256": "0" * 64,
            }
        ]
    return claim


def _atoms(payload: dict) -> list[dict]:
    return payload["atoms"]


def _actions(payload: dict) -> list[str]:
    return [atom["action"] for atom in payload["atoms"]]


def test_confirmed_claim_produces_atoms():
    payload = build_behavior_atoms(
        _ledger([_claim("원문과 입력값을 대조해 누락을 확인했습니다.")])
    )
    assert _actions(payload) == ["대조", "확인"]
    assert all(atom["authority_status"] == "factual" for atom in _atoms(payload))


def test_unconfirmed_claim_never_produces_atoms():
    payload = build_behavior_atoms(
        _ledger([_claim("원문과 입력값을 대조했습니다.", status="draft")])
    )
    assert _atoms(payload) == []
    assert "unconfirmed_claim" in {row["code"] for row in payload["rejected"]}


def test_metric_claim_never_produces_atoms():
    payload = build_behavior_atoms(
        _ledger([_claim("처리 시간이 20% 감소했습니다.", field="metric:performance")])
    )
    assert _atoms(payload) == []
    assert "metric_claim_no_behavior" in {row["code"] for row in payload["rejected"]}


def test_context_only_action_rejected_without_claim_backing():
    payload = build_behavior_atoms(
        _ledger(
            [_claim("자료를 정리했습니다.", evidence=False, field="experience_summary")],
            actions=["원문과 입력값을 대조해 누락을 구분했습니다"],
        )
    )
    assert "대조" not in _actions(payload)
    assert "context_only_action_no_claim" in {row["code"] for row in payload["rejected"]}


def test_source_bound_action_when_corroborated_in_actions():
    payload = build_behavior_atoms(
        _ledger(
            [_claim("원문과 입력값을 대조해 누락을 확인했습니다.")],
            actions=["원문과 입력값을 대조해 누락을 구분했습니다"],
        )
    )
    assert all(
        atom["action"] != "대조" or atom["projection_kind"] == "source_bound_action"
        for atom in _atoms(payload)
    )


def test_korean_inflection_normalization_is_invariant():
    left = _actions(
        build_behavior_atoms(_ledger([_claim("원문과 대조해 누락을 확인했습니다.")]))
    )
    right = _actions(
        build_behavior_atoms(_ledger([_claim("원문과 대조하여 누락을 확인했습니다.")]))
    )
    assert left == ["대조", "확인"]
    assert right == left


def test_wrong_actor_never_applicant_direct_material():
    payload = build_behavior_atoms(
        _ledger([_claim("팀이 원문과 입력값을 대조해 누락을 확인했습니다.")])
    )
    assert all(atom["actor"] == "team" for atom in _atoms(payload))


def test_verb_without_inflection_tail_needs_boundary():
    payload = build_behavior_atoms(
        _ledger([_claim("관리자와 상담을 진행했습니다.")])
    )
    assert "관리" not in _actions(payload)


def test_atom_ids_and_signatures_are_stable():
    fixture = _ledger([_claim("원문과 입력값을 대조해 누락을 확인했습니다.")])
    first = build_behavior_atoms(fixture)
    second = build_behavior_atoms(fixture)
    assert [atom["atom_id"] for atom in first["atoms"]] == [
        atom["atom_id"] for atom in second["atoms"]
    ]
