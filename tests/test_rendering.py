from docx import Document

from career_pipeline.models import DraftResponse, Question
from career_pipeline.rendering import render_draft_docx, render_draft_markdown


def test_markdown_and_docx_contain_all_questions(tmp_path):
    questions = [
        Question(1, "지원동기", 600),
        Question(2, "문제해결", 600),
    ]
    responses = [
        DraftResponse(1, "지원 답변", ("경험정리/a.docx",)),
        DraftResponse(2, "개선 답변", ("경험정리/b.docx",)),
    ]

    markdown = render_draft_markdown(questions, responses)
    output = tmp_path / "draft.docx"
    render_draft_docx(questions, responses, output)

    assert "## 1. 지원동기" in markdown
    assert "개선 답변" in markdown
    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert "지원 답변" in text
    assert "개선 답변" in text
