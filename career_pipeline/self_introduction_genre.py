"""Genre gate for natural Korean self-introduction prose.

This gate is intentionally separate from factual validation.  Factual
boundaries belong in deterministic validators; readers should encounter those
boundaries through accurate subjects and verbs, not an explanation of the
writer's internal audit process.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


GENRE_CONTRACT_VERSION = "self_introduction_genre_v3"


@dataclass(frozen=True)
class GenreIssue:
    code: str
    message: str
    severity: str = "hard"


_SENTENCE = re.compile(r"[^.!?。！？\n]+[.!?。！？]?")
_AUDIT_META_PATTERNS = (
    re.compile(r"(?:확대해|과장해|단정해)\s*(?:말할|설명할|주장할)\s*수(?:는)?\s*(?:없|없었)"),
    re.compile(r"(?:확대|과장)(?:하지|할 수)\s*(?:않|없)"),
    re.compile(r"(?:결과|성과|해결|효과|기여).{0,32}단정(?:하지|할 수)\s*(?:않|없)"),
    re.compile(r"단정(?:하지|할 수)\s*(?:않|없).{0,32}(?:결과|성과|해결|효과|기여)"),
    re.compile(r"(?:제|저의)\s*단독\s*성과(?:로)?\s*(?:말|설명|주장)"),
    re.compile(r"(?:결과|성과)의\s*범위를\s*(?:구분|한정|설명)"),
    re.compile(r"(?:확인할 수 있는|확인된)\s*(?:결과|자료).{0,24}(?:범위|한정)"),
    re.compile(r"(?:근거|자료)가\s*부족.{0,24}(?:말|설명|주장)"),
)
_SELF_EXPLANATION_PATTERNS = (
    re.compile(r"(?:이 답변|이 글|이 문단)은"),
    re.compile(r"(?:이 경험|이 사례)은\s*(?:.+?)(?:역량|행동|사례)(?:입니다|라는 점)"),
    re.compile(r"(?:작성|검증)\s*(?:방식|과정)을\s*(?:설명|보여)"),
)
_DEFENSIVE_ENDING = re.compile(
    r"(?:확인하지 않았|말할 수 없|확대하지\s*(?:않았|않습니다|않겠다|않을)|과장하지\s*(?:않았|않습니다|않겠다|않을)|단정하지\s*(?:않았|않습니다|않겠다|않을)|제 단독 성과.{0,12}(?:아니|아닙)|한정됩니다?)"
)
_CONTROL_WORDS = ("확인", "검증", "범위", "근거", "단정", "확대")
_REPORT_DIALECT_PATTERNS = (
    re.compile(r"업무\s*접점"),
    re.compile(r"역량을\s*(?:개발|함양)(?:하기\s*위한)?"),
    re.compile(r"결과의\s*범위"),
    re.compile(r"효율적으로\s*(?:관리|지원|수행)"),
    re.compile(r"체계적으로\s*(?:관리|지원|수행)"),
    re.compile(r"처리\s*절차를\s*(?:변경|개선|정비)"),
)
_TECHNICAL_STRUCTURE_CONTEXT = re.compile(
    r"(?:데이터베이스|DB|SQL|JSON|스키마|테이블|코드|변수|API|정보\s*모델)"
)


def _sentences(text: str) -> list[str]:
    return [match.group(0).strip() for match in _SENTENCE.finditer(text) if match.group(0).strip()]


def _issues_for_patterns(text: str, patterns: Iterable[re.Pattern[str]], code: str, message: str, severity: str) -> list[GenreIssue]:
    if any(pattern.search(text) for pattern in patterns):
        return [GenreIssue(code, message, severity)]
    return []


def validate_self_introduction_genre(answer: str) -> list[GenreIssue]:
    """Reject audit prose while allowing role-appropriate judgment boundaries.

    The patterns deliberately require an explanation or disclaimer.  A normal
    work sentence such as "이상 신호만으로 부정을 판단하지 않고 담당자에게
    보고하겠습니다" is a professional decision boundary, not meta leakage.
    """
    text = " ".join(str(answer).split())
    if not text:
        return [GenreIssue("empty_answer", "자기소개서 본문이 비어 있습니다.")]

    issues = _issues_for_patterns(
        text,
        _AUDIT_META_PATTERNS,
        "audit_meta_leakage",
        "내부 사실 검증 또는 기여도 한계 설명이 자기소개서 본문에 노출되었습니다.",
        "hard",
    )
    issues.extend(_issues_for_patterns(
        text,
        _SELF_EXPLANATION_PATTERNS,
        "self_explanation",
        "독자에게 작성 방식이나 평가 기준을 해설하는 문장이 있습니다.",
        "material",
    ))

    sentences = _sentences(text)
    if sentences and _DEFENSIVE_ENDING.search(sentences[-1]):
        issues.append(GenreIssue(
            "defensive_disclaimer",
            "답변이 한계 해명이나 방어 문장으로 끝납니다.",
            "hard",
        ))

    count = sum(text.count(word) for word in _CONTROL_WORDS)
    distinct = sum(1 for word in _CONTROL_WORDS if word in text)
    if count >= 5 and distinct >= 3:
        issues.append(GenreIssue(
            "control_lexicon_density",
            "확인·검증·범위 등 통제 어휘가 지나치게 반복됩니다.",
            "material",
        ))

    report_hits = sum(bool(pattern.search(text)) for pattern in _REPORT_DIALECT_PATTERNS)
    needless_structure = "구조화" in text and not _TECHNICAL_STRUCTURE_CONTEXT.search(text)
    if needless_structure or report_hits >= 2:
        issues.append(GenreIssue(
            "institutional_report_diction",
            "자기소개서보다 내부 보고서에 가까운 추상 명사가 사용되었습니다. 정리·분류·대조처럼 실제 행동이 보이는 동사로 바꾸십시오.",
            "material",
        ))
    return issues


def blocking_genre_issues(answer: str) -> list[GenreIssue]:
    """Return all genre issues that disqualify a benchmark candidate."""
    return [issue for issue in validate_self_introduction_genre(answer) if issue.severity in {"hard", "material"}]
