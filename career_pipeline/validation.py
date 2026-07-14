"""자기소개서 검증. 빈 답변, 글자수, 블라인드 용어, 타기관명, [확인 필요] 마커 등을 검사합니다."""
import re
from .character_count import count_characters
from .facts import METRIC, _normalize
from .models import DraftResponse, Question, ValidationIssue
from .prompt_policy import requires_experience_evidence
from .profile_schema import ExperienceLedger, claim_is_submission_safe


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
        needs_experience = requires_experience_evidence(question.prompt)
        has_acceptable_evidence = bool(response.evidence_paths) or (
            not needs_experience and bool(response.research_refs)
        )
        if not has_acceptable_evidence:
            issues.append(
                ValidationIssue(
                    "missing_evidence",
                    question.index,
                    "승인 경험 파일 또는 공식 조사 근거가 없습니다.",
                )
            )
        if (
            question.minimum_character_limit is not None
            and answer_length < question.minimum_character_limit
        ):
            issues.append(
                ValidationIssue(
                    "under_minimum_limit",
                    question.index,
                    f"{answer_length}/{question.minimum_character_limit}",
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
                    require_experience_refs=(
                        require_experience_refs and needs_experience
                    ),
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
    if ledger.schema_version >= 2:
        return _validate_v2_experience_refs(response, ledger, issues)
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
            for claim in confirmed:
                if not _claim_visible_in_answer(claim.normalized_value, response.answer, claim.field):
                    issues.append(
                        ValidationIssue(
                            "experience_claim_not_visible",
                            response.question_index,
                            f"참조한 경험 claim이 답변에 드러나지 않습니다: {reference.experience_id}.{field}",
                        )
                    )
            allowed_values.update(claim.normalized_value for claim in confirmed)

    # Research-only answers are checked against the research ledger, not the
    # personal experience ledger.  Do not treat their external figures as
    # unapproved personal metrics.
    if not response.experience_refs:
        return issues

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


def _validate_v2_experience_refs(
    response: DraftResponse,
    ledger: ExperienceLedger,
    issues: list[ValidationIssue],
) -> list[ValidationIssue]:
    by_id = {item.experience_id: item for item in ledger.experiences}
    allowed_values: set[str] = set()
    for reference in response.experience_refs:
        experience = by_id.get(reference.experience_id)
        if experience is None:
            issues.append(ValidationIssue(
                "unknown_experience_ref", response.question_index,
                f"unknown experience ID: {reference.experience_id}",
            ))
            continue
        if reference.claim_fields:
            issues.append(ValidationIssue(
                "claim_ids_required", response.question_index,
                f"schema v2 requires exact claim_ids: {reference.experience_id}",
            ))
        claims_by_id = {claim.claim_id: claim for claim in experience.claims}
        for claim_id in reference.claim_ids:
            claim = claims_by_id.get(claim_id)
            if claim is None:
                issues.append(ValidationIssue(
                    "unknown_claim_id", response.question_index,
                    f"unknown claim ID: {reference.experience_id}.{claim_id}",
                ))
                continue
            if experience.status != "confirmed" or not claim_is_submission_safe(claim):
                issues.append(ValidationIssue(
                    "unsafe_claim_ref", response.question_index,
                    f"unsafe or unconfirmed claim: {reference.experience_id}.{claim_id}",
                ))
                continue
            if not _claim_visible_in_answer(claim.normalized_value, response.answer, claim.field):
                issues.append(ValidationIssue(
                    "experience_claim_not_visible", response.question_index,
                    f"referenced claim is not visible: {reference.experience_id}.{claim_id}",
                ))
            if _claim_overstates_contribution(claim, response.answer):
                issues.append(ValidationIssue(
                    "contribution_overstatement", response.question_index,
                    f"answer exceeds contribution scope: {reference.experience_id}.{claim_id}",
                ))
            allowed_values.add(claim.normalized_value)
            # A confirmed narrative claim can legitimately contain grounded
            # counts (for example, "50명 인터뷰" or "3,000페이지").  The
            # previous check only added the entire claim string, so the
            # metric scanner rejected those embedded values as unapproved even
            # though the exact claim ID was attached.  Extract the numeric
            # tokens from the referenced claim itself; unreferenced numbers
            # still fail below.
            for metric in METRIC.finditer(claim.normalized_value):
                normalized, _ = _normalize(
                    metric.group("number"), metric.group("unit")
                )
                allowed_values.add(normalized)
    # Research-only answers are verified by ``validate_research_evidence``;
    # their numbers do not belong to the personal experience ledger.  Scan
    # numeric tokens here only when the answer actually cites an experience,
    # otherwise a verified external figure (for example, an official support
    # limit) is incorrectly reported as an unapproved personal metric.
    if response.experience_refs:
        for match in METRIC.finditer(response.answer):
            normalized, _ = _normalize(match.group("number"), match.group("unit"))
            if normalized not in allowed_values:
                issues.append(ValidationIssue(
                    "unapproved_metric", response.question_index,
                    f"metric is not backed by an approved claim: {match.group(0)}",
                ))
    return issues


def _claim_visible_in_answer(value: str, answer: str, field: str) -> bool:
    """Require an experience reference to be used, not merely attached."""
    compact_answer = re.sub(r"[\s,]", "", answer).casefold()
    compact_value = re.sub(r"[\s,]", "", value).casefold()
    if not compact_value:
        return False
    if field.startswith("metric:"):
        return compact_value in compact_answer
    # Narrative claims are often safely paraphrased ("자료를 체계적으로
    # 분류하여" -> "자료의 체계적 분류"). Exact four-character anchors
    # made those paraphrases look ungrounded. Compare normalized content
    # stems while still requiring two shared terms for a multi-term claim.
    def stems(text: str) -> set[str]:
        suffixes = (
            "으로", "에서", "까지", "부터", "하여", "하며", "하고", "해서",
            "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "로",
            "한", "함", "된", "되는", "했습니다",
        )
        result: set[str] = set()
        for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", text):
            stem = token.casefold()
            for suffix in sorted(suffixes, key=len, reverse=True):
                if stem.endswith(suffix) and len(stem) - len(suffix) >= 2:
                    stem = stem[: -len(suffix)]
                    break
            if len(stem) >= 2:
                result.add(stem)
        return result

    claim_terms = stems(value)
    answer_terms = stems(answer)
    overlap = claim_terms & answer_terms
    required = 2 if len(claim_terms) >= 2 else 1
    return len(overlap) >= required


def _claim_overstates_contribution(claim, answer: str) -> bool:
    verification = claim.verification
    if verification is None:
        return False
    # Contribution language must be evaluated where the referenced past claim
    # is actually described.  A future-facing sentence such as
    # "입사 후 기여하겠습니다" must not retroactively upgrade every cited
    # experience in the answer.
    terms = re.findall(r"[가-힣A-Za-z0-9]{3,}", claim.normalized_value)
    anchors = {
        term[index : index + 4].casefold()
        for term in terms
        for index in range(max(1, len(term) - 3))
    }
    sentences = re.split(r"(?<=[.!?])\s+|\n+", answer)
    relevant = [
        sentence
        for sentence in sentences
        if any(anchor in re.sub(r"[\s,]", "", sentence).casefold() for anchor in anchors)
    ]
    claim_context = " ".join(relevant) if relevant else answer
    rank = {"unknown": -1, "observed": 0, "contributed": 1, "caused": 2}
    required = 0
    if re.search(r"(?:향상|감소|해결|달성|개선|증가|절감|완수)(?:시켰|했|한|하였|되었습니다)", claim_context):
        required = 2
    elif re.search(r"(?:기여|완화)(?:했|한|하였|되었습니다)|도왔", claim_context):
        required = 1
    return rank.get(verification.contribution, -1) < required


def referenced_claim_values(
    responses: list[DraftResponse], ledger: ExperienceLedger
) -> set[str]:
    by_id = {item.experience_id: item for item in ledger.experiences}
    values: set[str] = set()
    if ledger.schema_version >= 2:
        for response in responses:
            for reference in response.experience_refs:
                experience = by_id.get(reference.experience_id)
                if experience is None or experience.status != "confirmed":
                    continue
                selected = set(reference.claim_ids)
                values.update(
                    claim.normalized_value
                    for claim in experience.claims
                    if claim.claim_id in selected and claim_is_submission_safe(claim)
                )
        return values
    for response in responses:
        for reference in response.experience_refs:
            experience = by_id.get(reference.experience_id)
            if experience is None or experience.status != "confirmed":
                continue
            for claim in experience.claims:
                if claim.field in reference.claim_fields and claim.status == "confirmed":
                    values.add(claim.normalized_value)
    return values
