from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re

from .facts import extract_fact_claims
from .models import ExtractedDocument, FactClaim
from .profile_schema import (
    ClaimVerification,
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
    stable_claim_id,
)
from .source_policy import is_evidence_path


ACTION_CUES = ("확인", "분석", "정리", "개선", "활용", "대조", "안내", "협업", "조정", "제안", "도입")
OUTCOME_CUES = ("결과", "달성", "감소", "증가", "절감", "적발", "완료", "방지", "막", "신뢰", "통일")
EXPERIENCE_CUES = ACTION_CUES + OUTCOME_CUES + ("담당", "역할", "맡", "문제", "실패", "오류")
WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
SENTENCE = re.compile(r"(?<=[.!?。])\s+")
EDITABLE_EVIDENCE_EXTENSIONS = {".docx", ".txt", ".md"}
MAX_PROPOSED_EXPERIENCES_PER_SOURCE = 30
COMPETENCY_CUES = {
    "정확성": ("확인", "대조", "검증", "정확"),
    "분석력": ("분석", "자료", "원인"),
    "문제 해결": ("문제", "개선", "제안", "도입", "오류"),
    "협업": ("협업", "조정", "담당자", "소통"),
    "신뢰": ("신뢰", "책임", "성실", "원칙"),
}


def stable_experience_id(
    source_path: str, paragraph_index: int, tokens: frozenset[str]
) -> str:
    anchors = "|".join(sorted(tokens)[:4])
    payload = f"{Path(source_path).as_posix()}\0{paragraph_index}\0{anchors}"
    return "exp_" + sha256(payload.encode("utf-8")).hexdigest()[:16]


def excerpt_sha256(context: str) -> str:
    normalized = " ".join(context.split())
    return sha256(normalized.encode("utf-8")).hexdigest()


def _profile_claim(claim: FactClaim, source_sha256: str, experience_id: str) -> ProfileClaim:
    provisional = ProfileClaim(
        field=claim.field,
        normalized_value=claim.normalized_value,
        status="proposed",
        evidence=(
            EvidenceRef(
                source_path=claim.source_path,
                paragraph_index=claim.paragraph_index,
                source_sha256=source_sha256,
                excerpt_sha256=excerpt_sha256(claim.context),
            ),
        ),
        verification=ClaimVerification(),
    )
    return ProfileClaim(
        field=provisional.field,
        normalized_value=provisional.normalized_value,
        status=provisional.status,
        evidence=provisional.evidence,
        claim_id=stable_claim_id(experience_id, provisional),
        verification=provisional.verification,
    )


def _sentences(context: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in SENTENCE.split(context) if item.strip())


def _qualitative_claim(
    source_path: str,
    paragraph_index: int,
    context: str,
    source_sha256: str,
    experience_id: str,
) -> ProfileClaim:
    provisional = ProfileClaim(
        field="experience_summary",
        normalized_value=" ".join(context.split()),
        status="proposed",
        evidence=(
            EvidenceRef(
                source_path,
                paragraph_index,
                source_sha256,
                excerpt_sha256(context),
            ),
        ),
        verification=ClaimVerification(
            method="direct_source", scope="source excerpt", contribution="observed"
        ),
    )
    return ProfileClaim(
        field=provisional.field,
        normalized_value=provisional.normalized_value,
        status=provisional.status,
        evidence=provisional.evidence,
        claim_id=stable_claim_id(experience_id, provisional),
        verification=provisional.verification,
    )


def _structured_fields(context: str) -> tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    sentences = _sentences(context)
    role = next(
        (sentence for sentence in sentences if any(cue in sentence for cue in ("담당", "역할", "맡"))),
        "",
    )
    actions = tuple(
        sentence for sentence in sentences if any(cue in sentence for cue in ACTION_CUES)
    )
    outcomes = tuple(
        sentence for sentence in sentences if any(cue in sentence for cue in OUTCOME_CUES)
    )
    competencies = tuple(
        competency
        for competency, cues in COMPETENCY_CUES.items()
        if any(cue in context for cue in cues)
    )
    situation = next(
        (sentence for sentence in sentences if sentence not in actions and sentence not in outcomes),
        sentences[0] if sentences else context,
    )
    return role, situation, actions, outcomes, competencies


def build_proposed_ledger(
    workspace_root: Path, documents: list[ExtractedDocument]
) -> ExperienceLedger:
    dedicated_experience_folder = any(
        Path(document.source.relative_path).parts[:1] == ("경험정리",)
        for document in documents
    )
    evidence_documents = [
        document
        for document in documents
        if is_evidence_path(document.source.relative_path)
        and (
            not dedicated_experience_folder
            or Path(document.source.relative_path).parts[:1] == ("경험정리",)
        )
    ]
    if any(
        document.source.extension in EDITABLE_EVIDENCE_EXTENSIONS
        for document in evidence_documents
    ):
        evidence_documents = [
            document
            for document in evidence_documents
            if document.source.extension in EDITABLE_EVIDENCE_EXTENSIONS
        ]
    source_hashes = {
        document.source.relative_path: document.source.sha256
        for document in evidence_documents
    }
    grouped: dict[tuple[str, int], list[FactClaim]] = defaultdict(list)
    for claim in extract_fact_claims(evidence_documents):
        grouped[(claim.source_path, claim.paragraph_index)].append(claim)

    contexts: dict[tuple[str, int], str] = {}
    for document in evidence_documents:
        for paragraph_index, paragraph in enumerate(document.paragraphs):
            context = " ".join(paragraph.split())
            if 30 <= len(context) <= 1000 and any(
                cue in context for cue in EXPERIENCE_CUES
            ):
                key = (document.source.relative_path, paragraph_index)
                contexts[key] = context
                grouped.setdefault(key, [])

    candidates: dict[str, list[tuple[int, int, list[FactClaim], str]]] = defaultdict(list)
    for (source_path, paragraph_index), claims in grouped.items():
        context = claims[0].context if claims else contexts[(source_path, paragraph_index)]
        role, situation, actions, outcomes, _ = _structured_fields(context)
        priority = (
            len(claims) * 10
            + len(actions) * 3
            + len(outcomes) * 3
            + int("했습니다" in context or "하였다" in context) * 2
            + int(bool(role))
        )
        candidates[source_path].append((priority, paragraph_index, claims, context))

    selected: list[tuple[str, int, list[FactClaim], str]] = []
    for source_path, entries in candidates.items():
        selected.extend(
            (source_path, paragraph_index, claims, context)
            for _, paragraph_index, claims, context in sorted(
                entries, key=lambda item: (-item[0], item[1])
            )[:MAX_PROPOSED_EXPERIENCES_PER_SOURCE]
        )

    experiences: list[Experience] = []
    for source_path, paragraph_index, claims, context in sorted(selected):
        tokens = (
            frozenset().union(*(claim.tokens for claim in claims))
            if claims
            else frozenset(token.lower() for token in WORD.findall(context))
        )
        role, situation, actions, outcomes, competencies = _structured_fields(context)
        experience_id = stable_experience_id(source_path, paragraph_index, tokens)
        profile_claims = (
            tuple(
                _profile_claim(claim, source_hashes[source_path], experience_id)
                for claim in claims
            )
            if claims
            else (
                _qualitative_claim(
                    source_path,
                    paragraph_index,
                    context,
                    source_hashes[source_path],
                    experience_id,
                ),
            )
        )
        experiences.append(
            Experience(
                experience_id=experience_id,
                title=f"{Path(source_path).stem} 문단 {paragraph_index + 1}",
                organization_alias="",
                period=None,
                role=role,
                situation=situation,
                actions=actions,
                outcomes=outcomes,
                competencies=competencies,
                claims=profile_claims,
                status="proposed",
                confirmed_at=None,
            )
        )

    return ExperienceLedger(
        schema_version=2,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        workspace_root=workspace_root.as_posix(),
        experiences=tuple(experiences),
    )


def render_proposed_ledger_review(ledger: ExperienceLedger) -> str:
    """Render a concise local review aid without treating proposed data as fact."""
    lines = [
        "# 경험 후보 원장 검토",
        "",
        "이 문서는 자동 추출 후보입니다. 사실·기간·수치를 확인하기 전에는 자기소개서나 면접 답변의 근거로 사용할 수 없습니다.",
        "",
        f"- 후보 경험 수: {len(ledger.experiences)}",
        "- 상태: 모두 proposed",
        "",
        "| 후보 ID | 출처 | 요약 |",
        "|---|---|---|",
    ]
    for experience in ledger.experiences:
        source = experience.claims[0].evidence[0].source_path
        summary = " ".join(experience.situation.split())[:160]
        lines.append(f"| `{experience.experience_id}` | {source} | {summary} |")
    lines.extend(
        [
            "",
            "확인 시에는 실제 경험 여부, 기간, 본인 역할, 수치, 출처 문단을 함께 검토한 뒤 confirmed 원장으로 옮깁니다.",
            "",
        ]
    )
    return "\n".join(lines)


def build_experience_review_queue(
    ledger: ExperienceLedger, *, per_source_limit: int = 8
) -> list[dict[str, str | int]]:
    """Choose a small, balanced set of high-signal candidates for user confirmation."""
    by_source: dict[str, list[tuple[int, Experience]]] = defaultdict(list)
    for experience in ledger.experiences:
        source = experience.claims[0].evidence[0].source_path
        score = (
            len(experience.actions) * 4
            + len(experience.outcomes) * 4
            + len(experience.competencies) * 2
            + int(experience.claims[0].field != "experience_summary") * 3
        )
        by_source[source].append((score, experience))

    queue: list[dict[str, str | int]] = []
    for source in sorted(by_source):
        for score, experience in sorted(
            by_source[source], key=lambda item: (-item[0], item[1].experience_id)
        )[:per_source_limit]:
            queue.append(
                {
                    "experience_id": experience.experience_id,
                    "source_path": source,
                    "paragraph_index": experience.claims[0].evidence[0].paragraph_index,
                    "review_priority": score,
                    "summary": " ".join(experience.situation.split())[:220],
                    "check": "실제 경험 여부·본인 역할·수치·기간을 확인",
                }
            )
    return sorted(queue, key=lambda item: (-int(item["review_priority"]), str(item["experience_id"])))


def render_experience_review_queue(queue: list[dict[str, str | int]]) -> str:
    lines = [
        "# 경험 확정 우선 검토표",
        "",
        "자동 추출 후보 중 행동·결과·수치 단서가 상대적으로 많은 항목만 모았습니다. 체크 전에는 proposed 상태이며 제출 근거로 사용할 수 없습니다.",
        "",
        "| 우선도 | 후보 ID | 출처 | 확인할 내용 |",
        "|---:|---|---|---|",
    ]
    for item in queue:
        lines.append(
            f"| {item['review_priority']} | `{item['experience_id']}` | {item['source_path']}#{int(item['paragraph_index']) + 1} | {item['check']} |"
        )
    lines.append("")
    return "\n".join(lines)
