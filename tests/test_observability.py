"""\uadd9c\ucca0\ub3c4 \ud14c\uc2a4\ud2b8."""
import json
from pathlib import Path
from dataclasses import replace
from docx import Document

from career_pipeline.state import write_state


def test_state_includes_started_at(tmp_path):
    state = {"status": "running", "run_dir": str(tmp_path)}
    write_state(tmp_path, state)
    loaded = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert "started_at" in loaded
    assert "T" in loaded["started_at"]


def test_cost_limit_module_importable():
    from career_pipeline.cost_limit import CostTracker, CostLimitExceeded
    tracker = CostTracker(budget=5)
    assert tracker.budget == 5
    assert tracker.calls == 0
