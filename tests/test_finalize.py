import json
from pathlib import Path

from career_pipeline.orchestrator import finalize_run


def test_finalize_requires_research_strategy_draft_and_interview(tmp_path: Path):
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "status": "ready_for_research",
                "target": "HUG",
                "questions": [
                    {
                        "index": 1,
                        "prompt": "지원동기",
                        "character_limit": 600,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "draft.json").write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "answer": "검증 가능한 지원 답변",
                    "evidence_paths": ["경험정리/a.docx"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "02_사실원장.json").write_text(
        json.dumps(
            [{"source_path": "경험정리/a.docx"}], ensure_ascii=False
        ),
        encoding="utf-8",
    )
    (tmp_path / "04_기업직무조사.md").write_text(
        "# 조사\n\n[HUG 공식 홈페이지](https://www.khug.or.kr/)\n",
        encoding="utf-8",
    )
    (tmp_path / "05_문항전략.md").write_text("# 전략\n", encoding="utf-8")
    (tmp_path / "08_면접대비팩.md").write_text(
        "# 면접대비팩\n\n## 1분 자기소개\n## 꼬리질문\n## 압박질문\n## 근거\n",
        encoding="utf-8",
    )

    state = finalize_run(tmp_path)

    assert state["status"] == "complete"
    assert (tmp_path / "06_자기소개서.md").exists()
    assert (tmp_path / "06_자기소개서.docx").exists()
    assert (tmp_path / "07_자기소개서_검토보고서.md").exists()


def test_finalize_blocks_when_research_has_no_link(tmp_path: Path):
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "status": "ready_for_research",
                "target": "HUG",
                "questions": [
                    {"index": 1, "prompt": "지원동기", "character_limit": 100}
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "draft.json").write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "answer": "답변",
                    "evidence_paths": ["a.docx"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "02_사실원장.json").write_text(
        json.dumps([{"source_path": "a.docx"}]), encoding="utf-8"
    )
    (tmp_path / "04_기업직무조사.md").write_text("# 조사\n", encoding="utf-8")
    (tmp_path / "05_문항전략.md").write_text("# 전략\n", encoding="utf-8")
    (tmp_path / "08_면접대비팩.md").write_text(
        "# 면접\n1분 자기소개\n꼬리질문\n압박질문\n근거\n", encoding="utf-8"
    )

    state = finalize_run(tmp_path)

    assert state["status"] == "blocked_validation"
    assert "missing_research_link" in {
        issue["code"] for issue in state["validation_issues"]
    }
