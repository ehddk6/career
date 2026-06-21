from pathlib import Path

from career_pipeline.inventory import build_inventory


def test_inventory_excludes_sensitive_paths_without_reading_them_and_marks_duplicates(
    tmp_path: Path, monkeypatch
):
    (tmp_path / "경험정리").mkdir()
    (tmp_path / "학교성적").mkdir()
    (tmp_path / "경험정리" / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "경험정리" / "b.txt").write_text("same", encoding="utf-8")
    (tmp_path / "학교성적" / "grade.txt").write_text("private", encoding="utf-8")
    (tmp_path / ".worktrees").mkdir()
    (tmp_path / ".worktrees" / "nested.txt").write_text("internal", encoding="utf-8")
    (tmp_path / "Chrome 비밀번호.csv").write_text("secret", encoding="utf-8")

    from career_pipeline import inventory

    original_digest = inventory._digest

    def guarded_digest(path: Path) -> str:
        assert "Chrome 비밀번호" not in path.name
        assert "학교성적" not in path.parts
        return original_digest(path)

    monkeypatch.setattr(inventory, "_digest", guarded_digest)
    records = build_inventory(tmp_path)
    statuses = {record.relative_path: record.status for record in records}

    assert statuses["학교성적/"] == "excluded"
    assert ".worktrees/" in statuses
    assert "학교성적/grade.txt" not in statuses
    assert ".worktrees/nested.txt" not in statuses
    assert statuses["Chrome 비밀번호.csv"] == "excluded"
    assert sorted(
        statuses[path] for path in ["경험정리/a.txt", "경험정리/b.txt"]
    ) == ["duplicate", "use"]
