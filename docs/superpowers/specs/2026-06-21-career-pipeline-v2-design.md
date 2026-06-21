# Career Pipeline V2: 승인 경험 원장과 채용공고 자동 분석

작성일: 2026-06-21

## 1. 목표

Career Pipeline V2의 첫 개선 사이클은 매 기업 지원 때마다 흩어진 문서를 다시 진실로 해석하는 방식을 끝내고, 다음 두 계층을 도입한다.

1. 사용자가 승인한 개인 경험·사실을 영구 보존하는 로컬 경험 원장
2. 공식 URL 또는 로컬 PDF·DOCX에서 직무·역량·문항·제약을 구조화하는 채용공고 분석기

이 두 계층을 기존 `prepare → research → finalize` 흐름에 연결해, 제출 답변에 사용되는 모든 사실과 직무 연결을 추적 가능하게 만든다.

## 2. 범위

### 포함

- 기존 취업 자료에서 경험 원장 후보 자동 생성
- 사용자 승인 상태와 정확한 근거 파일·문단·해시 보존
- 승인 원장의 스키마 검증과 근거 파일 변경 감지
- 공식 HTTPS URL, 로컬 PDF, 로컬 DOCX 채용공고 분석
- 직무, 업무, 역량, 지원요건, 우대사항, 문항, 글자 수, 블라인드·제출 제약 추출
- 공고와 승인 경험 사이의 설명 가능한 문항별 매칭
- 기존 명령 호환 모드와 품질 경고
- 현재 HUG 실행 및 기존 테스트의 회귀 검증

### 제외

- 다중 초안 생성·비교 평가
- 벡터 데이터베이스와 임베딩 검색
- HWP/HWPX 직접 분석
- 이미지 OCR
- GUI 또는 웹 대시보드
- 합격 가능성 예측

위 제외 항목은 첫 개선 사이클이 완료된 뒤 별도 명세로 다룬다.

## 3. 설계 원칙

- 진실은 승인된 경험 원장에만 존재한다.
- 새 추출 결과는 승인 사실을 자동으로 덮어쓰지 않는다.
- AI는 사실 결정자가 아니라 공고 매칭·조사·문장 합성자로 사용한다.
- 모든 수치·역할·기간·성과는 근거 파일과 원문 위치로 역추적할 수 있어야 한다.
- 공식성을 확인하지 못한 공고는 추측하지 않고 차단한다.
- 기존 사용자 문서와 승인 원장은 자동 수정하지 않는다.
- 민감 파일과 경험 원장은 외부 사이트에 업로드하거나 검색어에 포함하지 않는다.

## 4. 시스템 구조

```text
기존 취업 자료
   │
   ├─ profile build ──> 경험 후보 원장 ──> 사용자 확인 ──> 승인 경험 원장
   │                                                   │
공식 URL/PDF/DOCX ── posting analyze ──> 공고 분석 ─────┤
                                                       │
작성 중인 초안 ── 질문 추출 ──────────────────────────┤
                                                       ▼
                                         설명 가능한 경험·문항 매칭
                                                       │
                                                       ▼
                                research → draft → interview → finalize
```

구현 단위는 다음처럼 분리한다.

- `profile_schema.py`: 경험 원장 모델과 스키마 검증
- `profile_builder.py`: 기존 자료에서 경험·사실 후보 생성
- `profile_refresh.py`: 승인 원장과 새 후보 비교, 변경·충돌·stale 판정
- `posting_loader.py`: URL·PDF·DOCX 원문 획득과 스냅샷 보존
- `posting_parser.py`: 공고 구조화와 불확실성 기록
- `matching.py`: 공고·문항·경험의 설명 가능한 매칭
- `quality.py`: 프로필·공고·매칭 품질 게이트

기존 `inventory.py`, `extractors.py`, `questions.py`, `facts.py`, `conflicts.py`, `orchestrator.py`, `validation.py`는 위 모듈을 호출하는 현재 책임만 유지한다.

## 5. 승인 경험 원장

### 5.1 저장 위치

기본 경로는 다음과 같다.

```text
.career_profile/
  experience_ledger.proposed.json
  experience_ledger.json
  profile_review.md
```

`.career_profile/`은 Git과 취업 자료 인벤토리에서 기본 제외한다. 승인 원장은 사용자 PC 안에서만 유지한다.

### 5.2 스키마

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-21T12:00:00+09:00",
  "workspace_root": "C:/.../취업",
  "experiences": [
    {
      "experience_id": "exp_<stable-hash>",
      "title": "숙박비 증빙 교차 검증",
      "organization_alias": "지자체",
      "period": {
        "value": null,
        "status": "unknown"
      },
      "role": "의료인력 숙박비 증빙 검토",
      "situation": "영수증 금액과 지역 시세의 불일치 가능성",
      "actions": [
        "엑셀로 이상치 선별",
        "시세와 계약 자료 교차 확인",
        "의심 사례를 담당자에게 보고"
      ],
      "outcomes": [
        "부정수급 의심 20건 확인",
        "예산 누수 1,000만원 방지"
      ],
      "competencies": [
        "데이터 검증",
        "정확성",
        "공공자금 책임"
      ],
      "claims": [
        {
          "field": "budget_savings",
          "normalized_value": "10000000원",
          "status": "confirmed",
          "evidence": [
            {
              "source_path": "근거.docx",
              "paragraph_index": 12,
              "source_sha256": "...",
              "excerpt_sha256": "..."
            }
          ]
        }
      ],
      "status": "confirmed",
      "confirmed_at": "2026-06-21T12:00:00+09:00"
    }
  ]
}
```

### 5.3 상태

- `proposed`: 자동 추출됐지만 사용자 확인 전
- `confirmed`: 제출 답변에 사용 가능
- `rejected`: 잘못된 경험·수치로 판정
- `stale`: 근거 파일 또는 근거 문단 해시가 변경됨
- `unknown`: 기간 등 값이 확인되지 않음

`prepare`와 `finalize`는 `confirmed` 주장만 사용한다. `proposed`, `rejected`, `stale`, `unknown` 값은 제출 답변의 사실 근거가 될 수 없다.

### 5.4 식별과 갱신

- `experience_id`는 최초 근거의 정규화 경로, 문단 인덱스, 경험 앵커 토큰을 해시해 생성한다.
- `profile build`는 최초 후보 파일만 만든다.
- `profile refresh`는 승인 원장을 수정하지 않고 새 후보와 차이를 `experience_ledger.proposed.json` 및 `profile_review.md`에 기록한다.
- 동일 근거의 파일 해시가 바뀌면 해당 경험을 `stale` 후보로 보고하되 기존 승인본은 보존한다.
- 사용자가 값을 확인하면 Codex가 후보 파일에 결정을 반영하고 `profile validate`를 통과시킨 뒤 승인 원장으로 저장한다.

## 6. 채용공고 분석

### 6.1 입력

지원 입력은 다음과 같다.

- 공식 HTTPS URL
- 로컬 PDF
- 로컬 DOCX

로컬 파일은 공식 원문 URL을 함께 제공하거나 사용자가 공식 파일임을 명시해야 한다. 공식성 상태는 다음 중 하나로 기록한다.

- `verified_domain`: 지정한 공식 도메인에서 직접 획득
- `user_attested`: 사용자가 공식 원문 파일이라고 확인
- `unverified`: 공식성을 확인하지 못함

`unverified`는 `blocked_posting` 상태를 발생시킨다.

### 6.2 URL 보안

- 기본적으로 HTTPS만 허용한다.
- localhost, 루프백, 사설 IP, 링크 로컬 주소는 거부한다.
- 리다이렉트는 최대 5회 허용하고 매 단계 주소를 다시 검증한다.
- 연결·읽기 제한시간은 각각 10초, 전체 30초로 제한한다.
- 응답 크기는 20MB로 제한한다.
- 허용 콘텐츠 유형은 HTML, PDF, DOCX, 일반 텍스트다.
- URL 요청에는 로컬 문서 내용, 사용자 개인정보, 브라우저 쿠키를 전송하지 않는다.

### 6.3 스냅샷 스키마

실행 폴더에 다음을 생성한다.

```text
00_채용공고원문/
  source.<ext>
00_채용공고분석.json
00_채용공고분석.md
```

분석 JSON은 다음 필드를 가진다.

```json
{
  "schema_version": 1,
  "target": "기관 직무 근무지",
  "source": {
    "kind": "url|pdf|docx",
    "location": "...",
    "retrieved_at": "...",
    "content_sha256": "...",
    "official_status": "verified_domain|user_attested|unverified"
  },
  "organization": "기관명",
  "role": "직무명",
  "locations": ["근무지"],
  "duties": ["주요 업무"],
  "competencies": ["필요 역량"],
  "requirements": ["지원요건"],
  "preferences": ["우대사항"],
  "questions": [
    {
      "index": 1,
      "prompt": "문항",
      "character_limit": 600
    }
  ],
  "constraints": ["블라인드 및 제출 제약"],
  "uncertainties": ["확인하지 못한 항목"]
}
```

### 6.4 파싱 규칙

- HTML은 제목·본문·목록·표의 가시 텍스트만 추출한다.
- PDF와 DOCX는 기존 추출기를 재사용한다.
- `담당업무`, `직무내용`, `지원자격`, `우대사항`, `근무지`, `자기소개서`, `유의사항` 등 섹션 헤더를 기준으로 블록을 분류한다.
- 자기소개서 문항과 글자 수는 기존 질문 추출기를 확장해 공고와 초안 양쪽에서 읽는다.
- 공고와 초안의 문항이 다르면 `blocked_posting`으로 중단한다.
- 필수 필드인 기관, 직무, 업무 한 개 이상을 추출하지 못하면 `blocked_posting`으로 중단한다.
- 규칙으로 확정하지 못한 내용은 `uncertainties`에 기록한다.
- Codex가 보완하는 내용도 반드시 공고 원문 인용 위치를 함께 기록해야 한다.

## 7. 경험·직무 매칭

### 7.1 입력

- 승인 경험 원장
- 채용공고 분석 JSON
- 자기소개서 문항

### 7.2 출력

```text
03_경험직무매칭.json
03_경험직무매칭.md
```

각 문항에 대해 상위 경험 세 개와 다음 설명을 기록한다.

- 일치한 직무 업무
- 일치한 필요 역량
- 문항 유형과 경험 구조의 적합성
- 사용할 수 있는 확정 주장
- 사용하면 안 되는 미확정 주장
- 다른 문항과의 경험 중복

### 7.3 점수

점수는 순위 보조값이며 합격 확률로 해석하지 않는다.

- 근거 신뢰도: 최대 40점
- 직무 업무 일치: 최대 25점
- 필요 역량 일치: 최대 20점
- 문항 유형 적합성: 최대 15점
- 동일 경험의 두 번째 사용부터 문항당 15점 감점

근거 신뢰도는 `confirmed` 상태와 유효한 해시 근거가 모두 있을 때만 40점을 부여한다. 단순 단어 일치만으로 높은 순위를 만들지 않도록 근거 신뢰도를 최우선으로 둔다.

## 8. CLI

### 8.1 경험 원장

```powershell
career-pipeline profile build `
  --root . `
  --output .career_profile/experience_ledger.proposed.json

career-pipeline profile refresh `
  --root . `
  --profile .career_profile/experience_ledger.json

career-pipeline profile validate `
  --profile .career_profile/experience_ledger.json
```

### 8.2 공고 분석

```powershell
career-pipeline posting analyze `
  --target "기관 직무 근무지" `
  --source "<공식 URL 또는 PDF·DOCX>" `
  --official-domain "example.or.kr" `
  --output "career_runs/<run-dir>"
```

로컬 공고 파일은 `--official-domain` 대신 `--official-source`를 사용해 사용자 확인 사실을 기록한다.

### 8.3 자기소개서 실행

```powershell
career-pipeline prepare `
  --root . `
  --profile .career_profile/experience_ledger.json `
  --target "기관 직무 근무지" `
  --posting "<공식 URL 또는 PDF·DOCX>" `
  --draft "<초안.docx>"
```

기존 `--profile` 없는 명령은 호환 모드로 동작한다. 호환 모드는 현재 사실 추출·충돌 검사 방식을 유지하고 `quality_mode: legacy`를 `run.json`에 기록한다.

## 9. 실행 상태

- `blocked_profile`: 승인 원장 없음, 스키마 오류, stale 근거 사용
- `blocked_posting`: 공식성 미확인, 공고 읽기 실패, 필수 구조 누락, 문항 불일치
- `blocked_conflict`: 승인 원장과 새 후보의 사실 충돌
- `ready_for_research`: 승인 사실·공고·문항·매칭 검증 완료
- `blocked_validation`: 최종 답변 검증 실패
- `complete`: 모든 산출물과 검증 통과

기존 `blocked` 상태가 저장된 실행은 재개 시 `blocked_conflict`로 해석한다. CLI는 모든 `blocked_*` 상태에서 종료 코드 2를 반환한다.

## 10. 품질 게이트

`ready_for_research`가 되려면 다음을 모두 만족해야 한다.

- 승인 경험 원장이 존재하고 스키마 검증을 통과함
- 제출에 사용 가능한 주장이 모두 `confirmed`
- 사용 예정 근거의 파일·문단 해시가 유효함
- 공고 공식성 상태가 `verified_domain` 또는 `user_attested`
- 기관·직무·주요 업무를 추출함
- 공고와 초안의 문항·글자 수가 일치하거나 한쪽에만 문항이 존재함
- 각 문항에 근거 신뢰도 40점인 경험이 한 개 이상 있음
- 미확인 내용이 제출 주장 후보에서 제외됨

`complete`가 되려면 기존 검증에 더해 다음을 만족해야 한다.

- `draft.json`의 모든 근거가 승인 원장의 `experience_id`와 `claim`을 참조함
- 답변의 수치 문자열이 참조한 확정 주장과 일치함
- `08_면접대비팩.md`가 동일한 승인 주장만 사용함
- `07_자기소개서_검토보고서.md`에 프로필·공고·매칭 게이트 결과가 포함됨

## 11. 오류 처리

- URL 접근 실패: 오류 유형과 URL만 기록하고 로컬 공식 파일을 요청한다.
- 비공개·로그인 공고: 인증을 우회하지 않고 로컬 파일을 요청한다.
- 공식성 불명확: `unverified`로 기록하고 중단한다.
- HWP/HWPX·이미지 공고: `[변환 필요]`를 기록하고 중단한다.
- 경험 원장 JSON 오류: JSON 경로와 기대 형식을 표시한다.
- 근거 파일 없음: 해당 경험을 `stale`로 보고한다.
- 근거 해시 변경: 승인값을 보존하고 재확인을 요청한다.
- 공고·초안 문항 불일치: 양쪽 문항과 글자 수를 비교표로 출력한다.
- 부분 추출 실패: 성공한 결과를 보존하고 실패한 필수 항목 때문에 상태를 차단한다.

## 12. 개인정보와 보안

- `.career_profile/`은 `.gitignore`와 인벤토리 제외 목록에 추가한다.
- 민감 기본 제외 폴더와 `Chrome 비밀번호.csv` 정책을 유지한다.
- URL 요청에 로컬 파일 본문, 이름, 연락처, 쿠키를 포함하지 않는다.
- 원장에는 조직 실명 대신 제출용 별칭을 기본 저장한다.
- 근거 원문 전체를 중복 저장하지 않고 경로, 인덱스, 해시를 저장한다.
- 보고서에 원문 인용이 필요하면 최소 문장만 로컬 실행 폴더에 기록한다.

## 13. 테스트 전략

### 단위 테스트

- 경험 원장 스키마의 정상·누락·잘못된 상태
- 경험 ID 안정성
- confirmed·proposed·rejected·stale 사용 규칙
- 근거 파일·문단 해시 변경 감지
- HTML·PDF·DOCX 공고 로딩
- 사설 IP, 비HTTPS, 과도한 리다이렉트·응답 크기 차단
- 공고 섹션, 업무, 역량, 요건, 문항, 글자 수 추출
- 공식성 상태 판정
- 설명 가능한 매칭 점수와 중복 감점
- 기존 호환 모드

### 통합 테스트

- 임시 DOCX 경험 자료 → 후보 원장 → 승인 원장 검증
- 공식 공고 HTML 고정 fixture → 공고 분석 JSON
- 승인 원장 + 공고 + 초안 → 매칭 → `ready_for_research`
- stale 근거 → `blocked_profile`
- 미확인 공고 → `blocked_posting`
- 공고·초안 문항 불일치 → 비교 보고서
- 승인 주장과 다른 초안 수치 → `blocked_validation`

### 회귀 테스트

- 기존 전체 테스트 통과
- 현재 HUG 초안에서 문항 4개와 600자 제한 유지
- 기존 `prepare` 명령이 호환 모드로 동작
- 기존 민감 파일 제외와 실제 파일 잠금 처리 유지

실제 네트워크는 테스트에서 사용하지 않는다. 공식 공고의 고정 스냅샷을 fixture로 저장해 재현 가능한 테스트를 구성한다.

## 14. 완료 기준

- 세 개의 `profile` 하위 명령이 동작한다.
- URL·PDF·DOCX 공고 분석 명령이 구조화 JSON·Markdown을 생성한다.
- 승인되지 않은 경험과 stale 근거가 제출 흐름을 차단한다.
- 공고 공식성 미확인이 제출 흐름을 차단한다.
- 문항별 경험 매칭에 점수와 근거 설명이 포함된다.
- 기존 HUG 실행과 전체 회귀 테스트가 통과한다.
- 사용법 문서와 로컬 스킬이 V2 명령과 상태를 설명한다.
- `.career_profile/`과 사용자 민감 자료가 Git 및 외부 요청에서 제외된다.

## 15. 후속 사이클

첫 개선 사이클이 완료된 뒤 별도 설계로 다음을 추진한다.

- 문항별 다중 초안 생성
- 근거 밀도·직무 적합성·차별성·자연스러움·면접 방어력 평가
- 문항 간 경험·표현 중복 최소화
- 전문가 평가표와 합격 사례를 이용한 품질 벤치마크
- HWP/HWPX 및 OCR 지원
