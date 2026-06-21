from pathlib import Path

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
    assert state["status"] == "blocked"
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
        }
    ]


def test_prepare_excludes_company_research_from_personal_fact_conflicts(tmp_path: Path):
    write_docx(tmp_path / "career.docx", "서울시청 근무 기간은 1개월입니다.")
    research = tmp_path / "자료조사"
    research.mkdir()
    write_docx(research / "posting.docx", "채용 근무 기간은 3개월입니다.")
    draft = tmp_path / "draft.docx"
    write_docx(
        draft,
        "지원동기를 작성해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
    )

    state = prepare_run(tmp_path, "HUG 금융·기금", draft, None, "research-filter")

    assert state["status"] == "ready_for_research"


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
