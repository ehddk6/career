"""프로젝트 공통 글쓰기 에디터 계약 로더.

이 계약은 생성·심사·교열 정책이며 경험이나 기관 사실의 근거가 아니다.
"""

from pathlib import Path
from functools import lru_cache


EDITOR_PROMPT = Path(__file__).with_name("writing_editor_prompt.md")
HUMAN_SELF_INTRO_PROMPT = Path(__file__).parent.parent / "prompts" / "human_self_intro_editor.md"
_FALLBACK = (
    "저자의 의미·의도·어조를 보존하고, 승인되지 않은 사실·수치·권한을 추가하지 않는다. "
    "자기소개서는 자연스러움, 문장 리듬, 종결 반복, 문장 길이 균형, 번역투·AI 관용구, "
    "과도한 명사화를 각각 점검한다."
)


@lru_cache(maxsize=1)
def load_editor_contract() -> str:
    """Return the complete editor contract, with a safe local fallback."""

    sections: list[str] = []
    for path in (EDITOR_PROMPT, HUMAN_SELF_INTRO_PROMPT):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            sections.append(value)
    return "\n\n".join(sections) or _FALLBACK
