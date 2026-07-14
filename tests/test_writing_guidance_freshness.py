import os
from pathlib import Path

from career_pipeline.writing_guidance import guidance_freshness


def _touch(path: Path, timestamp: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def test_guidance_freshness_detects_newer_external_source(
    tmp_path: Path, monkeypatch
):
    imported = tmp_path / "imported"
    external = tmp_path / "external"
    _touch(imported / "run_summary.json", 1_700_000_000)
    _touch(external / "analyses" / "video.json", 1_700_000_100)
    monkeypatch.setenv("CAREER_YOUTUBE_GUIDANCE_ROOT", str(external))

    result = guidance_freshness(imported)

    assert result["status"] == "stale"
    assert result["external_source_latest_at"] is not None
    assert result["imported_snapshot_latest_at"] is not None


def test_guidance_freshness_is_fresh_when_snapshot_is_newer(
    tmp_path: Path, monkeypatch
):
    imported = tmp_path / "imported"
    external = tmp_path / "external"
    _touch(imported / "run_summary.json", 1_700_000_200)
    _touch(external / "progress.json", 1_700_000_100)
    monkeypatch.setenv("CAREER_YOUTUBE_GUIDANCE_ROOT", str(external))

    assert guidance_freshness(imported)["status"] == "fresh"
