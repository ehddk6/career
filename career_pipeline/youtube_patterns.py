"""Versioned, strategy-only design patterns extracted from YouTube guidance.

The packet deliberately contains no company facts, candidate facts, example
sentences, or numbers.  It is an operational contract for using the imported
analysis as a writing heuristic while keeping factual provenance elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path
import csv
import re
from typing import Any


PATTERN_PACKET_VERSION = "youtube_design_patterns_v1"
PATTERN_PACKET_KIND = "youtube_design_patterns"
GUIDANCE_POLICY = "strategy_only_not_factual_evidence"


YOUTUBE_DESIGN_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "id": "QUESTION_TYPE_FIRST",
        "label": "문항 유형 먼저 판별",
        "applies_to": ["question_classification", "candidate_selection", "final_audit"],
        "rule": "문항 원문·평가 요소·글자 수를 먼저 분해하고 복합 요구를 누락 검사한다.",
        "counterexample": "키워드 하나만 보고 모든 문항을 같은 공식으로 분류한다.",
        "promotion": "global_guidance",
    },
    {
        "id": "ONE_EXPERIENCE_ONE_COMPETENCY",
        "label": "한 문항 한 경험·역량",
        "applies_to": ["question_classification", "candidate_generation", "candidate_selection"],
        "rule": "특별한 요구가 없으면 핵심 경험 하나와 핵심 역량 하나를 선명하게 둔다.",
        "counterexample": "한 경험으로 정확성·소통·책임감 등 여러 역량을 동시에 주장한다.",
        "promotion": "global_guidance",
    },
    {
        "id": "JUDGMENT_BEFORE_TRAITS",
        "label": "성격보다 판단·행동",
        "applies_to": ["candidate_generation", "candidate_selection", "humanization"],
        "rule": "추상적인 성격 평가 대신 무엇을 보고 왜 그렇게 처리했는지를 앞세운다.",
        "counterexample": "꼼꼼함·책임감·적극성을 선언하고 실제 판단 장면은 생략한다.",
        "promotion": "global_guidance",
    },
    {
        "id": "REPRODUCIBLE_ACTION_CHAIN",
        "label": "재현 가능한 업무 흐름",
        "applies_to": ["candidate_generation", "candidate_selection", "final_audit"],
        "rule": "기준 설정 → 확인 → 예외 분류·조정 → 근거 전달·실행 → 결과 확인의 흐름을 경험에 맞게 사용한다.",
        "counterexample": "확인·정리·보고를 절차처럼 나열하고 판단 이유를 쓰지 않는다.",
        "promotion": "global_guidance",
    },
    {
        "id": "OBSERVABLE_RESULT",
        "label": "관찰 가능한 결과",
        "applies_to": ["candidate_generation", "candidate_selection", "final_audit"],
        "rule": "검증 가능한 수치가 없더라도 누락 재확인·중복 방지·예외 분리·후속 조치처럼 변화를 제시한다.",
        "counterexample": "역량을 키웠다·성장했다처럼 자기평가로 결과를 끝낸다.",
        "promotion": "global_guidance",
    },
    {
        "id": "TEAM_PERSON_SPLIT",
        "label": "팀 성과와 개인 행동 분리",
        "applies_to": ["candidate_generation", "candidate_selection", "final_audit"],
        "rule": "팀이 만든 결과와 지원자가 직접 수행한 범위를 문장 수준에서 분리한다.",
        "counterexample": "팀 전체 처리량을 개인 성과처럼 읽히게 쓴다.",
        "promotion": "global_guidance",
    },
    {
        "id": "JOB_BEHAVIOR_BRIDGE",
        "label": "경험에서 직무 행동으로 연결",
        "applies_to": ["candidate_generation", "candidate_selection"],
        "rule": "과거의 판단 방식이 지원 직무에서 어떤 확인·분류·전달 행동으로 재현될지 쓴다.",
        "counterexample": "기관명과 상품 설명을 붙인 뒤 정확히 기여하겠다는 말로 끝낸다.",
        "promotion": "global_guidance",
    },
    {
        "id": "HUMAN_VOICE_AUDIT",
        "label": "판단 이유와 작은 난점 보존",
        "applies_to": ["humanization", "final_audit"],
        "rule": "매끄러운 모범답안보다 실제 관찰·망설임·예상과 달랐던 점·판단 변화를 남긴다.",
        "counterexample": "모든 문항을 같은 두괄식·병렬 구조·결론 문구로 정돈한다.",
        "promotion": "global_guidance",
    },
    {
        "id": "ANTI_TEMPLATE_REUSE",
        "label": "문구·템플릿 복사 방지",
        "applies_to": ["candidate_generation", "humanization", "final_audit"],
        "rule": "원문 문장 대신 추상 패턴만 전달하고 영상·기존 답변·문항 간 구문 중복을 경고한다.",
        "counterexample": "좋은 예시의 첫 문장과 결론을 바꿔 끼워 반복한다.",
        "promotion": "global_guardrail",
    },
    {
        "id": "FACT_BOUNDARY",
        "label": "사실 근거 경계",
        "applies_to": ["prepare", "candidate_generation", "final_audit"],
        "rule": "회사 사실은 공식 자료, 개인 경험은 confirmed ledger만 근거로 삼고 유튜브는 구조 참고로만 사용한다.",
        "counterexample": "영상의 회사·상품·채용 정보나 지원자 수치를 현재 지원서에 옮긴다.",
        "promotion": "global_guardrail",
    },
)


def _read_run_summary(source_dir: Path) -> dict[str, Any]:
    path = source_dir / "run_summary.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def source_quality(source_dir: Path) -> dict[str, Any]:
    """Return conservative source-quality metadata without inventing confidence."""

    summary = _read_run_summary(source_dir)
    video_count = summary.get("video_count")
    frame_count = summary.get("frame_count")
    nonempty = summary.get("nonempty_ocr_frame_count")
    usable = summary.get("usable_frame_count")
    company_counts = summary.get("company_counts")
    if not isinstance(company_counts, dict):
        company_counts = {}
    try:
        usable_int = int(usable) if usable is not None else None
    except (TypeError, ValueError):
        usable_int = None
    try:
        nonempty_int = int(nonempty) if nonempty is not None else None
    except (TypeError, ValueError):
        nonempty_int = None
    bounded_ocr = (
        usable_int is not None
        and nonempty_int is not None
        and nonempty_int > 0
        and usable_int < nonempty_int
    )
    return {
        "video_count": video_count,
        "frame_count": frame_count,
        "nonempty_ocr_frame_count": nonempty,
        "usable_frame_count": usable,
        "distinct_company_labels": len(company_counts),
        "ocr_confidence": "bounded_not_absolute" if bounded_ocr else "not_estimated",
        "manual_review_required": bool(bounded_ocr),
        "quality_basis": "run_summary.json" if summary else "metadata_unavailable",
        "source_generated_at": summary.get("generated_at"),
    }


def build_pattern_packet(
    source_dir: Path,
    *,
    freshness: dict[str, Any] | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-safe packet passed between pipeline stages."""

    quality = source_quality(source_dir)
    return {
        "schema_version": 1,
        "packet_version": PATTERN_PACKET_VERSION,
        "kind": PATTERN_PACKET_KIND,
        "use_policy": GUIDANCE_POLICY,
        "target": target,
        "source_snapshot": {
            "source_dir": source_dir.as_posix(),
            "freshness": freshness or {"status": "unknown"},
            **quality,
        },
        "patterns": [dict(pattern) for pattern in YOUTUBE_DESIGN_PATTERNS],
        "stage_policy": {
            "prepare": "broad_discovery_narrow_delivery",
            "question_classification": "high",
            "candidate_generation": "moderate_abstract_only",
            "candidate_selection": "high",
            "humanization": "moderate_high_audit_only",
            "final_audit": "very_high",
        },
        "prohibited_uses": [
            "company_facts",
            "product_specs",
            "recruitment_dates_or_rules",
            "candidate_identity_or_metrics",
            "personal_experience_completion",
            "verbatim_sentence_or_template_copy",
            "low_confidence_ocr_promotion_without_manual_review",
        ],
        "manual_review_gate": {
            "required_when": [
                "a_low_confidence_frame_would_promote_a_global_pattern",
                "a_phrase_overlap_alert_would_change_candidate_selection",
                "a_core_counterexample_depends_on_ambiguous_ocr",
            ],
            "automatic_action": "hold_pattern_promotion_and_mark_manual_review_required",
        },
    }


def build_application_log(packet: dict[str, Any]) -> dict[str, Any]:
    """Create an explicit, non-claiming plan of where patterns may be used."""

    pattern_ids = [item["id"] for item in packet.get("patterns", [])]
    return {
        "schema_version": 1,
        "packet_version": packet.get("packet_version"),
        "use_policy": GUIDANCE_POLICY,
        "status": "planned_not_yet_applied",
        "entries": [
            {
                "stage": "prepare",
                "mode": "discovery_only",
                "allowed_pattern_ids": pattern_ids,
                "delivered_fields": [
                    "applicable_patterns",
                    "excluded_patterns",
                    "question_type_candidates",
                    "source_quality",
                    "manual_review_required",
                ],
                "blocked_content": ["raw_ocr", "example_sentences", "company_facts", "personal_facts"],
            },
            {
                "stage": "question_classification",
                "mode": "high",
                "allowed_pattern_ids": ["QUESTION_TYPE_FIRST", "ONE_EXPERIENCE_ONE_COMPETENCY"],
                "verification": "question_text_and_posting_requirements_remain_authoritative",
            },
            {
                "stage": "candidate_generation",
                "mode": "moderate_abstract_only",
                "allowed_pattern_ids": [
                    "JUDGMENT_BEFORE_TRAITS",
                    "REPRODUCIBLE_ACTION_CHAIN",
                    "OBSERVABLE_RESULT",
                    "TEAM_PERSON_SPLIT",
                    "JOB_BEHAVIOR_BRIDGE",
                ],
                "blocked_content": ["verbatim_examples", "invented_experience", "invented_numbers"],
            },
            {
                "stage": "candidate_selection",
                "mode": "high",
                "allowed_pattern_ids": pattern_ids,
                "verification": "candidate_must_still_pass_fact_and_experience_gates_without_youtube",
            },
            {
                "stage": "humanization",
                "mode": "audit_only",
                "allowed_pattern_ids": ["HUMAN_VOICE_AUDIT", "ANTI_TEMPLATE_REUSE"],
                "blocked_content": ["forced_colloquialism", "new_emotions", "new_facts"],
            },
            {
                "stage": "final_audit",
                "mode": "very_high",
                "allowed_pattern_ids": pattern_ids,
                "required_checks": [
                    "fact_provenance_map",
                    "experience_consistency_check",
                    "phrase_overlap_report",
                    "unsupported_number_flags",
                    "ai_style_flags",
                    "manual_review_gate",
                ],
            },
        ],
    }


def _compact_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", value or "").casefold()


def phrase_overlap_report(
    responses: list[Any],
    source_dir: Path,
    *,
    min_phrase_chars: int = 10,
    max_matches: int = 50,
) -> dict[str, Any]:
    """Warn about verbatim overlap without treating it as an automatic failure.

    The source index is only used for a bounded warning report.  It never adds
    source text to a draft or turns a match into factual evidence.
    """

    index_path = source_dir / "05_문장_근거색인.csv"
    if not index_path.is_file():
        return {
            "status": "source_unavailable",
            "use_policy": GUIDANCE_POLICY,
            "manual_review_required": False,
            "matches": [],
        }
    phrases: list[tuple[str, int, str]] = []
    try:
        with index_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            for row in csv.DictReader(stream):
                phrase = (row.get("line") or "").strip()
                normalized = _compact_text(phrase)
                if len(normalized) < min_phrase_chars:
                    continue
                try:
                    count = int(row.get("count") or 0)
                except (TypeError, ValueError):
                    count = 0
                phrases.append((phrase, count, normalized))
    except (OSError, csv.Error, UnicodeError):
        return {
            "status": "source_unavailable",
            "use_policy": GUIDANCE_POLICY,
            "manual_review_required": False,
            "matches": [],
        }

    matches: list[dict[str, Any]] = []
    for response in responses:
        answer = str(getattr(response, "answer", "") or "")
        normalized_answer = _compact_text(answer)
        if not normalized_answer:
            continue
        for phrase, count, normalized in phrases:
            if normalized not in normalized_answer:
                continue
            matches.append(
                {
                    "question_index": int(getattr(response, "question_index", 0) or 0),
                    "phrase": phrase,
                    "source_count": count,
                    "action": "manual_review_warning",
                }
            )
            if len(matches) >= max_matches:
                break
        if len(matches) >= max_matches:
            break
    return {
        "status": "available",
        "use_policy": GUIDANCE_POLICY,
        "manual_review_required": bool(matches),
        "match_count": len(matches),
        "matches": matches,
        "note": "경고용 유사도 보고이며 자동 탈락·사실 근거 승격에 사용하지 않습니다.",
    }
