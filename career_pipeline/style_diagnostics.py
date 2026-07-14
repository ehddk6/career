"""설명 가능한 한국어 문체 위험 진단. AI 작성 여부를 판정하지 않습니다."""

from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re
from statistics import mean, pstdev


_SENTENCE = re.compile(r"[^.!?…。\n]+(?:[.!?…。]+|$)")
_START = re.compile(r"^\s*(?:[-*]|\d+[.)])?\s*([^\s,，。.!?\n]{2,12})")
_CLOSING = re.compile(
    r"(했습니다|하겠습니다|합니다|됩니다|입니다|습니다|했어요|해요|어요|아요|한다|했다)$"
)
_PASSIVE = re.compile(r"되었|되어|하게 되|진행되|수행되|받게|되어진")
_NOMINAL = re.compile(r"것|부분|측면")
_NOMINAL_END = re.compile(r"(?:함|됨|임)$")
_ABSTRACT = re.compile(r"최선을 다|성장하겠|기여하겠|노력하겠|발전하겠")
_ABILITY = re.compile(r"[가-힣]+\s+수\s+있(?:습니다|었습니다|다|었다)")
_ADNOMINAL = re.compile(r"[가-힣]+(?:는|은|한|할)\s+[가-힣]+")
_SUBJECT_PRONOUN = re.compile(r"^\s*(저는|제가|우리는|이것은)\b")

_CONNECTORS = ("이를 통해", "또한", "특히", "따라서")
_CONCLUSION_CLICHES = (
    "중요합니다",
    "필요합니다",
    "도움이 됩니다",
    "기여할 수 있습니다",
)
_ABSTRACT_NOUNS = ("효율성 제고", "역량 강화", "가치 창출")
_UNSOLICITED_OPENINGS = (
    "요청하신",
    "먼저 설명드리면",
    "결론부터 말씀드리면",
    "좋은 질문입니다",
    "도움이 되셨으면",
)
_FORMAL_DOCUMENT_TYPES = {
    "self_introduction",
    "report",
    "public_report",
    "technical",
    "legal",
}
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
    chunks: list[str] = []
    for match in _SENTENCE.finditer(text):
        sentence = match.group(0).strip().rstrip(".!?…。 ")
        if sentence:
            chunks.append(sentence)
    return chunks


def _normalized_sentence(text: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", text).lower()


def _has_semantic_repeat(sentences: list[str]) -> bool:
    normalized = [_normalized_sentence(sentence) for sentence in sentences]
    for index, value in enumerate(normalized):
        if len(value) < 25:
            continue
        for other in normalized[:index]:
            if len(other) >= 25 and SequenceMatcher(None, value, other).ratio() >= 0.88:
                return True
    return False


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


def diagnose_text(
    text: str,
    question_index: int = 0,
    *,
    document_type: str = "self_introduction",
) -> StyleDiagnostics:
    sentences = _sentences(text)
    endings = [
        matches[-1] if (matches := _CLOSING.findall(sentence)) else None
        for sentence in sentences
    ]
    starts = [
        match.group(1).strip()
        for sentence in sentences
        if (match := _START.search(sentence))
    ]
    lengths = [len(sentence.replace(" ", "")) for sentence in sentences]
    reasons: list[str] = []
    score = 0
    formal_document = document_type in _FORMAL_DOCUMENT_TYPES

    if _has_consecutive_repeat(endings):
        reasons.append("같은 종결 표현 3회 이상 반복")
        score += 1 if formal_document else 2
    start_counts = Counter(starts)
    if any(count >= 2 for count in start_counts.values()):
        reasons.append("같은 문장 시작 표현 반복")
        score += 2
    cliché_hits = sum(text.count(phrase) for phrase in _CLICHES)
    if cliché_hits:
        reasons.append("상투 표현 반복")
        score += min(2, cliché_hits)

    variance = pstdev(lengths) if len(lengths) >= 3 else 999.0
    length_cv = variance / mean(lengths) if len(lengths) >= 5 and mean(lengths) else 999.0
    if len(lengths) >= 5 and length_cv < 0.18:
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

    connector_counts = {phrase: text.count(phrase) for phrase in _CONNECTORS}
    repeated_connectors = [
        phrase for phrase, count in connector_counts.items() if count >= 2
    ]
    if repeated_connectors:
        reasons.append("연결어 반복: " + ", ".join(repeated_connectors))
        score += 2 if len(repeated_connectors) >= 2 else 1

    ability_hits = len(_ABILITY.findall(text))
    if ability_hits >= 2:
        reasons.append("'할 수 있습니다' 반복")
        score += 2

    conclusion_hits = sum(text.count(phrase) for phrase in _CONCLUSION_CLICHES)
    if conclusion_hits >= 2:
        reasons.append("결론형 상투어 반복")
        score += 2
    abstract_noun_hits = sum(text.count(phrase) for phrase in _ABSTRACT_NOUNS)
    if abstract_noun_hits >= 2:
        reasons.append("행동 근거 없는 추상 명사 반복")
        score += 2

    pronoun_starts = sum(bool(_SUBJECT_PRONOUN.search(sentence)) for sentence in sentences)
    pronoun_threshold = 3 if document_type == "self_introduction" else 2
    if pronoun_starts >= pronoun_threshold:
        reasons.append("불필요한 주어·대명사 반복")
        score += 1 if formal_document else 2

    nominal_end_hits = sum(bool(_NOMINAL_END.search(sentence)) for sentence in sentences)
    if nominal_end_hits >= 2:
        reasons.append("명사형 종결 반복")
        score += 1 if document_type in {"report", "public_report"} else 2

    long_relative_hits = sum(
        len(sentence.replace(" ", "")) >= 70
        and len(_ADNOMINAL.findall(sentence)) >= 3
        for sentence in sentences
    )
    if long_relative_hits:
        reasons.append("긴 관형절이 겹친 문장")
        score += 1

    semantic_repeat = _has_semantic_repeat(sentences)
    if semantic_repeat:
        reasons.append("같은 의미의 문장 반복")
        score += 2

    unsolicited_opening = next(
        (phrase for phrase in _UNSOLICITED_OPENINGS if text.lstrip().startswith(phrase)),
        None,
    )
    if unsolicited_opening:
        reasons.append("요청하지 않은 서론·완충 문구")
        score += 2

    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    list_lines = sum(
        bool(re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line))
        for line in nonempty_lines
    )
    excessive_list = len(nonempty_lines) >= 4 and list_lines / len(nonempty_lines) >= 0.6
    if excessive_list:
        reasons.append("과도한 목록 구성")
        score += 1 if document_type in {"report", "public_report"} else 2

    return StyleDiagnostics(
        question_index=question_index,
        style_risk_score=min(10, score),
        style_reasons=tuple(reasons),
        should_rewrite=score >= 2,
        metrics={
            "sentence_count": len(sentences),
            "sentence_length_variance": round(variance, 3),
            "sentence_length_cv": round(length_cv, 3),
            "passive_ratio": round(passive_ratio, 3),
            "nominal_ratio": round(nominal_ratio, 3),
            "repeated_connector_count": len(repeated_connectors),
            "ability_phrase_count": ability_hits,
            "conclusion_cliche_count": conclusion_hits,
            "abstract_noun_count": abstract_noun_hits,
            "pronoun_start_count": pronoun_starts,
            "nominal_ending_count": nominal_end_hits,
            "long_relative_sentence_count": long_relative_hits,
            "semantic_repeat": int(semantic_repeat),
            "excessive_list": int(excessive_list),
        },
    )


def diagnose_responses(
    responses,
    *,
    document_type: str = "self_introduction",
) -> list[StyleDiagnostics]:
    diagnostics = [
        diagnose_text(
            response.answer,
            response.question_index,
            document_type=document_type,
        )
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
