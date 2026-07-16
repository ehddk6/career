"""채용 문항의 하위 요구를 구조화하고 결정적으로 검증한다."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any, Iterable

from .character_count import count_characters
from .models import DraftResponse, Question, ValidationIssue


_REQUIREMENT_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        "motivation_reason",
        ("지원동기", "지원하게 된", "지원한 이유", "선택한 이유"),
        ("때문", "선택", "지원했", "가치", "의미", "관심", "신뢰"),
        "지원 이유",
    ),
    (
        "learning_plan",
        ("배우", "학습", "성장"),
        ("배우", "익히", "학습", "숙지", "이해", "피드백"),
        "학습·성장 방법",
    ),
    (
        "contribution_plan",
        ("기여", "입사 후"),
        ("확인", "대조", "기록", "보고", "안내", "점검", "하겠습니다", "겠습니다"),
        "현실적인 기여 행동",
    ),
    (
        "experience_action",
        ("경험", "사례", "상황"),
        ("확인", "대조", "분석", "정리", "제안", "조정", "설명", "기록", "보고", "실행"),
        "본인의 직접 행동",
    ),
    (
        "lesson_or_change",
        ("배운", "느낀", "변화", "교훈", "보완"),
        ("배웠", "느꼈", "이후", "보완", "바꾸", "개선", "적용"),
        "배운 점과 이후 변화",
    ),
    (
        "collaboration_process",
        ("협업", "협력", "갈등", "팀"),
        ("공유", "조율", "설명", "경청", "합의", "분담", "협업", "협력"),
        "협업·조정 과정",
    ),
    (
        "execution_sequence",
        ("업무수행계획", "근무계획", "직무계획"),
        ("먼저", "초기", "이후", "점검", "재확인", "익숙", "반복"),
        "초기 학습·실행·점검 순서",
    ),
    (
        "issue_reasoning",
        ("경제", "사회", "시사", "이슈"),
        ("원인", "영향", "때문", "따라서", "반면", "위험", "대응"),
        "이슈의 원인·영향·대응 논리",
    ),
)


def _prompt_digest(question: Question) -> str:
    return sha256(question.prompt.encode("utf-8")).hexdigest()


def _target_range(question: Question) -> dict[str, int | None]:
    if question.character_limit is None:
        return {"minimum": question.minimum_character_limit, "preferred_maximum": None}
    # The formal minimum is a validity floor, not the quality target. Short
    # answers need enough room for evidence, judgment and the job bridge.
    preferred_ratio = 0.85 if question.character_limit <= 800 else 0.80
    minimum = max(
        question.minimum_character_limit or 0,
        round(question.character_limit * preferred_ratio),
    )
    return {
        "minimum": minimum,
        "preferred_maximum": max(minimum, round(question.character_limit * 0.93)),
    }


def _requires_target_specificity(prompt: str) -> bool:
    return any(
        marker in prompt
        for marker in (
            "지원동기",
            "지원하게 된",
            "지원한 이유",
            "입사 후",
            "기여",
            "업무수행계획",
            "근무계획",
            "직무계획",
        )
    )


def _requires_job_connection(prompt: str) -> bool:
    return any(
        marker in prompt
        for marker in ("직무", "업무", "기여", "입사", "근무", "지원동기")
    )


def build_question_requirement_map(
    questions: Iterable[Question],
    *,
    target: str,
    posting: dict[str, Any] | None = None,
    matches: Iterable[Any] = (),
) -> dict[str, Any]:
    posting = posting or {}
    match_by_index: dict[int, Any] = {}
    for match in matches:
        question = getattr(match, "question", None)
        if question is not None:
            match_by_index[int(question.index)] = match

    duties = [str(item).strip() for item in posting.get("duties", []) if str(item).strip()]
    competencies = [
        str(item).strip() for item in posting.get("competencies", []) if str(item).strip()
    ]
    rows: list[dict[str, Any]] = []
    for question in questions:
        requirements = [
            {
                "requirement_id": "direct_answer",
                "description": "문항의 핵심 질문에 첫 두 문장 안에서 직접 답함",
                "hard_fail_if_missing": True,
                "answer_cues": [],
            }
        ]
        for requirement_id, prompt_markers, answer_cues, description in _REQUIREMENT_RULES:
            if any(marker in question.prompt for marker in prompt_markers):
                requirements.append(
                    {
                        "requirement_id": requirement_id,
                        "description": description,
                        "hard_fail_if_missing": True,
                        "answer_cues": list(answer_cues),
                    }
                )
        match = match_by_index.get(question.index)
        recommended = getattr(match, "recommended", None)
        target_range = _target_range(question)
        rows.append(
            {
                "question_index": question.index,
                "prompt": question.prompt,
                "prompt_sha256": _prompt_digest(question),
                "character_limit": question.character_limit,
                "count_mode": question.count_mode,
                "preferred_character_range": target_range,
                "requires_target_specificity": _requires_target_specificity(question.prompt),
                "requires_job_connection": _requires_job_connection(question.prompt),
                "requirements": requirements,
                "job_duties": duties,
                "job_competencies": competencies,
                "recommended_experience_id": (
                    str(recommended.experience_id) if recommended is not None else None
                ),
                "reuse_policy": "AVOID_WHEN_CONFIRMED_ALTERNATIVE_EXISTS",
            }
        )
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": 1,
        "target": target,
        "question_set_sha256": sha256(canonical.encode("utf-8")).hexdigest(),
        "questions": rows,
    }


def validate_question_requirement_map(
    responses: Iterable[DraftResponse],
    requirement_map: dict[str, Any] | None,
    *,
    target: str,
    enforce_preferred_range: bool = False,
) -> list[ValidationIssue]:
    if not requirement_map:
        return []
    by_index = {item.question_index: item for item in responses}
    issues: list[ValidationIssue] = []
    target_tokens = [token for token in target.replace("/", " ").split() if len(token) >= 2]
    for row in requirement_map.get("questions", []):
        if not isinstance(row, dict):
            continue
        index = int(row.get("question_index", 0))
        response = by_index.get(index)
        if response is None or not response.answer.strip():
            continue
        answer = response.answer.strip()
        if enforce_preferred_range:
            preferred = row.get("preferred_character_range")
            minimum = preferred.get("minimum") if isinstance(preferred, dict) else None
            count_mode = str(row.get("count_mode") or "spaces_included")
            answer_length = count_characters(answer, count_mode)
            if isinstance(minimum, int) and answer_length < minimum:
                issues.append(
                    ValidationIssue(
                        "under_preferred_minimum",
                        index,
                        f"최고 품질 모드의 권장 최소 분량에 미달했습니다: "
                        f"{answer_length}/{minimum}자",
                    )
                )
        if row.get("requires_target_specificity") and target_tokens and not any(
            token.casefold() in answer.casefold() for token in target_tokens
        ):
            issues.append(
                ValidationIssue(
                    "missing_target_specificity",
                    index,
                    "문항 계약이 요구한 기관·사업·직무 고유 연결이 없습니다.",
                )
            )
        if row.get("requires_job_connection"):
            job_terms = [
                str(item).strip()
                for key in ("job_duties", "job_competencies")
                for item in row.get(key, [])
                if str(item).strip()
            ]
            action_bridge = any(
                marker in answer
                for marker in ("확인", "대조", "기록", "보고", "안내", "점검", "분석", "조정")
            )
            if job_terms and not any(term in answer for term in job_terms) and not action_bridge:
                issues.append(
                    ValidationIssue(
                        "missing_job_connection",
                        index,
                        "문항 계약이 요구한 공고 업무·역량과의 연결이 없습니다.",
                    )
                )
        for requirement in row.get("requirements", []):
            if not isinstance(requirement, dict) or requirement.get("requirement_id") == "direct_answer":
                continue
            cues = [str(item) for item in requirement.get("answer_cues", []) if str(item)]
            if cues and not any(cue in answer for cue in cues):
                issues.append(
                    ValidationIssue(
                        f"missing_requirement_{requirement.get('requirement_id', 'unknown')}",
                        index,
                        f"문항 하위 요구가 누락되었습니다: {requirement.get('description', '')}",
                    )
                )
    return issues


def question_requirement_map_from_state(
    questions: Iterable[Question], state: dict[str, Any]
) -> dict[str, Any]:
    """구버전 실행의 JSON 산출물이 없을 때 최소 계약을 재구성한다."""
    posting = state.get("posting_analysis")
    if not isinstance(posting, dict):
        posting = {}
    return build_question_requirement_map(
        questions,
        target=str(state.get("target", "")),
        posting=posting,
    )
