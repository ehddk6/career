from pathlib import Path

import json
from docx import Document
import pytest
import yaml

from career_pipeline.conflicts import override_key
from career_pipeline.extractors import extract_path
from career_pipeline.facts import extract_fact_claims
from career_pipeline.inventory import build_inventory
from career_pipeline.orchestrator import prepare_run


def write_docx(path: Path, *paragraphs: str) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def test_prepare_writes_artifacts_blocks_on_conflict_and_resumes(tmp_path: Path):
    write_docx(
        tmp_path / "a.docx",
        "서울시청 의료인력 숙박비 검증으로 예산 4천만원을 줄였습니다.",
    )
    write_docx(
        tmp_path / "b.docx",
        "서울시청 의료인력 숙박비 검증으로 예산 1억 원을 지켰습니다.",
    )
    draft = tmp_path / "draft.docx"
    write_docx(
        draft,
        "지원동기를 작성해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
    )

    state = prepare_run(tmp_path, "HUG 금융·기금", draft, None, "test")

    run_dir = Path(state["run_dir"])
    assert state["status"] == "blocked_conflict"
    assert (run_dir / "01_자료목록.md").exists()
    assert (run_dir / "02_사실원장.json").exists()
    assert (run_dir / "03_충돌검사.md").exists()
    assert not (run_dir / "06_자기소개서.md").exists()

    documents = [
        extract_path(item)
        for item in build_inventory(tmp_path)
        if item.status == "use"
    ]
    savings = next(
        item
        for item in extract_fact_claims(documents)
        if item.field == "budget_savings" and item.normalized_value == "40000000원"
    )
    (run_dir / "fact_overrides.yaml").write_text(
        yaml.safe_dump(
            {override_key(savings): "40000000원"}, allow_unicode=True
        ),
        encoding="utf-8",
    )

    resumed = prepare_run(
        tmp_path,
        "HUG 금융·기금",
        draft,
        None,
        "test",
        run_dir,
    )

    assert resumed["run_dir"] == str(run_dir)
    assert resumed["status"] == "ready_for_research"
    assert resumed["questions"] == [
        {
            "index": 1,
                "prompt": "지원동기를 작성해 주십시오.",
                "character_limit": 600,
                "count_mode": "spaces_included",
                "minimum_character_limit": None,
            }
    ]


def test_prepare_excludes_company_research_from_personal_fact_conflicts(tmp_path: Path):
    write_docx(tmp_path / "career.docx", "서울시청 근무 기간은 1개월입니다.")
    research = tmp_path / "자료조사"
    research.mkdir()
    frame_dir = tmp_path / "자료조사" / "자소서_유튜브_프레임분석_2026-07-03"
    frame_dir.mkdir(parents=True)
    (frame_dir / "01_자소서_작성원칙_요약.md").write_text(
        "# 작성 원칙\n\n- 유튜브 예시 문장은 사실 근거가 아닙니다.\n",
        encoding="utf-8",
    )
    write_docx(research / "posting.docx", "채용 근무 기간은 3개월입니다.")
    draft = tmp_path / "draft.docx"
    write_docx(
        draft,
        "지원동기를 작성해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
    )

    state = prepare_run(tmp_path, "HUG 금융·기금", draft, None, "research-filter")

    run_dir = Path(state["run_dir"])
    fact_payload = json.loads(
        (run_dir / "02_사실원장.json").read_text(encoding="utf-8")
    )

    assert state["status"] == "ready_for_research"
    assert state["writing_guidance"]["status"] == "available"
    assert (run_dir / "05_작성가이드_유튜브프레임.md").exists()
    assert all("유튜브 예시 문장" not in item["context"] for item in fact_payload)


def test_prepare_fails_fast_with_clear_message_when_draft_is_locked(
    tmp_path: Path, monkeypatch
):
    draft = tmp_path / "draft.docx"
    write_docx(draft, "지원동기를 작성해 주십시오.")

    from career_pipeline import inventory

    original_digest = inventory._digest

    def deny_draft(path: Path) -> str:
        if path == draft:
            raise PermissionError("file is in use")
        return original_digest(path)

    monkeypatch.setattr(inventory, "_digest", deny_draft)

    with pytest.raises(PermissionError, match="초안 파일을 닫고"):
        prepare_run(tmp_path, "HUG", draft, None, "locked-draft")
