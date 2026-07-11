"""NH/지역농협 자기소개서 문항 가이드와 검증 규칙.

사용자가 제공한 지역농협 자기소개서 팁과 합격 예시에서 반복되는
평가 포인트를 프로그램 안에서 재사용할 수 있도록 정리한다.
이 모듈은 실제 한글 문항을 기준으로 동작하며, 기존 파이프라인의
근거 검증을 대체하지 않고 문항 구조와 누락 요소만 보강한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Question, ValidationIssue


@dataclass(frozen=True)
class NonghyupPromptGuide:
    question_type: str
    title: str
    required_elements: tuple[str, ...]
    recommended_flow: tuple[str, ...]
    good_experience_cues: tuple[str, ...]


GROWTH_GUIDE = NonghyupPromptGuide(
    "growth",
    "성장 가능성",
    (
        "처음 부족했던 역량 또는 문제 인식",
        "계획적인 보완 행동",
        "구체적인 성과 또는 주변 반응",
        "농협 업무에서의 활용 계획",
    ),
    (
        "부족함을 인식한 계기",
        "반복 점검·학습·피드백 등 개선 과정",
        "성과와 변화",
        "농협 실무 적용",
    ),
    (
        "문서정리",
        "민원응대",
        "정확성",
        "금융지식",
        "커뮤니케이션",
        "체계적 개선",
    ),
)

DECISION_GUIDE = NonghyupPromptGuide(
    "decision",
    "판단 기준이 있는 의사결정",
    (
        "선택해야 했던 상황",
        "판단 기준",
        "정보·자료 검토 또는 비교 분석",
        "최종 결정과 책임 있는 실행",
    ),
    (
        "상황과 선택지",
        "고객·조직 관점의 판단 기준",
        "자료 확인과 분석",
        "결정 결과와 배운 점",
    ),
    (
        "고객 요청과 규정 사이 조율",
        "일정·예산·인원 우선순위 판단",
        "정확성과 속도 균형",
        "객관적 기준으로 의견 조율",
    ),
)

TRUST_GUIDE = NonghyupPromptGuide(
    "trust",
    "맡은 역할을 통한 신뢰 형성",
    (
        "팀 또는 조직의 공동 목표",
        "본인이 맡은 구체적 역할",
        "문제·혼선·누락 가능성",
        "신뢰를 얻은 행동과 결과",
    ),
    (
        "공동 목표",
        "본인의 역할",
        "역할 수행 중 발생한 이슈",
        "책임 있는 행동",
        "결과와 주변 반응",
    ),
    (
        "일정 관리",
        "정산",
        "고객응대",
        "운영관리",
        "누락 방지 체계",
        "보이지 않는 실무 수행",
    ),
)

VALUE_GUIDE = NonghyupPromptGuide(
    "value_role",
    "농협 가치관과 입사 후 역할",
    (
        "하나의 가치 또는 원칙",
        "그 가치가 농협에서 중요한 이유",
        "본인 경험 근거",
        "입사 후 수행할 구체적 역할",
    ),
    (
        "가치 제시",
        "농협 실무와 연결",
        "본인 경험으로 검증",
        "입사 후 역할",
    ),
    (
        "신뢰",
        "책임감",
        "원칙",
        "상생",
        "고객 중심",
        "지역사회 연결",
    ),
)

INTEGRATED_BUSINESS_GUIDE = NonghyupPromptGuide(
    "integrated_business",
    "교육지원·경제·금융 사업의 복합 구조",
    (
        "교육지원·경제·금융 사업의 연결 구조",
        "그 구조가 만드는 지역 경쟁력",
        "현장에서 중요하게 볼 지점",
        "본인이 기여할 수 있는 역할",
    ),
    (
        "세 사업 구조의 의미",
        "지역 밀착형 경쟁력",
        "현장 관점",
        "본인의 기여",
    ),
    (
        "고객 요구 파악",
        "지역 농산물 유통",
        "금융 안내",
        "지역 주민 의견 수집",
        "사업 간 연결",
    ),
)

FUTURE_GUIDE = NonghyupPromptGuide(
    "future_innovation",
    "미래성장과 혁신",
    (
        "농협이 나아가야 할 방향",
        "스마트팜·디지털·유통 혁신 등 구체 분야",
        "본인의 경험 또는 관심 계기",
        "현장에서 실행할 수 있는 기여",
    ),
    (
        "방향 제시",
        "기술·시장·지역 문제와 연결",
        "본인 경험",
        "실행 가능한 기여",
    ),
    (
        "스마트팜",
        "디지털 마케팅",
        "데이터 분석",
        "청년농",
        "브랜딩",
        "판로 확대",
    ),
)


GUIDES = (
    GROWTH_GUIDE,
    DECISION_GUIDE,
    TRUST_GUIDE,
    VALUE_GUIDE,
    INTEGRATED_BUSINESS_GUIDE,
    FUTURE_GUIDE,
)


def is_nonghyup_target(target_org: str) -> bool:
    compact = target_org.replace(" ", "").lower()
    return any(keyword in compact for keyword in ("농협", "지역농협", "nh"))


def classify_nonghyup_prompt(prompt: str) -> NonghyupPromptGuide | None:
    compact = prompt.replace(" ", "")
    if any(keyword in compact for keyword in ("성장가능성", "부족하다고판단", "보완하기위해")):
        return GROWTH_GUIDE
    if any(keyword in compact for keyword in ("의사결정", "판단", "기준", "정보를검토")):
        return DECISION_GUIDE
    if any(keyword in compact for keyword in ("신뢰", "맡은역할", "동료", "구성원")):
        return TRUST_GUIDE
    if any(keyword in compact for keyword in ("가치관", "원칙", "중요하게생각", "역할을수행")):
        return VALUE_GUIDE
    if all(keyword in compact for keyword in ("교육지원", "경제", "금융")):
        return INTEGRATED_BUSINESS_GUIDE
    if any(keyword in compact for keyword in ("미래성장", "혁신", "스마트팜", "디지털")):
        return FUTURE_GUIDE
    return None


def render_nonghyup_guidance(question: Question) -> list[str]:
    guide = classify_nonghyup_prompt(question.prompt)
    if guide is None:
        return []
    lines = [
        f"- 지역농협 작성 포인트: {guide.title}",
        f"- 권장 흐름: {' → '.join(guide.recommended_flow)}",
        f"- 필수 확인: {', '.join(guide.required_elements)}",
        f"- 잘 맞는 경험 단서: {', '.join(guide.good_experience_cues)}",
    ]
    return lines


def validate_nonghyup_answer(
    question: Question, answer: str, target_org: str
) -> list[ValidationIssue]:
    if not is_nonghyup_target(target_org):
        return []
    guide = classify_nonghyup_prompt(question.prompt)
    if guide is None:
        return []

    compact = answer.replace(" ", "")
    issues: list[ValidationIssue] = []

    def has_any(*keywords: str) -> bool:
        return any(keyword.replace(" ", "") in compact for keyword in keywords)

    if guide is GROWTH_GUIDE:
        if not has_any("부족", "미숙", "처음", "보완", "개선"):
            issues.append(_issue(question, "nonghyup_missing_growth_start", "성장 문항에는 처음 부족했던 점이나 보완 필요성을 밝혀야 합니다."))
        if not has_any("피드백", "반복", "학습", "점검", "연습", "계획"):
            issues.append(_issue(question, "nonghyup_missing_growth_process", "성장 문항에는 계획적인 개선 과정이 필요합니다."))
        if not has_any("농협", "조합원", "고객", "농업인", "지역"):
            issues.append(_issue(question, "nonghyup_missing_application", "성장 경험을 농협 업무 활용으로 연결해야 합니다."))

    elif guide is DECISION_GUIDE:
        if not has_any("기준", "원칙", "규정", "우선순위", "고객", "조직"):
            issues.append(_issue(question, "nonghyup_missing_decision_standard", "의사결정 문항에는 판단 기준이 드러나야 합니다."))
        if not has_any("자료", "정보", "분석", "비교", "검토", "확인"):
            issues.append(_issue(question, "nonghyup_missing_decision_review", "의사결정 문항에는 정보 검토와 분석 과정이 필요합니다."))
        if not has_any("결정", "선택", "판단", "실행", "결과"):
            issues.append(_issue(question, "nonghyup_missing_decision_result", "의사결정 문항에는 최종 결정과 결과가 필요합니다."))

    elif guide is TRUST_GUIDE:
        if not has_any("역할", "담당", "맡", "책임"):
            issues.append(_issue(question, "nonghyup_missing_role", "신뢰 문항에는 본인이 맡은 역할이 구체적으로 필요합니다."))
        if not has_any("공유", "조율", "확인", "정리", "관리", "소통"):
            issues.append(_issue(question, "nonghyup_missing_trust_action", "신뢰 문항에는 구성원을 안심시키는 행동 과정이 필요합니다."))
        if not has_any("신뢰", "만족", "누락", "기한", "완성", "평가"):
            issues.append(_issue(question, "nonghyup_missing_trust_result", "신뢰 문항에는 결과나 주변 반응이 필요합니다."))

    elif guide is VALUE_GUIDE:
        if not has_any("신뢰", "책임", "원칙", "상생", "고객", "지역"):
            issues.append(_issue(question, "nonghyup_missing_value", "가치관 문항에는 농협 실무와 연결되는 핵심 가치를 하나 분명히 잡아야 합니다."))
        if not has_any("경험", "당시", "과정", "실천", "지켰"):
            issues.append(_issue(question, "nonghyup_missing_value_evidence", "가치관 문항에는 그 가치를 실천한 경험 근거가 필요합니다."))
        if not has_any("역할", "기여", "입사", "농협", "조합원", "지역"):
            issues.append(_issue(question, "nonghyup_missing_future_role", "가치관 문항에는 입사 후 역할이 구체적으로 필요합니다."))

    elif guide is INTEGRATED_BUSINESS_GUIDE:
        if not all(keyword in compact for keyword in ("교육지원", "경제", "금융")):
            issues.append(_issue(question, "nonghyup_missing_three_businesses", "교육지원·경제·금융 세 사업을 모두 언급해야 합니다."))
        if not has_any("연결", "통합", "동시에", "선순환", "종합"):
            issues.append(_issue(question, "nonghyup_missing_business_linkage", "세 사업이 어떻게 연결되는지 설명해야 합니다."))
        if not has_any("기여", "역할", "현장", "고객", "조합원", "지역"):
            issues.append(_issue(question, "nonghyup_missing_business_contribution", "복합 사업 구조 안에서 본인이 기여할 역할이 필요합니다."))

    elif guide is FUTURE_GUIDE:
        if not has_any("스마트팜", "디지털", "데이터", "브랜딩", "유통", "청년농", "판로"):
            issues.append(_issue(question, "nonghyup_missing_innovation_field", "미래성장 문항에는 구체적인 혁신 분야가 필요합니다."))
        if not has_any("경험", "연구", "분석", "참여", "관심", "계기"):
            issues.append(_issue(question, "nonghyup_missing_innovation_basis", "혁신 방향을 선택한 본인 경험 또는 관심 계기가 필요합니다."))
        if not has_any("실행", "기획", "교육", "확대", "지원", "기여"):
            issues.append(_issue(question, "nonghyup_missing_innovation_action", "입사 후 실행 가능한 기여가 필요합니다."))

    return issues


def _issue(question: Question, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(code, question.index, message)
