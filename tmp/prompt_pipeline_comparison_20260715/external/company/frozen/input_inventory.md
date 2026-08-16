# Input Inventory

- 데이터 패키지: `CR-DATA-001` v1.0
- 조회일: 2026-07-15

| Source ID | 자료명 | 작성 주체 | 유형 | 발표일 | 기준일 | 대상 법인 | 원본 위치 | SHA-256 | 처리 |
|---|---|---|---|---|---|---|---|---|---|
| SRC-01 | 채용공고 분석 | 로컬 career run; 원문은 사용자 확인 | JSON | 2026-07-09 | 2026-07-09 | 신용보증기금 | `inputs/workspace/career_run/00_채용공고분석.json` | `ba3b...d3b` | 사용 |
| SRC-02 | 확정경험원장 | 지원자 로컬 원장 | JSON | 2026-07-10 생성 | 경험별 기간 미상 | 지원자 | `inputs/workspace/career_run/02_확정경험원장.json` | `485c...2c4` | confirmed claim만 사용 |
| SRC-03 | 경험직무매칭 | 로컬 career run | JSON | UNVERIFIED | UNVERIFIED | 지원자·신용보증기금 | `inputs/workspace/career_run/03_경험직무매칭.json` | `f3fa...061` | 후보 라우팅만 사용 |
| SRC-04 | 공식근거 원장 | 로컬 원장; 기초자료 작성 주체는 각 공식기관 | JSON | 항목별 | 2026-03~2026-07 | 신용보증기금·한국은행 | `inputs/workspace/career_run/04_공식근거.json` | `4956...cf0` | 핵심 근거 |
| SRC-05 | 기업·직무 조사 | 로컬 research synthesis | Markdown | 2026-07-13 확인 | 2026-07-13 | 신용보증기금 | `inputs/workspace/career_run/04_기업직무조사.md` | `c704...e54` | 해석은 INFERENCE로 사용 |
| SRC-X01~X06 | 상담·영업 직무기술서 6개 | 한국도로공사서비스(주) | PDF | UNVERIFIED | UNVERIFIED | 한국도로공사서비스(주) | `inputs/workspace/직무기술서/` | `frozen/manifest.json` 참조 | 대상 법인 불일치로 제외 |

PDF 6개의 전체 해시는 `frozen/manifest.json`에 기록했다. 발표일·기준일을 파일 본문에서 확인할 수 없어 임의로 부여하지 않았다.
