"""문항 유형에 따라 필요한 근거와 품질 기준을 결정합니다."""


_RESEARCH_ONLY_CUES = (
    "경제사회이슈",
    "경제이슈",
    "사회이슈",
    "산업이슈",
    "최근이슈",
    "산업동향",
    "시장동향",
    "정책이슈",
    "사회문제",
    "주요사업",
    "기관의역할",
    "회사의역할",
    "기업분석",
    "산업분석",
)
_PERSONAL_EVIDENCE_CUES = (
    "경험",
    "사례",
    "본인이수행",
    "본인이실천",
    "실제근무과정",
    "본인의역할",
    "본인의경험",
    "지원동기",
    "기여",
    "활용",
    "입사후",
    "업무수행계획",
    "근무계획",
    "직무계획",
)


def normalize_prompt(prompt: str) -> str:
    return "".join(prompt.split()).replace("·", "").lower()


def is_research_only_prompt(prompt: str) -> bool:
    """개인 경험보다 외부 사실의 분석을 직접 요구하는 문항인지 판정합니다."""

    normalized = normalize_prompt(prompt)
    asks_research = any(cue in normalized for cue in _RESEARCH_ONLY_CUES)
    asks_personal_evidence = any(
        cue in normalized for cue in _PERSONAL_EVIDENCE_CUES
    )
    return asks_research and not asks_personal_evidence


def is_issue_analysis_prompt(prompt: str) -> bool:
    """경제·사회·산업 이슈의 원인과 영향을 분석하는 문항인지 반환합니다."""

    normalized = normalize_prompt(prompt)
    return any(
        cue in normalized
        for cue in (
            "경제사회이슈",
            "경제이슈",
            "사회이슈",
            "산업이슈",
            "최근이슈",
            "산업동향",
            "시장동향",
            "정책이슈",
            "사회문제",
        )
    )


def requires_experience_evidence(prompt: str) -> bool:
    """V2에서 승인 경험 원장 참조가 필요한 문항인지 반환합니다."""

    return not is_research_only_prompt(prompt)


def needs_target_specificity(prompt: str) -> bool:
    """기관·사업·직무를 답변에 명시해야 하는 문항인지 반환합니다."""

    if is_research_only_prompt(prompt):
        return False
    normalized = normalize_prompt(prompt)
    return any(
        cue in normalized
        for cue in (
            "지원동기",
            "지원하게된",
            "주요사업",
            "기관의역할",
            "회사의역할",
            "업무수행계획",
            "근무계획",
            "직무계획",
            "입사후",
        )
    )
