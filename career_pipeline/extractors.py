from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from .models import ExtractedDocument, SourceRecord


def _extract_docx(path: Path) -> list[str]:
    document = Document(path)
    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]
    for table in document.tables:
        for row in table.rows:
            text = " | ".join(
                cell.text.strip() for cell in row.cells if cell.text.strip()
            )
            if text:
                paragraphs.append(text)
    return paragraphs


def _extract_pdf(path: Path) -> list[str]:
    paragraphs = []
    for page in PdfReader(path).pages:
        text = (page.extract_text() or "").strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _extract_xlsx(path: Path) -> list[str]:
    workbook = load_workbook(path, read_only=False, data_only=False)
    paragraphs = []
    for sheet in workbook.worksheets:
        paragraphs.append(f"[시트] {sheet.title}")
        for row in sheet.iter_rows():
            values = [
                str(cell.value).strip()
                for cell in row
                if cell.value not in (None, "")
            ]
            if values:
                paragraphs.append(" | ".join(values))
    return paragraphs


def extract_path(source: SourceRecord) -> ExtractedDocument:
    if source.extension == ".docx":
        paragraphs = _extract_docx(source.path)
    elif source.extension == ".pdf":
        paragraphs = _extract_pdf(source.path)
    elif source.extension == ".xlsx":
        paragraphs = _extract_xlsx(source.path)
    elif source.extension in {".txt", ".md"}:
        paragraphs = [source.path.read_text(encoding="utf-8-sig").strip()]
    else:
        raise ValueError(f"unsupported extension: {source.extension}")

    clean = tuple(paragraph for paragraph in paragraphs if paragraph)
    return ExtractedDocument(source, "\n".join(clean), clean)
