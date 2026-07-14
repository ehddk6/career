"""기업조사 근거 검증. 공식 도메인, checked_at 타임스탬프, 클레임 가시성을 검사합니다."""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .models import DraftResponse, Question, ValidationIssue
from .prompt_policy import (
    is_issue_analysis_prompt,
    is_research_only_prompt,
    normalize_prompt,
)


TARGET_OFFICIAL_DOMAINS = {
    "HUG": "khug.or.kr",
    "주택도시보증공사": "khug.or.kr",
    "HF": "hf.go.kr",
    "한국주택금융공사": "hf.go.kr",
    "NPS": "nps.or.kr",
    "국민연금공단": "nps.or.kr",
}
REQUIRED_RESEARCH_POLICY = "evidence-first"
DEFAULT_RESEARCH_METHOD = "evidence-first-research"
RESEARCH_CLAIM_TYPES = {
    "organization_role",
    "job_duty",
    "industry_issue",
    "program_or_service",
    "risk_or_limit",
    "eligibility",
    "selection_criteria",
}


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    claim: str
    source_url: str
    checked_at: str
    evidence_excerpt: str
    source_type: str = ""
    published_at: str = ""
    basis_date: str = ""
    verification_status: str = "confirmed"
    conflict_note: str = ""
    claim_type: str = "unspecified"
    application_use: str = ""


@dataclass(frozen=True)
class ResearchExecution:
    policy: str
    skill_name: str
    mode: str
    searched_at: str
    status: str
    queries: tuple[str, ...]
    source_families: tuple[str, ...]
    verified_claim_ids: tuple[str, ...]


def load_research_claims(path: Path) -> tuple[ResearchClaim, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("04_공식근거.json: expected array")
    claims: list[ResearchClaim] = []
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict):
            raise ValueError(f"04_공식근거.json[{index}]: expected object")
        claims.append(
            ResearchClaim(
                claim_id=str(item.get("claim_id", "")),
                claim=str(item.get("claim", "")),
                source_url=str(item.get("source_url", "")),
                checked_at=str(item.get("checked_at", "")),
                evidence_excerpt=str(item.get("evidence_excerpt", "")),
                source_type=str(item.get("source_type", "")),
                published_at=str(item.get("published_at", "")),
                basis_date=str(item.get("basis_date", "")),
                verification_status=str(item.get("verification_status", "confirmed")),
                conflict_note=str(item.get("conflict_note", "")),
                claim_type=str(item.get("claim_type", "unspecified")),
                application_use=str(item.get("application_use", "")),
            )
        )
    return tuple(claims)


def load_research_execution(path: Path) -> ResearchExecution:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("04_리서치실행.json: expected object")
    return ResearchExecution(
        policy=str(payload.get("policy", "")),
        skill_name=str(payload.get("skill_name", "")),
        mode=str(payload.get("mode", "")),
        searched_at=str(payload.get("searched_at", "")),
        status=str(payload.get("status", "")),
        queries=tuple(str(item) for item in payload.get("queries", [])),
        source_families=tuple(
            str(item) for item in payload.get("source_families", [])
        ),
        verified_claim_ids=tuple(
            str(item) for item in payload.get("verified_claim_ids", [])
        ),
    )


def _valid_timestamp(value: str) -> bool:
    if not value or not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_research_execution(
    execution: ResearchExecution,
    claims: tuple[ResearchClaim, ...],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    checks = (
        (
            execution.policy == REQUIRED_RESEARCH_POLICY,
            "invalid_research_policy",
            f"기업조사 정책은 {REQUIRED_RESEARCH_POLICY}여야 합니다.",
        ),
        (
            bool(execution.skill_name.strip()),
            "missing_research_method",
            "기업조사에 사용한 방법 또는 도구 식별자가 없습니다.",
        ),
        (
            execution.status == "verified",
            "invalid_research_status",
            "기업조사가 검증 완료 상태가 아닙니다.",
        ),
        (
            _valid_timestamp(execution.searched_at),
            "invalid_research_timestamp",
            "기업조사 실행 시각에 시간대가 포함되어야 합니다.",
        ),
        (
            bool(execution.queries),
            "missing_research_queries",
            "기업조사 검색 질의 기록이 없습니다.",
        ),
        (
            bool(execution.source_families),
            "missing_research_source_families",
            "기업조사 출처 계층 기록이 없습니다.",
        ),
    )
    for valid, code, message in checks:
        if not valid:
            issues.append(ValidationIssue(code, 0, message))

    missing_claim_ids = {
        claim.claim_id for claim in claims
    } - set(execution.verified_claim_ids)
    if missing_claim_ids:
        issues.append(
            ValidationIssue(
                "unverified_research_claims",
                0,
                "실행 기록에서 검증되지 않은 공식 근거 ID: "
                + ", ".join(sorted(missing_claim_ids)),
            )
        )
    return issues


def official_domains_for_target(
    target: str, explicit_domains: tuple[str, ...] = ()
) -> tuple[str, ...]:
    domains = {domain.lower().strip(".") for domain in explicit_domains if domain}
    domains.update(
        domain for marker, domain in TARGET_OFFICIAL_DOMAINS.items() if marker in target
    )
    return tuple(sorted(domains))


def _needs_research(prompt: str) -> bool:
    normalized = normalize_prompt(prompt)
    return (
        is_research_only_prompt(prompt)
        or "주요사업" in normalized
        or ("지원" in normalized and "동기" in normalized)
        or "기관의역할" in normalized
        or "회사의역할" in normalized
        or "업무수행계획" in normalized
        or "직무계획" in normalized
    )


def _required_claim_type_groups(prompt: str) -> tuple[set[str], ...]:
    normalized = normalize_prompt(prompt)
    groups: list[set[str]] = []
    if is_issue_analysis_prompt(prompt):
        groups.append({"industry_issue", "risk_or_limit"})
    if any(cue in normalized for cue in ("지원동기", "지원하게된", "기관의역할", "회사의역할", "주요사업")):
        groups.append({"organization_role", "program_or_service"})
    if any(cue in normalized for cue in ("업무수행계획", "직무계획", "근무계획", "주요업무", "직무", "업무")):
        groups.append({"job_duty", "program_or_service"})
    return tuple(groups)


def _application_use_mentions_question(application_use: str, index: int) -> bool:
    compact = re.sub(r"\s+", "", application_use)
    if "전체문항" in compact or "공통문항" in compact:
        return True
    for match in re.finditer(r"문항([0-9·,과및~\-]+)", compact):
        expression = match.group(1)
        if str(index) in re.findall(r"\d+", expression):
            return True
        for start, end in re.findall(r"(\d+)[~\-](\d+)", expression):
            lower, upper = sorted((int(start), int(end)))
            if lower <= index <= upper:
                return True
    return False


def _official(url: str, allowed_domains: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and bool(host) and any(
        host == domain or host.endswith("." + domain)
        for domain in allowed_domains
    )


def _claim_visible_in_answer(claim: str, answer: str) -> bool:
    compact_answer = re.sub(r"\s+", "", answer)
    terms = re.findall(r"[가-힣A-Za-z0-9]{4,}", claim)
    if not terms:
        return True
    anchors = {
        term[index : index + 4]
        for term in terms
        for index in range(max(1, len(term) - 3))
    }
    return any(anchor in compact_answer for anchor in anchors)


PROMPT_INJECTION_CUES = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "이전 지시",
    "위 지시",
    "시스템 지시",
    "규칙을 무시",
    "명령을 무시",
    "지시를 무시",
)


def contains_prompt_injection(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(cue in normalized for cue in PROMPT_INJECTION_CUES)


def validate_research_evidence(
    questions: list[Question],
    responses: list[DraftResponse],
    claims: tuple[ResearchClaim, ...],
    *,
    allowed_domains: tuple[str, ...],
    strict: bool = False,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_id = {claim.claim_id: claim for claim in claims}
    response_by_index = {response.question_index: response for response in responses}
    for question in questions:
        response = response_by_index.get(question.index)
        if response is None:
            continue
        required_claim_type_groups = _required_claim_type_groups(question.prompt)
        referenced_claim_types: set[str] = set()
        referenced_hosts: set[str] = set()
        if _needs_research(question.prompt) and not response.research_refs:
            issues.append(
                ValidationIssue(
                    "missing_research_reference",
                    question.index,
                    "기관·사업 주장을 뒷받침하는 공식 근거 참조가 없습니다.",
                )
            )
        for claim_id in response.research_refs:
            claim = by_id.get(claim_id)
            if claim is None:
                issues.append(
                    ValidationIssue(
                        "unknown_research_reference",
                        question.index,
                        f"공식 근거 원장에 없는 ID: {claim_id}",
                    )
                )
                continue
            source_valid = _official(claim.source_url, allowed_domains)
            host = (urlparse(claim.source_url).hostname or "").lower()
            if source_valid and host:
                referenced_hosts.add(host)
            if not source_valid:
                issues.append(
                    ValidationIssue(
                        "non_official_research_source",
                        question.index,
                        f"공식 HTTPS 도메인이 아닌 출처: {claim.source_url}",
                    )
                )
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", claim.checked_at):
                issues.append(
                    ValidationIssue(
                        "missing_research_checked_at",
                        question.index,
                        f"확인일이 없거나 잘못됨: {claim_id}",
                    )
                )
            if not claim.evidence_excerpt.strip():
                issues.append(
                    ValidationIssue(
                        "missing_research_excerpt",
                        question.index,
                        f"근거 문장이 없음: {claim_id}",
                    )
                )
            if claim.verification_status not in {"confirmed", "verified"}:
                issues.append(
                    ValidationIssue(
                        "unverified_research_claim",
                        question.index,
                        f"공식 근거가 검증 완료 상태가 아닙니다: {claim_id}",
                    )
                )
            if strict and claim.claim_type not in RESEARCH_CLAIM_TYPES:
                issues.append(
                    ValidationIssue(
                        "missing_research_claim_type",
                        question.index,
                        f"공식 근거의 용도 분류가 없습니다: {claim_id}",
                    )
                )
            else:
                referenced_claim_types.add(claim.claim_type)
            if strict and len(claim.claim.strip()) < 15:
                issues.append(
                    ValidationIssue(
                        "weak_research_claim",
                        question.index,
                        f"공식 근거 주장이 너무 추상적입니다: {claim_id}",
                    )
                )
            if strict and len(claim.evidence_excerpt.strip()) < 12:
                issues.append(
                    ValidationIssue(
                        "weak_research_excerpt",
                        question.index,
                        f"공식 근거 발췌가 너무 짧습니다: {claim_id}",
                    )
                )
            if strict and not claim.application_use.strip():
                issues.append(
                    ValidationIssue(
                        "missing_research_application_use",
                        question.index,
                        f"공식 근거를 자기소개서·면접에 어떻게 사용할지 기록되지 않았습니다: {claim_id}",
                    )
                )
            elif strict and not _application_use_mentions_question(
                claim.application_use, question.index
            ):
                issues.append(
                    ValidationIssue(
                        "research_application_use_not_linked",
                        question.index,
                        f"공식 근거의 활용 기록이 실제 사용 문항 {question.index}과 연결되지 않습니다: {claim_id}",
                    )
                )
            if contains_prompt_injection(claim.claim) or contains_prompt_injection(
                claim.evidence_excerpt
            ):
                issues.append(
                    ValidationIssue(
                        "research_prompt_injection",
                        question.index,
                        f"외부 문서 지시문으로 보이는 문장이 근거에 포함됨: {claim_id}",
                    )
                )
            if not _claim_visible_in_answer(claim.claim, response.answer):
                issues.append(
                    ValidationIssue(
                        "unlinked_research_claim",
                        question.index,
                        f"공식 근거의 핵심 주장이 답변에 드러나지 않습니다: {claim_id}",
                    )
                )
        if strict and referenced_claim_types:
            for required_group in required_claim_type_groups:
                if required_group.intersection(referenced_claim_types):
                    continue
                issues.append(
                    ValidationIssue(
                        "research_claim_type_mismatch",
                        question.index,
                        "문항 유형에 필요한 공식 근거 분류가 없습니다. "
                        f"필요: {', '.join(sorted(required_group))}",
                    )
                )
        if (
            strict
            and is_issue_analysis_prompt(question.prompt)
            and response.research_refs
            and len(referenced_hosts) < 2
        ):
            issues.append(
                ValidationIssue(
                    "insufficient_issue_source_diversity",
                    question.index,
                    "경제·사회 이슈 문항은 서로 다른 두 공식 출처로 맥락과 대응을 교차 확인해야 합니다.",
                )
            )
    return issues
