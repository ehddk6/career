"""문항-경험 매칭. 직무/역량/문항 적합도로 점수를 계산하고 재사용 패널티를 적용합니다."""
from dataclasses import dataclass, replace
import re

from .models import Question
from .nonghyup_guidance import classify_nonghyup_prompt, render_nonghyup_guidance
from .posting_schema import PostingAnalysis
from .profile_schema import Experience, ExperienceLedger, ProfileClaim


QUESTION_TYPES = {
    "motivation": ("지원동기", "지원하게 된 동기", "입사 후"),
    "problem_solving": ("문제", "개선", "새로운 접근", "변화"),
    "collaboration": ("협업", "갈등", "팀"),
    "trust": ("책임감", "성실", "신뢰", "원칙"),
}
TYPE_CUES = {
    "problem_solving": ("문제", "개선", "해결", "확인", "분석", "변화"),
    "collaboration": ("협업", "협력", "갈등", "팀", "조정", "공동"),
    "trust": ("책임", "성실", "신뢰", "원칙", "정확"),
    "motivation": ("고객", "정확", "자료", "지원", "학습"),
    "general": ("확인", "정리", "기록", "자료", "고객"),
    "growth": ("부족", "보완", "개선", "학습", "피드백", "성장"),
    "decision": ("기준", "자료", "분석", "비교", "검토", "결정", "판단"),
    "value_role": ("신뢰", "책임", "원칙", "상생", "고객", "지역"),
    "integrated_business": ("교육지원", "경제", "금융", "연결", "통합", "지역"),
    "future_innovation": ("스마트팜", "디지털", "데이터", "브랜딩", "유통", "청년농"),
}
SYNONYMS = {
    "검토": "확인",
    "검증": "확인",
    "대조": "확인",
    "협력": "협업",
    "정확성": "정확",
}
TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
STOPWORDS = {"업무", "경험", "상황", "관련", "대한"}
KOREAN_PARTICLES = ("에서", "에게", "으로", "까지", "부터", "을", "를", "이", "가", "은", "는", "의", "에", "와", "과", "도")


@dataclass(frozen=True)
class MatchCandidate:
    experience_id: str
    total_score: int
    evidence_score: int
    duty_score: int
    competency_score: int
    question_fit_score: int
    reuse_penalty: int
    matched_duties: tuple[str, ...]
    matched_competencies: tuple[str, ...]
    allowed_claims: tuple[str, ...]
    blocked_claims: tuple[str, ...]


@dataclass(frozen=True)
class QuestionMatch:
    question: Question
    question_type: str
    candidates: tuple[MatchCandidate, ...]
    recommended: MatchCandidate | None
    allocation_note: str = ""


def _tokens(text: str) -> frozenset[str]:
    normalized_tokens: set[str] = set()
    for token in TOKEN.findall(text):
        normalized = token.lower()
        for particle in KOREAN_PARTICLES:
            if len(normalized) > len(particle) + 1 and normalized.endswith(particle):
                normalized = normalized[: -len(particle)]
                break
        if normalized.endswith("해") and len(normalized) > 2:
            normalized = normalized[:-1]
        normalized = SYNONYMS.get(normalized, normalized)
        if normalized not in STOPWORDS:
            normalized_tokens.add(normalized)
    return frozenset(normalized_tokens)


def _experience_text(experience: Experience) -> str:
    return " ".join(
        (
            experience.title,
            experience.role,
            experience.situation,
            *experience.actions,
            *experience.outcomes,
            *experience.competencies,
        )
    )


def _classify_question(prompt: str) -> str:
    nonghyup_guide = classify_nonghyup_prompt(prompt)
    if nonghyup_guide is not None:
        return nonghyup_guide.question_type
    for question_type, markers in QUESTION_TYPES.items():
        if any(marker in prompt for marker in markers):
            return question_type
    return "general"


def _valid_hash(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _claim_has_evidence(claim: ProfileClaim) -> bool:
    return bool(claim.evidence) and all(
        _valid_hash(item.source_sha256) and _valid_hash(item.excerpt_sha256)
        for item in claim.evidence
    )


def _claims(experience: Experience, status: str) -> tuple[str, ...]:
    return tuple(
        f"{claim.field}={claim.normalized_value}"
        for claim in experience.claims
        if claim.status == status
    )


def _candidate(
    experience: Experience,
    posting: PostingAnalysis,
    question_type: str,
) -> MatchCandidate:
    text = _experience_text(experience)
    experience_tokens = _tokens(text)
    matched_duties = tuple(
        duty
        for duty in posting.duties
        if len(experience_tokens.intersection(_tokens(duty))) >= 2
    )
    matched_competencies = tuple(
        competency
        for competency in posting.competencies
        if experience_tokens.intersection(_tokens(competency))
    )
    evidence_score = (
        40
        if any(
            claim.status == "confirmed" and _claim_has_evidence(claim)
            for claim in experience.claims
        )
        else 0
    )
    duty_score = (
        round(25 * len(matched_duties) / len(posting.duties))
        if posting.duties
        else 0
    )
    competency_score = (
        round(20 * len(matched_competencies) / len(posting.competencies))
        if posting.competencies
        else 0
    )
    question_fit_score = (
        15
        if TYPE_CUES[question_type]
        and any(cue in text for cue in TYPE_CUES[question_type])
        else 0
    )
    allowed = _claims(experience, "confirmed")
    blocked = tuple(
        f"{claim.field}={claim.normalized_value} ({claim.status})"
        for claim in experience.claims
        if claim.status != "confirmed"
    )
    total = evidence_score + duty_score + competency_score + question_fit_score
    return MatchCandidate(
        experience.experience_id,
        total,
        evidence_score,
        duty_score,
        competency_score,
        question_fit_score,
        0,
        matched_duties,
        matched_competencies,
        allowed,
        blocked,
    )


def match_questions(
    ledger: ExperienceLedger,
    posting: PostingAnalysis,
    questions: list[Question] | tuple[Question, ...],
) -> tuple[QuestionMatch, ...]:
    confirmed = tuple(
        experience for experience in ledger.experiences if experience.status == "confirmed"
    )
    used: dict[str, int] = {}
    results: list[QuestionMatch] = []
    for question in questions:
        question_type = _classify_question(question.prompt)
        raw = sorted(
            (_candidate(experience, posting, question_type) for experience in confirmed),
            key=lambda item: (-item.total_score, item.experience_id),
        )
        adjusted = [
            replace(
                item,
                reuse_penalty=15 if used.get(item.experience_id, 0) else 0,
                total_score=item.total_score
                - (15 if used.get(item.experience_id, 0) else 0),
            )
            for item in raw
        ]
        recommended = min(
            adjusted,
            key=lambda item: (-item.total_score, item.experience_id),
            default=None,
        )
        allocation_note = ""
        unused = [item for item in raw if not used.get(item.experience_id, 0)]
        reused = [item for item in raw if used.get(item.experience_id, 0)]
        if unused and reused:
            best_reused = reused[0]
            best_unused = unused[0]
            raw_gap = best_reused.total_score - best_unused.total_score
            if raw_gap < 4:
                recommended = next(
                    item for item in adjusted
                    if item.experience_id == best_unused.experience_id
                )
                allocation_note = (
                    f"재사용 후보({best_reused.experience_id})와 대체 후보"
                    f"({best_unused.experience_id})의 원점수 차이가 {raw_gap}점으로 4점 미만이어서 "
                    "대체 경험을 우선함"
                )
            else:
                allocation_note = (
                    f"재사용 후보({best_reused.experience_id})가 대체 후보"
                    f"({best_unused.experience_id})보다 원점수 {raw_gap}점 높아 재사용을 허용함"
                )
        if recommended is not None:
            used[recommended.experience_id] = used.get(recommended.experience_id, 0) + 1
        results.append(QuestionMatch(
            question, question_type, tuple(raw[:3]), recommended, allocation_note
        ))
    return tuple(results)


def render_matches_markdown(matches: tuple[QuestionMatch, ...]) -> str:
    lines = ["# 경험·직무 매칭", "", "점수는 순위 보조값이며 확률이 아닙니다.", ""]
    for match in matches:
        lines.extend(
            [
                f"## {match.question.index}. {match.question.prompt}",
                "",
                f"- 문항 유형: `{match.question_type}`",
                f"- 추천 경험: `{match.recommended.experience_id if match.recommended else '없음'}`",
                f"- 배치 판단: {match.allocation_note or '첫 사용 또는 대체 후보 없음'}",
                "",
            ]
        )
        lines.extend(render_nonghyup_guidance(match.question))
        lines.append("")
        for candidate in match.candidates:
            lines.extend(
                [
                    f"### `{candidate.experience_id}` · {candidate.total_score}점",
                    "",
                    f"- 근거 {candidate.evidence_score} / 업무 {candidate.duty_score} / 역량 {candidate.competency_score} / 문항 {candidate.question_fit_score}",
                    f"- 일치 업무: {', '.join(candidate.matched_duties) or '없음'}",
                    f"- 일치 역량: {', '.join(candidate.matched_competencies) or '없음'}",
                    f"- 사용 가능: {', '.join(candidate.allowed_claims) or '없음'}",
                    f"- 사용 금지: {', '.join(candidate.blocked_claims) or '없음'}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"
