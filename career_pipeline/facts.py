import re

from .models import ExtractedDocument, FactClaim


METRIC = re.compile(
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>억\s*원|천만\s*원|만\s*원|원|건|명|%|페이지|일|주|개월|년)"
)
TOKEN = re.compile(r"[가-힣A-Za-z]{2,}")
STOPWORDS = {
    "경험",
    "당시",
    "결과",
    "통해",
    "했습니다",
    "있습니다",
    "업무",
    "대한",
}
PARTICLES = ("에서", "으로", "로서", "로써", "을", "를", "은", "는", "이", "가", "의", "에", "와", "과")


def _normalize_token(token: str) -> str:
    for particle in PARTICLES:
        if token.endswith(particle) and len(token) > len(particle) + 1:
            return token[: -len(particle)]
    return token


def _normalize(number: str, unit: str) -> tuple[str, str]:
    value = float(number.replace(",", ""))
    compact = unit.replace(" ", "")
    if compact == "억원":
        return f"{int(value * 100_000_000)}원", "money"
    if compact == "천만원":
        return f"{int(value * 10_000_000)}원", "money"
    if compact == "만원":
        return f"{int(value * 10_000)}원", "money"
    return (
        f"{number.replace(',', '')}{compact}",
        "percentage" if compact == "%" else compact,
    )


def _field(context: str, number: str, unit_kind: str) -> str:
    escaped_number = re.escape(number)
    if unit_kind == "percentage" and (
        re.search(
            rf"(?:속도|시간|업무량|처리량).{{0,30}}{escaped_number}\s*%",
            context,
        )
        or re.search(
            rf"{escaped_number}\s*%.{{0,20}}(?:단축|감소|향상)",
            context,
        )
    ):
        return "metric:percentage"
    if any(word in context for word in ("절감", "예산", "누수", "낭비", "지켜")) and unit_kind in {
        "money",
        "percentage",
    }:
        return "budget_savings"
    if unit_kind == "건" and re.search(
        rf"{escaped_number}\s*건(?:의\s*(?:영수증|청구|자료)|[을를]\s*처리)",
        context,
    ):
        return "processed_case_count"
    if unit_kind == "건" and any(
        word in context for word in ("적발", "발견", "확인", "처리")
    ):
        return "case_count"
    if unit_kind == "년" and len(number.replace(",", "")) == 4:
        return "metric:년"
    if unit_kind == "년" and re.search(r"\d[\d,]*(?:\.\d+)?\s*년\s*차", context):
        return "metric:년"
    if unit_kind in {"일", "주", "개월", "년"} and (
        "근무" in context
        or "재직" in context
        or "인턴 기간" in context
        or "아르바이트 기간" in context
    ):
        return "employment_period"
    return f"metric:{unit_kind}"


def _sentence_window(context: str, start: int, end: int) -> tuple[str, int, int]:
    left = max(context.rfind(mark, 0, start) for mark in (".", "!", "?", "\n"))
    boundaries = [context.find(mark, end) for mark in (".", "!", "?", "\n")]
    right_candidates = [position for position in boundaries if position >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(context)
    segment_start = left + 1
    return context[segment_start:right].strip(), start - segment_start, end - segment_start


def extract_fact_claims(documents: list[ExtractedDocument]) -> list[FactClaim]:
    claims = []
    for document in documents:
        for paragraph_index, context in enumerate(document.paragraphs):
            for match in METRIC.finditer(context):
                sentence, local_start, local_end = _sentence_window(
                    context, match.start(), match.end()
                )
                nearby = sentence[
                    max(0, local_start - 120) : min(len(sentence), local_end + 120)
                ]
                classification = sentence[
                    max(0, local_start - 50) : min(len(sentence), local_end + 50)
                ]
                tokens = frozenset(
                    normalized
                    for raw in TOKEN.findall(nearby)
                    if (normalized := _normalize_token(raw)) not in STOPWORDS
                )
                normalized, unit_kind = _normalize(
                    match.group("number"), match.group("unit")
                )
                claims.append(
                    FactClaim(
                        document.source.relative_path,
                        paragraph_index,
                        context,
                        _field(classification, match.group("number"), unit_kind),
                        match.group(0),
                        normalized,
                        unit_kind,
                        tokens,
                    )
                )
    return claims
