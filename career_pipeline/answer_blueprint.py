"""Deterministic narrative planning for evidence-grounded Korean self-introductions.

The module deliberately stops before prose generation.  It converts a posting,
confirmed experience ledger, question/experience matches, and official research
claims into a compact intermediate representation (IR).  A model can then draft
from this IR instead of improvising directly from a large evidence packet.

Design goals:
- question semantics before keywords;
- portfolio-level experience allocation rather than greedy per-question reuse;
- claim-bounded evidence selection;
- character budget allocation before prose;
- explicit narrative beats and interview-defense constraints;
- no new factual authority: the downstream validators remain authoritative.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import itertools
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from .research_evidence import needs_research


SCHEMA_VERSION = 1
TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
METRIC = re.compile(r"(?<![A-Za-z0-9])[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|건|명|원|만원|억원|페이지|시간|일|개월|회)(?![A-Za-z0-9])")

_STOPWORDS = {
    "자기소개서", "지원자", "지원", "관련", "대하여", "대한", "본인의", "본인", "경험",
    "사례", "업무", "직무", "기관", "회사", "조직", "과정", "내용", "작성", "설명",
}
_PARTICLES = (
    "으로부터", "에서부터", "에게서", "으로써", "으로", "에서", "에게", "까지", "부터",
    "처럼", "보다", "하고", "하며", "해서", "하는", "한", "할", "했던", "께서", "의", "을",
    "를", "이", "가", "은", "는", "에", "와", "과", "도", "로",
)

_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("issue_analysis", ("시사", "이슈", "현안", "사회문제", "경제", "약식논술", "논술")),
    ("motivation", ("지원동기", "지원 동기", "지원한 이유", "지원하게 된", "선택한 이유")),
    ("job_plan", ("업무수행계획", "직무수행계획", "근무계획", "직무계획", "입사 후 계획")),
    ("adaptation", ("새로운 조직", "적응", "낯선 조직", "새 환경")),
    ("collaboration", ("협업", "협력", "갈등", "팀워크", "의견 차이", "조율")),
    ("problem_solving", ("문제해결", "문제 해결", "개선", "어려움", "새로운 접근", "해결한")),
    ("growth", ("부족", "실패", "배운 점", "성장", "보완", "개선한 점")),
    ("integrity", ("윤리", "원칙", "책임감", "신뢰", "정직", "규정")),
    ("competency", ("강점", "역량", "능력", "전문성", "직무역량", "경쟁력")),
)

_REQUIREMENT_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("reason", ("이유", "동기", "왜", "계기"), "선택·판단의 이유를 답한다."),
    ("action", ("어떻게", "행동", "노력", "수행", "과정"), "본인이 실제로 한 행동을 구체화한다."),
    ("result", ("결과", "성과", "변화", "효과"), "행동 이후 확인된 결과·변화를 제시한다."),
    ("lesson", ("배운", "느낀", "교훈", "깨달"), "경험에서 얻은 판단 기준 또는 변화가 드러나야 한다."),
    ("contribution", ("기여", "입사 후", "활용"), "지원 직무에서의 현실적인 적용 행동을 제시한다."),
    ("learning", ("배우", "학습", "성장"), "무엇을 어떤 순서로 익힐지 제시한다."),
    ("collaboration", ("협업", "갈등", "팀", "조율"), "상대·쟁점·조율 행동과 합의 결과를 제시한다."),
    ("criteria", ("기준", "판단", "선택"), "선택 기준과 그 기준을 적용한 이유를 제시한다."),
    ("cause", ("원인", "왜 발생", "배경"), "원인과 작동 메커니즘을 구분해 설명한다."),
    ("impact", ("영향", "문제점", "위험"), "누구에게 어떤 경로로 영향이 발생하는지 설명한다."),
    ("response", ("대응", "해결방안", "방안", "역할"), "대응 수단과 부작용·한계를 함께 다룬다."),
)

_INTENT_PATTERNS: dict[str, tuple[tuple[str, float], ...]] = {
    "motivation": (
        ("direct_answer", 0.14), ("personal_criterion", 0.19), ("company_fact", 0.17),
        ("proof_of_fit", 0.27), ("job_bridge", 0.15), ("closing", 0.08),
    ),
    "adaptation": (
        ("direct_answer", 0.13), ("scene", 0.15), ("judgment", 0.16),
        ("action", 0.28), ("result", 0.15), ("transfer", 0.13),
    ),
    "collaboration": (
        ("direct_answer", 0.11), ("conflict_context", 0.16), ("stakeholder_view", 0.12),
        ("coordination_action", 0.29), ("result", 0.16), ("lesson_transfer", 0.16),
    ),
    "problem_solving": (
        ("direct_answer", 0.10), ("problem_definition", 0.14), ("diagnosis", 0.16),
        ("decision", 0.13), ("action", 0.25), ("result", 0.13), ("learning", 0.09),
    ),
    "growth": (
        ("direct_answer", 0.11), ("failure_or_gap", 0.18), ("cause_reflection", 0.17),
        ("change_action", 0.27), ("verified_change", 0.14), ("current_standard", 0.13),
    ),
    "integrity": (
        ("direct_answer", 0.12), ("pressure_or_tradeoff", 0.17), ("principle", 0.14),
        ("action", 0.27), ("result", 0.13), ("job_transfer", 0.17),
    ),
    "competency": (
        ("direct_answer", 0.12), ("competency_definition", 0.10), ("scene", 0.14),
        ("action", 0.28), ("result", 0.14), ("job_bridge", 0.22),
    ),
    "job_plan": (
        ("priority", 0.12), ("learning_sequence", 0.20), ("execution_control", 0.27),
        ("escalation_rule", 0.14), ("customer_or_peer_handoff", 0.12), ("improvement_loop", 0.15),
    ),
    "issue_analysis": (
        ("one_issue_position", 0.10), ("mechanism", 0.24), ("affected_group", 0.13),
        ("policy_tradeoff", 0.19), ("institution_response", 0.22), ("guardrail", 0.12),
    ),
    "general_experience": (
        ("direct_answer", 0.11), ("scene", 0.16), ("judgment", 0.14),
        ("action", 0.29), ("result", 0.16), ("meaning", 0.14),
    ),
}

_BEAT_GUIDANCE = {
    "direct_answer": "첫 1~2문장에 문항의 질문에 바로 답한다. 배경 설명으로 시작하지 않는다.",
    "personal_criterion": "기관 칭찬이 아니라 본인이 중요하게 보는 선택 기준·문제의식·경험의 연결점을 둔다.",
    "company_fact": "검증된 기관 고유 사실 1개만 사용하고, 홍보문구 나열을 피한다.",
    "proof_of_fit": "선택 기준을 뒷받침하는 본인의 확정 경험·행동을 한 장면으로 보여준다.",
    "job_bridge": "경험에서 확인된 행동 방식을 실제 공고 업무의 행동 단위로 번역한다.",
    "closing": "'기여하겠습니다'만 남기지 말고 초기 행동 또는 학습 기준으로 끝낸다.",
    "scene": "상황 설명은 필요한 맥락만 남기고 문제·대상·제약을 압축한다.",
    "judgment": "무엇을 먼저 보거나 왜 그 순서를 택했는지 근거가 있을 때만 제시한다.",
    "action": "본인이 직접 한 행동을 대상·도구·순서가 보이게 쓴다.",
    "result": "확인된 결과만 쓰고 기여 범위를 넘어 인과를 확대하지 않는다.",
    "transfer": "과거 행동의 원리를 새 직무의 구체 행동으로 연결한다.",
    "conflict_context": "사람 성격이 아니라 서로 다른 목표·정보·제약을 쟁점으로 정의한다.",
    "stakeholder_view": "상대 관점을 추측하지 말고 실제 확인한 요구·제약만 적는다.",
    "coordination_action": "경청·공유 같은 추상어 대신 어떤 자료·기준·대안을 제시했는지 쓴다.",
    "lesson_transfer": "배운 점을 성격 미사여구가 아니라 이후의 판단 기준으로 표현한다.",
    "problem_definition": "증상과 원인을 구분하고, 해결해야 할 핵심 문제를 한 문장으로 좁힌다.",
    "diagnosis": "확인·비교·분석을 무엇과 무엇 사이에서 했는지 드러낸다.",
    "decision": "대안 중 선택했다면 기준과 포기한 것을 함께 드러낸다. 근거가 없으면 발명하지 않는다.",
    "learning": "결과 뒤에 이후 바뀐 행동이나 재사용 가능한 원칙을 남긴다.",
    "failure_or_gap": "실패를 포장하지 말고 본인의 부족했던 판단·행동 범위를 특정한다.",
    "cause_reflection": "외부 탓보다 자신이 통제할 수 있었던 원인을 분리한다.",
    "change_action": "보완을 위해 새로 만든 절차·도구·습관을 구체화한다.",
    "verified_change": "개선 결과는 근거가 있는 변화만 사용한다.",
    "current_standard": "현재 반복해서 적용하는 기준으로 마무리한다.",
    "pressure_or_tradeoff": "원칙을 지키기 어려웠던 실제 압력·상충 조건을 드러낸다.",
    "principle": "원칙을 선언하는 데 그치지 말고 판단 기준으로 정의한다.",
    "job_transfer": "직무의 실제 책임·권한 범위 안에서 원칙을 어떻게 적용할지 쓴다.",
    "competency_definition": "역량 이름보다 그 역량을 구성하는 관찰 가능한 행동을 정의한다.",
    "priority": "입사 후 모든 것을 하겠다고 하지 말고 초기 우선순위를 하나 정한다.",
    "learning_sequence": "규정/목적 이해 → 예시 관찰 → 직접 수행 → 피드백 반영처럼 학습 순서를 설계한다.",
    "execution_control": "확인·대조를 반복 나열하지 말고 오류가 발생하기 쉬운 지점과 통제 방법을 연결한다.",
    "escalation_rule": "인턴 권한 밖의 판단을 언제 누구에게 어떤 근거로 보고할지 정한다.",
    "customer_or_peer_handoff": "고객 안내·동료 인계 시 남겨야 할 정보와 이유를 구체화한다.",
    "improvement_loop": "충분히 익힌 뒤 반복 오류를 관찰하고 작은 개선안을 검증하는 순서를 둔다.",
    "one_issue_position": "문항이 하나를 요구하면 선택 문장에서 이슈를 정확히 하나만 명명한다.",
    "mechanism": "현상 나열이 아니라 원인→전달 경로→기업/고객 영향의 인과사슬을 설명한다.",
    "affected_group": "누가 왜 더 취약한지 조건을 구분한다.",
    "policy_tradeoff": "지원 확대의 편익과 재원·도덕적 해이·선별 오류 같은 비용을 함께 다룬다.",
    "institution_response": "기관이 실제 수행 가능한 역할과 공고/공식근거에 확인된 수단만 연결한다.",
    "guardrail": "속도와 건전성, 지원과 사후관리 사이의 통제 기준을 제시한다.",
    "meaning": "경험의 의미를 지원 직무나 이후 행동 변화와 연결한다.",
}

_GENERIC_ACTIONS = {
    "확인", "정리", "관리", "지원", "업무", "처리", "수행", "진행", "노력", "소통", "협업",
}


def _norm_tokens(value: str) -> set[str]:
    result: set[str] = set()
    for raw in TOKEN.findall(value or ""):
        token = raw.casefold()
        for particle in _PARTICLES:
            if len(token) >= len(particle) + 2 and token.endswith(particle):
                token = token[: -len(particle)]
                break
        if token and token not in _STOPWORDS:
            result.add(token)
    return result


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(prefix: str, value: Any, length: int = 20) -> str:
    return f"{prefix}_{sha256(_canonical(value)).hexdigest()[:length]}"


def _question_row(question: Any) -> dict[str, Any]:
    if isinstance(question, Mapping):
        row = dict(question)
    else:
        row = {
            key: getattr(question, key)
            for key in ("index", "prompt", "character_limit", "count_mode", "minimum_character_limit")
            if hasattr(question, key)
        }
    return {
        "index": int(row["index"]),
        "prompt": str(row.get("prompt", "")),
        "character_limit": row.get("character_limit"),
        "count_mode": str(row.get("count_mode", "spaces_included")),
        "minimum_character_limit": row.get("minimum_character_limit"),
    }


def classify_question(prompt: str) -> str:
    compact = re.sub(r"\s+", "", prompt)
    for intent, markers in _INTENT_RULES:
        if any(marker.replace(" ", "") in compact for marker in markers):
            return intent
    return "general_experience"


def _prompt_requirements(prompt: str) -> list[dict[str, Any]]:
    compact = re.sub(r"\s+", "", prompt)
    requirements = [
        {
            "requirement_id": "direct_answer",
            "description": "문항의 핵심 질문에 첫 1~2문장 안에서 직접 답한다.",
            "hard": True,
        }
    ]
    for requirement_id, markers, description in _REQUIREMENT_RULES:
        if any(marker.replace(" ", "") in compact for marker in markers):
            requirements.append(
                {"requirement_id": requirement_id, "description": description, "hard": True}
            )
    return requirements


def _selection_cardinality(prompt: str) -> int | None:
    compact = re.sub(r"\s+", "", prompt)
    patterns = (
        r"(?:한|1)(?:가지|개)(?:를|의|만|로)?",
        r"가장[^,.!?]{0,20}(?:하나|1개|한가지)",
        r"하나를선택",
    )
    return 1 if any(re.search(pattern, compact) for pattern in patterns) else None


def _experience_mode(intent: str, prompt: str) -> str:
    if intent == "issue_analysis":
        return "none"
    if any(marker in prompt for marker in ("경험", "사례", "했던", "수행한", "해결한", "갈등", "협업")):
        return "required"
    if intent in {"motivation", "job_plan", "competency", "adaptation"}:
        return "preferred"
    return "required"


def _research_mode(intent: str, prompt: str) -> str:
    # This must share the validator's policy.  A prompt cannot be planned as
    # research-free and then be rejected after prose generation for lacking an
    # official reference.
    if needs_research(prompt):
        return "required"
    if intent == "issue_analysis":
        return "required"
    if intent in {"motivation", "job_plan"}:
        return "required"
    if any(marker in prompt for marker in ("기관", "회사", "사업", "직무", "업무")):
        return "preferred"
    return "none"


def _target_character_plan(question: Mapping[str, Any]) -> dict[str, Any]:
    limit = question.get("character_limit")
    minimum = question.get("minimum_character_limit")
    if not isinstance(limit, int) or limit < 1:
        return {
            "count_mode": question.get("count_mode", "spaces_included"),
            "hard_maximum": None,
            "quality_minimum": minimum if isinstance(minimum, int) else None,
            "target": None,
        }
    quality_minimum = max(
        minimum if isinstance(minimum, int) else 0,
        round(limit * (0.84 if limit <= 800 else 0.80)),
    )
    target = min(limit, max(quality_minimum, round(limit * 0.90)))
    return {
        "count_mode": question.get("count_mode", "spaces_included"),
        "hard_maximum": limit,
        "quality_minimum": quality_minimum,
        "target": target,
    }


def _allocate_beats(intent: str, character_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    pattern = _INTENT_PATTERNS[intent]
    target = character_plan.get("target")
    budgets: list[int | None]
    if isinstance(target, int):
        raw = [target * ratio for _, ratio in pattern]
        budgets = [max(1, math.floor(value)) for value in raw]
        remainder = target - sum(budgets)
        for index in itertools.cycle(range(len(budgets))):
            if remainder <= 0:
                break
            budgets[index] += 1
            remainder -= 1
    else:
        budgets = [None] * len(pattern)
    return [
        {
            "beat": beat,
            "character_budget": budget,
            "guidance": _BEAT_GUIDANCE[beat],
        }
        for (beat, _), budget in zip(pattern, budgets)
    ]


def _experience_map(ledger: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in ledger.get("experiences", []) or []:
        if not isinstance(raw, Mapping) or raw.get("status") != "confirmed":
            continue
        experience_id = str(raw.get("experience_id", "")).strip()
        if experience_id:
            result[experience_id] = dict(raw)
    return result


def _is_metric_claim(claim: Mapping[str, Any]) -> bool:
    value = str(claim.get("normalized_value", ""))
    return bool(METRIC.search(value)) or str(claim.get("field", "")).startswith("metric:")


def _claim_safe_for_planning(claim: Mapping[str, Any]) -> bool:
    """Conservative pre-filter; downstream profile validation remains authoritative."""
    if claim.get("status") != "confirmed" or not claim.get("evidence"):
        return False
    if not _is_metric_claim(claim):
        return True
    verification = claim.get("verification")
    if not isinstance(verification, Mapping):
        return False
    method = str(verification.get("method", "none"))
    contribution = str(verification.get("contribution", "unknown"))
    if method == "none" or contribution not in {"observed", "contributed", "caused"}:
        return False
    if not str(verification.get("scope", "")).strip():
        return False
    value = str(claim.get("normalized_value", ""))
    if "%" in value:
        return (
            method == "before_after"
            and bool(verification.get("baseline"))
            and bool(verification.get("result"))
            and bool(verification.get("formula"))
        )
    if method == "direct_count" and not verification.get("measurement_period"):
        return False
    return True


def _safe_claims(experience: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(claim)
        for claim in experience.get("claims", []) or []
        if isinstance(claim, Mapping) and _claim_safe_for_planning(claim)
    ]


def _story_completeness(experience: Mapping[str, Any]) -> int:
    score = 0
    if str(experience.get("situation", "")).strip():
        score += 3
    actions = [str(item).strip() for item in experience.get("actions", []) or [] if str(item).strip()]
    outcomes = [str(item).strip() for item in experience.get("outcomes", []) or [] if str(item).strip()]
    score += min(6, len(actions) * 2)
    score += min(4, len(outcomes) * 2)
    score += min(6, len(_safe_claims(experience)) * 2)
    if str(experience.get("role", "")).strip():
        score += 2
    return score


def _specific_action(experience: Mapping[str, Any]) -> str | None:
    best: tuple[int, str] | None = None
    for raw in experience.get("actions", []) or []:
        action = str(raw).strip()
        if not action:
            continue
        tokens = _norm_tokens(action)
        generic = sum(token in _GENERIC_ACTIONS for token in tokens)
        score = len(tokens) * 3 - generic * 2 + min(8, len(action) // 12)
        if METRIC.search(action):
            # Numbers in action prose are context only unless an allowed claim authorizes them.
            score -= 2
        if best is None or score > best[0]:
            best = (score, action)
    return best[1] if best else None


def _match_rows(matches: Iterable[Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for raw in matches:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        question = row.get("question")
        if isinstance(question, Mapping):
            index = question.get("index")
        else:
            index = row.get("question_index")
        if isinstance(index, int):
            result[index] = row
    return result


def _persuasion_evidence_score(
    question: Mapping[str, Any], experience: Mapping[str, Any]
) -> int:
    """Prefer an accepted proposal over one-way guidance for persuasion prompts."""
    prompt = str(question.get("prompt", ""))
    if not re.search(r"설득|생각이나 의견|의견으로", prompt):
        return 0
    actions = " ".join(str(item) for item in experience.get("actions", []) or [])
    outcomes = " ".join(str(item) for item in experience.get("outcomes", []) or [])
    role = str(experience.get("role", ""))
    proposed = any(token in actions + " " + role for token in ("제안", "의견", "방안"))
    accepted = any(token in outcomes + " " + role for token in ("채택", "반영", "수용"))
    implemented = any(token in actions + " " + outcomes for token in ("실행", "부착", "재분류", "적용"))
    if proposed and accepted:
        return 90 + (10 if implemented else 0)
    if proposed:
        return 25
    return 5 if "설명" in actions else 0


def _candidate_options(
    question: Mapping[str, Any],
    intent: str,
    match: Mapping[str, Any] | None,
    experiences: Mapping[str, Mapping[str, Any]],
    posting: Mapping[str, Any],
) -> list[dict[str, Any]]:
    prompt_tokens = _norm_tokens(str(question.get("prompt", "")))
    job_tokens = set()
    for key in ("duties", "competencies"):
        for value in posting.get(key, []) or []:
            job_tokens.update(_norm_tokens(str(value)))
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_candidates = match.get("candidates", []) if isinstance(match, Mapping) else []
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        raw_candidates = []
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            continue
        experience_id = str(raw.get("experience_id", "")).strip()
        experience = experiences.get(experience_id)
        if not experience:
            continue
        text = " ".join(
            [
                str(experience.get("title", "")),
                str(experience.get("role", "")),
                str(experience.get("situation", "")),
                *[str(item) for item in experience.get("actions", []) or []],
                *[str(item) for item in experience.get("outcomes", []) or []],
                *[str(item) for item in experience.get("competencies", []) or []],
            ]
        )
        exp_tokens = _norm_tokens(text)
        semantic_overlap = (
            len(exp_tokens & prompt_tokens) * 3
            + len(exp_tokens & job_tokens)
            + _persuasion_evidence_score(question, experience)
        )
        base = int(raw.get("total_score", 0))
        score = base + _story_completeness(experience) + semantic_overlap
        candidates.append(
            {
                "experience_id": experience_id,
                "score": score,
                "base_match_score": base,
                "matched_duties": list(raw.get("matched_duties", []) or []),
                "matched_competencies": list(raw.get("matched_competencies", []) or []),
                "story_completeness": _story_completeness(experience),
            }
        )
        seen.add(experience_id)
    # Fall back to confirmed experiences so a sparse/missing matching artifact does not
    # collapse planning.  These options score lower than an actual match unless their
    # story/evidence quality is clearly stronger.
    for experience_id, experience in experiences.items():
        if experience_id in seen:
            continue
        text = " ".join(
            [
                str(experience.get("title", "")), str(experience.get("role", "")),
                str(experience.get("situation", "")),
                *[str(item) for item in experience.get("actions", []) or []],
                *[str(item) for item in experience.get("outcomes", []) or []],
                *[str(item) for item in experience.get("competencies", []) or []],
            ]
        )
        overlap = len(_norm_tokens(text) & (prompt_tokens | job_tokens))
        candidates.append(
            {
                "experience_id": experience_id,
                "score": (
                    _story_completeness(experience)
                    + overlap * 2
                    + _persuasion_evidence_score(question, experience)
                ),
                "base_match_score": 0,
                "matched_duties": [],
                "matched_competencies": [],
                "story_completeness": _story_completeness(experience),
            }
        )
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["experience_id"])))
    return candidates[:5]


def _portfolio_assignment(
    questions: list[dict[str, Any]],
    intents: Mapping[int, str],
    experience_modes: Mapping[int, str],
    match_by_index: Mapping[int, Mapping[str, Any]],
    experiences: Mapping[str, Mapping[str, Any]],
    posting: Mapping[str, Any],
) -> tuple[dict[int, str | None], dict[int, list[dict[str, Any]]]]:
    options_by_index: dict[int, list[dict[str, Any]]] = {}
    states: list[tuple[float, dict[int, str | None], Counter[str]]] = [(0.0, {}, Counter())]
    for question in questions:
        index = int(question["index"])
        mode = experience_modes[index]
        if mode == "none":
            options: list[dict[str, Any]] = []
        else:
            options = _candidate_options(
                question,
                intents[index],
                match_by_index.get(index),
                experiences,
                posting,
            )
        options_by_index[index] = options
        choices: list[dict[str, Any] | None] = list(options)
        if mode == "preferred":
            choices.append(None)
        if mode == "required" and not choices:
            choices = [None]
        if mode == "none":
            choices = [None]

        next_states: list[tuple[float, dict[int, str | None], Counter[str]]] = []
        for score, assignment, used in states:
            for option in choices:
                if option is None:
                    option_score = -25.0 if mode == "required" else -3.0 if mode == "preferred" else 0.0
                    experience_id = None
                else:
                    experience_id = str(option["experience_id"])
                    prior = used[experience_id]
                    reuse_penalty = 26 * prior + 10 * max(0, prior - 1)
                    diversity_bonus = 6 if prior == 0 else 0
                    option_score = float(option["score"]) + diversity_bonus - reuse_penalty
                new_assignment = dict(assignment)
                new_assignment[index] = experience_id
                new_used = used.copy()
                if experience_id:
                    new_used[experience_id] += 1
                next_states.append((score + option_score, new_assignment, new_used))
        next_states.sort(
            key=lambda item: (
                -item[0],
                sum(max(0, count - 1) for count in item[2].values()),
                tuple(sorted((key, value or "") for key, value in item[1].items())),
            )
        )
        states = next_states[:192]
    return (states[0][1] if states else {}), options_by_index


def _select_claims(
    experience: Mapping[str, Any],
    question: Mapping[str, Any],
    posting: Mapping[str, Any],
    *,
    maximum: int = 3,
) -> list[dict[str, Any]]:
    prompt_tokens = _norm_tokens(str(question.get("prompt", "")))
    job_tokens = set()
    for key in ("duties", "competencies"):
        for item in posting.get(key, []) or []:
            job_tokens.update(_norm_tokens(str(item)))
    ranked: list[tuple[int, dict[str, Any]]] = []
    for claim in _safe_claims(experience):
        claim_text = f"{claim.get('field', '')} {claim.get('normalized_value', '')}"
        tokens = _norm_tokens(claim_text)
        verification = claim.get("verification") if isinstance(claim.get("verification"), Mapping) else {}
        contribution = str(verification.get("contribution", "unknown"))
        score = len(tokens & prompt_tokens) * 5 + len(tokens & job_tokens) * 2
        score += 4 if _is_metric_claim(claim) else 2
        score += 2 if contribution in {"contributed", "caused"} else 0
        ranked.append((score, claim))
    ranked.sort(
        key=lambda item: (
            -item[0], str(item[1].get("field", "")), str(item[1].get("claim_id", ""))
        )
    )
    selected: list[dict[str, Any]] = []
    selected_metric_values: set[str] = set()
    for _score, claim in ranked:
        if _is_metric_claim(claim):
            metric_value = re.sub(
                r"[\s,]", "", str(claim.get("normalized_value", "")).lower()
            )
            if metric_value in selected_metric_values:
                continue
            selected_metric_values.add(metric_value)
        selected.append(dict(claim))
        if len(selected) >= maximum:
            break
    return selected


def _required_metric_claim_ids(
    question: Mapping[str, Any], selected_claims: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Require every selected scale/duration metric for achievement prompts."""
    prompt = re.sub(r"\s+", "", str(question.get("prompt", "")))
    if not any(
        cue in prompt
        for cue in ("목표", "성과", "달성", "완료", "기한", "분량", "규모")
    ):
        return []
    return [
        str(claim.get("claim_id", ""))
        for claim in selected_claims
        if _is_metric_claim(claim) and str(claim.get("claim_id", "")).strip()
    ]


def _research_claim_type_preferences(intent: str) -> tuple[str, ...]:
    if intent == "issue_analysis":
        return ("industry_issue", "risk_or_limit", "program_or_service", "organization_role")
    if intent == "motivation":
        return ("organization_role", "program_or_service", "job_duty")
    if intent == "job_plan":
        return ("job_duty", "program_or_service", "organization_role")
    return ("job_duty", "program_or_service", "organization_role", "selection_criteria")


def _application_use_score(value: str, question_index: int) -> int:
    compact = re.sub(r"\s+", "", value or "")
    if "전체문항" in compact or "공통문항" in compact:
        return 4
    if re.search(rf"문항[^\d]{{0,3}}{question_index}(?!\d)", compact):
        return 8
    return 0


def _select_research_claims(
    question: Mapping[str, Any],
    intent: str,
    research_mode: str,
    claims: Sequence[Mapping[str, Any]],
    target: str,
) -> list[dict[str, Any]]:
    if research_mode == "none":
        return []
    prompt_tokens = _norm_tokens(str(question.get("prompt", "")) + " " + target)
    preferred = _research_claim_type_preferences(intent)
    rank_by_type = {claim_type: len(preferred) - index for index, claim_type in enumerate(preferred)}
    ranked: list[tuple[int, Mapping[str, Any]]] = []
    for claim in claims:
        if str(claim.get("verification_status", "confirmed")) not in {"confirmed", "verified"}:
            continue
        claim_id = str(claim.get("claim_id", "")).strip()
        text = str(claim.get("claim", "")).strip()
        if not claim_id or not text:
            continue
        claim_type = str(claim.get("claim_type", "unspecified"))
        score = rank_by_type.get(claim_type, 0) * 5
        score += _application_use_score(str(claim.get("application_use", "")), int(question["index"]))
        score += len(_norm_tokens(text) & prompt_tokens)
        if str(claim.get("evidence_excerpt", "")).strip():
            score += 2
        ranked.append((score, claim))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("claim_id", ""))))
    maximum = 2 if intent == "issue_analysis" else 1
    selected = [dict(item[1]) for item in ranked[:maximum] if item[0] > 0]
    if research_mode == "required" and not selected and ranked:
        selected = [dict(ranked[0][1])]
    return selected


def _claim_contract(claim: Mapping[str, Any]) -> dict[str, Any]:
    verification = claim.get("verification") if isinstance(claim.get("verification"), Mapping) else {}
    return {
        "claim_id": str(claim.get("claim_id", "")),
        "field": str(claim.get("field", "")),
        "normalized_value": str(claim.get("normalized_value", "")),
        "is_metric": _is_metric_claim(claim),
        "verification_method": str(verification.get("method", "none")),
        "contribution": str(verification.get("contribution", "unknown")),
        "scope": verification.get("scope"),
        "evidence_paths": sorted({
            str(item.get("source_path", ""))
            for item in claim.get("evidence", []) or []
            if isinstance(item, Mapping) and str(item.get("source_path", "")).strip()
        }),
        "causal_language": (
            "caused_only_for_this_claim" if verification.get("contribution") == "caused"
            else "contribution_only" if verification.get("contribution") == "contributed"
            else "observation_only"
        ),
    }


def _experience_contract(
    experience: Mapping[str, Any],
    selected_claims: Sequence[Mapping[str, Any]],
    option: Mapping[str, Any] | None,
    required_metric_claim_ids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "experience_id": str(experience.get("experience_id", "")),
        "title": str(experience.get("title", "")),
        "role": str(experience.get("role", "")),
        "situation": str(experience.get("situation", "")),
        "actions": [str(item) for item in experience.get("actions", []) or []],
        "outcomes": [str(item) for item in experience.get("outcomes", []) or []],
        "competencies": [str(item) for item in experience.get("competencies", []) or []],
        "signature_action": _specific_action(experience),
        "selected_claims": [_claim_contract(claim) for claim in selected_claims],
        "required_metric_claim_ids": list(required_metric_claim_ids),
        "matched_duties": list(option.get("matched_duties", []) if option else []),
        "matched_competencies": list(option.get("matched_competencies", []) if option else []),
        "numeric_context_rule": (
            "Numbers found only in situation/actions/outcomes are context, not submission authority. "
            "Use a number only when selected_claims authorizes the exact normalized value."
        ),
    }


def _research_contract(claim: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": str(claim.get("claim_id", "")),
        "claim": str(claim.get("claim", "")),
        "claim_type": str(claim.get("claim_type", "unspecified")),
        "evidence_excerpt": str(claim.get("evidence_excerpt", "")),
        "checked_at": str(claim.get("checked_at", "")),
        "basis_date": str(claim.get("basis_date", "")),
        "application_use": str(claim.get("application_use", "")),
        "source_url": str(claim.get("source_url", "")),
    }


def _blueprint_risks(intent: str, cardinality: int | None) -> list[str]:
    risks = [
        "Do not invent a motive, decision rationale, result, duty, company fact, or number that is absent from the packet.",
        "Do not turn an observed/contributed outcome into sole personal causation.",
        "Do not use writing guidance or model knowledge as factual evidence.",
        "Do not pad the answer with generic promises merely to fill the character limit.",
        "Do not repeat the same opening, closing, or generic action chain across questions.",
    ]
    if intent == "motivation":
        risks.extend(
            [
                "Do not open with a brochure-style description of the organization.",
                "Do not make organization praise substitute for the applicant's personal selection criterion.",
            ]
        )
    if intent == "job_plan":
        risks.append(
            "Do not write a checklist manual made only of 확인/대조/기록/보고; explain priority, failure points, and escalation logic."
        )
    if intent == "issue_analysis":
        risks.extend(
            [
                "Do not list many issues. Build one causal mechanism and one bounded policy position.",
                "Do not present a plausible policy instrument as an existing institution program unless an official research claim supports it.",
            ]
        )
    if cardinality == 1:
        risks.append("The prompt selects exactly one item; name exactly one selected item in the thesis.")
    return risks


def _defense_questions(intent: str, experience: Mapping[str, Any] | None, claims: Sequence[Mapping[str, Any]]) -> list[str]:
    questions = [
        "이 답변의 핵심 주장을 20초 안에 다시 말하면 무엇인가?",
        "답변에서 본인이 직접 한 행동과 타인의 행동을 어디까지 구분할 수 있는가?",
    ]
    if experience is not None:
        questions.append("이 경험에서 가장 어려웠던 판단 또는 확인 지점은 무엇이었는가?")
    if any(_is_metric_claim(claim) for claim in claims):
        questions.append("사용한 수치의 범위·산식·측정 기간·개인 기여도를 설명할 수 있는가?")
    if intent in {"motivation", "job_plan"}:
        questions.append("기관 고유 사실을 빼도 지원자의 선택 기준과 직무 연결 논리가 남는가?")
    if intent == "issue_analysis":
        questions.append("반대 관점에서 가장 강한 반론은 무엇이며 어떤 조건에서 수용할 것인가?")
    return questions


def build_answer_blueprint_packet(
    questions: Iterable[Any],
    *,
    target: str,
    posting: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
    matches: Iterable[Any] = (),
    research_claims: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the portfolio-level narrative IR.

    The result is deterministic for the same inputs.  It does not authorize any
    fact by itself; claim/reference validation must still run after drafting.
    """
    question_rows = sorted((_question_row(item) for item in questions), key=lambda item: item["index"])
    posting = dict(posting or {})
    ledger = dict(ledger or {})
    experiences = _experience_map(ledger)
    match_by_index = _match_rows(matches)
    research_rows = [dict(item) for item in research_claims if isinstance(item, Mapping)]

    intents = {row["index"]: classify_question(row["prompt"]) for row in question_rows}
    experience_modes = {
        row["index"]: _experience_mode(intents[row["index"]], row["prompt"])
        for row in question_rows
    }
    research_modes = {
        row["index"]: _research_mode(intents[row["index"]], row["prompt"])
        for row in question_rows
    }
    assignment, options_by_index = _portfolio_assignment(
        question_rows,
        intents,
        experience_modes,
        match_by_index,
        experiences,
        posting,
    )

    blueprints: list[dict[str, Any]] = []
    used_experiences = Counter(value for value in assignment.values() if value)
    for question in question_rows:
        index = question["index"]
        intent = intents[index]
        character_plan = _target_character_plan(question)
        experience_id = assignment.get(index)
        experience = experiences.get(experience_id or "")
        option = next(
            (
                item for item in options_by_index.get(index, [])
                if item["experience_id"] == experience_id
            ),
            None,
        )
        selected_claims = _select_claims(experience, question, posting) if experience else []
        required_metric_claim_ids = _required_metric_claim_ids(question, selected_claims)
        selected_research = _select_research_claims(
            question,
            intent,
            research_modes[index],
            research_rows,
            target,
        )
        alternatives = [
            {
                "experience_id": item["experience_id"],
                "planning_score": item["score"],
                "story_completeness": item["story_completeness"],
            }
            for item in options_by_index.get(index, [])
            if item["experience_id"] != experience_id
        ][:3]
        cardinality = _selection_cardinality(question["prompt"])
        blueprint = {
            "question_index": index,
            "prompt": question["prompt"],
            "prompt_sha256": sha256(question["prompt"].encode("utf-8")).hexdigest(),
            "intent": intent,
            "logic_contract": {
                "argument_pattern": [beat for beat, _ in _INTENT_PATTERNS[intent]],
                "selection_cardinality": cardinality,
                "experience_mode": experience_modes[index],
                "research_mode": research_modes[index],
                "requirements": _prompt_requirements(question["prompt"]),
            },
            "character_plan": character_plan,
            "beats": _allocate_beats(intent, character_plan),
            "experience": (
                _experience_contract(
                    experience,
                    selected_claims,
                    option,
                    required_metric_claim_ids,
                )
                if experience is not None
                else None
            ),
            "alternative_experiences": alternatives,
            "research_claims": [_research_contract(claim) for claim in selected_research],
            "portfolio_constraints": {
                "experience_reused_elsewhere": bool(
                    experience_id and used_experiences[experience_id] > 1
                ),
                "avoid_repeating_generic_chain": ["확인", "대조", "기록", "보고"],
                "distinctive_anchor": _specific_action(experience) if experience else None,
            },
            "risk_controls": _blueprint_risks(intent, cardinality),
            "interview_defense_questions": _defense_questions(intent, experience, selected_claims),
        }
        blueprint["blueprint_id"] = _digest(
            "bp",
            {
                "target": target,
                "question": question,
                "intent": intent,
                "experience_id": experience_id,
                "claim_ids": [claim.get("claim_id") for claim in selected_claims],
                "research_ids": [claim.get("claim_id") for claim in selected_research],
                "beats": blueprint["beats"],
            },
        )
        blueprints.append(blueprint)

    packet = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "experience_ledger_schema_version": ledger.get("schema_version"),
        "posting_identity": {
            "source_sha256": (
                posting.get("source", {}).get("content_sha256")
                if isinstance(posting.get("source"), Mapping)
                else None
            ),
            "duties": [str(item) for item in posting.get("duties", []) or []],
            "competencies": [str(item) for item in posting.get("competencies", []) or []],
        },
        "portfolio": {
            "experience_assignment": {str(key): value for key, value in sorted(assignment.items())},
            "unique_experience_count": len({value for value in assignment.values() if value}),
            "reuse_count": sum(max(0, count - 1) for count in used_experiences.values()),
            "optimization": "beam_global_fit_plus_evidence_plus_story_minus_reuse",
            "cross_answer_rules": [
                "Each answer must contribute a different proof, judgment, or scene to the application set.",
                "Do not repeat the same generic opening or closing across questions.",
                "If an experience is reused, change the evaluated capability and evidence angle; never paraphrase the same story.",
            ],
        },
        "questions": blueprints,
    }
    packet["packet_id"] = _digest("narrative", packet)
    return packet


def render_blueprint_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        "# 자기소개서 서사 설계도",
        "",
        f"- packet: `{packet.get('packet_id', '')}`",
        f"- target: {packet.get('target', '')}",
        f"- 경험 재사용: {packet.get('portfolio', {}).get('reuse_count', 0)}회",
        "",
        "이 문서는 사실 근거가 아니라 작성 중간표현(IR)이다. 실제 제출 근거는 확정 경험원장과 공식 근거 검증이 결정한다.",
        "",
    ]
    for row in packet.get("questions", []) or []:
        lines.extend(
            [
                f"## 문항 {row['question_index']} · {row['intent']}",
                "",
                f"- 설계 ID: `{row['blueprint_id']}`",
                f"- 문항: {row['prompt']}",
                f"- 경험: `{(row.get('experience') or {}).get('experience_id', '없음')}`",
                f"- 시그니처 행동: {(row.get('experience') or {}).get('signature_action') or '없음'}",
                f"- 공식근거: {', '.join(item['claim_id'] for item in row.get('research_claims', [])) or '없음'}",
                f"- 목표 분량: {row['character_plan'].get('target') or '미지정'} / 최대 {row['character_plan'].get('hard_maximum') or '미지정'}",
                "",
                "### 논증 순서",
                "",
            ]
        )
        for beat in row.get("beats", []):
            budget = f" · 약 {beat['character_budget']}자" if beat.get("character_budget") else ""
            lines.append(f"- **{beat['beat']}**{budget}: {beat['guidance']}")
        lines.extend(["", "### 금지·주의", ""])
        lines.extend(f"- {item}" for item in row.get("risk_controls", []))
        lines.extend(["", "### 면접 방어 질문", ""])
        lines.extend(f"- {item}" for item in row.get("interview_defense_questions", []))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
