"""글자수 계산 (공백 포함/제외 모드). 자소서 글자수 검사에 사용됩니다."""
from typing import Literal


CharacterCountMode = Literal["spaces_included", "spaces_excluded"]


def count_characters(text: str, mode: CharacterCountMode) -> int:
    if mode == "spaces_excluded":
        return sum(not character.isspace() for character in text)
    return len(text)

