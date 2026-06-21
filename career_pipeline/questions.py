import re

from .models import Question


LIMIT = re.compile(r"(?:0\s*/\s*)?(\d{2,4})(?:\s*자|\s*\(\s*글자)")
QUESTION_END = re.compile(r"(?:주십시오|주세요|하시오|입니까|인가요)\.?$")


def extract_questions(paragraphs: tuple[str, ...]) -> list[Question]:
    questions: list[Question] = []
    pending: str | None = None
    for paragraph in paragraphs:
        limit = LIMIT.search(paragraph)
        if limit and pending:
            questions.append(
                Question(len(questions) + 1, pending, int(limit.group(1)))
            )
            pending = None
        elif QUESTION_END.search(paragraph):
            if pending:
                questions.append(Question(len(questions) + 1, pending, None))
            pending = paragraph
    if pending:
        questions.append(Question(len(questions) + 1, pending, None))
    return questions
