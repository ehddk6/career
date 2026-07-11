from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from .extractors import extract_path
from .inventory import digest_path
from .models import SourceRecord
from .profile_builder import excerpt_sha256
from .profile_schema import ExperienceLedger, ledger_to_dict


@dataclass(frozen=True)
class ProfileReviewItem:
    experience_id: str
    source_path: str
    status: str
    reason: str


@dataclass(frozen=True)
class ProfileReview:
    generated_at: str
    items: tuple[ProfileReviewItem, ...]


def _review_reference(
    root: Path,
    experience_id: str,
    source_path: str,
    paragraph_index: int,
    expected_source_hash: str,
    expected_excerpt_hash: str,
) -> ProfileReviewItem:
    candidate = (root / Path(source_path)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return ProfileReviewItem(
            experience_id, source_path, "missing", "path_outside_workspace"
        )
    if not candidate.is_file():
        return ProfileReviewItem(experience_id, source_path, "missing", "source_missing")

    current_source_hash = digest_path(candidate)
    if current_source_hash != expected_source_hash:
        return ProfileReviewItem(
            experience_id, source_path, "stale", "source_sha256_changed"
        )

    source = SourceRecord(
        path=candidate,
        relative_path=source_path,
        extension=candidate.suffix.lower(),
        size=candidate.stat().st_size,
        sha256=current_source_hash,
        status="use",
    )
    try:
        paragraphs = extract_path(source).paragraphs
    except (OSError, ValueError):
        return ProfileReviewItem(
            experience_id, source_path, "missing", "source_unreadable"
        )
    if paragraph_index >= len(paragraphs):
        return ProfileReviewItem(
            experience_id,
            source_path,
            "missing",
            "paragraph_index_out_of_range",
        )
    if excerpt_sha256(paragraphs[paragraph_index]) != expected_excerpt_hash:
        return ProfileReviewItem(
            experience_id, source_path, "stale", "excerpt_sha256_changed"
        )
    return ProfileReviewItem(experience_id, source_path, "unchanged", "unchanged")


def refresh_profile(root: Path, ledger: ExperienceLedger) -> ProfileReview:
    resolved_root = root.resolve()
    items: list[ProfileReviewItem] = []
    seen: set[tuple[str, str, int]] = set()
    for experience in ledger.experiences:
        for claim in experience.claims:
            for evidence in claim.evidence:
                key = (
                    experience.experience_id,
                    evidence.source_path,
                    evidence.paragraph_index,
                )
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    _review_reference(
                        resolved_root,
                        experience.experience_id,
                        evidence.source_path,
                        evidence.paragraph_index,
                        evidence.source_sha256,
                        evidence.excerpt_sha256,
                    )
                )
    return ProfileReview(
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        items=tuple(items),
    )


def render_profile_review(review: ProfileReview) -> str:
    sections = (
        ("변경 없음", {"unchanged"}),
        ("재확인 필요", {"stale"}),
        ("근거 없음", {"missing"}),
    )
    lines = ["# 경험 원장 갱신 검토", "", f"생성 시각: {review.generated_at}", ""]
    for title, statuses in sections:
        lines.extend([f"## {title}", ""])
        matching = [item for item in review.items if item.status in statuses]
        if not matching:
            lines.extend(["- 없음", ""])
            continue
        lines.extend(
            f"- `{item.experience_id}` · `{item.source_path}` · {item.reason}"
            for item in matching
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_refresh_outputs(
    profile_dir: Path,
    review: ProfileReview,
    proposed_ledger: ExperienceLedger,
) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profile_review.md").write_text(
        render_profile_review(review), encoding="utf-8"
    )
    (profile_dir / "experience_ledger.proposed.json").write_text(
        json.dumps(
            ledger_to_dict(proposed_ledger),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
