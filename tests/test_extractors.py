from pathlib import Path

from docx import Document
from openpyxl import Workbook

from career_pipeline.extractors import extract_path
from career_pipeline.models import SourceRecord


def record(path: Path) -> SourceRecord:
    return SourceRecord(
        path,
        path.name,
        path.suffix.lower(),
        path.stat().st_size,
        "hash",
        "use",
    )


def test_extracts_docx_paragraphs_and_tables(tmp_path: Path):
    path = tmp_path / "draft.docx"
    document = Document()
    document.add_paragraph("첫 번째 문항")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "항목"
    table.cell(0, 1).text = "답변 내용"
    document.save(path)

    result = extract_path(record(path))

    assert result.paragraphs == ("첫 번째 문항", "항목 | 답변 내용")


def test_extracts_xlsx_cells_and_sheet_names(tmp_path: Path):
    path = tmp_path / "interview.xlsx"
    workbook = Workbook()
    workbook.active.title = "가이드"
    workbook.active["B2"] = "면접 전략"
    workbook.active["C4"] = "지원동기"
    workbook.save(path)

    result = extract_path(record(path))

    assert "[시트] 가이드" in result.text
    assert "면접 전략" in result.text
    assert "지원동기" in result.text


def test_extracts_utf8_bom_text(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("경험 근거", encoding="utf-8-sig")
    assert extract_path(record(path)).text == "경험 근거"


def test_rejects_unsupported_file(tmp_path: Path):
    path = tmp_path / "image.jpg"
    path.write_bytes(b"jpg")

    try:
        extract_path(record(path))
    except ValueError as error:
        assert "unsupported extension" in str(error)
    else:
        raise AssertionError("unsupported file was accepted")
