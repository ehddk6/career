# INTERVIEW ARCHITECTURE PACKET

## 확인된 면접 구조

| 요소 | 내용 | 상태 | 근거 |
|---|---|---|---|
| 면접 목적 | 기본인성과 직무능력 평가 | CONFIRMED | 2026 하반기 공식 채용공고 |
| 실시 범위 | 2026-08-12~2026-08-14, 영업본부별 | CONFIRMED | 공식 채용공고 |
| 개인 일정·장소 | 서류합격 발표 시 안내 | CONFIRMED | 공식 채용공고 |
| 방식·시간·패널 | 공고에 명시 없음 | UNKNOWN | 확인 가능한 공식 근거 없음 |
| 주요업무 | 신용보증 기한연장, 기업신용 상시관리 등 | CONFIRMED | 공식 채용공고 |
| 발표·토론·케이스 | 명시 없음 | UNKNOWN | 없다고 단정하지 않음 |

## 회사·직무·평가 연결

| 축 | 면접에서 보여 줄 내용 | 주요 근거 | 상태 |
|---|---|---|---|
| 기관 이해 | 담보력이 약한 기업의 자금융통을 신용보증으로 지원하고 신용질서·균형발전에 기여 | CR-001~003 | CONFIRMED |
| 2026 방향 | 생산적 금융, 지역금융, 중소·중견기업 경쟁력, 위기대응 | CR-004~006 | CONFIRMED |
| 직무 이해 | 자료 확인·변동 대조·기한 관리·보고·인계로 담당자의 판단을 지원 | SCL-004, SCL-010 | SUPPORTED_INFERENCE |
| 기본인성 | 기준을 묻고 기록하며, 모르는 것은 숨기지 않고 사실·판단을 구분 | SCL-006~008 | SUPPORTED_INFERENCE |
| 직무능력 | 대량·이질 자료를 기준으로 비교하고 이상을 근거와 함께 보고 | SCL-002, SCL-009 | SUPPORTED_INFERENCE |
| 리스크 감각 | 신속 지원과 보증재원 건전성, 일시 충격과 구조적 문제를 구분 | SCL-011~016 | SUPPORTED_INFERENCE |

## 예상 면접관 관점

| 관점 | 확인하려는 것 | 대응 방식 | 상태 |
|---|---|---|---|
| RECRUITER | 지원동기, 조직 적응, 근무 지속성 | 결론 먼저, 구체 행동 2개 | SUPPORTED_INFERENCE |
| JOB_MANAGER | 기한연장·상시관리 보조의 정확성 | 확인-기록-보고-인계 흐름 | SUPPORTED_INFERENCE |
| FACT_AUDITOR | 자소서 수치와 경험의 진실성 | Claim ID 범위 안에서만 답변 | SUPPORTED_INFERENCE |
| SITUATIONAL_INTERVIEWER | 누락·불일치·민원·마감 충돌 대응 | 원칙-행동-보고-재발방지 | SUPPORTED_INFERENCE |
| EXECUTIVE | 공공기관 태도, 정책금융 균형감 | 고객지원과 재원책임을 함께 제시 | WEAK_INFERENCE |
| RED_TEAM | 과장, 암기답변, 역할 월권 | 한계 인정 후 확인 경로 제시 | SUPPORTED_INFERENCE |

## 답변 아키텍처

1. `DIRECT_FIRST`: 지원동기·가치관·직무계획·상황판단
2. `EVIDENCE_FIRST`: 경험 성과·수치·회사 사실·경제 이슈
3. `REFLECTIVE`: 실패·약점·갈등·피드백

답변은 기본적으로 `결론 1문장 → 근거/사례 → 직접 행동 → KODIT 직무 연결 → 한계` 순서로 구성한다.

