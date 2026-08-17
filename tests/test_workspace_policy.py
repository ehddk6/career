import json
from pathlib import Path

import pytest

from career_pipeline.golden_path import (
    GoldenPathError,
    _parser,
    advance_golden_path,
    start_golden_path,
)
from career_pipeline.workspace_policy import (
    WorkspacePolicyError,
    confine_posting_source,
    confine_private_directory,
    confine_private_file,
    paths_overlap,
    validate_private_workspace,
)


def test_external_private_workspace_is_accepted(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "private"
    repo.mkdir()
    workspace.mkdir()
    assert validate_private_workspace(workspace, repo_root=repo) == workspace.resolve()


@pytest.mark.parametrize("kind", ["same", "workspace_under_repo", "repo_under_workspace"])
def test_overlapping_workspace_and_repo_are_rejected(tmp_path: Path, kind: str):
    if kind == "same":
        repo = workspace = tmp_path / "repo"
        repo.mkdir()
    elif kind == "workspace_under_repo":
        repo = tmp_path / "repo"
        workspace = repo / "private"
        repo.mkdir()
    else:
        workspace = tmp_path / "private"
        repo = workspace / "repo"
        repo.mkdir(parents=True)

    with pytest.raises(WorkspacePolicyError, match="must be outside"):
        validate_private_workspace(workspace, repo_root=repo, create=True)

    if kind == "workspace_under_repo":
        assert not workspace.exists(), "rejected workspace must not be created in repo"


def test_paths_overlap_is_symmetric(tmp_path: Path):
    parent = tmp_path / "a"
    child = parent / "b"
    child.mkdir(parents=True)
    assert paths_overlap(parent, child)
    assert paths_overlap(child, parent)


def test_start_rejects_code_repository_as_workspace():
    repo = Path(__file__).resolve().parents[1]
    with pytest.raises(GoldenPathError, match="must be outside the code repository"):
        start_golden_path(
            root=repo,
            target="Synthetic Corp",
            draft=Path("draft.docx"),
            posting="posting.docx",
            profile=Path(".career_profile/experience_ledger.json"),
        )


def test_resume_rejects_run_symlink_even_when_target_is_inside_workspace(tmp_path: Path):
    workspace = tmp_path / "private"
    real_run = workspace / "career_runs" / "real"
    link_run = workspace / "career_runs" / "link"
    real_run.mkdir(parents=True)
    (real_run / "run.json").write_text(
        '{"quality_mode":"v2","strict_quality":true,"root":'
        + json.dumps(str(workspace))
        + "}",
        encoding="utf-8",
    )
    try:
        link_run.symlink_to(real_run, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(GoldenPathError, match="golden path run must be"):
        advance_golden_path(link_run)


def test_resume_rejects_run_directory_outside_recorded_workspace(tmp_path: Path):
    workspace = tmp_path / "private"
    outside_run = tmp_path / "outside-run"
    workspace.mkdir()
    outside_run.mkdir()
    (outside_run / "run.json").write_text(
        '{"quality_mode":"v2","strict_quality":true,"root":'
        + json.dumps(str(workspace))
        + "}",
        encoding="utf-8",
    )

    with pytest.raises(GoldenPathError, match="golden path run must be"):
        advance_golden_path(outside_run)


def test_private_run_directory_must_remain_inside_workspace(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "private"
    run = workspace / "career_runs" / "run-1"
    outside = tmp_path / "outside-run"
    repo.mkdir()
    run.mkdir(parents=True)
    outside.mkdir()

    validated = validate_private_workspace(workspace, repo_root=repo)
    assert confine_private_directory(validated, run, label="golden path run") == run.resolve()
    with pytest.raises(WorkspacePolicyError, match="golden path run must be"):
        confine_private_directory(validated, outside, label="golden path run")


def test_private_file_must_remain_inside_workspace(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "private"
    repo.mkdir()
    workspace.mkdir()
    inside = workspace / "draft.docx"
    outside = tmp_path / "outside.docx"
    inside.write_bytes(b"fixture")
    outside.write_bytes(b"fixture")

    validated = validate_private_workspace(workspace, repo_root=repo)
    assert confine_private_file(validated, inside, label="draft") == inside.resolve()
    with pytest.raises(WorkspacePolicyError, match="draft must be"):
        confine_private_file(validated, outside, label="draft")


def test_local_posting_is_confined_but_https_url_is_preserved(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "private"
    repo.mkdir()
    workspace.mkdir()
    posting = workspace / "posting.docx"
    posting.write_bytes(b"fixture")
    validated = validate_private_workspace(workspace, repo_root=repo)

    assert confine_posting_source(validated, posting) == str(posting.resolve())
    assert (
        confine_posting_source(validated, "https://jobs.example.invalid/posting")
        == "https://jobs.example.invalid/posting"
    )


def test_workspace_can_be_created_explicitly(tmp_path: Path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "private"
    repo.mkdir()
    assert validate_private_workspace(workspace, repo_root=repo, create=True) == workspace.resolve()
    assert workspace.is_dir()


def test_workspace_symlink_is_rejected_when_supported(tmp_path: Path):
    repo = tmp_path / "repo"
    real = tmp_path / "real-private"
    link = tmp_path / "private-link"
    repo.mkdir()
    real.mkdir()
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(WorkspacePolicyError):
        validate_private_workspace(link, repo_root=repo)


@pytest.mark.parametrize("flag", ["--workspace", "--root"])
def test_start_cli_accepts_workspace_and_legacy_root_alias(tmp_path: Path, flag: str):
    args = _parser().parse_args(
        [
            "start",
            flag,
            str(tmp_path / "private"),
            "--target",
            "Synthetic Corp",
            "--draft",
            str(tmp_path / "private" / "draft.docx"),
            "--posting",
            str(tmp_path / "private" / "posting.docx"),
            "--profile",
            str(tmp_path / "private" / ".career_profile" / "experience_ledger.json"),
        ]
    )
    assert args.workspace == tmp_path / "private"
