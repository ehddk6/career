"""문항 추출. 글자수 제한 패턴을 정규식으로 추출합니다."""
import re

from .models import Question


LIMIT = re.compile(
    r"(?:최대\s*)?(?:0\s*/\s*)?(\d{2,4})\s*"
    r"(?:자(?:\s*(?:이내|내외))?|bytes?|\(\s*글자[^)]*\))",
    re.IGNORECASE,
)
RANGE_LIMIT = re.compile(r"(\d{2,4})\s*자\s*이상\s*(\d{2,4})\s*자\s*이내")
QUESTION_END = re.compile(r"(?:주십시오|주세요|하시오|입니까|인가요)\.?$")


def _count_mode(text: str) -> str:
    return "spaces_excluded" if "공백 제외" in text else "spaces_included"


def _clean_prompt(text: str) -> str:
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    return " ".join(text.split())


def extract_questions(paragraphs: tuple[str, ...]) -> list[Question]:
    questions: list[Question] = []
    pending: str | None = None
    for paragraph in paragraphs:
        range_limit = RANGE_LIMIT.search(paragraph)
        limit = range_limit or LIMIT.search(paragraph)
        prompt = RANGE_LIMIT.sub("", paragraph) if range_limit else LIMIT.sub("", paragraph)
        prompt = prompt.strip()
        limit_value = int(range_limit.group(2)) if range_limit else (int(limit.group(1)) if limit else None)
        if re.fullmatch(r"\d+[.)]", prompt):
            pending = prompt
            continue
        if pending and re.fullmatch(r"\d+[.)]", pending):
            prompt = f"{pending} {prompt}".strip()
            if limit:
                pending = None
            else:
                pending = prompt
                continue
        numbered_limited_prompt = bool(limit and re.match(r"^\s*\d+[.)]\s*", prompt))
        numbered_prompt = bool(re.match(r"^\s*\d+[.)]\s*", prompt))
        if prompt and (QUESTION_END.search(prompt) or numbered_limited_prompt or numbered_prompt):
            if pending:
                questions.append(Question(len(questions) + 1, pending, None))
            if limit:
                questions.append(
                    Question(
                        len(questions) + 1,
                        prompt,
                        limit_value,
                        _count_mode(paragraph),
                    )
                )
                pending = None
            else:
                pending = prompt
        elif limit and pending:
            questions.append(
                Question(
                    len(questions) + 1,
                    f"{pending} {prompt}".strip(),
                    limit_value,
                    _count_mode(paragraph),
                )
            )
            pending = None
    if pending:
        questions.append(Question(len(questions) + 1, pending, None))
    return [
        Question(item.index, _clean_prompt(item.prompt), item.character_limit, item.count_mode)
        for item in questions
    ]
