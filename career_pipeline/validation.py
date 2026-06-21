from .models import DraftResponse, Question, ValidationIssue


BLIND_TERMS = ("대학교", "대학원", "출신지역", "생년월일", "가족관계")
KNOWN_ORGANIZATIONS = (
    "주택도시보증공사",
    "국민연금공단",
    "국민건강보험공단",
    "한국주택금융공사",
    "서울교통공사",
    "IBK기업은행",
)
TARGET_ALIASES = {
    "HUG": {"주택도시보증공사"},
    "HF": {"한국주택금융공사"},
    "NPS": {"국민연금공단"},
}


def _is_target_organization(organization: str, target_org: str) -> bool:
    if organization in target_org:
        return True
    return any(
        alias in target_org and organization in organizations
        for alias, organizations in TARGET_ALIASES.items()
    )


def validate_draft(
    questions: list[Question],
    responses: list[DraftResponse],
    target_org: str,
    known_sources: set[str],
) -> list[ValidationIssue]:
    by_index = {item.question_index: item for item in responses}
    issues = []
    for question in questions:
        response = by_index.get(question.index)
        answer = response.answer.strip() if response else ""
        if not answer:
            issues.append(
                ValidationIssue("empty_answer", question.index, "답변이 비어 있습니다.")
            )
            continue
        if question.character_limit and len(answer) > question.character_limit:
            issues.append(
                ValidationIssue(
                    "over_limit",
                    question.index,
                    f"{len(answer)}/{question.character_limit}자",
                )
            )
        if not response.evidence_paths:
            issues.append(
                ValidationIssue(
                    "missing_evidence", question.index, "근거 파일이 없습니다."
                )
            )
        for path in response.evidence_paths:
            if path not in known_sources:
                issues.append(
                    ValidationIssue(
                        "unknown_evidence",
                        question.index,
                        f"사실 원장에 없는 근거: {path}",
                    )
                )
        for term in BLIND_TERMS:
            if term in answer:
                issues.append(
                    ValidationIssue(
                        "blind_term",
                        question.index,
                        f"블라인드 위험 표현: {term}",
                    )
                )
        for organization in KNOWN_ORGANIZATIONS:
            if organization in answer and not _is_target_organization(
                organization, target_org
            ):
                issues.append(
                    ValidationIssue(
                        "other_organization",
                        question.index,
                        f"타기관명: {organization}",
                    )
                )
    return issues
