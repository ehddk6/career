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


def _field(context: str, unit_kind: str) -> str:
    if any(word in context for word in ("절감", "예산", "누수", "낭비", "지켜", "줄였")) and unit_kind in {
        "money",
        "percentage",
    }:
        return "budget_savings"
    if unit_kind == "건" and any(
        word in context for word in ("적발", "발견", "확인", "처리")
    ):
        return "case_count"
    if unit_kind in {"일", "주", "개월", "년"}:
        return "duration"
    return f"metric:{unit_kind}"


def extract_fact_claims(documents: list[ExtractedDocument]) -> list[FactClaim]:
    claims = []
    for document in documents:
        for paragraph_index, context in enumerate(document.paragraphs):
            tokens = frozenset(
                normalized
                for raw in TOKEN.findall(context)
                if (normalized := _normalize_token(raw)) not in STOPWORDS
            )
            for match in METRIC.finditer(context):
                normalized, unit_kind = _normalize(
                    match.group("number"), match.group("unit")
                )
                claims.append(
                    FactClaim(
                        document.source.relative_path,
                        paragraph_index,
                        context,
                        _field(context, unit_kind),
                        match.group(0),
                        normalized,
                        unit_kind,
                        tokens,
                    )
                )
    return claims
