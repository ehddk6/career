from pathlib import Path

from docx import Document
from docx.shared import Pt

from .models import DraftResponse, Question


def render_draft_markdown(
    questions: list[Question], responses: list[DraftResponse]
) -> str:
    by_index = {item.question_index: item.answer for item in responses}
    chunks = ["# 자기소개서", ""]
    for question in questions:
        chunks.extend(
            [
                f"## {question.index}. {question.prompt}",
                f"제한: {question.character_limit or '미지정'}자",
                "",
                by_index.get(question.index, ""),
                "",
            ]
        )
    return "\n".join(chunks)


def render_draft_docx(
    questions: list[Question], responses: list[DraftResponse], output: Path
) -> None:
    by_index = {item.question_index: item.answer for item in responses}
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(10.5)
    document.add_heading("자기소개서", level=0)
    for question in questions:
        document.add_heading(f"{question.index}. {question.prompt}", level=1)
        document.add_paragraph(
            f"제한: {question.character_limit or '미지정'}자"
        )
        document.add_paragraph(by_index.get(question.index, ""))
    document.save(output)
