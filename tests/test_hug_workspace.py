import os
from pathlib import Path

import pytest

from career_pipeline.orchestrator import prepare_run


WORKSPACE = os.getenv("CAREER_PIPELINE_WORKSPACE")


@pytest.mark.skipif(
    not WORKSPACE, reason="set CAREER_PIPELINE_WORKSPACE for local acceptance"
)
def test_current_hug_draft_is_detected_and_conflicts_block_generation():
    root = Path(WORKSPACE)
    draft = root / (
        "26-06-21_주택도시보증공사(HUG) "
        "일반전형_금융·기금(강원).docx"
    )

    state = prepare_run(
        root, "HUG 금융·기금(강원)", draft, None, "hug-acceptance"
    )

    assert len(state["questions"]) == 4
    assert state["status"] == "blocked"
    assert state["conflict_count"] >= 1
    report = Path(state["run_dir"], "01_자료목록.md").read_text(
        encoding="utf-8"
    )
    for sensitive in ["Chrome 비밀번호.csv", "학교성적/", "자격증/", "경력증명서/"]:
        assert sensitive in report
    assert "| excluded | Chrome 비밀번호.csv |" in report
