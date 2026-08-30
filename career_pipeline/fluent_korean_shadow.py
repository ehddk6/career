"""Korean realization constraints for the PRIVATE NRS comparison path.

This is a compact, task-specific adaptation of the output-style principles in
https://github.com/snflkd/fluent-korean.  It is deliberately prompt-only: the
existing deterministic validators remain the factual authority, and no
production writer behaviour is changed.
"""
from __future__ import annotations


PROFILE_ID = "fluent-korean-shadow-v2"
SOURCE_URL = "https://github.com/snflkd/fluent-korean"
_HEADER = "[한국어 표현 규칙: fluent-korean shadow v2]"


def fluent_korean_realization_constraints() -> str:
    """Return one shared realization rule set for both blinded trial arms."""
    return (
        "\n\n"
        + _HEADER
        + "\n이 답변은 한국어 자기소개서입니다. 다음 규칙을 반드시 지키십시오.\n"
        "1. 사실 근거에 있는 기관명·직무명·수치·날짜·역할·인과관계는 바꾸지 마십시오.\n"
        "2. 근거에 없는 영어 표현, 영어식 소제목, 약어, 번역투를 넣지 마십시오. 다만 승인된 근거에만 있는 고유명사는 그대로 보존하십시오.\n"
        "3. 조사와 어미를 생략하지 말고, 모든 문장을 완결된 서술어와 종결어미로 끝내십시오.\n"
        "4. 명사만 나열하는 문장, 지나친 수동 표현, 추상적인 다짐, 비유적 표현, 관공서식 체크리스트 문구를 피하십시오.\n"
        "5. 한 문장에는 한 가지 핵심 행동과 판단을 담고, 필요한 경우에만 의미 전환 지점에서 문단을 나누십시오.\n"
        "6. 독자에게 사실 확인, 작성 방식, 기여도 한계를 해설하지 마십시오. 본인 행동·협업 결과·관찰된 변화의 주어와 동사를 정확히 써서 사실 경계를 자연스럽게 드러내십시오.\n"
        "7. 문장 순서와 논증 경로는 제공된 계획을 따르되, 읽는 사람이 바로 이해할 수 있는 자연스러운 한국어로 실현하십시오.\n"
    )


def apply_fluent_korean_shadow_prompt(stage: str, prompt: str) -> str:
    """Add the shared constraints only when an answer is being realized.

    Route planning is deliberately excluded.  This prevents surface-language
    constraints from changing the underlying argument search, while ensuring
    that the fresh control and NRS candidate use the same realization rule.
    """
    prose_stage = stage.startswith(("deep_prose_generate", "nrs_shadow_generate"))
    if not prose_stage or _HEADER in prompt:
        return prompt
    return prompt + fluent_korean_realization_constraints()
