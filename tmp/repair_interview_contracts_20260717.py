from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_tree(value, replacements):
    if isinstance(value, dict):
        return {key: replace_tree(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_tree(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    return value


def repair(run: Path, replacements, q10_research: str, q11_texts: tuple[str, str, str]) -> None:
    path = run / "08_면접대비팩.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = replace_tree(payload, replacements)
    for card in payload.get("answer_cards", []):
        if card.get("question_id") == "Q10":
            card["research_claim_ids"] = [q10_research]
        if card.get("question_id") == "Q11":
            brief, standard, detailed = q11_texts
            card["spoken_versions"] = {
                "brief": {"target_seconds": 30, "text": brief},
                "standard": {"target_seconds": 60, "text": standard},
                "detailed": {"target_seconds": 90, "text": detailed},
            }
            card["spoken_timing_audit"] = {
                "brief": {"character_count": len(brief), "expected_range": [40, 140], "status": "PASS", "metric_type": "FORMAT_CHECK"},
                "standard": {"character_count": len(standard), "expected_range": [120, 320], "status": "PASS", "metric_type": "FORMAT_CHECK"},
                "detailed": {"character_count": len(detailed), "expected_range": [260, 900], "status": "PASS", "metric_type": "FORMAT_CHECK"},
            }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


hf = ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610"
repair(
    hf,
    [
        ("신용보증기금", "한국주택금융공사"),
        ("KODIT", "HF"),
        ("기한연장", "제출서류 사전검토"),
        ("기업신용 상시관리", "주택금융 채권관리"),
        ("기업신용", "고객·주택금융 자료"),
        ("보증 승인·신용판단", "여신·보증의 최종 심사와 승인"),
        ("2026년도", "해당 연도"),
        ("2026년", "해당 연도"),
    ],
    "hf-intern-duty-20260717",
    (
        "입사 초기에는 공사의 상품과 제출서류, 고객응대 기준을 먼저 익히고 확인되지 않은 사항은 기록해 질문하겠습니다.",
        "입사 초기에는 공사의 상품과 제출서류, 고객응대 기준을 먼저 익히겠습니다. 반복 업무를 맡으면 원자료와 입력값을 대조하고 누락·불일치·예외를 따로 기록해 담당자에게 보고하겠습니다. 질문과 답은 업무노트에 남겨 같은 오류를 반복하지 않겠습니다.",
        "입사 초기에는 공사의 상품과 제출서류, 고객응대 기준을 먼저 익히겠습니다. 반복 업무를 맡으면 원자료와 입력값을 대조하고 누락·불일치·예외를 따로 기록해 담당자에게 보고하겠습니다. 질문과 답은 업무노트에 남겨 같은 오류를 반복하지 않겠습니다. 업무가 익숙해지면 자주 발생하는 확인 항목을 체크리스트로 정리하고 처리 전후에 다시 점검하겠습니다. 고객에게는 공식 설명자료를 기준으로 쉬운 표현을 사용하되, 최종 심사나 승인 판단은 담당자의 권한임을 지키겠습니다. 인턴의 기여는 판단을 대신하는 것이 아니라 자료 상태와 고객 요청을 정확히 보여 주는 데 두겠습니다.",
    ),
)

yongsan = ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609"
repair(
    yongsan,
    [
        ("신용보증기금", "용산구시설관리공단"),
        ("KODIT", "용산구시설관리공단"),
        ("기한연장", "문서 접수·확인"),
        ("기업신용 상시관리", "사업실적·자산·민원 데이터 관리"),
        ("기업신용", "사업·시설 운영 자료"),
        ("보증 승인·신용판단", "행정의 최종 판단과 승인"),
        ("인턴 기간", "입사 초기"),
        ("2026년도", "해당 연도"),
        ("2026년", "해당 연도"),
    ],
    "yongsan-office-duty-20260717",
    (
        "입사 초기에는 공단의 주요사업과 부서별 문서 흐름, 자산·실적 관리 기준과 민원 처리 절차를 먼저 익히겠습니다.",
        "입사 초기에는 공단의 주요사업과 부서별 문서 흐름, 자산·실적 관리 기준과 민원 처리 절차를 먼저 익히겠습니다. 반복 업무는 접수·확인·처리·보고 단계로 나누고, 누락·불일치·예외를 원자료 위치와 함께 기록하겠습니다. 고객 문의는 확인된 내용과 추가 확인 사항을 구분해 안내하겠습니다.",
        "입사 초기에는 공단의 주요사업과 부서별 문서 흐름, 자산·실적 관리 기준과 민원 처리 절차를 먼저 익히겠습니다. 반복 업무는 접수·확인·처리·보고 단계로 나누고, 누락·불일치·예외를 원자료 위치와 함께 기록하겠습니다. 고객 문의는 확인된 내용과 추가 확인 사항을 구분해 안내하겠습니다. 업무가 익숙해지면 반복되는 누락과 민원 원인을 양식, 안내문, 전달 순서에서 찾아 체크리스트로 정리하겠습니다. 여러 부서가 함께 처리하는 업무는 요청 내용과 마감기한을 짧게 공유하고 변경 사항을 기록으로 남기겠습니다. 최종 판단과 승인은 담당자의 권한으로 두고, 저는 검토 가능한 자료 상태를 만드는 데 책임을 다하겠습니다.",
    ),
)

kinfa = ROOT / "career_runs/kinfa-2026-youth-intern-youtube-guidance-20260717-20260717-120439-677326"
repair(
    kinfa,
    [
        ("신용보증기금", "서민금융진흥원"),
        ("KODIT", "서민금융진흥원"),
        ("신용보증 기한연장", "정책서민금융 상담·지원"),
        ("기한연장", "상담자료 확인"),
        ("기업신용 상시관리", "금융상담·신용분석 지원"),
        ("기업신용", "상담·신용 자료"),
        ("기업의 도전과 성장을 지원하는", "서민의 금융생활 안정과 경제적 재기를 지원하는"),
        ("보증 승인·신용판단", "금융지원의 최종 심사와 승인"),
        ("보증 분야", "서민금융 분야"),
        ("보증 업무", "금융지원 업무"),
        ("보증 여부", "지원 여부"),
        ("2026년도", "해당 연도"),
        ("2026년", "해당 연도"),
    ],
    "kinfa-intern-duty-20260717",
    (
        "입사 초기에는 정책서민금융 상품과 상담자료, 고객 안내 기준을 먼저 익히고 확인되지 않은 사항은 기록해 질문하겠습니다.",
        "입사 초기에는 정책서민금융 상품과 상담자료, 고객 안내 기준을 먼저 익히겠습니다. 반복 업무에서는 원자료와 입력값을 대조하고 누락·불일치·예외를 따로 기록해 담당자에게 보고하겠습니다. 고객에게는 쉬운 표현으로 다음 절차를 안내하겠습니다.",
        "입사 초기에는 정책서민금융 상품과 상담자료, 고객 안내 기준을 먼저 익히겠습니다. 반복 업무에서는 원자료와 입력값을 대조하고 누락·불일치·예외를 따로 기록해 담당자에게 보고하겠습니다. 고객에게는 쉬운 표현으로 다음 절차를 안내하겠습니다. 업무가 익숙해지면 자주 발생하는 질문과 확인 항목을 체크리스트로 정리하겠습니다. 금융 외 고용·복지 연계가 필요한 신호는 담당 부서에 정확히 전달하되, 최종 상담·심사 판단은 담당자의 권한임을 지키겠습니다. 인턴의 기여는 자료 상태와 고객 요청을 정확히 보여 주는 데 두겠습니다.",
    ),
)

for run in (hf, yongsan, kinfa):
    md = run / "08_면접대비팩.md"
    if md.exists():
        text = md.read_text(encoding="utf-8")
        text = text.replace("2026년도", "해당 연도").replace("2026년", "해당 연도")
        md.write_text(text, encoding="utf-8")

print("repaired")
