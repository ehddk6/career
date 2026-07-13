"""설명 가능한 문체 위험 진단. AI 작성 여부를 판정하지 않습니다."""

from collections import Counter
from dataclasses import asdict, dataclass
import re
from statistics import pstdev


_SENTENCE_END = re.compile(r"([^.!?…。]+)[.!?…。]+")
_START = re.compile(r"^\s*([^,，。.!?\n]{2,12})")
_CLOSING = re.compile(r"(습니다|합니다|됩니다|했습니다|하겠습니다|입니다|해요|어요|아요|한다)(?=[.!?…。]|$)")
_PASSIVE = re.compile(r"되었|되어|하게 되|진행되|수행되|받게")
_NOMINAL = re.compile(r"것|부분|사항|과정|관련|대해|위해|바탕으로")
_ABSTRACT = re.compile(r"최선을 다|성장하겠|기여하겠|노력하겠|발전하겠")
_CLICHES = (
    "다양한 경험을 바탕으로",
    "끊임없이 노력하겠습니다",
    "문제 해결 능력을 발휘",
    "적극적으로 기여하겠습니다",
    "성장하는 인재",
)


@dataclass(frozen=True)
class StyleDiagnostics:
    question_index: int
    style_risk_score: int
    style_reasons: tuple[str, ...]
    should_rewrite: bool
    metrics: dict[str, float | int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    chunks = [match.group(1).strip() for match in _SENTENCE_END.finditer(text)]
    return chunks or ([text.strip()] if text.strip() else [])


def _has_consecutive_repeat(values: list[str | None], minimum: int = 3) -> bool:
    previous: str | None = None
    run = 0
    for value in values:
        if value is not None and value == previous:
            run += 1
        elif value is not None:
            previous = value
            run = 1
        else:
            previous = None
            run = 0
        if run >= minimum:
            return True
    return False


def diagnose_text(text: str, question_index: int = 0) -> StyleDiagnostics:
    sentences = _sentences(text)
    endings = [
        match.group(1) if (match := _CLOSING.search(sentence)) else None
        for sentence in sentences
    ]
    starts = [match.group(1).strip() for sentence in sentences if (match := _START.search(sentence))]
    lengths = [len(sentence.replace(" ", "")) for sentence in sentences]
    reasons: list[str] = []
    score = 0

    if _has_consecutive_repeat(endings):
        reasons.append("같은 종결 표현 3회 이상 반복")
        score += 2
    start_counts = Counter(starts)
    if any(count >= 2 for count in start_counts.values()):
        reasons.append("같은 문장 시작 표현 반복")
        score += 2
    cliché_hits = sum(text.count(phrase) for phrase in _CLICHES)
    if cliché_hits:
        reasons.append("상투 표현 반복")
        score += min(2, cliché_hits)
    variance = pstdev(lengths) if len(lengths) >= 3 else 999.0
    if len(lengths) >= 3 and variance < 8:
        reasons.append("문장 길이 분산이 지나치게 낮음")
        score += 1
    passive_ratio = len(_PASSIVE.findall(text)) / max(1, len(sentences))
    if passive_ratio >= 0.5:
        reasons.append("피동 표현 과다")
        score += 2
    nominal_ratio = len(_NOMINAL.findall(text)) / max(1, len(sentences))
    if nominal_ratio >= 1.0:
        reasons.append("명사화 표현 과다")
        score += 1
    abstract_hits = len(_ABSTRACT.findall(text))
    if abstract_hits >= 2:
        reasons.append("추상적 다짐 반복")
        score += 2
    return StyleDiagnostics(
        question_index=question_index,
        style_risk_score=min(10, score),
        style_reasons=tuple(reasons),
        should_rewrite=bool(reasons),
        metrics={
            "sentence_count": len(sentences),
            "sentence_length_variance": round(variance, 3),
            "passive_ratio": round(passive_ratio, 3),
            "nominal_ratio": round(nominal_ratio, 3),
        },
    )


def diagnose_responses(responses) -> list[StyleDiagnostics]:
    diagnostics = [
        diagnose_text(response.answer, response.question_index)
        for response in responses
    ]
    normalized = [re.sub(r"\s+", "", response.answer) for response in responses]
    for index, value in enumerate(normalized):
        if not value:
            continue
        for other_index in range(index):
            other = normalized[other_index]
            if len(value) >= 30 and (value in other or other in value):
                item = diagnostics[index]
                diagnostics[index] = StyleDiagnostics(
                    item.question_index,
                    min(10, item.style_risk_score + 2),
                    item.style_reasons + ("문항 간 표현 중복",),
                    True,
                    {**item.metrics, "cross_question_overlap": 1},
                )
                break
    return diagnostics
