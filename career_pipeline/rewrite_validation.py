"""교열 결과의 사실·의미·형식 보존을 검증하는 공용 모듈."""

from collections import Counter
from dataclasses import dataclass
import re
from difflib import SequenceMatcher


WARNING_CHANGE_RATIO = 0.12
MAX_CHANGE_RATIO = 0.20

_NUMBER = re.compile(
    r"(?<![\w])\d[\d,]*(?:\.\d+)?\s*(?:%|년|개월|주|일|시간|분|초|건|명|개|회|원|만원|억원|km|㎞|m|kg|명|점)?"
)
_DATE_OR_PERIOD = re.compile(
    r"(?:\d{2,4}[./-]\d{1,2}(?:[./-]\d{1,2})?|\d+\s*(?:년|개월|주|일|시간|분기|분))"
)
_QUOTED = (
    re.compile(r'"([^"\n]+)"'),
    re.compile(r"“([^”\n]+)”"),
    re.compile(r"‘([^’\n]+)’"),
    re.compile(r"「([^」\n]+)」"),
    re.compile(r"『([^』\n]+)』"),
)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9._-]{1,}\b")
_NEGATION = re.compile(r"않|못|없|아니|불가|제외|미달|금지|어렵")
_CAUSATION = re.compile(r"때문|결과|따라|덕분|원인|영향|(?:으로|로)\s*인(?:해|하여)")
_KOREAN_NAMED_ENTITY = re.compile(
    r"[가-힣A-Za-z0-9·&]{2,}(?:공사|공단|은행|협회|재단|대학교|센터|본부|직무)"
)


@dataclass(frozen=True)
class RewriteValidation:
    valid: bool
    issues: tuple[str, ...] = ()
    change_ratio: float = 0.0
    warning: bool = False
    sentence_count_original: int = 0
    sentence_count_rewritten: int = 0


def _normalize_token(value: str) -> str:
    return re.sub(r"\s+", "", value).replace(",", "")


def _counter(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(_normalize_token(match.group(0)) for match in pattern.finditer(text))


def _quoted_values(text: str) -> Counter[str]:
    return Counter(
        match
        for pattern in _QUOTED
        for match in pattern.findall(text)
    )


def sentence_count(text: str) -> int:
    endings = re.findall(r"[.!?…。]+(?:[\"'”’」』)\]]*)", text)
    return len(endings) or (1 if text.strip() else 0)


def change_ratio(original: str, rewritten: str) -> float:
    def normalize(value: str) -> str:
        value = re.sub(r"\s+", "", value)
        return re.sub(r"[.,!?;:，。！？；：·…]", "", value)

    return 1.0 - SequenceMatcher(None, normalize(original), normalize(rewritten)).ratio()


def protected_terms_from_text(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_KOREAN_NAMED_ENTITY.findall(text)))


def meaning_preservation_issue(
    original: str,
    rewritten: str,
    protected_terms: tuple[str, ...] = (),
) -> str | None:
    if _counter(_NUMBER, original) != _counter(_NUMBER, rewritten):
        return "숫자·단위 변경"
    if _counter(_DATE_OR_PERIOD, original) != _counter(_DATE_OR_PERIOD, rewritten):
        return "날짜·기간 변경"
    if _quoted_values(original) != _quoted_values(rewritten):
        return "인용문 변경"
    if Counter(_ACRONYM.findall(original)) != Counter(_ACRONYM.findall(rewritten)):
        return "대문자 약어 변경"
    if bool(_NEGATION.search(original)) != bool(_NEGATION.search(rewritten)):
        return "부정 표현 변경"
    if bool(_CAUSATION.search(original)) != bool(_CAUSATION.search(rewritten)):
        return "인과 표현 변경"
    compact_original = re.sub(r"\s+", "", original)
    compact_rewritten = re.sub(r"\s+", "", rewritten)
    for term in protected_terms:
        compact_term = re.sub(r"\s+", "", term)
        if compact_term and compact_term in compact_original and compact_term not in compact_rewritten:
            return f"보호 용어 변경: {term}"
    return None


def validate_rewrite(
    original: str,
    rewritten: str,
    *,
    protected_terms: tuple[str, ...] = (),
    warning_ratio: float = WARNING_CHANGE_RATIO,
    max_ratio: float = MAX_CHANGE_RATIO,
) -> RewriteValidation:
    rewritten = rewritten.strip()
    issues: list[str] = []
    original_sentences = sentence_count(original)
    rewritten_sentences = sentence_count(rewritten)
    if not rewritten:
        issues.append("빈 출력")
    if original_sentences != rewritten_sentences:
        issues.append("문장 수 변경")
    meaning_issue = meaning_preservation_issue(original, rewritten, protected_terms)
    if meaning_issue:
        issues.append(meaning_issue)
    ratio = change_ratio(original, rewritten)
    if ratio > max_ratio:
        issues.append(f"변경률 {ratio:.1%}가 최대 허용률 {max_ratio:.1%} 초과")
    return RewriteValidation(
        valid=not issues,
        issues=tuple(issues),
        change_ratio=ratio,
        warning=ratio > warning_ratio,
        sentence_count_original=original_sentences,
        sentence_count_rewritten=rewritten_sentences,
    )
