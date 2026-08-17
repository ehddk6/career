"""Safety boundary between the public code checkout and private career workspace."""
from __future__ import annotations

from pathlib import Path

from .path_policy import PathConfinementError, confine_path


class WorkspacePolicyError(ValueError):
    """A Golden Path workspace or private input violates the workspace boundary."""


def code_repository_root() -> Path:
    """Return the source/package parent treated as the code repository boundary."""
    return Path(__file__).resolve().parents[1]


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def paths_overlap(left: Path, right: Path) -> bool:
    """Return True when either path is the same as or contains the other."""
    a = Path(left).resolve(strict=False)
    b = Path(right).resolve(strict=False)
    return _contains(a, b) or _contains(b, a)


def validate_private_workspace(
    workspace: Path,
    *,
    repo_root: Path | None = None,
    create: bool = False,
) -> Path:
    """Resolve a private workspace and require it to be disjoint from the code repo."""
    raw = Path(workspace).expanduser()
    repository = (
        Path(repo_root).resolve(strict=False)
        if repo_root is not None
        else code_repository_root()
    )

    # Check before mkdir so an invalid `repo/private` argument cannot create a
    # directory inside a public checkout as a side effect of being rejected.
    if paths_overlap(raw, repository):
        raise WorkspacePolicyError(
            "private career workspace must be outside the code repository and "
            "must not contain the code repository"
        )

    if create:
        try:
            raw.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise WorkspacePolicyError(
                f"private career workspace could not be created: {raw}"
            ) from error

    try:
        # Candidate "." preserves path_policy's root symlink/reparse check.
        resolved = confine_path(raw, ".", must_exist=True, reject_links=True)
    except (PathConfinementError, OSError) as error:
        raise WorkspacePolicyError(
            f"private career workspace is not a safe directory: {raw}"
        ) from error

    if not resolved.is_dir():
        raise WorkspacePolicyError(
            f"private career workspace must be a directory: {resolved}"
        )
    if paths_overlap(resolved, repository):
        raise WorkspacePolicyError(
            "private career workspace must be outside the code repository and "
            "must not contain the code repository"
        )
    return resolved


def confine_private_directory(
    workspace: Path,
    candidate: str | Path,
    *,
    label: str,
) -> Path:
    """Require an existing private directory to remain inside the workspace."""
    try:
        resolved = confine_path(
            workspace,
            candidate,
            must_exist=True,
            require_file=False,
            reject_links=True,
        )
    except (PathConfinementError, OSError) as error:
        raise WorkspacePolicyError(
            f"{label} must be a directory inside the private career workspace"
        ) from error
    if not resolved.is_dir():
        raise WorkspacePolicyError(
            f"{label} must be a directory inside the private career workspace"
        )
    return resolved


def confine_private_file(
    workspace: Path,
    candidate: str | Path,
    *,
    label: str,
) -> Path:
    """Require a private local input file to remain inside the workspace."""
    try:
        return confine_path(
            workspace,
            candidate,
            must_exist=True,
            require_file=True,
            reject_links=True,
        )
    except (PathConfinementError, OSError) as error:
        raise WorkspacePolicyError(
            f"{label} must be a regular file inside the private career workspace"
        ) from error


def confine_posting_source(workspace: Path, source: str | Path) -> str:
    """Confine local posting files while preserving HTTP(S) posting URLs."""
    text = str(source)
    if text.lower().startswith(("http://", "https://")):
        return text
    return str(confine_private_file(workspace, source, label="posting"))
