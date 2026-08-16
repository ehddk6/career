from collections import defaultdict
from dataclasses import dataclass
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
OUTCOME_CUES = (
    "결과", "달성", "감소", "증가", "절감", "적발", "완료", "방지",
    "막", "통일", "향상", "원활",
)
EXPERIENCE_CUES = ACTION_CUES + OUTCOME_CUES + ("담당", "역할", "맡", "문제", "실패", "오류")
WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
SENTENCE = re.compile(r"(?<=[.!?。])\s+")
EDITABLE_EVIDENCE_EXTENSIONS = {".docx", ".txt", ".md"}
MAX_PROPOSED_EXPERIENCES_PER_SOURCE = 30
MAX_EXPERIENCE_BLOCK_LENGTH = 3000
BLOCK_PRIORITY_BONUS = 1000
BLOCK_HEADING = re.compile(r"^(?:\d[\ufe0f\u20e3]*|🔹\s*\d+\.)")
BLOCK_END = re.compile(r"^📌\s*(?:어필|활용)")
BLOCK_SECTION = re.compile(
    r"^✅\s*(?:Situation\s*\(상황\)|Task\s*\(과제\)|Action\s*\(실행\)|Result\s*\(결과\))\s*:?\s*",
    re.IGNORECASE,
)
PERSONAL_METRIC = re.compile(
    r"(?<![A-Za-z])\d[\d,.]*\s*(?:%|건|명|원|만원|억원|페이지|시간|일|주(?:일)?|개월|년|회|개|세|배)"
)
COMPETENCY_CUES = {
    "정확성": ("확인", "대조", "검증", "정확"),
    "분석력": ("분석", "자료", "원인"),
    "문제 해결": ("문제", "개선", "제안", "도입", "오류"),
    "협업": ("협업", "조정", "담당자", "소통"),
    "신뢰": ("신뢰", "책임", "성실", "원칙"),
}


@dataclass(frozen=True)
class _ExperienceCandidate:
    source_path: str
    paragraph_index: int
    claims: tuple[FactClaim, ...]
    context: str
    evidence_contexts: tuple[tuple[int, str], ...]
    title: str
    priority: int


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
    context: str,
    evidence_contexts: tuple[tuple[int, str], ...],
    source_sha256: str,
    experience_id: str,
) -> ProfileClaim:
    provisional = ProfileClaim(
        field="experience_summary",
        normalized_value=" ".join(context.split()),
        status="proposed",
        evidence=tuple(
            EvidenceRef(
                source_path,
                paragraph_index,
                source_sha256,
                excerpt_sha256(evidence_context),
            )
            for paragraph_index, evidence_context in evidence_contexts
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


def _strip_personal_metrics(text: str) -> str:
    """Remove unverified personal metrics from qualitative block fields.

    Numeric claims remain separate proposed claims and therefore cannot become
    submission evidence without their own verification.  This also prevents a
    confirmed qualitative summary from smuggling a D4-required number into the
    rigorous frozen packet.
    """
    cleaned = PERSONAL_METRIC.sub("", text)
    cleaned = re.sub(r"\s+([,.])", r"\1", cleaned)
    return " ".join(cleaned.split()).strip(" ·,;:-")


def _complete_block_sentence(text: str) -> bool:
    return bool(re.search(r"[.!?。]$", text)) and not text.lower().endswith("vs.")


def _reassemble_block_parts(
    paragraphs: tuple[str, ...], body_start: int, end: int
) -> tuple[tuple[tuple[int, str], ...], str]:
    """Join layout-driven line wraps while preserving explicit bullet boundaries."""
    evidence_contexts: list[tuple[int, str]] = []
    sentences: list[str] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer:
            sentences.append(buffer.rstrip(".!?。") + ".")
            buffer = ""

    for index in range(body_start, end):
        original = " ".join(paragraphs[index].split())
        if not original:
            continue
        section_match = BLOCK_SECTION.match(original)
        explicit_bullet = original.startswith("✅") and section_match is None
        if section_match or explicit_bullet:
            flush()
        cleaned = BLOCK_SECTION.sub("", original)
        cleaned = re.sub(r"^✅\s*", "", cleaned).strip()
        cleaned = _strip_personal_metrics(cleaned)
        if not cleaned:
            continue
        evidence_contexts.append((index, original))
        if buffer and _complete_block_sentence(buffer):
            flush()
        buffer = f"{buffer} {cleaned}".strip() if buffer else cleaned
    flush()
    return tuple(evidence_contexts), " ".join(sentences)


def _experience_blocks(
    paragraphs: tuple[str, ...],
) -> tuple[tuple[int, str, tuple[tuple[int, str], ...], str], ...]:
    """Recover authored experience sections split across DOCX paragraphs.

    The source documents use headings such as ``2️⃣`` and ``🔹 4.`` followed by
    STAR labels or bullet lines.  The general extractor deliberately preserves
    those paragraph boundaries, so this builder layer groups only explicitly
    marked sections and leaves ordinary adjacent paragraphs independent.
    """
    starts = [
        index for index, paragraph in enumerate(paragraphs)
        if BLOCK_HEADING.match(paragraph.strip())
    ]
    blocks: list[tuple[int, str, tuple[tuple[int, str], ...], str]] = []
    for position, start in enumerate(starts):
        hard_end = starts[position + 1] if position + 1 < len(starts) else len(paragraphs)
        end = hard_end
        for index in range(start + 1, hard_end):
            if BLOCK_END.match(paragraphs[index].strip()):
                end = index
                break

        title_parts: list[str] = []
        body_start = start
        for index in range(start, end):
            text = " ".join(paragraphs[index].split())
            if index > start and (text.startswith("✅") or BLOCK_SECTION.match(text)):
                body_start = index
                break
            title_parts.append(text)
            body_start = index + 1
        title = " ".join(title_parts).strip()
        body = paragraphs[body_start:end]
        is_star = not title.startswith("🔹")
        has_star_sections = any(BLOCK_SECTION.match(item.strip()) for item in body)
        bullet_count = sum(item.strip().startswith("✅") for item in body)
        if (is_star and not has_star_sections) or (not is_star and bullet_count < 2):
            continue

        evidence_contexts, context = _reassemble_block_parts(
            paragraphs, body_start, end
        )
        if (
            evidence_contexts
            and 30 <= len(context) <= MAX_EXPERIENCE_BLOCK_LENGTH
            and any(cue in context for cue in EXPERIENCE_CUES)
        ):
            blocks.append((start, title, tuple(evidence_contexts), context))
    return tuple(blocks)


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
    block_candidates: list[_ExperienceCandidate] = []
    covered: set[tuple[str, int]] = set()
    for document in evidence_documents:
        claims_by_paragraph = {
            paragraph_index: tuple(grouped.get((document.source.relative_path, paragraph_index), ()))
            for paragraph_index in range(len(document.paragraphs))
        }
        for start, title, evidence_contexts, context in _experience_blocks(document.paragraphs):
            indexes = {index for index, _ in evidence_contexts}
            indexes.add(start)
            covered.update((document.source.relative_path, index) for index in indexes)
            block_claims = tuple(
                claim
                for index in sorted(indexes)
                for claim in claims_by_paragraph.get(index, ())
            )
            role, _, actions, outcomes, _ = _structured_fields(context)
            block_candidates.append(
                _ExperienceCandidate(
                    source_path=document.source.relative_path,
                    paragraph_index=start,
                    claims=block_claims,
                    context=context,
                    evidence_contexts=evidence_contexts,
                    title=title or f"{Path(document.source.relative_path).stem} 경험",
                    priority=(
                        BLOCK_PRIORITY_BONUS
                        + len(actions) * 3
                        + len(outcomes) * 3
                        + int(bool(role))
                    ),
                )
            )
        for paragraph_index, paragraph in enumerate(document.paragraphs):
            context = " ".join(paragraph.split())
            if (document.source.relative_path, paragraph_index) in covered:
                continue
            if 30 <= len(context) <= 1000 and any(
                cue in context for cue in EXPERIENCE_CUES
            ):
                key = (document.source.relative_path, paragraph_index)
                contexts[key] = context
                grouped.setdefault(key, [])

    candidates: dict[str, list[_ExperienceCandidate]] = defaultdict(list)
    for candidate in block_candidates:
        candidates[candidate.source_path].append(candidate)
    for (source_path, paragraph_index), claims in grouped.items():
        if (source_path, paragraph_index) in covered:
            continue
        context = claims[0].context if claims else contexts[(source_path, paragraph_index)]
        role, situation, actions, outcomes, _ = _structured_fields(context)
        priority = (
            len(claims) * 10
            + len(actions) * 3
            + len(outcomes) * 3
            + int("했습니다" in context or "하였다" in context) * 2
            + int(bool(role))
        )
        candidates[source_path].append(
            _ExperienceCandidate(
                source_path=source_path,
                paragraph_index=paragraph_index,
                claims=tuple(claims),
                context=context,
                evidence_contexts=((paragraph_index, context),),
                title=f"{Path(source_path).stem} 문단 {paragraph_index + 1}",
                priority=priority,
            )
        )

    selected: list[_ExperienceCandidate] = []
    for source_path, entries in candidates.items():
        selected.extend(
            sorted(
                entries, key=lambda item: (-item.priority, item.paragraph_index)
            )[:MAX_PROPOSED_EXPERIENCES_PER_SOURCE]
        )

    experiences: list[Experience] = []
    for candidate in sorted(
        selected, key=lambda item: (item.source_path, item.paragraph_index)
    ):
        source_path = candidate.source_path
        paragraph_index = candidate.paragraph_index
        claims = candidate.claims
        context = candidate.context
        tokens = (
            frozenset().union(*(claim.tokens for claim in claims))
            if claims
            else frozenset(token.lower() for token in WORD.findall(context))
        )
        role, situation, actions, outcomes, competencies = _structured_fields(context)
        experience_id = stable_experience_id(source_path, paragraph_index, tokens)
        is_block = len(candidate.evidence_contexts) > 1 or candidate.title != (
            f"{Path(source_path).stem} 문단 {paragraph_index + 1}"
        )
        profile_claims = tuple(
            [
                _qualitative_claim(
                    source_path,
                    context,
                    candidate.evidence_contexts,
                    source_hashes[source_path],
                    experience_id,
                )
            ]
            if is_block or not claims
            else []
        ) + tuple(
            _profile_claim(claim, source_hashes[source_path], experience_id)
            for claim in claims
        )
        experiences.append(
            Experience(
                experience_id=experience_id,
                title=candidate.title,
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
