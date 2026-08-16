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
_AI_FORMULA = (
    "체화하겠습니다",
    "체화했습니다",
    "핵심 교량",
    "다수 포진",
    "탄탄한 기반",
    "든든한 조력자",
    "실질적인 개선",
    "선제적으로",
    "체계적으로",
    "책임감을 갖고",
    "신뢰받는 인턴",
)
_CONTROL_FORMULA = (
    "근거와 함께 보고",
    "임의로 판단하지 않",
    "확인한 사실과",
    "추가 확인 사항",
    "업무 흐름",
    "업무별 점검표",
    "반복되는 오류",
    "처리 결과",
)
_PROCEDURAL_TEMPLATE = (
    "초기 학습, 실행, 점검",
    "첫째",
    "둘째",
    "셋째",
    "입사 초기에는",
    "이후에는",
    "처리 후에는",
    "먼저 익히고",
)
_COMMON_FORMULA = (
    "이를 통해",
    "바탕으로",
    "입사 후에는",
    "기여하겠습니다",
    "중요하다고 생각합니다",
)
_HUMAN_SCENE = re.compile(
    r"처음에는|그때|당시|그 뒤|그러자|그제야|오히려|직접|한참|머뭇|표정|목소리|대화|"
    r"긴장을|손을 움직|하나씩|막막|현장에서|만났|발견했|느꼈|알게 (?:됐|되었)|"
    r"모습을 보|말씀드|여쭤|들었습니다"
)
_CONTROL_VERBS = re.compile(r"확인|정리|구분|기록|보고|점검|대조|숙지")
_NOMINAL_VOCAB = re.compile(
    r"(?:과정|부분|사항|측면|역량|태도|방식|체계|수행|실현|제고|강화|확립|도출|마련)"
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


def editor_axis_scores(text: str) -> dict[str, float]:
    """Score six editor-contract axes without claiming to detect authorship.

    Scores are deterministic writing-risk indicators. They deliberately reward
    readable variation and penalize repeated control language that can make a
    verified self-introduction sound like a procedure manual.
    """

    sentences = _sentences(text)
    sentence_count = max(1, len(sentences))
    lengths = [len(sentence.replace(" ", "")) for sentence in sentences]
    deviation = pstdev(lengths) if len(lengths) >= 3 else 0.0
    average = mean(lengths) if lengths else 0.0
    cv = deviation / average if average else 0.0

    endings = [
        matches[-1] if (matches := _CLOSING.findall(sentence)) else None
        for sentence in sentences
    ]
    ending_counts = Counter(item for item in endings if item)
    dominant_ending_ratio = (
        max(ending_counts.values()) / max(1, sum(ending_counts.values()))
        if ending_counts
        else 0.0
    )
    ending_run = _has_consecutive_repeat(endings)

    repeated_common = sum(max(0, text.count(phrase) - 1) for phrase in _COMMON_FORMULA)
    ai_formula_hits = sum(text.count(phrase) for phrase in _AI_FORMULA)
    control_hits = sum(text.count(phrase) for phrase in _CONTROL_FORMULA)
    procedural_template_hits = sum(
        text.count(phrase) for phrase in _PROCEDURAL_TEMPLATE
    )
    control_verb_hits = len(_CONTROL_VERBS.findall(text))
    scene_hits = len(_HUMAN_SCENE.findall(text))
    nominal_hits = len(_NOMINAL.findall(text)) + len(_NOMINAL_VOCAB.findall(text))
    passive_hits = len(_PASSIVE.findall(text))

    naturalness = 84 + min(16, scene_hits * 3)
    naturalness -= min(30, ai_formula_hits * 7)
    naturalness -= min(20, repeated_common * 5)
    naturalness -= min(16, control_hits * 3)
    naturalness -= min(18, max(0.0, control_verb_hits / sentence_count - 0.8) * 10)
    naturalness -= min(14, max(0, procedural_template_hits - 1) * 3)

    sentence_rhythm = 92.0
    if len(lengths) >= 5:
        if cv < 0.18:
            sentence_rhythm -= 32
        elif cv < 0.25:
            sentence_rhythm -= 18
        elif cv > 0.9:
            sentence_rhythm -= 12
        long_ratio = sum(length >= 85 for length in lengths) / len(lengths)
        sentence_rhythm -= max(0.0, long_ratio - 0.35) * 40
    if ending_run:
        sentence_rhythm -= 15

    ending_variety = 94.0
    if ending_run:
        ending_variety -= 35
    if len(sentences) >= 4 and dominant_ending_ratio >= 0.75:
        ending_variety -= 25
    elif len(sentences) >= 4 and dominant_ending_ratio >= 0.6:
        ending_variety -= 12

    length_balance = 92.0
    if len(lengths) >= 5:
        if not any(length <= 30 for length in lengths):
            length_balance -= 14
        if not any(length >= 55 for length in lengths):
            length_balance -= 14
        if cv < 0.2:
            length_balance -= 20

    translationese_ai = 96.0
    translationese_ai -= min(42, ai_formula_hits * 9)
    translationese_ai -= min(25, repeated_common * 6)
    translationese_ai -= min(20, max(0, control_hits - 1) * 4)
    translationese_ai -= min(12, passive_hits * 3)

    nominalization = 96.0 - min(48, max(0.0, nominal_hits / sentence_count - 0.7) * 16)

    axes = {
        "naturalness": naturalness,
        "sentence_rhythm": sentence_rhythm,
        "ending_variety": ending_variety,
        "sentence_length_balance": length_balance,
        "translationese_ai_safety": translationese_ai,
        "nominalization_control": nominalization,
    }
    normalized = {key: round(max(0.0, min(100.0, value)), 2) for key, value in axes.items()}
    weights = {
        "naturalness": 0.45,
        "sentence_rhythm": 0.10,
        "ending_variety": 0.10,
        "sentence_length_balance": 0.05,
        "translationese_ai_safety": 0.25,
        "nominalization_control": 0.05,
    }
    normalized["editor_total"] = round(
        sum(normalized[axis] * weight for axis, weight in weights.items()), 2
    )
    return normalized


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
    editor_axes = editor_axis_scores(text)

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

    procedural_template_hits = sum(
        text.count(phrase) for phrase in _PROCEDURAL_TEMPLATE
    )
    if procedural_template_hits >= 3:
        reasons.append("초기학습·실행·점검 절차 템플릿 과다")
        score += 1

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

    axis_labels = {
        "naturalness": "자연스러운 지원자 목소리 부족",
        "sentence_rhythm": "문장 호흡과 리듬 단조",
        "ending_variety": "종결 표현 다양성 부족",
        "sentence_length_balance": "장단문 균형 부족",
        "translationese_ai_safety": "번역투·AI 관용구 위험",
        "nominalization_control": "명사화 통제 부족",
    }
    for axis, label in axis_labels.items():
        if editor_axes[axis] < 72 and label not in reasons:
            reasons.append(label)
            score += 1

    rewrite_required = (
        score >= 2
        or editor_axes["editor_total"] < 80
        or min(editor_axes[axis] for axis in axis_labels) < 65
    )
    if (
        document_type == "self_introduction"
        and reasons
        and all("종결" in reason for reason in reasons)
    ):
        # Formal Korean applications naturally repeat polite declarative
        # endings. Keep the axis and warning visible, but do not spend a model
        # call when it is the only issue.
        rewrite_required = False

    return StyleDiagnostics(
        question_index=question_index,
        style_risk_score=min(10, score),
        style_reasons=tuple(reasons),
        should_rewrite=rewrite_required,
        metrics={
            "sentence_count": len(sentences),
            "sentence_length_variance": round(variance, 3),
            "sentence_length_cv": round(length_cv, 3),
            "passive_ratio": round(passive_ratio, 3),
            "nominal_ratio": round(nominal_ratio, 3),
            "repeated_connector_count": len(repeated_connectors),
            "procedural_template_count": procedural_template_hits,
            "ability_phrase_count": ability_hits,
            "conclusion_cliche_count": conclusion_hits,
            "abstract_noun_count": abstract_noun_hits,
            "pronoun_start_count": pronoun_starts,
            "nominal_ending_count": nominal_end_hits,
            "long_relative_sentence_count": long_relative_hits,
            "semantic_repeat": int(semantic_repeat),
            "excessive_list": int(excessive_list),
            **editor_axes,
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
    repeated_formulas = {
        phrase
        for phrase in (*_CONTROL_FORMULA, *_COMMON_FORMULA)
        if sum(phrase in response.answer for response in responses) >= 2
    }
    if repeated_formulas:
        for index, response in enumerate(responses):
            local = sorted(phrase for phrase in repeated_formulas if phrase in response.answer)
            if not local:
                continue
            item = diagnostics[index]
            metrics = dict(item.metrics)
            metrics["cross_question_formula_count"] = len(local)
            for axis in ("naturalness", "translationese_ai_safety", "editor_total"):
                metrics[axis] = round(max(0.0, float(metrics.get(axis, 0.0)) - 8), 2)
            diagnostics[index] = StyleDiagnostics(
                item.question_index,
                min(10, item.style_risk_score + 2),
                item.style_reasons + (
                    "문항 간 통제·상투 문구 반복: " + ", ".join(local),
                ),
                True,
                metrics,
            )
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


def style_repair_details(text: str) -> dict[str, object]:
    """Expose exact sentence starts and ending runs for a bounded style repair."""
    sentences = _sentences(text)
    rows: list[dict[str, object]] = []
    starts: list[str | None] = []
    endings: list[str | None] = []
    for index, sentence in enumerate(sentences, 1):
        start_match = _START.search(sentence)
        ending_matches = _CLOSING.findall(sentence)
        start = start_match.group(1).strip() if start_match else None
        ending = ending_matches[-1] if ending_matches else None
        starts.append(start)
        endings.append(ending)
        rows.append(
            {
                "sentence_index": index,
                "start_token": start,
                "ending_class": ending,
                "text": sentence,
            }
        )
    start_counts = Counter(item for item in starts if item)
    ending_runs: list[dict[str, object]] = []
    run_start = 0
    for index in range(1, len(endings) + 1):
        if index < len(endings) and endings[index] == endings[run_start] and endings[index]:
            continue
        if endings[run_start] and index - run_start >= 3:
            ending_runs.append(
                {
                    "ending_class": endings[run_start],
                    "sentence_indexes": list(range(run_start + 1, index + 1)),
                }
            )
        run_start = index
    return {
        "repeated_start_tokens": sorted(
            token for token, count in start_counts.items() if count >= 2
        ),
        "consecutive_ending_runs": ending_runs,
        "sentences": rows,
    }
