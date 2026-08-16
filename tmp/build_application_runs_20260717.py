from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HF = ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610"
YONGSAN = ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609"
KINFA = ROOT / "career_runs/kinfa-2026-youth-intern-youtube-guidance-20260717-20260717-120439-677326"
KINFA_PREV = ROOT / "career_runs/kinfa-2026-youth-intern-official-20260717-20260717-015633-347550"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.write_text(value.strip() + "\n", encoding="utf-8")


def eligibility(target: str) -> dict:
    return {
        "schema_version": 1,
        "decision_id": f"eligibility-manual-{target}",
        "posting_id": target,
        "profile_id": "approved-experience-ledger-20260717",
        "status": "manual_review",
        "evaluated_at": "2026-07-17",
        "rule_evaluations": [],
        "reasons": [{
            "code": "applicant_attestation_required",
            "field": "applicant",
            "message": "연령·근무 가능일·결격사유 등 개인 확인이 필요한 조건은 최종 제출 전 지원자가 직접 확인해야 합니다.",
        }],
        "human_review_required": True,
        "internal_status": "manual_review",
        "human_review_recommended": True,
    }


hf_claims = [
    {
        "claim_id": "hf-purpose-20260717",
        "claim": "한국주택금융공사는 주택금융의 장기적·안정적 공급을 촉진해 국민의 복지 증진과 국민경제 발전에 이바지하기 위해 설립된 주택금융 전문기관이다.",
        "source_url": "https://hf.go.kr/ko/sub05/sub05_01_02.do",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "공사 설립목적과 역할을 설명하는 공식 페이지",
        "source_type": "official",
        "published_at": "",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "",
        "claim_type": "organization_role",
        "application_use": "문항 2 지원동기와 1분 자기소개에 사용",
    },
    {
        "claim_id": "hf-intern-duty-20260717",
        "claim": "2026년 하반기 체험형 인턴은 본사 부서 운영 지원과 지사 유동화 심사지원·채권관리·고객응대 등 사무보조를 수행하며, 직무설명자료는 일반사무행정·주택금융 여신심사·채권관리를 제시한다.",
        "source_url": "https://hf.go.kr/ko/sub05/sub05_07_03.do",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "사용자 제공 공식 채용공고문·입사지원서·직무설명자료에서 확인",
        "source_type": "official_posting",
        "published_at": "2026-07",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "운영부점에 따라 실제 보조 업무가 달라질 수 있다.",
        "claim_type": "job_duty",
        "application_use": "문항 1 직무능력과 문항 2 목표, 면접 직무 방어에 사용",
    },
    {
        "claim_id": "hf-pension-improvement-20260717",
        "claim": "한국주택금융공사는 2026년 6월부터 저가주택을 보유한 취약 고령층 지원을 확대하고 주택연금 이용 편의를 높이는 제도 개선을 시행했다.",
        "source_url": "https://hf.go.kr/ko/sub05/sub05_04_05.do?article.offset=0&articleLimit=10&articleNo=600046&mode=view",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "취약 고령층 지원 확대와 가입 편의 제고",
        "source_type": "official",
        "published_at": "2026-05",
        "basis_date": "2026-06-01",
        "verification_status": "verified",
        "conflict_note": "세부 지급액과 상품 조건은 변경될 수 있어 자기소개서에 수치로 단정하지 않는다.",
        "claim_type": "program_or_service",
        "application_use": "문항 4 주택연금 관심 이유와 고객 안내 기여방안에 사용",
    },
    {
        "claim_id": "hf-ax-20260717",
        "claim": "공사는 2026~2028년 AI 전환을 통해 주택금융 서비스의 접근성과 업무 효율을 높이겠다는 방향을 공개했다.",
        "source_url": "https://hf.go.kr/ko/sub05/sub05_04_05.do?articleNo=599619&mode=view",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "AI 전환으로 주택금융 서비스 접근성을 높이는 계획",
        "source_type": "official",
        "published_at": "2025-12",
        "basis_date": "2026-2028",
        "verification_status": "verified",
        "conflict_note": "인턴이 AI 전환을 직접 설계한다고 표현하지 않는다.",
        "claim_type": "strategy",
        "application_use": "문항 2의 학습 목표와 문항 4의 정확하고 쉬운 고객 안내에 보조적으로 사용",
    },
    {
        "claim_id": "hf-selection-criteria-20260717",
        "claim": "면접은 공사 이해도, 직무능력, 의사표현, 책임감과 친화력 등을 종합 평가한다.",
        "source_url": "https://hf.go.kr/ko/sub05/sub05_07_03.do",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "사용자 제공 2026년 하반기 체험형 인턴 공식 공고의 면접 평가요소",
        "source_type": "official_posting",
        "published_at": "2026-07",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "",
        "claim_type": "selection_criteria",
        "application_use": "전체 문항 블라인드 비교와 면접 방어 기준에 사용",
    },
]

hf_research = {
    "policy": "evidence-first",
    "skill_name": "career-pipeline",
    "mode": "ordinary-online-and-official-local",
    "searched_at": "2026-07-17T12:00:00+09:00",
    "status": "verified",
    "queries": ["한국주택금융공사 설립목적", "한국주택금융공사 2026 주택연금 개선", "한국주택금융공사 AX 2026 2028"],
    "source_families": ["official", "official_posting"],
    "verified_claim_ids": [x["claim_id"] for x in hf_claims],
}

hf_draft = [
    {
        "question_index": 1,
        "answer": "여러 자료를 같은 기준으로 연결하고 다시 대조해 오류 가능성을 줄이는 것이 제가 가장 잘할 수 있는 직무역량입니다. 공공기관에서 기초연금 수급 가능 대상자를 찾을 때 단순 연금액만으로는 부동산 자산과 추가 소득을 함께 보기 어려웠습니다. 저는 VLOOKUP을 활용해 연금액, 부동산 공시지가, 소득 자료를 연결하고 우선 확인이 필요한 대상을 분류했습니다. 각 자료의 기준 시점과 누락값을 살피고, 결과가 원자료와 맞는지 다시 대조했습니다. 이 과정에서 한 수치만 빠르게 처리하기보다 자료 간 관계와 적용 기준을 함께 확인해야 행정 결과의 신뢰를 지킬 수 있음을 배웠습니다. 한국주택금융공사 인턴으로 근무한다면 고객정보와 제출서류를 기준별로 정리하고, 불일치·누락·예외를 근거와 함께 기록해 담당자의 심사와 채권관리 업무를 정확히 보조하겠습니다. 확인이 필요한 항목을 임의로 판단하지 않고 질문과 답을 남겨 같은 오류가 반복되지 않도록 하겠습니다.",
        "evidence_paths": ["경험정리/경험정리.docx"],
        "experience_refs": [{"experience_id": "exp_d5ef585ca8817f00", "claim_ids": ["clm_0f9d3ca934f40d35a58f"]}],
        "research_refs": ["hf-intern-duty-20260717"],
    },
    {
        "question_index": 2,
        "answer": "주거와 노후의 불안을 줄이는 공적 주택금융이 현장에서 신뢰를 얻는 과정을 배우고 싶어 지원했습니다. 한국주택금융공사는 장기적이고 안정적인 주택금융 공급을 통해 국민의 복지와 경제 발전에 기여하며, 인턴은 심사지원·채권관리·고객응대와 사무행정을 보조합니다. 서울시청 코로나19 지원과에서 의료 인력 숙박비 관련 영수증과 실제 임대인 증빙 금액을 대조하고 부동산 앱으로 시세를 확인하는 과정에 참여하면서, 공적 지원은 속도뿐 아니라 근거 확인과 기록이 함께 갖춰져야 신뢰를 얻는다는 점을 배웠습니다. 인턴 기간에는 주택금융 상품별 제출자료가 어떤 기준으로 검토되고 고객 안내와 사후관리로 이어지는지 익히겠습니다. 원자료와 처리 결과를 차분히 확인하고 판단이 필요한 사항은 근거와 함께 보고하는 습관을 실무 수준으로 높여, 담당자가 안심하고 다음 판단을 내릴 수 있는 보조자가 되는 것이 목표입니다.",
        "evidence_paths": ["경험정리/경험정리.docx"],
        "experience_refs": [{"experience_id": "exp_41223e54120aa428", "claim_ids": ["clm_a70e6de53f9342e21545"]}],
        "research_refs": ["hf-purpose-20260717", "hf-intern-duty-20260717"],
    },
    {
        "question_index": 3,
        "answer": "제가 선택한 조직문화 가치는 협력이며, 서로 다른 부담을 듣고 모두가 지킬 수 있는 절차로 바꾸는 것이 협력이라고 생각합니다. 반포한강공원 별보기 행사 지원 당시 출석부 미기재와 물품 혼선, 일정 지연이 이어지며 행정 담당자와 현장 인력 사이에 책임을 둘러싼 갈등이 생겼습니다. 저는 한쪽의 잘못을 먼저 가리기보다 출석부와 물품 흐름을 분석하고 각 관계자가 불편을 겪는 지점을 차례로 들었습니다. 이후 온라인 출석부 제출 방식과 자원봉사자 일정 조정 절차를 제안하고 사용 방법과 역할을 설명해 공유했습니다. 관계자들이 실행할 수 있는 수준으로 절차를 정리하면서 행사 진행과 실적 처리가 원활해졌습니다. 이 경험으로 협력은 양보를 요구하는 말이 아니라 서로의 부담을 줄이는 기준을 함께 만드는 행동임을 배웠습니다. 공사에서도 고객응대와 심사지원 사이의 정보가 끊기지 않도록 확인 사항을 짧고 명확하게 공유하겠습니다.",
        "evidence_paths": ["경험정리/경험정리.docx"],
        "experience_refs": [{"experience_id": "exp_cc49cbad1ed46e45", "claim_ids": ["clm_06a610656b7cc2c74351"]}],
        "research_refs": [],
    },
    {
        "question_index": 4,
        "answer": "가장 관심 있는 상품은 고령층이 살던 집에서 생활을 이어가며 노후 소득을 보완하도록 돕는 주택연금입니다. 공사는 2026년 제도 개선을 통해 저가주택을 보유한 취약 고령층의 지원과 이용 편의를 확대했습니다. 제도가 있어도 고객이 신청 절차와 서류를 이해하지 못하면 실제 접근성은 낮아질 수 있다고 생각합니다. 은행 아르바이트 중 시각·청각 장애가 있는 고객이 태블릿 서명 절차에 어려움을 겪자, 큰 소리로 천천히 설명하고 행동을 직접 보여드리며 절차를 마칠 수 있도록 도왔습니다. 이 경험을 통해 정확한 안내는 정보를 전달하는 데서 끝나지 않고 고객이 다음 행동을 할 수 있는지 확인하는 일임을 배웠습니다. 인턴으로서는 주택연금 신청자료를 빠짐없이 정리하고 고객 문의의 핵심과 확인 필요 사항을 구분해 담당자에게 전달하겠습니다. 공식 설명서와 체크리스트를 기준으로 쉬운 표현을 사용하고, 임의로 답할 수 없는 내용은 정확히 확인해 신뢰받는 고객 접점을 보조하겠습니다.",
        "evidence_paths": ["경험정리/경험정리.docx"],
        "experience_refs": [{"experience_id": "exp_196858201aa9d88c", "claim_ids": ["clm_ab3e09b38789ea202f92"]}],
        "research_refs": ["hf-pension-improvement-20260717"],
    },
]

y_claims = [
    {
        "claim_id": "yongsan-role-20260717",
        "claim": "용산구시설관리공단은 주차장, 체육시설, 청소년시설, 청사 등 주민 생활과 맞닿은 공공시설을 관리한다.",
        "source_url": "https://www.yong-san.or.kr/site/main/archive/post/2025%EB%85%84-%EC%A0%9C1%ED%9A%8C-%EC%A7%81%EC%9B%90-%EA%B3%B5%EA%B0%9C%EA%B2%BD%EC%9F%81%EC%B1%84%EC%9A%A9?arcId=101511&catId=20&cp=2&listType=list&sortDirection=DESC",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "공식 채용자료에 제시된 공단 주요사업",
        "source_type": "official",
        "published_at": "2025",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "",
        "claim_type": "organization_role",
        "application_use": "자유서술형 지원동기와 입사 후 기여에 사용",
    },
    {
        "claim_id": "yongsan-office-duty-20260717",
        "claim": "2026년 제3회 공개경쟁채용 사무직 8급 행정은 문서관리, 자산관리, 업무지원, 데이터 관리, 인력관리, 고객 서비스 등 공단 경영목표 달성을 위한 행정업무를 수행한다.",
        "source_url": "https://www.yong-san.or.kr/site/main/archive/post/list?catId=20",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "사용자 제공 공식 공고문 제2026-28호 6쪽 직무설명자료",
        "source_type": "official_posting",
        "published_at": "2026-07",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "ZIP의 다른 직무기술서는 사무직 8급 행정에 적용하지 않는다.",
        "claim_type": "job_duty",
        "application_use": "문서·데이터·고객·협업 경험의 직무 연결에 사용",
    },
    {
        "claim_id": "yongsan-ethics-20260717",
        "claim": "공단은 새로운 변화로 구민행복 증진과 용산구 발전에 기여한다는 미션과 윤리경영 체계를 공개하고 있다.",
        "source_url": "https://yong-san.or.kr/site/main/content/ethics_01",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "공단 미션과 윤리경영 비전",
        "source_type": "official",
        "published_at": "",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "",
        "claim_type": "strategy",
        "application_use": "지원동기와 책임 있는 행정 태도에 사용",
    },
    {
        "claim_id": "yongsan-iso41001-20260717",
        "claim": "공단은 시설관리경영시스템 ISO 41001 국제표준 인증을 획득해 시설관리 운영체계의 표준화를 추진했다.",
        "source_url": "https://yong-san.or.kr/site/main/archive/post/2025-27%ED%98%B8-%EC%9A%A9%EC%82%B0%EA%B5%AC%EC%8B%9C%EC%84%A4%EA%B4%80%EB%A6%AC%EA%B3%B5%EB%8B%A8-%EC%8B%9C%EC%84%A4%EA%B4%80%EB%A6%AC%EA%B2%BD%EC%98%81%EC%8B%9C%EC%8A%A4%ED%85%9C-iso-41001-%EA%B5%AD%EC%A0%9C%ED%91%9C%EC%A4%80-%EC%9D%B8%EC%A6%9D-%ED%9A%8D%EB%93%9D?arcId=101686&catId=23&cp=6&listType=list&sortDirection=DESC",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "시설관리경영시스템 ISO 41001 인증 획득",
        "source_type": "official",
        "published_at": "2025",
        "basis_date": "2025",
        "verification_status": "verified",
        "conflict_note": "인증 자체를 지원자의 성과로 오인하지 않는다.",
        "claim_type": "program_or_service",
        "application_use": "표준화된 문서·데이터 관리와 업무 개선 기여에 사용",
    },
    {
        "claim_id": "yongsan-selection-criteria-20260717",
        "claim": "서류는 자격·경험·발전가능성·적합성·직무수행능력을, 면접은 직원 정신자세·전문지식과 응용능력·표현의 정확성과 논리성·태도와 성실성·발전가능성을 평가한다.",
        "source_url": "https://www.yong-san.or.kr/site/main/archive/post/list?catId=20",
        "checked_at": "2026-07-17",
        "evidence_excerpt": "사용자 제공 공식 공고문 제2026-28호의 전형 기준",
        "source_type": "official_posting",
        "published_at": "2026-07",
        "basis_date": "2026-07-17",
        "verification_status": "verified",
        "conflict_note": "",
        "claim_type": "selection_criteria",
        "application_use": "블라인드 비교와 면접 방어 기준에 사용",
    },
]

y_research = {
    "policy": "evidence-first",
    "skill_name": "career-pipeline",
    "mode": "ordinary-online-and-official-local",
    "searched_at": "2026-07-17T12:00:00+09:00",
    "status": "verified",
    "queries": ["용산구시설관리공단 주요사업", "용산구시설관리공단 윤리경영", "용산구시설관리공단 ISO 41001"],
    "source_families": ["official", "official_posting"],
    "verified_claim_ids": [x["claim_id"] for x in y_claims],
}

y_answer = """[주민의 일상을 지키는 정확한 행정]
저는 시설을 직접 이용하는 주민의 불편을 줄이고, 현장의 운영이 끊기지 않도록 정확한 행정으로 뒷받침하고 싶어 용산구시설관리공단 사무직 8급에 지원했습니다. 공단은 주차장, 체육시설, 청소년시설과 청사 등 생활 가까이에 있는 공공시설을 운영합니다. 이 시설들은 눈에 보이는 현장 서비스뿐 아니라 문서, 자산, 인력, 데이터와 고객 문의가 같은 기준으로 관리될 때 안정적으로 운영된다고 생각합니다. 저는 공공기관과 은행, 행사 지원 현장에서 자료를 대조하고 고객의 눈높이에 맞춰 설명하며 관계자의 부담을 절차로 조정해 왔습니다. 이 경험을 문서관리·데이터 관리·업무지원·고객 서비스에 연결하겠습니다.

[근거를 남기는 문서·데이터 관리]
서울시청 코로나19 지원과에서 의료 인력 급여 산정과 숙박비 관련 업무를 맡았을 때, 영수증 금액과 실제 임대인 증빙 금액이 맞는지 대조하고 부동산 앱으로 시세를 확인하는 과정에 참여했습니다. 공적 지원은 빨리 처리하는 것만큼 같은 기준으로 자료를 확인하고 판단 근거를 남기는 일이 중요했습니다. 저는 자료 간 불일치가 있으면 어느 값이 다른지 구분하고, 추가 확인이 필요한 부분을 임의로 넘기지 않는 태도를 익혔습니다. 공단에서도 계약·지출·자산·인력 관련 문서를 접수할 때 기준일, 작성 항목, 첨부자료와 입력값을 순서대로 확인하겠습니다. 누락과 예외는 원자료 위치와 함께 기록해 담당자가 바로 검토할 수 있도록 하겠습니다.

기초연금 수급 가능 대상자를 찾는 업무에서는 단순 연금액만으로는 부동산 자산과 추가 소득을 함께 반영하기 어렵다는 한계를 발견했습니다. 저는 VLOOKUP을 활용해 연금액, 부동산 공시지가, 소득 자료를 연결하고 우선 확인이 필요한 대상을 분류했습니다. 이 과정에서 데이터 관리의 핵심은 함수를 사용하는 데 있지 않고, 서로 다른 자료의 기준과 관계를 확인해 오류 가능성을 줄이는 데 있음을 배웠습니다. 공단의 사업별 실적과 민원, 자산 현황을 다룰 때도 원자료와 집계값을 다시 대조하고, 빈칸·중복·이상값을 구분해 보고하겠습니다. 반복 업무는 체크리스트로 정리하되 예외를 억지로 일반 규칙에 맞추지 않겠습니다.

[고객이 다음 행동을 할 수 있는 안내]
은행 아르바이트 중 시각·청각 장애가 있는 고객이 태블릿 서명 절차에 어려움을 겪었습니다. 저는 목소리를 크게 하되 속도를 늦추고, 화면에서 해야 할 행동을 직접 보여드렸습니다. 긴장을 줄일 수 있도록 짧은 대화를 곁들이며 고객이 절차를 따라오는지 확인했습니다. 이 경험을 통해 고객 서비스는 친절한 말을 많이 하는 것이 아니라 상대가 무엇에서 막혔는지 파악하고, 이해할 수 있는 방식으로 설명한 뒤 다음 행동이 가능한지 확인하는 일임을 배웠습니다. 시설 이용 문의나 민원을 받을 때는 먼저 요구사항과 사실관계를 분리해 듣고, 즉시 안내할 내용과 담당 부서 확인이 필요한 내용을 구분하겠습니다. 답변할 수 없는 사항을 추측하지 않고 처리 경로와 예상되는 다음 절차를 명확히 안내하겠습니다.

[협업을 실행 가능한 절차로 바꾸는 사람]
반포한강공원 별보기 행사 지원 당시 출석부 미기재, 물품 혼선과 일정 지연이 이어졌고 행정 담당자와 현장 인력 사이에 책임을 둘러싼 갈등도 생겼습니다. 저는 한쪽의 잘못부터 정하기보다 출석부와 물품 흐름을 분석하고 각 관계자가 불편을 겪는 지점을 차례로 들었습니다. 행정 담당자는 실적 확인이 어려웠고, 현장 인력은 종이 출석부 작성과 전달이 번거로웠습니다. 양쪽의 부담을 함께 줄이기 위해 온라인 출석부 제출 방식과 자원봉사자 일정 조정 절차를 제안하고, 사용 방법과 역할을 설명해 공유했습니다. 관계자가 실제로 지킬 수 있는 수준으로 절차를 정리하면서 행사 진행과 실적 처리가 원활해졌습니다. 이를 통해 협업은 서로 양보하라고 요구하는 말이 아니라, 업무가 다시 막히지 않도록 공동의 기준과 흐름을 만드는 행동임을 배웠습니다.

[입사 후 기여]
입사 초기에는 공단의 주요사업과 부서별 문서 흐름, 자산·실적 관리 기준, 민원 처리 절차를 먼저 정확히 익히겠습니다. 업무를 맡으면 접수-확인-처리-보고의 각 단계에서 필요한 항목을 체크하고, 불일치와 예외를 근거와 함께 남기겠습니다. 고객 문의는 쉬운 표현으로 안내하되 확인되지 않은 답을 서둘러 주지 않겠습니다. 여러 부서가 함께 처리하는 업무에서는 각자의 요청과 마감기한을 짧게 정리해 공유하고, 변경된 내용은 기록으로 남기겠습니다. 나아가 반복되는 누락이나 민원 원인을 발견하면 개인의 실수로만 보지 않고 양식, 안내문, 전달 순서에서 개선할 지점을 찾겠습니다. 주민이 시설을 이용할 때 행정의 빈틈을 느끼지 않도록, 정확한 자료관리와 책임 있는 고객 응대, 실행 가능한 협업으로 공단의 안정적인 운영에 기여하겠습니다."""

y_draft = [{
    "question_index": 1,
    "answer": y_answer,
    "evidence_paths": ["경험정리/경험정리.docx"],
    "experience_refs": [
        {"experience_id": "exp_41223e54120aa428", "claim_ids": ["clm_a70e6de53f9342e21545"]},
        {"experience_id": "exp_d5ef585ca8817f00", "claim_ids": ["clm_0f9d3ca934f40d35a58f"]},
        {"experience_id": "exp_196858201aa9d88c", "claim_ids": ["clm_ab3e09b38789ea202f92"]},
        {"experience_id": "exp_cc49cbad1ed46e45", "claim_ids": ["clm_06a610656b7cc2c74351"]},
    ],
    "research_refs": ["yongsan-role-20260717", "yongsan-office-duty-20260717", "yongsan-ethics-20260717", "yongsan-iso41001-20260717"],
}]


def make_research_md(title: str, claims: list[dict], mappings: list[str], checks: list[str]) -> str:
    facts = "\n".join(f"- {c['claim']} [{c['claim_id']}]({c['source_url']})" for c in claims)
    return f"""# {title} 기업·직무 조사

## 확인된 사실

{facts}

## 해석

- 지원자의 역할은 최종 의사결정을 대신하는 것이 아니라 원자료 확인, 문서·데이터 정리, 고객 안내와 부서 간 정보 전달을 정확히 보조하는 데 있다.
- 확인된 기관 사실과 지원자의 해석을 분리하고, 공개되지 않은 내부 기준이나 성과는 추정하지 않는다.

## 문항·면접 활용 맵

{chr(10).join('- ' + x for x in mappings)}

## 확인 필요

{chr(10).join('- ' + x for x in checks)}

## 사용 경계

- 기관 사실은 `04_공식근거.json`의 claim ID로 추적한다.
- 경험 사실은 승인 경험 원장의 confirmed claim만 사용한다.
- 수치와 내부 권한을 추정하거나 인턴·신입이 최종 판단을 수행한다고 표현하지 않는다.
"""


def make_strategy_md(title: str, rows: list[tuple[str, str, str]]) -> str:
    body = [f"# {title} 문항별 최적 배치 전략", "", "## 공통 기준", "", "- 첫 두 문장 안에서 결론을 제시한다.", "- 상황보다 직접 행동과 확인 가능한 결과를 길게 쓴다.", "- 승인된 서로 다른 사건을 배치하고 기관 사실은 공식 근거 ID로 추적한다.", "- 면접에서 다시 설명할 수 없는 수치·성과·권한은 넣지 않는다."]
    for i, (event, reason, structure) in enumerate(rows, 1):
        body.extend(["", f"## 문항 {i}", "", f"- 배치 경험: {event}", f"- 이유: {reason}", f"- 구조: {structure}"])
    return "\n".join(body)


write_json(HF / "04_공식근거.json", hf_claims)
write_json(HF / "04_리서치실행.json", hf_research)
write_json(HF / "draft.json", hf_draft)
write_json(HF / "eligibility_decision.json", eligibility("hf-2026-h2-intern"))
write_text(HF / "04_기업직무조사.md", make_research_md(
    "한국주택금융공사",
    hf_claims,
    [
        "문항 1: `hf-intern-duty-20260717`과 데이터 연결 사건을 직무능력으로 연결",
        "문항 2: `hf-purpose-20260717`과 공적 지원 증빙 대조 사건을 지원동기·학습목표로 연결",
        "문항 3: 갈등 조정 사건을 조직문화 가치 ‘협력’으로 연결",
        "문항 4: `hf-pension-improvement-20260717`과 장애 고객 안내 사건을 주택연금 관심·기여방안으로 연결",
        "면접: `hf-selection-criteria-20260717`을 공사 이해도·직무능력·표현·책임감 방어 기준으로 사용",
    ],
    [
        "지원자가 선택할 운영부점과 해당 근무지에서 입사일부터 근무 가능한지 확인",
        "접수마감일 기준 청년 연령과 채용금지자 해당 여부 확인",
    ],
))
write_text(HF / "05_문항전략.md", make_strategy_md(
    "한국주택금융공사",
    [
        ("`exp_d5ef585ca8817f00` / `clm_0f9d3ca934f40d35a58f`", "다원 자료 연결·대조 행동이 심사지원과 문서 검토에 직접 연결된다.", "역량 결론 → 자료 연결 행동 → 확인 기준 → 공사 직무 기여"),
        ("`exp_41223e54120aa428` / `clm_a70e6de53f9342e21545`", "공적 지원 증빙 확인 경험이 주택금융의 신뢰와 현장 학습 목표를 뒷받침한다.", "기관 선택 이유 → 공적 지원 경험 → 배운 원칙 → 인턴 목표"),
        ("`exp_cc49cbad1ed46e45` / `clm_06a610656b7cc2c74351`", "이해관계자의 부담을 절차로 조정한 완결된 협력 사건이다.", "협력 정의 → 갈등 원인 → 경청·제안·공유 → 결과와 직무 적용"),
        ("`exp_196858201aa9d88c` / `clm_ab3e09b38789ea202f92`", "고객 눈높이 안내 경험이 취약 고령층의 주택연금 접근성에 연결된다.", "상품 선택 → 공식 변화 → 고객 안내 사건 → 인턴 기여"),
    ],
))

write_json(YONGSAN / "04_공식근거.json", y_claims)
write_json(YONGSAN / "04_리서치실행.json", y_research)
write_json(YONGSAN / "draft.json", y_draft)
write_json(YONGSAN / "eligibility_decision.json", eligibility("yongsan-2026-3-office8"))
write_text(YONGSAN / "04_기업직무조사.md", make_research_md(
    "용산구시설관리공단",
    y_claims,
    [
        "문항 1 지원동기: `yongsan-role-20260717`과 생활밀착 공공시설의 안정적 운영을 연결",
        "문항 1 문서·데이터: `yongsan-office-duty-20260717`과 증빙 대조·VLOOKUP 사건을 연결",
        "문항 1 고객서비스: 장애 고객 눈높이 안내 사건을 공단 고객 응대로 연결",
        "문항 1 협업: 행사 갈등을 온라인 출석부·일정 조정 절차로 바꾼 사건을 연결",
        "문항 1 입사 후 기여: `yongsan-iso41001-20260717`의 표준화 방향을 체크리스트·기록 개선에 연결",
        "면접: `yongsan-selection-criteria-20260717`을 정확성·논리성·태도·성실성 방어 기준으로 사용",
    ],
    [
        "정년, 병역, 출국 제한, 공단 인사규정 결격사유 해당 여부 확인",
        "새벽·야간·주말 근무 가능 여부와 실제 배치부서 확인",
    ],
))
write_text(YONGSAN / "05_문항전략.md", make_strategy_md(
    "용산구시설관리공단",
    [(
        "`exp_41223e54120aa428`, `exp_d5ef585ca8817f00`, `exp_196858201aa9d88c`, `exp_cc49cbad1ed46e45`",
        "하나의 자유서술형 안에서 문서 정확성·데이터 관리·고객 서비스·협업을 서로 다른 사건으로 입증한다.",
        "지원동기 → 증빙 대조 → 데이터 연결 → 고객 안내 → 갈등 조정 → 입사 후 기여",
    )],
))
write_json(YONGSAN / "application_screen_attestation.json", {
    "schema_version": 1,
    "source": "user_attested_official_application_screen",
    "confirmed_at": "2026-07-17",
    "question_count": 1,
    "required": True,
    "minimum_characters": 500,
    "maximum_characters": 20000,
    "target_range": {"minimum": 2000, "maximum": 3000},
    "note": "중복 노출된 입력란 명칭과 필수 안내는 별도 문항이 아니다.",
})

# KINFA: preserve the previous official research packet but make the YouTube strategy
# an explicit, auditable generation contract in this new run.
for name in ("04_공식근거.json", "04_리서치실행.json", "04_기업직무조사.md"):
    shutil.copy2(KINFA_PREV / name, KINFA / name)
write_json(KINFA / "draft.json", json.loads((KINFA_PREV / "draft_final.json").read_text(encoding="utf-8")))
write_json(KINFA / "eligibility_decision.json", json.loads((KINFA_PREV / "eligibility_decision.json").read_text(encoding="utf-8")))
write_json(KINFA / "05_유튜브프레임_적용계약.json", {
    "schema_version": 1,
    "source_dir": "자료조사/자소서_유튜브_프레임분석_2026-07-03",
    "use_policy": "strategy_only_not_factual_evidence",
    "principles": [
        "첫 문장은 결론·역량·관심 분야를 먼저 제시하는 두괄식",
        "기관명을 바꿔도 통하는 일반론을 피하고 고객·현장·직무·사업 접점을 제시",
        "상황보다 직접 행동과 확인 가능한 결과를 중심으로 작성",
        "증명된 행동 방식을 입사 후 업무에 연결",
        "고객 서비스는 문제 파악·설명·조율·재발 방지로 표현",
        "책임은 규정·기록·확인·공정성을 지킨 행동으로 표현",
        "승인 경험 원장과 공식 기관 근거로 면접 방어 가능한 사실만 사용",
    ],
    "question_application": {
        "1": ["두괄식 지원동기", "기관 고유성", "공적 지원 증빙 대조", "입사 후 학습·기여"],
        "2": ["필요 역량 정의", "실제 적용 경험", "확인 가능한 행동", "직무 연결"],
        "3": ["이해관계자 차이", "경청·조율 행동", "절차 개선", "재발 방지"],
        "4": ["관심 분야 결론", "고객 접근성 문제", "직접 안내 행동", "업무 기여"],
    },
    "evidence_boundary": "이 계약은 writing guidance이며 research_refs나 experience_refs의 사실 근거로 사용하지 않는다.",
})
write_text(KINFA / "05_유튜브프레임_적용계약.md", """# 서민금융진흥원 유튜브 프레임 명시 적용 계약

## 적용 키워드

- 두괄식
- 기관 고유성
- 행동 중심
- 직무 연결
- 문제 파악·설명·조율·재발 방지
- 규정·기록·확인·공정성
- 면접 방어 가능성

## 문항별 적용

- 문항 1: 기관 선택 이유를 먼저 말하고 공적 지원 증빙 대조 경험과 인턴의 학습·기여로 연결한다.
- 문항 2: 필요한 역량을 먼저 정의한 뒤 실제 적용 행동과 직무 활용을 제시한다.
- 문항 3: 이해관계자의 차이, 경청과 조율 행동, 절차 개선과 재발 방지를 보여 준다.
- 문항 4: 관심 분야를 먼저 밝히고 고객 접근성 문제, 직접 안내 행동, 업무 기여로 연결한다.

## 근거 경계

- 이 계약은 작성 전략일 뿐 기관 사실이나 사용자 경험 사실의 evidence가 아니다.
- 기관 사실은 `04_공식근거.json`, 경험 사실은 승인 경험 원장만 사용한다.
""")
write_text(KINFA / "05_문항전략.md", (KINFA_PREV / "05_문항전략.md").read_text(encoding="utf-8") + """

## 유튜브 프레임 명시 적용

- 문항 1: 두괄식·기관 고유성·공적 지원 경험·학습 목표.
- 문항 2: 역량 정의·실제 적용 행동·직무 연결.
- 문항 3: 이해관계자 차이·경청·조율·절차 개선·재발 방지.
- 문항 4: 관심 분야 결론·고객 접근성·직접 안내·업무 기여.
- `05_유튜브프레임_적용계약.json`은 전략 추적용이며 사실 근거로 사용하지 않는다.
""")
strategy = json.loads((KINFA / "05_문항전략.json").read_text(encoding="utf-8"))
strategy["writing_guidance_contract"] = "05_유튜브프레임_적용계약.json"
strategy["writing_guidance_keywords"] = ["두괄식", "기관 고유성", "행동 중심", "직무 연결", "재발 방지", "기록·확인", "면접 방어"]
for q in strategy["questions"]:
    q["requirements"].append({
        "requirement_id": "youtube_frame_explicit_application",
        "description": "두괄식으로 시작하고 상황보다 행동을 강조하며 승인 경험을 기관 직무 기여로 연결함",
        "hard_fail_if_missing": True,
        "answer_cues": ["확인", "대조", "설명", "제안", "기록", "배웠", "하겠습니다"],
    })
write_json(KINFA / "05_문항전략.json", strategy)

print("HF draft lengths:", [len(x["answer"].replace(" ", "").replace("\n", "")) for x in hf_draft])
print("Yongsan draft length:", len(y_answer))
print("Prepared:", HF)
print("Prepared:", YONGSAN)
print("Prepared:", KINFA)
