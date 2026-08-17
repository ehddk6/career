"""Deterministic company-research requirement compiler.

This module decides *what must be proven* before any browsing or prose.  It is
factual-authority neutral: it never creates company facts.  It only compiles
question semantics into research slots that later claims must fill.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1

_RESEARCH_CUES = (
    "지원동기", "지원 동기", "지원하게", "지원한 이유", "기관의 역할", "회사의 역할",
    "주요사업", "주요 사업", "직무수행", "업무수행", "근무계획", "직무계획", "입사 후",
    "시사", "이슈", "현안", "산업", "경제", "사회문제", "사회 문제", "정책", "기관이",
    "회사가", "기업이", "조직이",
)

_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("issue_analysis", ("시사", "이슈", "현안", "사회문제", "사회 문제", "산업", "경제", "논술", "정책")),
    ("motivation", ("지원동기", "지원 동기", "지원한 동기", "지원한 이유", "지원하게 된", "지원하게", "선택한 이유")),
    ("job_plan", ("업무수행계획", "직무수행계획", "근무계획", "직무계획", "입사 후 계획", "입사 후")),
)


@dataclass(frozen=True)
class ResearchSlot:
    slot_id: str
    argument_role: str
    description: str
    claim_types: tuple[str, ...]
    required: bool
    minimum_claims: int
    freshness_requirement: str
    maximum_source_tier: int
    suggested_query: str


@dataclass(frozen=True)
class QuestionResearchPlan:
    question_index: int
    prompt: str
    intent: str
    research_required: bool
    slots: tuple[ResearchSlot, ...]


def _prompt(question: Any) -> tuple[int, str]:
    if isinstance(question, Mapping):
        return int(question.get("index", 0)), str(question.get("prompt", ""))
    return int(getattr(question, "index", 0)), str(getattr(question, "prompt", ""))


def matched_research_intents(prompt: str) -> tuple[str, ...]:
    compact = " ".join(prompt.lower().split())
    found = [
        intent
        for intent, cues in _INTENT_RULES
        if any(cue.lower() in compact for cue in cues)
    ]
    return tuple(found)


def classify_research_intent(prompt: str) -> str:
    found = matched_research_intents(prompt)
    if "motivation" in found:
        return "motivation"
    if found:
        return found[0]
    return "general"


def needs_company_research(prompt: str) -> bool:
    compact = " ".join(prompt.lower().split())
    return any(cue.lower() in compact for cue in _RESEARCH_CUES)


def _slot(
    slot_id: str,
    role: str,
    description: str,
    claim_types: tuple[str, ...],
    *,
    required: bool,
    freshness: str,
    max_tier: int,
    target: str,
    query_hint: str,
    minimum_claims: int = 1,
) -> ResearchSlot:
    query = " ".join(part for part in (target.strip(), query_hint.strip()) if part)
    return ResearchSlot(
        slot_id=slot_id,
        argument_role=role,
        description=description,
        claim_types=claim_types,
        required=required,
        minimum_claims=minimum_claims,
        freshness_requirement=freshness,
        maximum_source_tier=max_tier,
        suggested_query=query,
    )


def slots_for_intent(intent: str, target: str, prompt: str) -> tuple[ResearchSlot, ...]:
    if intent == "motivation":
        return (
            _slot(
                "organization_differentiator", "organization_differentiator",
                "다른 기관·기업과 구분되는 고유 역할, 사업 구조 또는 법정·시장 기능",
                ("organization_role", "program_or_service"), required=True,
                freshness="stable_or_current", max_tier=1, target=target,
                query_hint="공식 주요 사업 역할 설립 목적 차별점",
            ),
            _slot(
                "real_operating_role", "real_operating_role",
                "지원 직무 또는 조직이 실제로 수행하는 행동 단위와 책임 범위",
                ("job_duty", "program_or_service"), required=True,
                freshness="current", max_tier=1, target=target,
                query_hint="채용 직무기술서 주요 업무 직무 역할",
            ),
            _slot(
                "current_priority", "current_priority",
                "최근 사업계획·경영방향·공식 공시에서 확인되는 현재 우선순위",
                ("program_or_service", "industry_issue", "organization_role"), required=False,
                freshness="current", max_tier=2, target=target,
                query_hint="최근 사업계획 경영목표 중점 추진 보도자료",
            ),
            _slot(
                "stakeholder_problem", "stakeholder_problem",
                "기관·기업이 실제 고객·국민·시장에게 해결하려는 문제 또는 마찰",
                ("organization_role", "program_or_service", "industry_issue"), required=False,
                freshness="stable_or_current", max_tier=2, target=target,
                query_hint="고객 대상 문제 지원 대상 정책 목적",
            ),
        )
    if intent == "job_plan":
        return (
            _slot(
                "real_operating_role", "real_operating_role",
                "직무기술서·채용공고 기준의 실제 업무, 책임, 산출물",
                ("job_duty",), required=True, freshness="posting_bound", max_tier=0,
                target=target, query_hint="채용공고 직무기술서 주요업무",
            ),
            _slot(
                "operating_constraint", "operating_constraint",
                "업무 수행 시 오류·권한·규정·고객 영향 등 현실적인 제약과 위험",
                ("risk_or_limit", "job_duty", "selection_criteria"), required=True,
                freshness="current", max_tier=1, target=target,
                query_hint="업무 규정 절차 리스크 유의사항 처리 기준",
            ),
            _slot(
                "current_priority", "current_priority",
                "현재 조직이 직무와 관련해 중점적으로 추진하는 사업·개선 방향",
                ("program_or_service", "organization_role"), required=False,
                freshness="current", max_tier=2, target=target,
                query_hint="최근 중점사업 업무계획 디지털 개선 고객서비스",
            ),
        )
    if intent == "issue_analysis":
        return (
            _slot(
                "issue_mechanism", "issue_mechanism",
                "선택한 이슈가 발생·확대되는 원인과 작동 메커니즘",
                ("industry_issue",), required=True, freshness="current", max_tier=3,
                target=target, query_hint="최근 현안 통계 원인 영향 공식 자료",
            ),
            _slot(
                "institution_response", "institution_response",
                "해당 이슈에 대한 기관의 현재 역할·사업·정책 수단",
                ("program_or_service", "organization_role"), required=True,
                freshness="current", max_tier=2, target=target,
                query_hint="현안 대응 사업 정책 지원 보도자료",
            ),
            _slot(
                "policy_tradeoff", "policy_tradeoff",
                "대응 수단의 한계·부작용·상충 조건 또는 리스크",
                ("risk_or_limit", "industry_issue"), required=True,
                freshness="current", max_tier=3, target=target,
                query_hint="정책 한계 리스크 부작용 유의사항 공식",
            ),
        )
    if needs_company_research(prompt):
        return (
            _slot(
                "real_operating_role", "real_operating_role",
                "문항과 직접 관련된 기관·기업의 실제 역할 또는 직무 사실",
                ("job_duty", "program_or_service", "organization_role"), required=True,
                freshness="stable_or_current", max_tier=1, target=target,
                query_hint="공식 주요 업무 직무 사업",
            ),
        )
    return ()


def compile_research_plan(
    questions: Iterable[Any],
    *,
    target: str,
    posting: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    plans: list[QuestionResearchPlan] = []
    for question in questions:
        index, prompt = _prompt(question)
        matched = matched_research_intents(prompt)
        intent = classify_research_intent(prompt)
        intents_for_slots = matched or (intent,)
        merged: list[ResearchSlot] = []
        seen_roles: set[str] = set()
        for slot_intent in intents_for_slots:
            for slot in slots_for_intent(slot_intent, target, prompt):
                if slot.argument_role in seen_roles:
                    continue
                seen_roles.add(slot.argument_role)
                merged.append(slot)
        slots = tuple(merged)
        plans.append(
            QuestionResearchPlan(
                question_index=index,
                prompt=prompt,
                intent=intent,
                research_required=bool(slots),
                slots=slots,
            )
        )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "posting_snapshot_id": None,
        "questions": [
            {
                "question_index": item.question_index,
                "prompt": item.prompt,
                "intent": item.intent,
                "matched_intents": list(matched_research_intents(item.prompt)),
                "research_required": item.research_required,
                "slots": [asdict(slot) for slot in item.slots],
            }
            for item in plans
        ],
        "policy": {
            "facts_must_come_from_evidence": True,
            "required_slots_fail_closed": True,
            "official_primary_sources_first": True,
            "stop_when_required_slots_are_covered": True,
        },
    }
    if isinstance(posting, Mapping):
        source = posting.get("source")
        if isinstance(source, Mapping):
            payload["posting_snapshot_id"] = source.get("content_sha256")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["plan_id"] = sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return payload
