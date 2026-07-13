"""Dependency-free filesystem confinement, persistence, and lock policies."""
from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath
from socket import gethostname
import stat
import tempfile
import time
from typing import Literal
import uuid


class PathPolicyError(ValueError):
    """Base error for shared filesystem policy."""


class PathConfinementError(PathPolicyError):
    """A candidate cannot be proven to remain under its root."""


class PathLinkError(PathConfinementError):
    """A candidate or existing ancestor is a symlink or reparse point."""


class LockAcquisitionError(PathPolicyError):
    """A lock cannot be safely acquired or released."""


@dataclass(frozen=True)
class LockOwner:
    schema_version: int
    owner_token: str
    pid: int
    hostname: str
    created_at: str


@dataclass(frozen=True)
class LockDiagnosis:
    status: Literal["absent", "held", "stale_suspected", "malformed"]
    lock_path: str
    age_seconds: float | None
    owner: LockOwner | None


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        attributes = os.lstat(path).st_file_attributes if hasattr(os.lstat(path), "st_file_attributes") else 0
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        return False


def _reject_windows_escape(root: Path, raw: str) -> None:
    candidate = PureWindowsPath(raw)
    root_windows = PureWindowsPath(str(root))
    if candidate.drive and not candidate.root:
        raise PathConfinementError("candidate must remain inside workspace")
    if candidate.drive.startswith("\\\\") or (candidate.root and not candidate.drive):
        raise PathConfinementError("candidate must remain inside workspace")
    if candidate.drive and candidate.root and root_windows.drive and candidate.drive.casefold() != root_windows.drive.casefold():
        raise PathConfinementError("candidate must remain inside workspace")


def confine_path(root: Path, candidate: str | Path, *, must_exist: bool = True, require_file: bool = False, reject_links: bool = True) -> Path:
    raw_root = Path(root)
    raw_candidate = str(candidate)
    _reject_windows_escape(raw_root, raw_candidate)
    try:
        if reject_links and _is_link_or_reparse(raw_root):
            raise PathLinkError("workspace link or reparse point is forbidden")
        resolved_root = raw_root.resolve(strict=True)
        path_candidate = Path(candidate)
        lexical_candidate = path_candidate if path_candidate.is_absolute() else resolved_root / path_candidate
        if reject_links:
            current = resolved_root
            for part in lexical_candidate.relative_to(resolved_root).parts:
                current /= part
                if _is_link_or_reparse(current):
                    raise PathLinkError("candidate link or reparse point is forbidden")
        if must_exist:
            resolved_candidate = lexical_candidate.resolve(strict=True)
        else:
            resolved_candidate = lexical_candidate.resolve(strict=False)
        resolved_candidate.relative_to(resolved_root)
    except PathLinkError:
        raise
    except (OSError, ValueError) as error:
        raise PathConfinementError("candidate must remain inside workspace") from error
    if reject_links and _is_link_or_reparse(resolved_candidate):
        raise PathLinkError("candidate link or reparse point is forbidden")
    if require_file and (not resolved_candidate.is_file() or (reject_links and _is_link_or_reparse(resolved_candidate))):
        raise PathConfinementError("candidate must be a regular file")
    return resolved_candidate


def _best_effort_fsync(handle) -> None:
    try:
        os.fsync(handle.fileno())
    except OSError:
        pass


def atomic_write_bytes(path: Path, data: bytes) -> None:
    destination = Path(path)
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _is_link_or_reparse(destination):
            raise PathLinkError("destination link or reparse point is forbidden")
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            _best_effort_fsync(handle)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def atomic_write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, data.encode(encoding))


def _owner_from_data(value: object) -> LockOwner:
    if not isinstance(value, dict) or set(value) != {"schema_version", "owner_token", "pid", "hostname", "created_at"}:
        raise ValueError
    owner = LockOwner(**value)
    if owner.schema_version != 1 or not isinstance(owner.owner_token, str) or not owner.owner_token:
        raise ValueError
    if not isinstance(owner.pid, int) or isinstance(owner.pid, bool) or not isinstance(owner.hostname, str):
        raise ValueError
    created_at = datetime.fromisoformat(owner.created_at.replace("Z", "+00:00"))
    if created_at.tzinfo is None or created_at.utcoffset() != timezone.utc.utcoffset(created_at):
        raise ValueError
    return owner


def _read_lock_owner(lock_path: Path) -> LockOwner:
    return _owner_from_data(json.loads(lock_path.read_text(encoding="utf-8")))


def diagnose_lock(lock_path: Path, *, stale_after_seconds: float = 300.0, now: datetime | None = None) -> LockDiagnosis:
    path = Path(lock_path)
    try:
        owner = _read_lock_owner(path)
    except FileNotFoundError:
        return LockDiagnosis("absent", str(path), None, None)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return LockDiagnosis("malformed", str(path), None, None)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    created_at = datetime.fromisoformat(owner.created_at.replace("Z", "+00:00"))
    age_seconds = max(0.0, (current - created_at).total_seconds())
    status: Literal["held", "stale_suspected"] = "stale_suspected" if age_seconds > stale_after_seconds else "held"
    return LockDiagnosis(status, str(path), age_seconds, owner)


def _owner_payload(owner: LockOwner) -> str:
    return json.dumps(asdict(owner), ensure_ascii=False, separators=(",", ":")) + "\n"


@contextmanager
def exclusive_lock(lock_path: Path, *, timeout_seconds: float = 5.0, poll_interval_seconds: float = 0.05, stale_after_seconds: float = 300.0) -> AbstractContextManager[LockOwner]:
    path = Path(lock_path)
    owner = LockOwner(1, uuid.uuid4().hex, os.getpid(), gethostname(), datetime.now(timezone.utc).isoformat())
    deadline = time.monotonic() + timeout_seconds
    handle = None
    while handle is None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("x", encoding="utf-8")
        except FileExistsError:
            if time.monotonic() >= deadline:
                diagnosis = diagnose_lock(path, stale_after_seconds=stale_after_seconds)
                raise LockAcquisitionError(f"lock timeout: {diagnosis.status}")
            time.sleep(poll_interval_seconds)
        except PermissionError as error:
            # Windows can briefly deny exclusive creation while a just-unlinked
            # lock is still deletion-pending. Treat that window as contention,
            # but preserve a bounded failure for persistent permission errors.
            if time.monotonic() >= deadline:
                raise LockAcquisitionError("could not acquire lock") from error
            time.sleep(poll_interval_seconds)
        except OSError as error:
            raise LockAcquisitionError("could not acquire lock") from error
    try:
        handle.write(_owner_payload(owner))
        handle.flush()
        _best_effort_fsync(handle)
        handle.close()
        handle = None
        yield owner
    finally:
        if handle is not None:
            handle.close()
        try:
            current = _read_lock_owner(path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise LockAcquisitionError("could not safely release lock") from error
        if current.owner_token != owner.owner_token:
            raise LockAcquisitionError("could not safely release lock")
        try:
            path.unlink()
        except OSError as error:
            raise LockAcquisitionError("could not safely release lock") from error
