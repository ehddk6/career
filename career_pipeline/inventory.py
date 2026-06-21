from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from .models import SourceRecord


SUPPORTED = {".docx", ".pdf", ".xlsx", ".txt", ".md"}
EXCLUDED_DIRS = {
    "학교성적",
    "자격증",
    "경력증명서",
    ".git",
    ".venv",
    ".worktrees",
    "career_runs",
}
EXCLUDED_NAMES = {"Chrome 비밀번호.csv"}


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_inventory(root: Path) -> list[SourceRecord]:
    root = root.resolve()
    records: list[SourceRecord] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative_path = path.relative_to(root)
        excluded = path.name in EXCLUDED_NAMES or any(
            part in EXCLUDED_DIRS for part in relative_path.parts
        )
        supported = path.suffix.lower() in SUPPORTED
        status = "excluded" if excluded or not supported else "use"
        reason = (
            "sensitive/default exclusion"
            if excluded
            else ("unsupported extension" if not supported else "")
        )
        records.append(
            SourceRecord(
                path=path,
                relative_path=relative_path.as_posix(),
                extension=path.suffix.lower(),
                size=path.stat().st_size,
                sha256="" if status == "excluded" else _digest(path),
                status=status,
                reason=reason,
            )
        )

    by_hash: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        if record.status == "use":
            by_hash[record.sha256].append(index)
    for indexes in by_hash.values():
        for index in indexes[1:]:
            records[index] = replace(
                records[index], status="duplicate", reason="same SHA-256"
            )
    return records
