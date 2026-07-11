"""자기소개서 검증. 빈 답변, 글자수, 블라인드 용어, 타기관명, [확인 필요] 마커 등을 검사합니다."""
from .character_count import count_characters
from .facts import METRIC, _normalize
from .models import DraftResponse, Question, ValidationIssue
from .profile_schema import ExperienceLedger


BLIND_TERMS = ("대학교", "대학원", "출신지역", "생년월일", "가족관계")
KNOWN_ORGANIZATIONS = (
    "주택도시보증공사",
    "국민연금공단",
    "국민건강보험공단",
    "한국주택금융공사",
    "서울교통공사",
    "IBK기업은행",
    "NH농협은행",
    "신한은행",
    "우리은행",
    "한국공정거래조정원",
    "건강보험심사평가원",
    "사회보장정보원",
    "새마을금고",
    "한국도로공사서비스",
    "서울특별시농수산식품공사",
    "농협",
)
TARGET_ALIASES = {
    "HUG": {"주택도시보증공사"},
    "HF": {"한국주택금융공사"},
    "NPS": {"국민연금공단"},
    "NH": {"NH농협은행", "농협"},
    "IBK": {"IBK기업은행"},
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
    *,
    profile_ledger: ExperienceLedger | None = None,
    require_experience_refs: bool = False,
) -> list[ValidationIssue]:
    by_index = {item.question_index: item for item in responses}
    issues = []
    known_indexes = {question.index for question in questions}
    seen_indexes: set[int] = set()
    for response in responses:
        if response.question_index not in known_indexes:
            issues.append(
                ValidationIssue(
                    "unknown_question_index",
                    response.question_index,
                    "초안에 정의되지 않은 문항 번호가 있습니다.",
                )
            )
        elif response.question_index in seen_indexes:
            issues.append(
                ValidationIssue(
                    "duplicate_response",
                    response.question_index,
                    "같은 문항에 대한 답변이 둘 이상 있습니다.",
                )
            )
        seen_indexes.add(response.question_index)
    for question in questions:
        response = by_index.get(question.index)
        answer = response.answer.strip() if response else ""
        if not answer:
            issues.append(
                ValidationIssue("empty_answer", question.index, "답변이 비어 있습니다.")
            )
            continue
        answer_length = count_characters(answer, question.count_mode)
        if question.character_limit and answer_length > question.character_limit:
            issues.append(
                ValidationIssue(
                    "over_limit",
                    question.index,
                    f"{answer_length}/{question.character_limit}자",
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
        if "[확인 필요" in answer:
            issues.append(
                ValidationIssue(
                    "unconfirmed_placeholder",
                    question.index,
                    "확인되지 않은 자리표시자가 포함되어 있습니다.",
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
        if profile_ledger is not None:
            issues.extend(
                _validate_experience_refs(
                    response,
                    profile_ledger,
                    require_experience_refs=require_experience_refs,
                )
            )
    return issues


def _validate_experience_refs(
    response: DraftResponse,
    ledger: ExperienceLedger,
    *,
    require_experience_refs: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if require_experience_refs and not response.experience_refs:
        return [
            ValidationIssue(
                "missing_experience_ref",
                response.question_index,
                "V2 답변에는 경험 원장 참조가 필요합니다.",
            )
        ]
    by_id = {item.experience_id: item for item in ledger.experiences}
    allowed_values: set[str] = set()
    for reference in response.experience_refs:
        experience = by_id.get(reference.experience_id)
        if experience is None:
            issues.append(
                ValidationIssue(
                    "unknown_experience_ref",
                    response.question_index,
                    f"경험 원장에 없는 ID: {reference.experience_id}",
                )
            )
            continue
        claims_by_field = {}
        for claim in experience.claims:
            claims_by_field.setdefault(claim.field, []).append(claim)
        for field in reference.claim_fields:
            claims = claims_by_field.get(field)
            if not claims:
                issues.append(
                    ValidationIssue(
                        "unknown_claim_field",
                        response.question_index,
                        f"경험 {reference.experience_id}에 없는 claim field: {field}",
                    )
                )
                continue
            confirmed = [claim for claim in claims if claim.status == "confirmed"]
            if experience.status != "confirmed" or not confirmed:
                issues.append(
                    ValidationIssue(
                        "unconfirmed_claim_ref",
                        response.question_index,
                        f"확정되지 않은 claim field: {reference.experience_id}.{field}",
                    )
                )
                continue
            allowed_values.update(claim.normalized_value for claim in confirmed)

    for match in METRIC.finditer(response.answer):
        normalized, _ = _normalize(match.group("number"), match.group("unit"))
        if normalized not in allowed_values:
            issues.append(
                ValidationIssue(
                    "unapproved_metric",
                    response.question_index,
                    f"승인된 참조 값이 아닌 수치: {match.group(0)}",
                )
            )
    return issues


def referenced_claim_values(
    responses: list[DraftResponse], ledger: ExperienceLedger
) -> set[str]:
    by_id = {item.experience_id: item for item in ledger.experiences}
    values: set[str] = set()
    for response in responses:
        for reference in response.experience_refs:
            experience = by_id.get(reference.experience_id)
            if experience is None or experience.status != "confirmed":
                continue
            for claim in experience.claims:
                if claim.field in reference.claim_fields and claim.status == "confirmed":
                    values.add(claim.normalized_value)
    return values
