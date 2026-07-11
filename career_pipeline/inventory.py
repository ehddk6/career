"""파일 인벤토리. 민감 정보 디렉토리(경력증명서, 자격증, 학교성적 등)를 제외하고 SHA-256으로 중복을 검출합니다."""
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
import os
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
    ".career_profile",
    ".agents",
    "career_runs",
    "docs",
    "_workspace",
    ".rendered_nonghyup",
    "tmp",
}
EXCLUDED_NAMES = {"Chrome 비밀번호.csv"}


def digest_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_digest = digest_path


def build_inventory(root: Path) -> list[SourceRecord]:
    root = root.resolve()
    records: list[SourceRecord] = []
    for current, directory_names, file_names in os.walk(root):
        current_path = Path(current)
        retained_directories = []
        for directory_name in sorted(directory_names):
            directory = current_path / directory_name
            relative = directory.relative_to(root)
            if directory_name in EXCLUDED_DIRS:
                records.append(
                    SourceRecord(
                        path=directory,
                        relative_path=relative.as_posix() + "/",
                        extension="",
                        size=0,
                        sha256="",
                        status="excluded",
                        reason="sensitive/default exclusion",
                    )
                )
            else:
                retained_directories.append(directory_name)
        directory_names[:] = retained_directories

        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(root)
            excluded = path.name in EXCLUDED_NAMES
            supported = path.suffix.lower() in SUPPORTED
            status = "excluded" if excluded or not supported else "use"
            reason = (
                "sensitive/default exclusion"
                if excluded
                else ("unsupported extension" if not supported else "")
            )
            digest = ""
            if status == "use":
                try:
                    digest = _digest(path)
                except OSError as error:
                    status = "failed"
                    reason = f"{type(error).__name__}: {error}"
            records.append(
                SourceRecord(
                    path=path,
                    relative_path=relative_path.as_posix(),
                    extension=path.suffix.lower(),
                    size=path.stat().st_size,
                    sha256=digest,
                    status=status,
                    reason=reason,
                )
            )

    records.sort(key=lambda record: record.relative_path)

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
