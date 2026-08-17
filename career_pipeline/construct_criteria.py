"""ConstructCriterion micro-decomposition (shadow, observation/audit only).

Decomposes the one-long-indicator-per-construct view into micro criteria that a
source-backed BehaviorAtom can satisfy.  taxonomy prior constructs always get
source_basis "taxonomy_prior" and can never produce target DIRECT evidence.
This module never changes production selection or v1 artifacts.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .job_analysis_schema import JobAnalysisGraph

SCHEMA_VERSION = 1
ARCHITECTURE = "construct_criterion_shadow_v1"
CRITERIA_JSON = "06_구성개념기준.json"

_FAMILY_PREFIX = "construct_"
_PRIOR_FAMILY_PREFIX = "prior_"


@dataclass(frozen=True)
class ConstructCriterion:
    criterion_id: str
    construct_id: str
    behavior_type: str
    action: str
    verbs: tuple[str, ...]
    object_class: tuple[str, ...]
    required_roles: tuple[str, ...]
    source_basis: str
    required_for_direct: bool
    optional_support: bool


# family_key -> (name, behavior_type, verbs, object_class, required_for_direct, optional_support)
_CRITERIA_BY_FAMILY: dict[str, tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], bool, bool], ...]] = {
    "criterion_application": (
        ("compare_against_rule_or_source", "compare", ("대조", "비교"), ("원문", "기준", "규정", "서류", "자료", "입력값"), True, False),
        ("detect_discrepancy", "detect", ("확인", "발견", "판별"), ("누락", "오류", "예외", "불일치", "차이"), True, False),
        ("classify_exception", "classify", ("분류", "구분", "선별"), ("예외", "누락", "오류", "유형"), False, True),
        ("preserve_decision_basis", "record", ("기록", "작성", "정리"), ("근거", "기록", "문서", "판단"), False, True),
    ),
    "analytical_diagnosis": (
        ("compare_or_segment_information", "compare", ("비교", "대조", "분석", "취합"), ("자료", "데이터", "정보", "현황", "지표"), True, False),
        ("identify_pattern_or_cause", "identify", ("분석", "진단", "파악", "발견"), ("원인", "패턴", "문제", "추이", "특이"), True, False),
        ("explain_basis", "explain", ("설명", "제시"), ("근거", "원인", "분석", "결과"), False, True),
    ),
    "stakeholder_explanation": (
        ("identify_recipient_need", "identify", ("확인", "파악"), ("요구", "수요", "문의", "민원", "고객", "수요자"), True, False),
        ("explain_rule_or_gap", "explain", ("안내", "설명", "상담", "소명"), ("기준", "보완", "절차", "내용", "사유"), True, False),
        ("state_next_action", "explain", ("안내", "설명"), ("다음", "절차", "일정", "행동"), False, True),
    ),
    "coordination": (
        ("identify_other_party_constraint", "identify", ("확인", "파악"), ("제약", "일정", "요구", "부서", "담당자", "협력"), True, False),
        ("exchange_or_align_requirements", "exchange", ("협의", "조정", "협업", "연계"), ("요구", "일정", "업무", "협력"), True, False),
        ("agree_or_define_next_action", "align", ("조정", "협의"), ("다음", "일정", "방안", "합의"), False, True),
    ),
    "boundary_escalation": (
        ("identify_authority_boundary", "identify", ("확인", "판단"), ("권한", "범위", "책임", "결재"), True, False),
        ("detect_out_of_scope_case", "detect", ("확인", "발견", "판별"), ("예외", "범위", "권한"), True, False),
        ("escalate_with_basis", "escalate", ("보고", "승인요청", "요청"), ("담당자", "상급", "권한", "결재"), True, False),
    ),
    "documentation": (
        ("record_decision_or_action", "record", ("기록", "작성", "정리"), ("판단", "처리", "결과", "내역"), True, False),
        ("preserve_traceability", "record", ("기록", "작성"), ("추적", "이력", "로그", "내역"), False, True),
    ),
    "execution_control": (
        ("inspect_status_or_deadline", "inspect", ("확인", "점검", "모니터링"), ("일정", "마감", "상태", "진행", "현황"), True, False),
        ("identify_missing_or_delayed_work", "detect", ("확인", "점검", "발견"), ("누락", "지연", "미처리", "이슈"), True, False),
        ("manage_next_action", "manage", ("관리", "처리"), ("일정", "우선순위", "다음", "진행"), False, True),
    ),
}


def _family_key(construct_id: str) -> str:
    if construct_id.startswith(_FAMILY_PREFIX):
        return construct_id[len(_FAMILY_PREFIX):]
    if construct_id.startswith(_PRIOR_FAMILY_PREFIX):
        rest = construct_id[len(_PRIOR_FAMILY_PREFIX):]
        for key in _CRITERIA_BY_FAMILY:
            if rest.startswith(key + "_"):
                return key
    return ""


def criteria_for_graph(graph: JobAnalysisGraph) -> tuple[ConstructCriterion, ...]:
    rows: list[ConstructCriterion] = []
    for construct in graph.constructs:
        family = _family_key(construct.construct_id)
        if not family or family not in _CRITERIA_BY_FAMILY:
            continue
        basis = "taxonomy_prior" if construct.status == "prior_supported" else "target"
        for name, behavior_type, verbs, objects, required, optional in _CRITERIA_BY_FAMILY[family]:
            rows.append(
                ConstructCriterion(
                    criterion_id=f"crit_{family}_{name}",
                    construct_id=construct.construct_id,
                    behavior_type=behavior_type,
                    action=verbs[0],
                    verbs=verbs,
                    object_class=objects,
                    required_roles=("actor_self", "actor_other") if behavior_type == "exchange" else ("actor_self",),
                    source_basis=basis,
                    required_for_direct=required,
                    optional_support=optional,
                )
            )
    return tuple(rows)


def write_construct_criteria(run_dir: Path, graph: JobAnalysisGraph) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    criteria = criteria_for_graph(graph)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "policy": {"decision_effect": "none_shadow_mode", "factual_authority_granted": False},
        "criteria": [asdict(item) for item in criteria],
    }
    jp = run_dir / CRITERIA_JSON
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mp = run_dir / "06_구성개념기준.md"
    lines = ["# 구성개념 미세 기준 (ConstructCriterion)", "", "> 관측/감사 전용 그림자 계층이며 생산 선택에 영향을 주지 않는다.", ""]
    for item in criteria:
        lines.append(f"- `{item.criterion_id}` (construct `{item.construct_id}`, basis `{item.source_basis}`): verbs={', '.join(item.verbs)} object={', '.join(item.object_class) or '(any)'} required_for_direct={item.required_for_direct}")
    lines.append("")
    mp.write_text("\n".join(lines), encoding="utf-8")
    return jp, mp, payload