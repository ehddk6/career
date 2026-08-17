"""Standardized interview backbone and adaptive probe selection."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .schema import (
    DIMENSIONS, WEAKNESS_PROFILE, _compact, _intent, _read_json,
)

def _question(
    question_id: str,
    *,
    application_index: int | None,
    family: str,
    prompt: str,
    target_nodes: Iterable[str],
    dimensions: Iterable[str],
    risk: float,
    standardized: bool,
    difficulty: int,
    expected_seconds: int,
    rationale: str,
    answer_expectations: Sequence[str],
    red_flags: Sequence[str],
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "application_question_index": application_index,
        "family": family,
        "prompt": prompt,
        "target_nodes": list(dict.fromkeys(target_nodes)),
        "dimensions": list(dict.fromkeys(dimensions)),
        "risk": round(float(risk), 2),
        "base_diagnostic_value": round(1.0 + float(risk) * 0.45 + len(set(dimensions)) * 0.18, 3),
        "standardized": standardized,
        "difficulty": max(1, min(5, difficulty)),
        "expected_seconds": expected_seconds,
        "rationale": rationale,
        "answer_expectations": list(answer_expectations),
        "red_flags": list(red_flags),
    }


def _nodes_by_question(graph: Mapping[str, Any]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in graph.get("nodes", []):
        if not isinstance(node, Mapping):
            continue
        for index in node.get("question_indexes", []):
            if isinstance(index, int):
                result[index].append(dict(node))
    return result


def _question_bank(
    draft: Sequence[DraftRef],
    prompts: Mapping[int, str],
    graph: Mapping[str, Any],
    target: str,
) -> list[dict[str, Any]]:
    bank: list[dict[str, Any]] = []
    by_question = _nodes_by_question(graph)
    intro_nodes = [
        str(node.get("node_id"))
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping) and node.get("factual_authority") is True and node.get("node_id")
    ]
    intro_risk = max(
        [float(node.get("risk", 1.0)) for node in graph.get("nodes", []) if isinstance(node, Mapping)] or [2.0]
    )
    bank.append(
        _question(
            "core:intro:60",
            application_index=None,
            family="core_intro",
            prompt=f"{target or '지원 기관'} 지원자로서 본인의 핵심 강점과 그 근거, 이 직무에서의 연결을 60초 안에 설명해봐.",
            target_nodes=intro_nodes,
            dimensions=("directness", "evidence_defensibility", "specificity", "job_understanding", "communication_density"),
            risk=intro_risk,
            standardized=True,
            difficulty=2,
            expected_seconds=60,
            rationale="모든 세션에서 동일한 기준점으로 사용하는 60초 자기소개 코어 질문",
            answer_expectations=("첫 문장에서 강점 또는 직무 연결을 직접 제시", "확정 경험의 행동 근거 사용", "추상적 포부보다 실제 행동 방식 제시"),
            red_flags=("근거 없는 새로운 성과", "기관 홍보문구 나열", "자기소개서와 다른 역할·수치"),
        )
    )
    for response in draft:
        nodes = by_question.get(response.question_index, [])
        app_nodes = [node for node in nodes if node.get("source_kind") == "applicant"]
        research_nodes = [node for node in nodes if node.get("source_kind") == "research"]
        intent = _intent(prompts.get(response.question_index, ""))
        risk = max([float(node.get("risk", 1.0)) for node in nodes] or [1.5])
        target_nodes = [str(node["node_id"]) for node in nodes]
        title = app_nodes[0].get("experience_title") if app_nodes else None
        if app_nodes:
            core_prompt = (
                f"자기소개서 문항 {response.question_index}에서 '{title}' 경험을 근거로 답했어. "
                "당시 핵심 상황, 네 판단, 네가 직접 한 행동, 확인된 결과를 60초 안에 설명해봐."
            )
        elif research_nodes:
            core_prompt = (
                f"자기소개서 문항 {response.question_index}의 핵심 주장을 60초 안에 다시 설명해봐. "
                "공식 사실과 네 해석을 구분하고, 왜 그 판단이 직무와 연결되는지도 말해봐."
            )
        else:
            core_prompt = f"자기소개서 문항 {response.question_index}의 답을 60초 안에 핵심 주장부터 다시 설명해봐."
        dims = ["directness", "evidence_defensibility", "specificity", "communication_density"]
        if app_nodes:
            dims.extend(("ownership_precision", "decision_visibility", "causal_precision"))
        if research_nodes:
            dims.extend(("organization_understanding", "job_understanding"))
        bank.append(
            _question(
                f"core:q{response.question_index}",
                application_index=response.question_index,
                family="core_past_behavior" if app_nodes else "core_research_defense",
                prompt=core_prompt,
                target_nodes=target_nodes,
                dimensions=dims,
                risk=risk,
                standardized=True,
                difficulty=2,
                expected_seconds=60,
                rationale=f"문항 {response.question_index}의 최종 제출 주장과 근거를 동일 질문으로 반복 측정",
                answer_expectations=("핵심 주장 → 근거 → 본인 행동/해석 → 결과 또는 직무 연결 순서", "최종 자기소개서의 범위를 넘지 않음"),
                red_flags=("새로운 수치·역할·회사 사실", "질문보다 긴 배경 설명", "자기소개서와 다른 인과관계"),
            )
        )

        for node in app_nodes:
            node_id = str(node["node_id"])
            exp_title = str(node.get("experience_title", "해당 경험"))
            contribution = str(node.get("verification", {}).get("contribution", "unknown"))
            bank.append(
                _question(
                    f"probe:q{response.question_index}:{node_id}:ownership",
                    application_index=response.question_index,
                    family="ownership_probe",
                    prompt=f"'{exp_title}'에서 팀이 한 일과 네가 직접 책임진 일을 분리해서 말해봐. 결과 중 네 기여라고 주장할 수 있는 범위는 정확히 어디까지야?",
                    target_nodes=(node_id,),
                    dimensions=("ownership_precision", "evidence_defensibility", "pressure_resilience"),
                    risk=float(node.get("risk", 1.0)) + (0.6 if contribution in {"observed", "unknown"} else 0.2),
                    standardized=False,
                    difficulty=4,
                    expected_seconds=45,
                    rationale="팀 성과를 개인 성과로 확장하는 위험과 역할 경계를 직접 검증",
                    answer_expectations=("본인 행동과 타인 행동을 구분", "검증된 contribution 범위를 넘지 않음"),
                    red_flags=("팀 성과 전체를 개인 단독 성과로 표현", "근거 없는 책임 범위 확대"),
                )
            )
            bank.append(
                _question(
                    f"probe:q{response.question_index}:{node_id}:decision",
                    application_index=response.question_index,
                    family="decision_probe",
                    prompt=f"'{exp_title}'에서 그 행동 순서나 방법을 선택한 기준은 뭐였어? 다른 대안과 비교했을 때 왜 그 선택이었는지 설명해봐.",
                    target_nodes=(node_id,),
                    dimensions=("decision_visibility", "specificity", "pressure_resilience"),
                    risk=float(node.get("risk", 1.0)),
                    standardized=False,
                    difficulty=3,
                    expected_seconds=45,
                    rationale="STAR 서술에 숨어 있는 판단 기준을 노출해 암기 답변과 실제 문제해결을 구분",
                    answer_expectations=("선택 기준을 먼저 제시", "실제 확인된 행동 범위에서 대안 비교"),
                    red_flags=("사후적으로 만든 그럴듯한 기준", "행동 설명만 반복하고 이유가 없음"),
                )
            )
            bank.append(
                _question(
                    f"probe:q{response.question_index}:{node_id}:counterfactual",
                    application_index=response.question_index,
                    family="counterfactual_probe",
                    prompt=f"같은 '{exp_title}' 상황을 다시 맡는다면 무엇을 그대로 하고 무엇을 바꾸겠어? 바꾸는 이유까지 말해봐.",
                    target_nodes=(node_id,),
                    dimensions=("reflection_quality", "decision_visibility", "pressure_resilience"),
                    risk=max(1.5, float(node.get("risk", 1.0)) - 0.2),
                    standardized=False,
                    difficulty=4,
                    expected_seconds=45,
                    rationale="성공담 재현이 아니라 한계 인식과 업데이트 가능한 판단 기준을 측정",
                    answer_expectations=("한계 또는 개선점 하나를 구체화", "바뀐 판단 기준이나 행동을 설명"),
                    red_flags=("모든 것이 완벽했다고 주장", "추상적인 '더 열심히'로 끝남"),
                )
            )
            if node.get("metric_values"):
                bank.append(
                    _question(
                        f"probe:q{response.question_index}:{node_id}:metric",
                        application_index=response.question_index,
                        family="metric_probe",
                        prompt="자기소개서에 쓴 수치가 어떻게 나온 값인지 설명해봐. 산식·측정 기간·범위·원자료와 네 기여분을 구분해서 말해봐.",
                        target_nodes=(node_id,),
                        dimensions=("evidence_defensibility", "causal_precision", "ownership_precision", "pressure_resilience"),
                        risk=min(5.0, float(node.get("risk", 1.0)) + 1.0),
                        standardized=False,
                        difficulty=5,
                        expected_seconds=60,
                        rationale="수치의 출처와 개인 기여도를 가장 높은 우선순위로 방어",
                        answer_expectations=("승인 원장의 산식·기간·범위 안에서 답변", "수치의 전체 결과와 개인 기여를 분리"),
                        red_flags=("기억으로 새 수치 생성", "산식 변경", "측정 기간 또는 모집단 범위 확대"),
                    )
                )
            if contribution in {"caused", "contributed", "observed", "unknown"}:
                bank.append(
                    _question(
                        f"probe:q{response.question_index}:{node_id}:causal",
                        application_index=response.question_index,
                        family="causality_probe",
                        prompt="그 결과가 정말 네 행동 때문에 생겼다고 볼 수 있는 근거는 뭐야? 동시에 영향을 준 다른 요인과 네가 확실히 말할 수 없는 부분도 구분해봐.",
                        target_nodes=(node_id,),
                        dimensions=("causal_precision", "evidence_defensibility", "ownership_precision", "pressure_resilience"),
                        risk=min(5.0, float(node.get("risk", 1.0)) + 0.8),
                        standardized=False,
                        difficulty=5,
                        expected_seconds=50,
                        rationale="성과 인과관계를 과장하는지와 불확실성 경계를 검증",
                        answer_expectations=("검증 방식과 기여 수준을 구분", "대안 원인을 인정하되 본인 행동의 실제 범위는 명확히 제시"),
                        red_flags=("상관관계를 단독 인과로 주장", "다른 요인을 전부 부정"),
                    )
                )

        for node in research_nodes:
            node_id = str(node["node_id"])
            claim = _compact(str(node.get("claim", "")), 120)
            bank.append(
                _question(
                    f"probe:q{response.question_index}:{node_id}:meaning",
                    application_index=response.question_index,
                    family="organization_probe",
                    prompt=f"공식 자료에서 확인한 '{claim}'라는 사실을 왜 중요하게 봤어? 그 사실 자체와 네 해석을 구분해서 직무 연결까지 설명해봐.",
                    target_nodes=(node_id,),
                    dimensions=("organization_understanding", "job_understanding", "evidence_defensibility", "decision_visibility"),
                    risk=float(node.get("risk", 1.0)) + 0.4,
                    standardized=False,
                    difficulty=4,
                    expected_seconds=55,
                    rationale="회사 사실 암기와 실제 의미 해석을 구분하고 지원 논리의 연결고리를 검증",
                    answer_expectations=("공식 사실과 개인 해석을 언어적으로 분리", "직무의 실제 행동 단위로 연결"),
                    red_flags=("출처에 없는 회사 사실 추가", "기관 칭찬만 하고 본인 판단이 없음"),
                )
            )
            if str(node.get("claim_type")) == "job_duty":
                bank.append(
                    _question(
                        f"probe:q{response.question_index}:{node_id}:situational",
                        application_index=response.question_index,
                        family="situational_job_probe",
                        prompt=f"입사 후 '{claim}' 업무에서 정보가 불완전하거나 판단 권한이 애매한 상황이 생기면 무엇부터 확인하고, 언제 누구에게 보고하거나 인계하겠어?",
                        target_nodes=(node_id,),
                        dimensions=("job_understanding", "decision_visibility", "pressure_resilience", "specificity"),
                        risk=float(node.get("risk", 1.0)) + 0.3,
                        standardized=False,
                        difficulty=4,
                        expected_seconds=60,
                        rationale="과거 경험뿐 아니라 실제 직무 상황에서의 판단 규칙을 분리 측정",
                        answer_expectations=("확인 → 판단 → escalation/handoff 순서를 제시", "신입 권한을 과장하지 않음"),
                        red_flags=("권한 밖의 독단적 결정", "구체적 확인 기준 없이 '소통'만 반복"),
                    )
                )

        if intent in {"motivation", "job_plan"} and research_nodes:
            bank.append(
                _question(
                    f"probe:q{response.question_index}:fit_counterfactual",
                    application_index=response.question_index,
                    family="fit_counterfactual_probe",
                    prompt="지금 말한 기관 사실을 빼더라도 네가 이 직무를 선택하는 개인적 기준이 남아 있어? 남는다면 무엇이고, 없다면 왜 이 기관만의 이유라고 보는지 설명해봐.",
                    target_nodes=target_nodes,
                    dimensions=("directness", "decision_visibility", "organization_understanding", "job_understanding"),
                    risk=risk + 0.5,
                    standardized=False,
                    difficulty=5,
                    expected_seconds=50,
                    rationale="기업 홍보문구를 제거해도 지원동기의 개인 선택 기준이 남는지 검증",
                    answer_expectations=("개인 선택 기준과 기관 고유 근거를 분리", "기관명만 바꿔도 성립하는 답을 피함"),
                    red_flags=("어느 기관에도 적용 가능한 답", "공식 사실을 개인 동기로 대체"),
                )
            )
    return bank


def _load_weakness_profile(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"status": "unavailable", "dimensions": {}, "flags": {}}
    path = root / WEAKNESS_PROFILE
    if not path.is_file():
        return {"status": "empty", "path": str(path), "dimensions": {}, "flags": {}}
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        return {"status": "invalid", "path": str(path), "dimensions": {}, "flags": {}}
    return {
        "status": "available",
        "path": str(path),
        "dimensions": dict(payload.get("dimensions", {})) if isinstance(payload.get("dimensions"), Mapping) else {},
        "flags": dict(payload.get("flags", {})) if isinstance(payload.get("flags"), Mapping) else {},
    }


def _profile_gap(profile: Mapping[str, Any], dimension: str) -> float:
    record = profile.get("dimensions", {}).get(dimension, {}) if isinstance(profile.get("dimensions"), Mapping) else {}
    if not isinstance(record, Mapping):
        return 0.0
    gaps: list[float] = []
    score = record.get("ema_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        gaps.append(max(0.0, 4.0 - float(score)) / 4.0)
    weak_signal = record.get("weak_signal_ema")
    if isinstance(weak_signal, (int, float)) and not isinstance(weak_signal, bool):
        gaps.append(max(0.0, min(1.0, float(weak_signal))))
    return max(gaps, default=0.0)


def select_next_question(
    plan: Mapping[str, Any],
    session: Mapping[str, Any] | None = None,
    weakness_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    session = session or {}
    weakness_profile = weakness_profile or plan.get("weakness_profile", {}) or {}
    turns = session.get("turns", []) if isinstance(session.get("turns", []), list) else []
    asked = {
        str(turn.get("question_id"))
        for turn in turns
        if isinstance(turn, Mapping) and turn.get("question_id")
    }
    bank = [dict(item) for item in plan.get("question_bank", []) if isinstance(item, Mapping)]
    unasked = [item for item in bank if str(item.get("question_id")) not in asked]
    if not unasked:
        return None
    core = [item for item in unasked if item.get("standardized")]
    if core:
        def core_key(item: Mapping[str, Any]) -> tuple[int, int, str]:
            if item.get("family") == "core_intro":
                return (0, 0, str(item.get("question_id")))
            index = item.get("application_question_index")
            return (1, int(index) if isinstance(index, int) else 10**9, str(item.get("question_id")))
        result = dict(sorted(core, key=core_key)[0])
        result["selection_utility"] = 100.0
        result["selection_reason"] = "standardized_backbone"
        return result
    pool = unasked

    weak_dimensions = set()
    raw_weak = session.get("weak_dimensions", [])
    if isinstance(raw_weak, list):
        weak_dimensions.update(str(item) for item in raw_weak)
    covered_dimensions = set()
    covered_nodes = set()
    last_family = None
    if turns:
        last_id = str(turns[-1].get("question_id", "")) if isinstance(turns[-1], Mapping) else ""
        for item in bank:
            if str(item.get("question_id")) == last_id:
                last_family = item.get("family")
                break
    for turn in turns:
        if not isinstance(turn, Mapping):
            continue
        qid = str(turn.get("question_id", ""))
        for item in bank:
            if str(item.get("question_id")) == qid:
                covered_dimensions.update(item.get("dimensions", []))
                covered_nodes.update(item.get("target_nodes", []))
                break

    scored: list[tuple[float, str, dict[str, Any]]] = []
    for item in pool:
        dimensions = [str(value) for value in item.get("dimensions", [])]
        nodes = [str(value) for value in item.get("target_nodes", [])]
        score = float(item.get("base_diagnostic_value", 1.0))
        score += sum(1.2 for dim in dimensions if dim in weak_dimensions)
        score += sum(_profile_gap(weakness_profile, dim) * 0.9 for dim in dimensions)
        score += sum(0.35 for dim in dimensions if dim not in covered_dimensions)
        score += sum(0.4 for node in nodes if node not in covered_nodes)
        score += float(item.get("risk", 1.0)) * 0.32
        if last_family and item.get("family") == last_family:
            score -= 0.8
        score -= max(0, int(item.get("difficulty", 1)) - 4) * 0.08
        scored.append((score, str(item.get("question_id")), item))
    scored.sort(key=lambda value: (-value[0], value[1]))
    result = dict(scored[0][2])
    result["selection_utility"] = round(scored[0][0], 3)
    result["selection_reason"] = "standardized_backbone" if result.get("standardized") else "expected_diagnostic_utility"
    return result


def _recommended_sequence(plan: Mapping[str, Any], limit: int = 14) -> list[str]:
    session: dict[str, Any] = {"turns": []}
    sequence: list[str] = []
    for _ in range(limit):
        question = select_next_question(plan, session)
        if question is None:
            break
        qid = str(question["question_id"])
        sequence.append(qid)
        session["turns"].append({"question_id": qid})
    return sequence
