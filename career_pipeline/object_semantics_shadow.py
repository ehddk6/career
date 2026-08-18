"""Bounded semantic object matcher for shadow calibration only.

The matcher uses explicit criterion-specific aliases and a very small set of stable
lexical equivalence groups. It is not an embedding model and does not itself grant
DIRECT construct evidence.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re
from typing import Iterable

ARCHITECTURE = "object_semantics_shadow_v1"
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")

# Stable lexical equivalences only. A group is activated only when the criterion's
# declared object class already contains the canonical key.
_EQUIV: dict[str, set[str]] = {
    "일정": {"날짜", "시간", "스케줄", "일정표", "배치안", "가용시간"},
    "누락": {"미기재", "미입력", "빠짐"},
    "차이": {"이탈", "초과", "상이", "다름", "다른"},
    "현황": {"진행상황", "진행률"},
}
# Criterion-specific expansions are deliberately narrow and auditable.
_CRITERION_ALIASES: dict[str, set[str]] = {
    "crit_documentation_record_decision_or_action": {
        "방식", "역할", "항목", "초안", "메모", "문의", "질문", "일정표", "배치안", "계획표", "체크리스트"
    },
    "crit_analytical_diagnosis_compare_or_segment_information": {
        "시장", "사례", "인터뷰", "대상", "집단", "그룹"
    },
}

@dataclass(frozen=True)
class ObjectMatch:
    matched: bool
    basis: str
    matched_terms: tuple[str, ...]
    object_tokens: tuple[str, ...]

    def to_dict(self):
        return asdict(self)


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(str(text or "")) if len(t) >= 2}


def semantic_object_match(
    criterion_id: str,
    object_text: str,
    object_class: Iterable[str],
) -> ObjectMatch:
    obj = _tokens(object_text)
    target = {str(x) for x in object_class if str(x)}
    exact = sorted(obj & target)
    if exact:
        return ObjectMatch(True, "exact", tuple(exact), tuple(sorted(obj)))

    hits: set[str] = set()
    for canonical in target:
        aliases = _EQUIV.get(canonical, set())
        for alias in aliases:
            if alias in obj or any(alias in tok for tok in obj):
                hits.add(f"{alias}->{canonical}")
    for alias in _CRITERION_ALIASES.get(str(criterion_id), set()):
        if alias in obj or any(alias in tok for tok in obj):
            hits.add(f"{alias}->criterion_alias")
    if hits:
        return ObjectMatch(True, "bounded_alias", tuple(sorted(hits)), tuple(sorted(obj)))
    return ObjectMatch(False, "none", (), tuple(sorted(obj)))
