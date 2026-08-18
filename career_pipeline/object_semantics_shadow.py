"""Bounded semantic object matcher for shadow calibration only.

The matcher uses explicit criterion-specific aliases and a very small set of stable
lexical equivalence groups. It is not an embedding model and does not itself grant
DIRECT construct evidence.

For the documentation criterion (``crit_documentation_record_decision_or_action``)
a verb-aware policy is applied (shadow only):

- inherently documentary verbs (작성/기록/메모) accept concrete content/object as
  strong documentation evidence;
- ``정리`` requires a materialized artifact marker (초안/일정표/배치안/계획표/
  체크리스트/문서/표/내역/기록/로그/워크시트/스프레드시트/엑셀/메모) to reach a
  full object match;
- weak generic terms (방식/역할/항목/문의/질문) never open DIRECT on their own.

Non-documentation criteria keep the previous bounded alias behavior.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re
from typing import Iterable

ARCHITECTURE = "object_semantics_shadow_v1"
# Version of the verb-aware documentation semantics policy applied by
# ``semantic_object_match_verb_aware``. Emitted as additive metadata in
# relation-shadow and 3-way audit outputs for auditability.
SEMANTIC_POLICY_VERSION = "documentation_verb_aware_v1"
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

# --- verb-aware documentation semantics (shadow only) ---
_DOCUMENTATION_CRITERION_ID = "crit_documentation_record_decision_or_action"
_DOCUMENTARY_VERBS = frozenset({"작성", "기록", "메모"})
_ORGANIZE_VERBS = frozenset({"정리"})
_STRONG_ARTIFACT_MARKERS = (
    "초안", "일정표", "배치안", "계획표", "체크리스트", "문서", "표", "내역",
    "기록", "로그", "워크시트", "스프레드시트", "엑셀", "메모",
)
_WEAK_GENERIC_TERMS = ("방식", "역할", "항목", "문의", "질문")


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


def _bounded_match(
    criterion_id: str,
    object_text: str,
    object_class: Iterable[str],
) -> ObjectMatch:
    """Legacy bounded alias/equivalence matching (unchanged behavior)."""
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


def semantic_object_match(
    criterion_id: str,
    object_text: str,
    object_class: Iterable[str],
) -> ObjectMatch:
    return _bounded_match(criterion_id, object_text, object_class)


def _artifact_hits(object_text: str) -> tuple[str, ...]:
    """Materialized artifact markers present in the object text.

    ``표`` is matched token-wise (equal or suffix) so that words like 표준/표시 do
    not false-positive as a table artifact.
    """
    tokens = _TOKEN_RE.findall(str(object_text or ""))
    hits: set[str] = set()
    for marker in _STRONG_ARTIFACT_MARKERS:
        if marker == "표":
            if any(tok == "표" or tok.endswith("표") for tok in tokens):
                hits.add(marker)
        else:
            if any(marker in tok for tok in tokens):
                hits.add(marker)
    return tuple(sorted(hits))


def _weak_hits(object_text: str) -> tuple[str, ...]:
    return tuple(sorted(t for t in _WEAK_GENERIC_TERMS if t in str(object_text or "")))


def _documentation_match(
    action: str,
    object_text: str,
    object_class: Iterable[str],
) -> ObjectMatch:
    obj = _tokens(object_text)
    artifacts = _artifact_hits(object_text)
    if action in _ORGANIZE_VERBS:
        # `정리` reaches a full object match only with a materialized artifact.
        if artifacts:
            return ObjectMatch(
                True, "artifact_supported", ("artifact_marker",), tuple(sorted(obj))
            )
        weak = _weak_hits(object_text)
        if weak:
            return ObjectMatch(False, "blocked_weak_generic", weak, tuple(sorted(obj)))
        return ObjectMatch(False, "blocked_no_artifact", (), tuple(sorted(obj)))
    if action in _DOCUMENTARY_VERBS:
        # 작성/기록/메모 with an artifact is the strongest documentation signal.
        if artifacts:
            return ObjectMatch(
                True, "artifact_supported", ("artifact_marker",), tuple(sorted(obj))
            )
        # Concrete content/object suffices for documentary verbs.
        return _bounded_match(_DOCUMENTATION_CRITERION_ID, object_text, object_class)
    return _bounded_match(_DOCUMENTATION_CRITERION_ID, object_text, object_class)


def semantic_object_match_verb_aware(
    criterion_id: str,
    action: str,
    object_text: str,
    object_class: Iterable[str],
) -> ObjectMatch:
    """Verb-aware semantic object match (shadow only).

    Documentation criterion applies the verb+artifact/weak-generic policy;
    all other criteria keep the previous bounded alias behavior.
    """
    if str(criterion_id) == _DOCUMENTATION_CRITERION_ID:
        return _documentation_match(str(action or ""), object_text, object_class)
    return _bounded_match(criterion_id, object_text, object_class)
