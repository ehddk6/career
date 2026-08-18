"""Shadow-only Narrative Realization Search primitives.

This module does not create factual authority and is not imported by the
canonical Golden Path.  It turns an already-validated argument route into a
small set of structurally different rhetorical plans so the same evidence can
be rendered in different orders without changing what is claimed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
POLICY_VERSION = "narrative_realization_shadow_v1"

# These are rhetorical functions, not factual evidence classes.
MOVE_BY_PROOF_KIND = {
    "context": "CONTEXT",
    "friction": "FRICTION",
    "criterion": "CRITERION",
    "judgment": "JUDGMENT",
    "action": "ACTION",
    "outcome": "OUTCOME",
    "reflection": "REFLECTION",
    "organization_fact": "ORG_FACT",
    "fit_bridge": "FIT_BRIDGE",
    "tradeoff": "CONTRAST",
    "guardrail": "GUARDRAIL",
}

_ANSWER_LATENCY = {
    "motivation": {"required_signal": "criterion_or_claim", "max_sentence": 2},
    "adaptation": {"required_signal": "judgment_or_action", "max_sentence": 3},
    "collaboration": {"required_signal": "friction_or_role_boundary", "max_sentence": 3},
    "problem_solving": {"required_signal": "friction_and_judgment", "max_sentence": 3},
    "growth": {"required_signal": "friction_or_reflection", "max_sentence": 3},
    "integrity": {"required_signal": "criterion_or_boundary", "max_sentence": 2},
    "competency": {"required_signal": "action_or_evidence", "max_sentence": 2},
    "job_plan": {"required_signal": "criterion_or_guardrail", "max_sentence": 3},
    "issue_analysis": {"required_signal": "tradeoff_or_judgment", "max_sentence": 3},
    "general_experience": {"required_signal": "action_or_judgment", "max_sentence": 2},
}

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_SENTENCE = re.compile(r"[^.!?。！？\n]+[.!?。！？]?")

class NarrativeRealizationError(ValueError):
    pass


@dataclass(frozen=True)
class KernelItem:
    proof_index: int
    kind: str
    move: str
    text: str
    support_refs: tuple[str, ...]
    distinctive_anchor: bool


@dataclass(frozen=True)
class NarrativeKernel:
    schema_version: int
    policy_version: str
    question_index: int
    question_intent: str
    prompt: str
    route_id: str
    thesis: str
    thesis_support_refs: tuple[str, ...]
    proof_items: tuple[KernelItem, ...]
    distinctive_anchor_refs: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    ownership_ceiling: str
    prohibited_inferences: tuple[str, ...]


@dataclass(frozen=True)
class RealizationPlan:
    plan_id: str
    family: str
    ordered_proof_indexes: tuple[int, ...]
    move_sequence: tuple[str, ...]
    opening_instruction: str
    answer_latency: Mapping[str, Any]
    rationale: str


def normalize_intent(value: Any) -> str:
    intent = str(value or "").strip()
    return intent if intent in _ANSWER_LATENCY else "general_experience"


def answer_latency_contract(intent: Any) -> dict[str, Any]:
    return dict(_ANSWER_LATENCY[normalize_intent(intent)])


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def build_narrative_kernel(
    blueprint: Mapping[str, Any],
    route: Mapping[str, Any],
    *,
    ownership_ceiling: str = "preserve_blueprint_and_route_contribution_limits",
) -> NarrativeKernel:
    """Build a support-preserving kernel from an already validated route.

    The function intentionally does not infer missing motives, outcomes,
    conflicts, trade-offs, or decision criteria. Missing route material stays
    missing and therefore cannot be required by a generated plan.
    """
    q = blueprint.get("question_index")
    if isinstance(q, bool) or not isinstance(q, int):
        raise NarrativeRealizationError("blueprint question_index must be int")
    route_q = route.get("question_index", q)
    if route_q != q:
        raise NarrativeRealizationError("route question_index mismatch")
    route_id = str(route.get("route_id", "")).strip()
    thesis = str(route.get("thesis", "")).strip()
    if not route_id or not thesis:
        raise NarrativeRealizationError("route_id and thesis are required")

    raw_proof = route.get("proof_chain")
    if not isinstance(raw_proof, Sequence) or isinstance(raw_proof, (str, bytes)) or not raw_proof:
        raise NarrativeRealizationError("route proof_chain is required")

    distinctive = set(_strings(route.get("distinctive_anchor_refs")))
    proof_items: list[KernelItem] = []
    for index, raw in enumerate(raw_proof):
        if not isinstance(raw, Mapping):
            raise NarrativeRealizationError("proof item must be object")
        kind = str(raw.get("kind", "")).strip()
        move = MOVE_BY_PROOF_KIND.get(kind)
        if move is None:
            raise NarrativeRealizationError(f"unsupported proof kind: {kind}")
        text = str(raw.get("text", "")).strip()
        refs = _strings(raw.get("support_refs"))
        if not text:
            raise NarrativeRealizationError("proof item text is required")
        proof_items.append(
            KernelItem(
                proof_index=index,
                kind=kind,
                move=move,
                text=text,
                support_refs=refs,
                distinctive_anchor=bool(distinctive.intersection(refs)),
            )
        )

    gaps = _strings(route.get("evidence_gaps"))
    prohibited = tuple(
        [
            "Do not add facts, numbers, motives, outcomes, causality, or ownership beyond the blueprint and selected route.",
            "Do not strengthen observed/contributed work into sole personal causation.",
        ]
        + ([f"Unresolved route gap: {gap}" for gap in gaps] if gaps else [])
    )
    return NarrativeKernel(
        schema_version=SCHEMA_VERSION,
        policy_version=POLICY_VERSION,
        question_index=q,
        question_intent=normalize_intent(blueprint.get("intent") or route.get("intent")),
        prompt=str(blueprint.get("prompt", "")),
        route_id=route_id,
        thesis=thesis,
        thesis_support_refs=_strings(route.get("thesis_support_refs")),
        proof_items=tuple(proof_items),
        distinctive_anchor_refs=tuple(sorted(distinctive)),
        evidence_gaps=gaps,
        ownership_ceiling=ownership_ceiling,
        prohibited_inferences=prohibited,
    )


def _ranked_order(
    kernel: NarrativeKernel,
    preferred_kinds: Sequence[str],
    *,
    anchor_first: bool = False,
) -> tuple[int, ...]:
    preferred = {kind: pos for pos, kind in enumerate(preferred_kinds)}
    def key(item: KernelItem) -> tuple[int, int, int]:
        if anchor_first and item.distinctive_anchor:
            return (-1, 0, item.proof_index)
        if item.kind in preferred:
            return (0, preferred[item.kind], item.proof_index)
        return (1, len(preferred), item.proof_index)
    return tuple(item.proof_index for item in sorted(kernel.proof_items, key=key))


def _moves(kernel: NarrativeKernel, order: Sequence[int]) -> tuple[str, ...]:
    by_index = {item.proof_index: item for item in kernel.proof_items}
    return tuple(by_index[index].move for index in order)


def _plan(
    kernel: NarrativeKernel,
    family: str,
    order: tuple[int, ...],
    opening_instruction: str,
    rationale: str,
) -> RealizationPlan:
    return RealizationPlan(
        plan_id=f"NRS-{kernel.question_index}-{family}",
        family=family,
        ordered_proof_indexes=order,
        move_sequence=_moves(kernel, order),
        opening_instruction=opening_instruction,
        answer_latency=answer_latency_contract(kernel.question_intent),
        rationale=rationale,
    )


def generate_realization_plans(
    kernel: NarrativeKernel,
    *,
    max_plans: int = 4,
) -> list[RealizationPlan]:
    """Generate structurally distinct plans from existing route proof items.

    Orthogonality v1 is intentionally simple and auditable: accepted plans must
    have a distinct first proof index and a distinct full ordering.  We do not
    manufacture a rhetorical family when the required evidence kind is absent.
    """
    if not 1 <= max_plans <= 5:
        raise ValueError("max_plans must be 1..5")

    kinds = {item.kind for item in kernel.proof_items}
    candidates: list[RealizationPlan] = []

    if kinds.intersection({"criterion", "judgment"}):
        order = _ranked_order(
            kernel,
            ("criterion", "judgment", "friction", "action", "outcome", "reflection", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "decision_first", order,
            "판단 기준이나 선택을 먼저 드러내고, 그 판단을 증명하는 상황·행동·결과를 뒤에 배치한다.",
            "Makes the applicant's decision logic the opening organizing principle.",
        ))

    if "friction" in kinds:
        order = _ranked_order(
            kernel,
            ("friction", "judgment", "criterion", "action", "outcome", "reflection", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "friction_first", order,
            "구체적인 제약·충돌·문제부터 시작하되, 문제 설명에 머물지 말고 곧바로 본인의 판단과 행동으로 전진한다.",
            "Uses the verified friction as narrative tension instead of generic context.",
        ))

    if any(item.distinctive_anchor for item in kernel.proof_items):
        order = _ranked_order(kernel, (), anchor_first=True)
        candidates.append(_plan(
            kernel, "anchor_first", order,
            "지원자에게만 있는 구체적 근거·대상·산출물을 초반에 보여주고, 왜 그것이 중요했는지 판단과 행동으로 연결한다.",
            "Surfaces a route-approved distinctive anchor without inventing a new artifact.",
        ))

    if kinds.intersection({"context", "guardrail"}):
        order = _ranked_order(
            kernel,
            ("guardrail", "context", "criterion", "judgment", "action", "outcome", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "boundary_first", order,
            "역할·권한·제약 또는 지켜야 할 기준을 먼저 밝히고, 그 경계 안에서 실제로 한 선택과 행동을 보여준다.",
            "Makes ownership and operating boundaries explicit before claiming contribution.",
        ))

    if "tradeoff" in kinds:
        order = _ranked_order(
            kernel,
            ("tradeoff", "criterion", "judgment", "action", "outcome", "guardrail", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "contrast_first", order,
            "두 선택지나 상충하는 요구를 먼저 대비시키고, 왜 한쪽을 택했는지 근거와 행동을 제시한다.",
            "Uses an already-supported trade-off as the organizing contrast.",
        ))

    # Preserve route order as a control only when evidence does not support enough
    # orthogonal openings. This is not labelled as an experimental improvement.
    if not candidates:
        order = tuple(item.proof_index for item in kernel.proof_items)
        candidates.append(_plan(
            kernel, "route_order_control", order,
            "선택된 argument route의 기존 proof 순서를 보존해 자연스럽게 산문으로 실현한다.",
            "Control realization because no supported orthogonal opening is available.",
        ))

    result: list[RealizationPlan] = []
    seen_orders: set[tuple[int, ...]] = set()
    seen_first: set[int] = set()
    for candidate in candidates:
        if candidate.ordered_proof_indexes in seen_orders:
            continue
        first = candidate.ordered_proof_indexes[0]
        if first in seen_first:
            continue
        seen_orders.add(candidate.ordered_proof_indexes)
        seen_first.add(first)
        result.append(candidate)
        if len(result) >= max_plans:
            break
    return result


def ordered_proof(kernel: NarrativeKernel, plan: RealizationPlan) -> list[dict[str, Any]]:
    by_index = {item.proof_index: item for item in kernel.proof_items}
    return [asdict(by_index[index]) for index in plan.ordered_proof_indexes]


def build_nrs_prompt(
    blueprint: Mapping[str, Any],
    packet: Mapping[str, Any],
    route: Mapping[str, Any],
    kernel: NarrativeKernel,
    plan: RealizationPlan,
    *,
    prior_answers: Sequence[Mapping[str, Any]] = (),
    surface_preferences: Sequence[str] = (),
    semantic_preferences: Sequence[str] = (),
) -> str:
    """Build a generation prompt compatible with Narrative Compiler payloads."""
    compact = {
        "target": packet.get("target"),
        "portfolio_rules": (
            packet.get("portfolio", {}).get("cross_answer_rules", [])
            if isinstance(packet.get("portfolio"), Mapping)
            else []
        ),
        "blueprint_id": blueprint.get("blueprint_id"),
        "question_index": blueprint.get("question_index"),
        "prompt": blueprint.get("prompt"),
        "intent": blueprint.get("intent"),
        "logic_contract": blueprint.get("logic_contract"),
        "character_plan": blueprint.get("character_plan"),
        "beats": blueprint.get("beats"),
        "experience": blueprint.get("experience"),
        "research_claims": blueprint.get("research_claims"),
        "portfolio_constraints": blueprint.get("portfolio_constraints"),
        "risk_controls": blueprint.get("risk_controls"),
        "interview_defense_questions": blueprint.get("interview_defense_questions"),
    }
    context = {
        "blueprint": compact,
        "selected_route": route,
        "narrative_kernel": asdict(kernel),
        "realization_plan": asdict(plan),
        "ordered_proof": ordered_proof(kernel, plan),
        "surface_preferences": list(surface_preferences),
        "semantic_preferences": list(semantic_preferences),
        "prior_answers_for_portfolio_diversity": [dict(item) for item in prior_answers],
    }
    latency = plan.answer_latency
    principles = [
        "이 작업은 같은 근거를 다른 서사 구조로 실현하는 shadow 실험이다. 새로운 사실 권한을 만들지 않는다.",
        "blueprint의 selected_claims/research_claims와 selected_route의 support_refs 밖의 사실·수치·동기·결과를 추가하지 않는다.",
        "observed/contributed 기여를 단독 인과나 최종 권한으로 강화하지 않는다.",
        "realization_plan.move_sequence는 소제목이 아니라 문장 기능의 우선순위다.",
        f"문항 intent={kernel.question_intent}에서 핵심 신호({latency['required_signal']})를 {latency['max_sentence']}번째 문장 이내에 드러낸다.",
        "지원자 고유의 anchor를 보존하되, 고유명사 자체를 개성으로 착각하지 않는다.",
        "문항에 직접 답하고, 면접에서 그대로 설명할 수 있는 한국어로 쓴다.",
        "실제로 사용한 claim/research ID만 반환한다.",
    ]
    return (
        "<context>\n"
        + json.dumps(context, ensure_ascii=False)
        + "\n</context>\n<writing_principles>\n- "
        + "\n- ".join(principles)
        + "\n</writing_principles>\n<task>\n"
        + "선택된 argument route의 사실 의미는 바꾸지 말고 realization plan의 구조를 실제 산문에 반영해 "
        + "자기소개서 답변 하나를 작성한다. JSON은 blueprint_id, question_index, answer, "
        + "used_claim_ids, used_research_ids만 반환한다.\n</task>"
    )


def _sentences(text: str) -> list[str]:
    return [match.group(0).strip() for match in _SENTENCE.finditer(text) if match.group(0).strip()]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text)}


def realization_diagnostics(
    answer: str,
    *,
    anchor_texts: Sequence[str] = (),
    plan: RealizationPlan | None = None,
) -> dict[str, Any]:
    """Heuristic prose diagnostics; never factual authority or hiring prediction."""
    sentences = _sentences(answer)
    anchor_tokens = set().union(*(_tokens(text) for text in anchor_texts)) if anchor_texts else set()
    matched = _tokens(answer).intersection(anchor_tokens)
    anchored_sentences = 0
    if anchor_tokens:
        for sentence in sentences:
            if _tokens(sentence).intersection(anchor_tokens):
                anchored_sentences += 1
    sentence_count = len(sentences)
    replaceable_ratio = (
        1.0
        if sentence_count and not anchor_tokens
        else (1.0 - anchored_sentences / sentence_count if sentence_count else 1.0)
    )
    anchor_coverage = len(matched) / len(anchor_tokens) if anchor_tokens else 0.0
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "heuristic_only": True,
        "sentence_count": sentence_count,
        "distinctive_anchor_token_count": len(anchor_tokens),
        "distinctive_anchor_matched_token_count": len(matched),
        "distinctive_anchor_coverage": round(anchor_coverage, 6),
        "replaceable_sentence_ratio": round(max(0.0, min(1.0, replaceable_ratio)), 6),
        "genericity_risk": round(max(0.0, min(1.0, replaceable_ratio)), 6),
        "move_sequence": list(plan.move_sequence) if plan else [],
        "answer_latency": dict(plan.answer_latency) if plan else None,
    }
