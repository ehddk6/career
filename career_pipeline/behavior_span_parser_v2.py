"""Precision-first Korean BehaviorSpan parser for shadow calibration.

This module is intentionally conservative. It distinguishes predicate uses of
behavior lexemes from nominal uses such as "확인 방식", "처리 속도", "검토 업무",
and "안내 표시". It does not grant factual authority and does not change production
relation semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Iterable

ARCHITECTURE = "behavior_span_parser_v2_shadow"

# Canonical action vocabulary stays close to the construct criteria plus a small
# set of observed operational verbs needed for documentation calibration.
_ACTION_ROOTS = (
    "모니터링", "승인요청",
    "대조", "비교", "확인", "발견", "판별", "분류", "구분", "선별",
    "기록", "작성", "정리", "메모", "분석", "취합", "진단", "파악",
    "설명", "제시", "안내", "상담", "소명", "협의", "조정", "협업",
    "연계", "판단", "보고", "요청", "관리", "처리", "점검", "개선",
    "검토", "보완",
)
# A lexeme followed by these nouns is normally a nominal modifier, not a predicate.
_NOMINAL_FOLLOWERS = {
    "방식", "속도", "업무", "표시", "항목", "프로세스", "사례", "기능",
    "결과", "절차", "자료", "기준", "대상", "체계", "과정",
}
_FINITE_SUFFIX_RE = re.compile(
    r"^(?:함|했다|했습니다|하였다|하였습니다|하여|해서|하고|하며|한다|합니다|한|"
    r"하고자)"
)
_CLAUSE_SPLIT_RE = re.compile(r"(?:→|⇒|=>|[.!?]\s*|\n+|&)")
_COMPOUND_ACTION_PAIRS = {("비교", "분석"), ("대조", "분석")}
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")

@dataclass(frozen=True)
class BehaviorSpan:
    action: str
    object: str
    source_segment: str
    predicate_basis: str
    object_basis: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n,;:·")


def _canonical_action(root: str) -> str:
    return "요청" if root == "승인요청" else root


def _after_word(text: str, end: int) -> str:
    return text[end:].lstrip()


def _is_nominal_use(segment: str, start: int, end: int) -> bool:
    after = _after_word(segment, end)
    m = re.match(r"([가-힣A-Za-z0-9]+)", after)
    if m and m.group(1) in _NOMINAL_FOLLOWERS:
        return True
    # Korean case particles immediately after the action noun strongly indicate
    # a nominal use: "분류가", "검토를", "안내는". Do not apply to finite suffixes.
    if after.startswith(("가 ", "이 ", "은 ", "는 ", "을 ", "를 ", "의 ")):
        return True
    return False


def _predicate_basis(segment: str, root: str, start: int, end: int) -> str | None:
    if _is_nominal_use(segment, start, end):
        return None
    after = _after_word(segment, end)
    if _FINITE_SUFFIX_RE.match(after):
        return "finite_or_connective"
    # Telegraphic bullet: "원인 분석" or "자료 대조" at segment end.
    if not after or re.fullmatch(r"[\s,;:)]*", after):
        return "telegraphic_segment_final"
    # Compound analytical predicate: "타 시장 비교 분석". The earlier action
    # is allowed only when followed immediately by another action predicate.
    next_m = re.match(r"\s*(" + "|".join(map(re.escape, _ACTION_ROOTS)) + r")", after)
    if next_m:
        tail_root = next_m.group(1)
        tail_after = after[next_m.end():].lstrip()
        tail_is_predicate = (not tail_after) or bool(_FINITE_SUFFIX_RE.match(tail_after))
        if tail_is_predicate and (root, tail_root) in _COMPOUND_ACTION_PAIRS:
            return "compound_action"
    return None


def _strip_leading_connective(text: str) -> str:
    value = _clean(text)
    # Keep the material after common instrumental/constraint markers.
    for marker in ("에 맞춰 ", "에 따라 ", "을 통해 ", "를 통해 ", "활용해 ", "활용하여 ", "위해 "):
        if marker in value:
            value = value.rsplit(marker, 1)[-1]
    return _clean(value)


def _object_from_prefix(prefix: str) -> tuple[str, str]:
    prefix = _clean(prefix)
    if not prefix:
        return "", "none"
    # Prefer an explicit Korean object-particle phrase, even when an instrument
    # phrase follows it before the predicate: "... 항목을 엑셀로 정리함".
    matches = list(re.finditer(r"([가-힣A-Za-z0-9·/&().\- ]{1,70}?)(?:을|를)(?=\s|$)", prefix))
    if matches:
        phrase = matches[-1].group(1)
        # Limit to the current local clause, then remove common connective lead-in.
        phrase = re.split(r"[,;:]", phrase)[-1]
        phrase = _strip_leading_connective(phrase)
        return phrase, "object_particle"
    # No explicit object particle: never slice by character count. Keep the local
    # phrase after the nearest punctuation/connective, bounded by token count.
    local = re.split(r"[,;:]", prefix)[-1]
    local = _strip_leading_connective(local)
    toks = _TOKEN_RE.findall(local)
    if not toks:
        return "", "none"
    return " ".join(toks[-8:]), "bounded_token_fallback"


def _coordinated_nominal_actions(segment: str) -> list[BehaviorSpan]:
    """Handle a narrow pattern like "증빙 대조와 지역 시세 확인".

    This deliberately does not fire if a higher-order matrix verb such as "제안함"
    appears after the coordinated phrase.
    """
    seg = _clean(segment)
    if not seg:
        return []
    # Only consider segments whose final token is a behavior predicate.
    final = None
    for root in _ACTION_ROOTS:
        m = re.search(re.escape(root) + r"\s*$", seg)
        if m:
            final = (root, m)
            break
    if not final:
        return []
    root2, m2 = final
    before2 = seg[:m2.start()]
    # Look for one earlier action joined by 와/과.
    for root1 in _ACTION_ROOTS:
        m1 = re.search(r"(.+?)\s*" + re.escape(root1) + r"(?:와|과)\s*(.+)$", before2)
        if not m1:
            continue
        obj1 = _clean(m1.group(1))
        obj2 = _clean(m1.group(2))
        if obj1 and obj2:
            return [
                BehaviorSpan(_canonical_action(root1), obj1, seg, "coordinated_telegraphic", "coordinated_phrase"),
                BehaviorSpan(_canonical_action(root2), obj2, seg, "telegraphic_segment_final", "coordinated_phrase"),
            ]
    return []


def _is_requirement_or_task_segment(segment: str) -> bool:
    value = str(segment or "")
    if "과제(Task)" in value or value.lstrip().startswith(("과제:", "목표:")):
        return True
    # Explicit deontic language is context/requirement, not performed behavior.
    if re.search(r"(?:해야|하여야|할 필요|해야만)", value):
        return True
    return False


def extract_behavior_spans(text: str) -> tuple[BehaviorSpan, ...]:
    spans: list[BehaviorSpan] = []
    seen: set[tuple[str, str, str]] = set()
    raw = str(text or "")
    for raw_segment in _CLAUSE_SPLIT_RE.split(raw):
        segment = _clean(raw_segment)
        if not segment:
            continue
        if _is_requirement_or_task_segment(segment):
            continue
        coord = _coordinated_nominal_actions(segment)
        if coord:
            for item in coord:
                key = (item.action, item.object, item.source_segment)
                if key not in seen:
                    spans.append(item); seen.add(key)
            continue
        for root in _ACTION_ROOTS:
            for m in re.finditer(re.escape(root), segment):
                basis = _predicate_basis(segment, root, m.start(), m.end())
                if not basis:
                    continue
                obj, obj_basis = _object_from_prefix(segment[:m.start()])
                item = BehaviorSpan(
                    action=_canonical_action(root),
                    object=obj,
                    source_segment=segment,
                    predicate_basis=basis,
                    object_basis=obj_basis,
                )
                key = (item.action, item.object, item.source_segment)
                if key not in seen:
                    spans.append(item); seen.add(key)
    return tuple(spans)
