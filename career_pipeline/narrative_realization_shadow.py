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

SCHEMA_VERSION = 2
POLICY_VERSION = "narrative_realization_shadow_v2"

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
    renderable_proof_items: tuple[KernelItem, ...]
    validation_constraints: tuple[KernelItem, ...]
    distinctive_anchor_refs: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    ownership_ceiling: str

    @property
    def proof_items(self) -> tuple[KernelItem, ...]:
        """Compatibility view containing only material that may be rendered.

        Schema v1 mixed route guardrails with prose evidence.  Callers that
        still use ``proof_items`` receive the safe, renderable subset, so a
        validation-only item can never re-enter a realization order by
        accident.
        """
        return self.renderable_proof_items


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
    renderable_proof_items: list[KernelItem] = []
    validation_constraints: list[KernelItem] = []
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
        item = KernelItem(
            proof_index=index,
            kind=kind,
            move=move,
            text=text,
            support_refs=refs,
            distinctive_anchor=bool(distinctive.intersection(refs)),
        )
        # A guardrail describes what the validator must enforce.  It is not
        # a sentence beat and must never be offered to the prose writer.
        if kind == "guardrail":
            validation_constraints.append(item)
        else:
            renderable_proof_items.append(item)

    if not renderable_proof_items:
        raise NarrativeRealizationError("route must contain renderable proof")

    gaps = _strings(route.get("evidence_gaps"))
    return NarrativeKernel(
        schema_version=SCHEMA_VERSION,
        policy_version=POLICY_VERSION,
        question_index=q,
        question_intent=normalize_intent(blueprint.get("intent") or route.get("intent")),
        prompt=str(blueprint.get("prompt", "")),
        route_id=route_id,
        thesis=thesis,
        thesis_support_refs=_strings(route.get("thesis_support_refs")),
        renderable_proof_items=tuple(renderable_proof_items),
        validation_constraints=tuple(validation_constraints),
        distinctive_anchor_refs=tuple(sorted(distinctive)),
        evidence_gaps=gaps,
        ownership_ceiling=ownership_ceiling,
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

    # A route can be fully defensible yet lack a named decision, tension, or
    # distinctive anchor.  Benchmark v2 still needs three genuinely different
    # supported orders; these use existing evidence functions rather than a
    # validation guardrail or an invented narrative premise.
    if "action" in kinds:
        order = _ranked_order(
            kernel,
            ("action", "judgment", "criterion", "friction", "context", "outcome", "reflection", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "action_first", order,
            "가장 구체적인 본인 행동으로 시작한 뒤, 그 행동의 판단 배경과 결과를 자연스럽게 연결한다.",
            "Opens with a route-approved applicant action when other narrative openings are scarce.",
        ))

    if "outcome" in kinds:
        order = _ranked_order(
            kernel,
            ("outcome", "friction", "judgment", "criterion", "action", "reflection", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "outcome_first", order,
            "확인된 변화나 산출물을 먼저 제시하고, 이를 만든 상황·판단·행동을 뒤에서 설명한다.",
            "Uses a route-approved outcome as a concise answer-first opening.",
        ))

    if "context" in kinds:
        order = _ranked_order(
            kernel,
            ("context", "friction", "judgment", "criterion", "action", "outcome", "reflection", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "context_first", order,
            "업무 상황을 짧게 제시한 뒤, 곧바로 본인의 판단과 행동으로 이어 간다.",
            "Uses an already-supported context without turning a validation boundary into prose.",
        ))

    if "reflection" in kinds:
        order = _ranked_order(
            kernel,
            ("reflection", "friction", "judgment", "action", "outcome", "fit_bridge"),
        )
        candidates.append(_plan(
            kernel, "reflection_first", order,
            "경험에서 얻은 구체적 판단을 먼저 제시하고, 그 판단이 형성된 장면과 행동을 이어 보인다.",
            "Uses an existing reflection rather than manufacturing a lesson.",
        ))

    # Last-resort structural expansion for a source-complete route: every
    # renderable proof item may be a factual opening, followed by the original
    # route order.  This is a change of emphasis only; it never creates a
    # guardrail-first or an unsupported rhetorical claim.
    route_order = tuple(item.proof_index for item in kernel.renderable_proof_items)
    for item in kernel.renderable_proof_items:
        order = (item.proof_index,) + tuple(index for index in route_order if index != item.proof_index)
        candidates.append(_plan(
            kernel,
            f"evidence_first_{item.kind}_{item.proof_index}",
            order,
            "선택된 사실 하나를 첫 문장에 제시한 뒤, 같은 근거를 원래의 논리 순서로 연결한다.",
            "Uses an existing proof item as the opening when a route needs another supported order.",
        ))

    # Preserve route order only when the route contains too little renderable
    # material to support any alternate opening.  The paired v2 runner uses a
    # separately constructed route-order control.
    if not candidates:
        order = route_order
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


def build_route_order_control_plan(kernel: NarrativeKernel) -> RealizationPlan:
    """Return the shared baseline realization order for benchmark v2.

    The control arm has no rhetorical-treatment advantage: it keeps the
    selected route order and varies only surface realization across its three
    candidates.
    """
    order = tuple(item.proof_index for item in kernel.renderable_proof_items)
    return _plan(
        kernel,
        "route_order_control",
        order,
        "선택된 근거의 순서를 유지해 질문에 바로 답하는 자연스러운 자기소개서로 쓴다.",
        "Shared route-order control for paired benchmark v2.",
    )


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
    experience = blueprint.get("experience")
    if not isinstance(experience, Mapping):
        experience = {}
    character_plan = blueprint.get("character_plan")
    if not isinstance(character_plan, Mapping):
        character_plan = {}
    hard_maximum = (
        blueprint.get("character_limit")
        or packet.get("character_limit")
        or character_plan.get("hard_maximum")
    )
    character_target = character_plan.get("target")
    selected_claims = experience.get("selected_claims", [])
    if not isinstance(selected_claims, Sequence) or isinstance(selected_claims, (str, bytes)):
        selected_claims = []
    observed_result = any(
        isinstance(claim, Mapping)
        and str(claim.get("contribution") or (claim.get("verification") or {}).get("contribution") or "").strip()
        in {"observed", "unknown"}
        for claim in selected_claims
    )
    selected_metrics = [
        str(claim.get("normalized_value", "")).strip()
        for claim in selected_claims
        if isinstance(claim, Mapping)
        and claim.get("is_metric") is True
        and str(claim.get("normalized_value", "")).strip()
    ]
    required_metric_ids = {
        str(value)
        for value in experience.get("required_metric_claim_ids", []) or []
    }
    actor_result_guidance = (
        "과거 경험에서는 본인이 한 행동을 먼저 쓰고, 이후 나타난 변화는 별도 문장에서 관찰된 결과로 제시합니다."
        if observed_result else
        "과거 경험에서는 본인이 한 행동과 그 행동의 결과를 각각 분명한 주어로 씁니다."
    )
    facts = {
        "target_role": packet.get("target"),
        "question": blueprint.get("prompt"),
        "question_index": blueprint.get("question_index"),
        "character_limit": {
            "count_mode": character_plan.get("count_mode"),
            "target": character_target,
            "hard_maximum": hard_maximum,
        },
        "job_connection": {
            "target": packet.get("target"),
            "matched_duties": experience.get("matched_duties", []),
            "matched_competencies": experience.get("matched_competencies", []),
        },
        "applicant_role": experience.get("role") or experience.get("position"),
        "allowed_claims": selected_claims,
        "actor_and_result": {
            "applicant": "지원자 본인",
            "past_result_expression": actor_result_guidance,
        },
        "allowed_research": blueprint.get("research_claims", []),
        "thesis": kernel.thesis,
        "proof_order": ordered_proof(kernel, plan),
    }
    output_contract = {
        "blueprint_id": blueprint.get("blueprint_id"),
        "question_index": blueprint.get("question_index"),
        "required_keys": [
            "blueprint_id", "question_index", "answer", "used_claim_ids", "used_research_ids"
        ],
    }
    latency = plan.answer_latency
    length_goal = (
        f"공백 제외 약 {character_target}자, 최대 {hard_maximum}자"
        if character_target and hard_maximum
        else (f"최대 {hard_maximum}자" if hard_maximum else "문항 분량")
    )
    metric_goal = (
        "- required_metric_claim_ids의 승인 수치를 모두 표기 그대로 본문에 사용합니다.\n"
        if required_metric_ids
        else "- selected_claims의 승인 수치 중 최소 한 개를 표기 그대로 본문에 사용합니다.\n"
        if selected_metrics else ""
    )
    return (
        "Role:\n한국어 공공기관 자기소개서 편집자입니다.\n\n"
        "# Goal\n제공된 사실만으로 질문에 직접 답하는 자연스러운 자기소개서 본문을 작성합니다.\n\n"
        "# Success Criteria\n"
        f"- 핵심 판단·행동을 {latency['max_sentence']}번째 문장 안에 보여 줍니다.\n"
        "- 본인 행동, 협업 결과, 관찰된 변화의 주어와 동사를 정확히 씁니다.\n"
        + metric_goal
        +
        f"- {actor_result_guidance}\n"
        f"- 분량은 {length_goal}에 맞춥니다.\n"
        "- 면접에서 그대로 말할 수 있는 자연스러운 한국어 문단을 만듭니다.\n\n"
        "# Constraints\n"
        "- 제공된 사실 밖의 수치·날짜·동기·결과를 보태지 않습니다.\n"
        "- 수치와 기간은 allowed_facts에 있는 표기를 그대로 사용합니다.\n"
        "- 작성 과정이나 사실 확인 과정을 독자에게 설명하지 않습니다.\n"
        "- 서사 순서는 아래 proof_order를 따르되, 소제목처럼 나열하지 않습니다.\n\n"
        "# Output\n본문과 사용한 근거 ID만 JSON으로 반환합니다.\n\n"
        "# Stop Rules\n필요한 사실이 없으면 추정하지 말고 제공된 사실로 답변을 완성합니다.\n\n"
        "<allowed_facts>\n"
        + json.dumps(facts, ensure_ascii=False)
        + "\n</allowed_facts>\n<output_contract>\n"
        + json.dumps(output_contract, ensure_ascii=False)
        + "\n</output_contract>"
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
