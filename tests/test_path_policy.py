import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from career_pipeline.path_policy import (
    LockAcquisitionError,
    LockOwner,
    PathConfinementError,
    PathLinkError,
    atomic_write_text,
    confine_path,
    diagnose_lock,
    exclusive_lock,
)
from career_pipeline.state import write_json


def test_confine_path_accepts_relative_and_absolute_paths_inside_root(tmp_path):
    target = tmp_path / "nested" / "record.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")
    assert confine_path(tmp_path, "nested/record.json") == target.resolve()
    assert confine_path(tmp_path, target.resolve()) == target.resolve()


@pytest.mark.parametrize("candidate", ("../outside.json", "C:relative.json", "C:\\outside.json", "\\\\server\\share\\outside.json", "\\rooted\\outside.json", "//server/share/outside.json"))
def test_confine_path_rejects_parent_drive_relative_foreign_drive_unc_and_rooted_escapes(tmp_path, candidate):
    with pytest.raises(PathConfinementError):
        confine_path(tmp_path, candidate, must_exist=False)
    foreign_drive = "D:" if tmp_path.drive.casefold() != "d:" else "C:"
    with pytest.raises(PathConfinementError):
        confine_path(tmp_path, foreign_drive + "\\outside.json", must_exist=False)


def test_confine_path_rejects_symlinks_when_supported(tmp_path):
    outside_directory = tmp_path.parent / "outside-directory"
    outside_directory.mkdir(exist_ok=True)
    outside_file = outside_directory / "outside.json"
    outside_file.write_text("{}", encoding="utf-8")
    directory_link = tmp_path / "directory_link"
    file_link = tmp_path / "file_link.json"
    try:
        directory_link.symlink_to(outside_directory, target_is_directory=True)
        file_link.symlink_to(outside_file)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(PathLinkError):
        confine_path(tmp_path, "directory_link/outside.json")
    with pytest.raises(PathLinkError):
        confine_path(tmp_path, "file_link.json", require_file=True)


def test_atomic_write_text_preserves_existing_destination_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_bytes(b"sentinel")
    monkeypatch.setattr("career_pipeline.path_policy.os.replace", lambda *_: (_ for _ in ()).throw(OSError("simulated replace failure")))
    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_text(path, "replacement")
    assert path.read_bytes() == b"sentinel"
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_write_text_rejects_link_destination_and_cleans_temporary_files(tmp_path):
    destination = tmp_path / "destination.txt"
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        destination.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(PathLinkError):
        atomic_write_text(destination, "replacement")
    assert outside.read_text(encoding="utf-8") == "outside"
    assert not list(tmp_path.glob(".destination.txt.*.tmp"))


def _owner_json(owner):
    return json.dumps(owner.__dict__, separators=(",", ":")) + "\n"


def test_diagnose_lock_is_read_only_and_marks_old_valid_owner_stale_suspected(tmp_path):
    path = tmp_path / "state.lock"
    owner = LockOwner(1, "a" * 32, 1, "host", (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat())
    path.write_text(_owner_json(owner), encoding="utf-8")
    before_bytes, before_stat = path.read_bytes(), path.stat()
    diagnosis = diagnose_lock(path, stale_after_seconds=300)
    after_stat = path.stat()
    assert diagnosis.status == "stale_suspected" and diagnosis.owner == owner
    assert path.read_bytes() == before_bytes
    assert (after_stat.st_size, after_stat.st_mtime_ns) == (before_stat.st_size, before_stat.st_mtime_ns)


def test_diagnose_lock_reports_malformed_without_deleting_it(tmp_path):
    path = tmp_path / "state.lock"
    path.write_bytes(b"{not json")
    original = path.read_bytes()
    assert diagnose_lock(path).status == "malformed"
    assert path.read_bytes() == original


def test_exclusive_lock_never_reclaims_stale_or_uncertain_lock(tmp_path):
    path = tmp_path / "state.lock"
    owner = LockOwner(1, "b" * 32, 1, "host", (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat())
    path.write_text(_owner_json(owner), encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises(LockAcquisitionError):
        with exclusive_lock(path, timeout_seconds=0.02, poll_interval_seconds=0.001, stale_after_seconds=0):
            pass
    assert path.read_bytes() == original


def test_exclusive_lock_serializes_concurrent_atomic_json_writers(tmp_path):
    lock_path, state_path = tmp_path / "state.lock", tmp_path / "state.json"

    def increment(_):
        with exclusive_lock(lock_path, timeout_seconds=5):
            count = json.loads(state_path.read_text(encoding="utf-8"))["count"] if state_path.exists() else 0
            atomic_write_text(state_path, json.dumps({"count": count + 1}) + "\n")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(increment, range(32)))
    assert json.loads(state_path.read_text(encoding="utf-8"))["count"] == 32
    assert not lock_path.exists() and not list(tmp_path.glob(".state.json.*.tmp"))


def test_exclusive_lock_retries_transient_windows_permission_error(tmp_path, monkeypatch):
    lock_path = tmp_path / "state.lock"
    original_open = Path.open
    attempts = 0

    def flaky_open(path, mode="r", *args, **kwargs):
        nonlocal attempts
        if path == lock_path and mode == "x" and attempts < 2:
            attempts += 1
            raise PermissionError(13, "simulated deletion-pending lock")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)
    with exclusive_lock(lock_path, timeout_seconds=1, poll_interval_seconds=0.001):
        assert attempts == 2
    assert not lock_path.exists()


def test_state_write_json_preserves_format_and_uses_atomic_replace(tmp_path):
    path = tmp_path / "state.json"
    write_json(path, {"text": "한글", "number": 1})
    assert path.read_text(encoding="utf-8") == '{\n  "text": "한글",\n  "number": 1\n}\n'
