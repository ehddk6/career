"""답변 품질 점수. 사실성, 직무적합성, 구체성, 자연성, 추상표현, 중복 등을 평가합니다."""
from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from .character_count import count_characters
from .facts import METRIC, _normalize
from .matching import QuestionMatch
from .models import DraftResponse, Question, ValidationIssue
from .nonghyup_guidance import validate_nonghyup_answer
from .posting_schema import PostingAnalysis
from .profile_schema import ExperienceLedger


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    artifact_path: str = ""


@dataclass(frozen=True)
class AnswerQualityScore:
    total: int
    factuality: int
    target_specificity: int
    action_result: int
    job_fit: int
    distinctiveness: int
    naturalness: int
    issues: tuple[str, ...]


MINIMUM_FILL_RATIO = 0.8
DEFAULT_MIN_ANSWER_SCORE = 65
STRICT_MIN_ANSWER_SCORE = 85
STRICT_MIN_AVERAGE_SCORE = 90
TEXT_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")
TARGET_STOPWORDS = {"일반전형", "체험형", "인턴", "금융", "기금", "강원", "직무"}
TEXT_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _normalized_answer(text: str) -> str:
    return "".join(TEXT_TOKEN.findall(text)).lower()


def _target_tokens(target_org: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in TEXT_TOKEN.findall(target_org)
        if len(token) >= 2 and token not in TARGET_STOPWORDS
    )


ACTION_CUES = ("확인", "분석", "대조", "정리", "제안", "개선", "조정", "검토", "작성", "도입")
RESULT_CUES = ("결과", "줄", "높", "개선", "달성", "완료", "방지", "신뢰", "정확", "절감")
ABSTRACT_PHRASES = ("최선을 다", "기여하겠습니다", "성실하게", "적극적으로", "노력하겠습니다", "역량을 발휘")
ACTION_CUES = ACTION_CUES + (
    "확인",
    "분석",
    "비교",
    "검토",
    "정리",
    "제안",
    "개선",
    "조율",
    "작성",
    "실행",
    "공유",
)
RESULT_CUES = RESULT_CUES + (
    "결과",
    "성과",
    "개선",
    "완료",
    "달성",
    "감소",
    "증가",
    "신뢰",
    "만족",
    "수상",
)
ABSTRACT_PHRASES = ABSTRACT_PHRASES + (
    "최선을 다하겠습니다",
    "기여하겠습니다",
    "성실하게",
    "적극적으로",
    "노력하겠습니다",
)


def _word_tokens(text: str) -> set[str]:
    return {token.lower() for token in TEXT_TOKEN.findall(text) if len(token) >= 2}


def score_answer_quality(
    question: Question,
    answer: str,
    target_org: str,
    *,
    job_terms: tuple[str, ...] = (),
    baseline_text: str | None = None,
    peer_answers: tuple[str, ...] = (),
) -> AnswerQualityScore:
    issues: list[str] = []
    factuality = 25
    if baseline_text is not None:
        from .patina_adapter import _metric_values

        if _metric_values(answer) != _metric_values(baseline_text):
            factuality = 0
            issues.append("fact_change")

    target_specificity = 20 if any(
        token.lower() in answer.lower() for token in _target_tokens(target_org)
    ) else 0
    if not target_specificity:
        issues.append("missing_target")

    has_action = any(cue in answer for cue in ACTION_CUES)
    has_result = any(cue in answer for cue in RESULT_CUES)
    action_result = (10 if has_action else 0) + (10 if has_result else 0)
    if not has_action:
        issues.append("missing_action")
    if not has_result:
        issues.append("missing_result")

    answer_tokens = _word_tokens(answer)
    job_tokens = set().union(*(_word_tokens(term) for term in job_terms)) if job_terms else set()
    overlap = answer_tokens.intersection(job_tokens)
    job_fit = 15 if len(overlap) >= 2 else 8 if overlap else 0
    if job_terms and not overlap:
        issues.append("missing_job_connection")

    abstract_hits = sum(phrase in answer for phrase in ABSTRACT_PHRASES)
    distinctiveness = max(0, 10 - abstract_hits * 2)
    normalized = _normalized_answer(answer)
    for peer in peer_answers:
        if SequenceMatcher(None, normalized, _normalized_answer(peer)).ratio() >= 0.75:
            distinctiveness = max(0, distinctiveness - 6)
            issues.append("similar_to_other_answer")
            break

    sentences = [item.strip() for item in re.split(r"[.!?。]+", answer) if item.strip()]
    naturalness = 5 if len(sentences) >= 3 else 2
    if len({len(sentence) // 10 for sentence in sentences}) >= 2:
        naturalness += 3
    naturalness = max(0, min(10, naturalness + 2 - abstract_hits))
    if abstract_hits >= 2:
        issues.append("abstract_expression")

    total = factuality + target_specificity + action_result + job_fit + distinctiveness + naturalness
    return AnswerQualityScore(
        total,
        factuality,
        target_specificity,
        action_result,
        job_fit,
        distinctiveness,
        naturalness,
        tuple(issues),
    )


def validate_answer_quality(
    questions: list[Question],
    responses: list[DraftResponse],
    target_org: str,
    *,
    job_terms: tuple[str, ...] = (),
    minimum_score: int = DEFAULT_MIN_ANSWER_SCORE,
    average_minimum_score: int | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_index = {response.question_index: response for response in responses}
    scores: list[AnswerQualityScore] = []
    for question in questions:
        response = by_index.get(question.index)
        if response is None or not response.answer.strip():
            continue
        answer = response.answer.strip()
        if question.character_limit and question.character_limit >= 200:
            minimum = round(question.character_limit * MINIMUM_FILL_RATIO)
            answer_length = count_characters(answer, question.count_mode)
            if answer_length < minimum:
                issues.append(
                    ValidationIssue(
                        "underfilled_answer",
                        question.index,
                        f"답변이 충분히 구체적이지 않습니다: {answer_length}/{question.character_limit}자 (최소 {minimum}자, {question.count_mode})",
                    )
                )
        prompt = question.prompt.replace(" ", "")
        needs_target = ("지원" in prompt and "동기" in prompt) or "주요사업" in prompt
        target_tokens = _target_tokens(target_org)
        if needs_target and target_tokens and not any(
            token.lower() in answer.lower() for token in target_tokens
        ):
            issues.append(
                ValidationIssue(
                    "missing_target_specificity",
                    question.index,
                    "지원 기관 또는 사업을 선택한 이유가 답변에 드러나지 않습니다.",
                )
            )

        issues.extend(_validate_prompt_requirements(question, answer))
        issues.extend(validate_nonghyup_answer(question, answer, target_org))
        score = score_answer_quality(
            question,
            answer,
            target_org,
            job_terms=job_terms,
        )
        scores.append(score)
        if score.total < minimum_score:
            issues.append(
                ValidationIssue(
                    "low_quality_score",
                    question.index,
                    f"품질 점수 {score.total}/100점으로 기준 {minimum_score}점에 미달합니다.",
                )
            )
        if "경험" in question.prompt and "missing_action" in score.issues:
            issues.append(
                ValidationIssue(
                    "missing_concrete_action",
                    question.index,
                    "경험 문항에 본인이 직접 수행한 행동이 드러나지 않습니다.",
                )
            )
        if "경험" in question.prompt and "missing_result" in score.issues:
            issues.append(
                ValidationIssue(
                    "missing_concrete_result",
                    question.index,
                    "경험 문항에 행동 이후의 결과 또는 변화가 없습니다.",
                )
            )
        if job_terms and "missing_job_connection" in score.issues:
            issues.append(
                ValidationIssue(
                    "missing_job_connection",
                    question.index,
                    "답변이 공고의 업무·역량과 연결되지 않습니다.",
                )
            )
        if "abstract_expression" in score.issues:
            issues.append(
                ValidationIssue(
                    "abstract_expression",
                    question.index,
                    "추상적 다짐이 반복됩니다. 행동과 결과로 바꾸십시오.",
                )
            )

    if len(questions) >= 4:
        first_use: dict[str, int] = {}
        for response in responses:
            for reference in response.experience_refs:
                previous = first_use.setdefault(
                    reference.experience_id, response.question_index
                )
                if previous != response.question_index:
                    issues.append(
                        ValidationIssue(
                            "reused_experience",
                            response.question_index,
                            f"문항 {previous}과 같은 경험({reference.experience_id})을 재사용했습니다.",
                        )
                    )
                    break

    normalized = [
        (response.question_index, _normalized_answer(response.answer))
        for response in responses
        if response.answer.strip()
    ]
    for position, (left_index, left) in enumerate(normalized):
        for right_index, right in normalized[position + 1 :]:
            if min(len(left), len(right)) < 80:
                continue
            if SequenceMatcher(None, left, right).ratio() >= 0.88:
                issues.append(
                    ValidationIssue(
                        "duplicate_answer",
                        right_index,
                        f"문항 {left_index}과 답변 내용이 지나치게 유사합니다.",
                    )
                )

    if average_minimum_score is not None and scores:
        average = round(sum(score.total for score in scores) / len(scores), 1)
        if average < average_minimum_score:
            issues.append(
                ValidationIssue(
                    "low_average_quality_score",
                    0,
                    f"전체 평균 품질 점수 {average}/100점으로 기준 {average_minimum_score}점에 미달합니다.",
                )
            )
    return issues


def validate_interview_pack(
    interview_text: str,
    questions: list[Question],
    responses: list[DraftResponse],
    *,
    allowed_metric_values: set[str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_sections = (
        "1분 자기소개",
        "30초",
        "60초",
        "90초",
        "꼬리질문",
        "압박질문",
        "평가 기준",
        "근거",
    )
    for section in required_sections:
        if section not in interview_text:
            issues.append(
                ValidationIssue(
                    "missing_interview_section",
                    0,
                    f"면접팩 누락: {section}",
                )
            )
    for question in questions:
        markers = (f"문항 {question.index}", f"문항{question.index}")
        if not any(marker in interview_text for marker in markers):
            issues.append(
                ValidationIssue(
                    "missing_interview_question",
                    question.index,
                    f"면접팩에 문항 {question.index} 대응 답변이 없습니다.",
                )
            )
    for response in responses:
        if response.answer.strip() and response.answer[:12] not in interview_text:
            prompt_marker = f"문항 {response.question_index}"
            if prompt_marker not in interview_text:
                issues.append(
                    ValidationIssue(
                        "interview_not_linked_to_answer",
                        response.question_index,
                        "면접팩이 최종 자기소개서 답변과 연결되어 있지 않습니다.",
                    )
                )
    if allowed_metric_values is not None:
        for match in METRIC.finditer(interview_text):
            normalized, _ = _normalize(match.group("number"), match.group("unit"))
            if normalized not in allowed_metric_values:
                issues.append(
                    ValidationIssue(
                        "unapproved_interview_metric",
                        0,
                        f"면접팩의 승인되지 않은 수치: {match.group(0)}",
                    )
                )
    return issues


def _has_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def _validate_prompt_requirements(
    question: Question, answer: str
) -> list[ValidationIssue]:
    prompt = question.prompt.replace(" ", "")
    issues: list[ValidationIssue] = []

    if "성장가능성" in prompt and "활용" in prompt:
        if not _has_any(answer, ("부족", "보완", "처음", "계기", "판단")) or not _has_any(
            answer, ("농협", "업무", "활용", "입사")
        ):
            issues.append(
                ValidationIssue(
                    "missing_growth_arc",
                    question.index,
                    "성장 문항에는 출발점·개선 노력과 농협 업무 활용을 모두 제시해야 합니다.",
                )
            )

    if "의사결정" in prompt and "기준" in prompt:
        if not _has_any(
            answer, ("기준", "규정", "자료", "정보", "시세", "비교", "대조", "검토", "분석")
        ) or not _has_any(answer, ("결정", "판단", "선택", "보류")):
            issues.append(
                ValidationIssue(
                    "missing_decision_basis",
                    question.index,
                    "의사결정 문항에는 검토 정보·판단 기준과 최종 결정을 모두 제시해야 합니다.",
                )
            )

    if "신뢰" in prompt and "태도" in prompt and "행동" in prompt:
        if not _has_any(answer, ("역할", "담당", "맡")) or not _has_any(
            answer, ("함께", "공유", "협조", "동료", "설명", "나눠")
        ):
            issues.append(
                ValidationIssue(
                    "missing_trust_process",
                    question.index,
                    "신뢰 문항에는 맡은 역할과 동료를 대하는 구체적 태도·행동이 필요합니다.",
                )
            )

    if ("가치" in prompt or "원칙" in prompt) and "역할" in prompt:
        if not _has_any(answer, ("경험", "당시", "때", "과정")) or not _has_any(
            answer, ("농협", "역할", "직원", "기여")
        ):
            issues.append(
                ValidationIssue(
                    "missing_value_evidence",
                    question.index,
                    "가치 문항에는 가치의 근거가 된 경험과 농협에서의 역할을 모두 제시해야 합니다.",
                )
            )

    integrated_prompt = all(
        cue in prompt for cue in ("교육지원", "경제", "금융")
    ) and "구조" in prompt
    if integrated_prompt:
        has_businesses = all(cue in answer for cue in ("교육지원", "경제", "금융"))
        has_linkage = _has_any(answer, ("연결", "맞물", "순환", "통합", "동시에"))
        has_contribution = _has_any(answer, ("기여", "역할", "하겠습니다", "입사"))
        if not (has_businesses and has_linkage and has_contribution):
            issues.append(
                ValidationIssue(
                    "missing_integrated_business_structure",
                    question.index,
                    "교육지원·경제·금융의 연결 구조와 본인의 구체적 기여를 모두 제시해야 합니다.",
                )
            )

    return issues


def validate_profile_gate(
    ledger: ExperienceLedger,
    *,
    selected_experience_ids: set[str],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    by_id = {item.experience_id: item for item in ledger.experiences}
    for experience_id in sorted(selected_experience_ids):
        experience = by_id.get(experience_id)
        if experience is None:
            issues.append(
                QualityIssue(
                    "unknown_profile_experience",
                    f"경험 원장에 없는 ID입니다: {experience_id}",
                    "02_확정경험원장.json",
                )
            )
            continue
        if experience.status == "stale" or any(
            claim.status == "stale" for claim in experience.claims
        ):
            issues.append(
                QualityIssue(
                    "stale_profile_evidence",
                    f"근거 재확인이 필요한 경험입니다: {experience_id}",
                    "02_확정경험원장.json",
                )
            )
        elif experience.status != "confirmed":
            issues.append(
                QualityIssue(
                    "unapproved_profile_experience",
                    f"승인되지 않은 경험입니다: {experience_id}",
                    "02_확정경험원장.json",
                )
            )

    claims_by_evidence: dict[tuple[str, int, str], set[str]] = {}
    for experience in ledger.experiences:
        if experience.status != "confirmed":
            continue
        for claim in experience.claims:
            if claim.status != "confirmed":
                continue
            # Generic extractor fields may legitimately contain multiple values in one
            # sentence (for example, time reduced 50% and errors reduced 90%). Only
            # semantically named, single-value fields are safe to treat as conflicts.
            if claim.field.startswith("metric:"):
                continue
            for evidence in claim.evidence:
                key = (evidence.source_path, evidence.paragraph_index, claim.field)
                claims_by_evidence.setdefault(key, set()).add(claim.normalized_value)
    for key, values in claims_by_evidence.items():
        if len(values) > 1:
            issues.append(
                QualityIssue(
                    "conflicting_profile_claim",
                    f"동일 근거의 확정 값이 충돌합니다: {key[0]}#{key[1]} {sorted(values)}",
                    "02_확정경험원장.json",
                )
            )
    return issues


def validate_posting_gate(analysis: PostingAnalysis) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if analysis.source.official_status == "unverified":
        issues.append(
            QualityIssue(
                "unverified_posting",
                "채용공고의 공식 출처를 확인하지 못했습니다.",
                "00_채용공고분석.md",
            )
        )
    for field, value in (
        ("organization", analysis.organization),
        ("role", analysis.role),
        ("duties", analysis.duties),
        ("questions", analysis.questions),
    ):
        if not value:
            issues.append(
                QualityIssue(
                    f"missing_posting_{field}",
                    f"채용공고 필수 항목을 추출하지 못했습니다: {field}",
                    "00_채용공고분석.md",
                )
            )
    return issues


def validate_matching_gate(
    matches: tuple[QuestionMatch, ...],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for match in matches:
        reliable = [
            candidate for candidate in match.candidates if candidate.evidence_score == 40
        ]
        if not reliable:
            issues.append(
                QualityIssue(
                    "missing_reliable_match",
                    f"문항 {match.question.index}에 근거 신뢰도 40점 경험이 없습니다.",
                    "03_경험직무매칭.md",
                )
            )
            continue
        if not any(
            candidate.duty_score
            + candidate.competency_score
            + candidate.question_fit_score
            >= 15
            for candidate in reliable
        ):
            issues.append(
                QualityIssue(
                    "missing_relevant_match",
                    f"문항 {match.question.index}에 직무 또는 문항 관련성이 확인된 경험이 없습니다.",
                    "03_경험직무매칭.md",
                )
            )
    return issues
