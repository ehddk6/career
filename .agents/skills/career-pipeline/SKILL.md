---
name: career-pipeline
description: 취업 자료에서 사용자 승인 경험 원장을 만들고 공식 채용공고를 분석한 뒤, 근거가 추적되는 자기소개서와 면접 대비팩을 생성·검증한다.
---

# Career Pipeline

V2는 승인된 경험과 공식 공고만 제출 답변의 근거로 사용한다. 자동 추출된 `proposed` 값은 사용자가 확인하기 전까지 확정하지 않는다.

## V2 실행 순서

1. `profile build`로 후보 경험 원장을 만들고 사용자가 승인한 `experience_ledger.json`만 사용한다. 승인본은 `profile validate`로 검사한다.
2. `posting analyze`로 공식 HTTPS 공고 또는 사용자가 공식 원문이라고 확인한 로컬 원문을 분석한다.
3. `prepare`로 공고·경험·문항·조사 상태를 연결한다. `ready_for_research`이면 `evidence-first-research` 규칙으로 공식 조사와 `04_공식근거.json`, `04_리서치실행.json`을 완성한다.
4. `finalize`로 결정론적 사실·형식·품질 검사를 먼저 실행하고, 통과한 초안에만 조건부 단일 배치 교열을 적용한다.
5. `audit`로 최종 manifest와 SHA-256, 승인 경험·공식 조사·문항·문체 진단을 감사한다.

## Phase 2 초기 자격 판정

Phase 2의 첫 단계는 브라우저 자동화가 아닌 구조화된 지원자·공고·자격 판정이다.

1. `profile applicant`로 확인된 `experience_ledger.json`의 `confirmed` 경험만 `ApplicantProfile`로 투영한다.
2. `posting record`로 공식 공고 분석을 `PostingRecord`와 본문 SHA-256으로 고정한다.
3. `eligibility evaluate`로 학력·경력·자격증·지역의 명시적 조건을 판정한다.

결과 상태는 `eligible`, `eligible_with_gaps`, `manual_review`, `ineligible` 네 가지뿐이다. 정보가 없거나 자연어 해석이 필요한 조건, 졸업예정·자격증 유효기간·지역 제한이 불명확한 조건은 합격으로 추정하지 않고 `manual_review`로 보낸다. 우대 조건 미충족은 `eligible_with_gaps`이며 필수 조건 미충족만 `ineligible`이다.

Phase 2 JSON 출력은 기본적으로 기존 파일을 덮어쓰지 않는다. 의도적으로 교체할 때만 `--force`를 사용하며, 자격 판정에는 `--evaluation-date`를 지정해 기준일을 고정할 수 있다. 결정 결과의 `reasons`는 `code`, `field`, `message`를 가진 구조화된 객체 배열이다.

## Phase 3 공식 공고 탐색과 검토 queue

Phase 3 초기 구현은 `discovery source-add`로 등록한 공식 allowlist 출처에서만 URL을 발견하고 `PostingRegistry`에 영속 저장한다. `manual_url`, 공식 목록 페이지, RSS/Atom, sitemap, 명시적 공식 JSON API를 지원하며 무제한 크롤링·로그인·브라우저 자동화·원서 제출은 지원하지 않는다.

```text
DiscoverySource
→ DiscoveryRun
→ 안전한 공고 URL 발견·다운로드
→ PostingRecord + raw/normalized SHA-256
→ registry 중복·변경·마감 판정
→ EligibilityDecision
→ review queue
```

registry 인덱스는 `.career_profile/posting_registry/`에 저장하고 원문은 별도 snapshot으로 분리한다. `new`, `exact_duplicate`, `content_duplicate`, `changed`, `unchanged`, `expired`, `closed`, `manual_review`를 구분한다. timezone이 없는 마감일, 파싱되지 않은 필수 조건, 변경·중복 공고는 합격으로 추정하지 않고 검토 queue로 보낸다. 상세 계약은 `docs/posting-discovery-and-registry.md`에 기록한다.

## 최종화 정책

기본 흐름은 다음과 같다.

```text
draft.json
→ Python 사실·형식·품질 검사
→ style diagnostics
→ postprocess=auto이면 수정 대상 문항만 한 번의 배치 교열
→ Python 재검증
→ 안전한 결과 선택
→ draft_final.json + 12_최종산출물.json
```

`--postprocess`는 `auto`가 기본이며 `always`, `never`를 지원한다. `auto`에서 모든 문항이 문체 진단을 통과하면 모델 호출은 정확히 0회다. 수정 대상이 있으면 대상 문항 전체를 한 번에 호출하며 문항별 재시도는 하지 않는다. 배치 실패, 사실·수치·문장 수·글자 수 검증 실패, 최대 변경률 초과 시 해당 문항 또는 전체 후보를 원문으로 복귀한다.

문체 진단은 AI 작성 여부를 판정하지 않고 `style_risk_score`, `style_reasons`만 기록한다. 검사는 종결·문장 시작·상투 표현·문장 길이 분산·피동·명사화·추상적 다짐·문항 간 중복을 설명 가능한 규칙으로 기록한다.

주요 명령은 다음과 같다.

```powershell
python -m career_pipeline profile build --root . --output ".career_profile/experience_ledger.proposed.json"
python -m career_pipeline profile validate --profile ".career_profile/experience_ledger.json"
python -m career_pipeline posting analyze --target "기관 직무" --source "공고.pdf" --official-source --output "career_runs/posting"
python -m career_pipeline prepare --root . --target "기관 직무" --draft "draft.docx" --posting "공고.pdf" --profile ".career_profile/experience_ledger.json" --official-source
python -m career_pipeline finalize --run "career_runs/<run-dir>"
```

`blocked_profile`, `blocked_posting`, `blocked_conflict`, `blocked_validation` 상태는 해당 근거와 `03_충돌검사.md`를 먼저 해결한다. 공고 조사에는 공식 출처를 우선한다.

최종 준비에는 `03_경험직무매칭.json`, `experience_refs`, `04_공식근거.json`, `draft.json`, `08_면접대비팩.md`가 필요하다. 면접팩에는 1분 자기소개·30/60/90초 답변·꼬리질문·압박질문·근거를 포함한다.

변경률 정책은 `career_pipeline/rewrite_validation.py`에서 관리한다.

- 목표·경고 기준: 12%
- 최대 허용: 20%
- 12% 초과는 경고만 기록한다.
- 20% 초과는 원문으로 복귀한다.

교열 프롬프트는 외부 스킬에 의존하지 않고 코드에 직접 작성한다. 교정 대상은 맞춤법·문법·번역투·불필요한 피동·과도한 명사화·상투 표현·반복·장황함이다. 숫자·날짜·기간·역할·성과·기관명·직무명·고유명사·인용문·긍정/부정·인과관계·문항/문단/문장 순서·새 사실은 변경하지 않는다.

## 모델 정책과 호출 한도

앱 내부 tier는 `luna`, `terra`, `sol`이다. 실제 모델 ID는 다음 환경변수에서만 읽으며 값이 없으면 `null`로 기록하고 추측하지 않는다.

- `CAREER_MODEL_LUNA`: 맞춤법·문법·작은 표현 수정
- `CAREER_MODEL_TERRA`: 문장 구조·번역투·반복·직무 연결 개선
- `CAREER_MODEL_SOL`: 논리적으로 어려운 문항 또는 사용자가 명시한 선택

자동 선택은 기본적으로 Luna이며 구조적 반복 위험이 있으면 Terra를 선택한다. Sol은 자동 기본 tier가 아니다. `run.json`과 `12_최종산출물.json`에는 논리 tier와 실제 모델 ID를 함께 기록한다.

지원 옵션:

```powershell
python -m career_pipeline finalize --run "career_runs/<run-dir>" `
  --postprocess auto `
  --postprocess-tier luna `
  --postprocess-timeout-ms 180000 `
  --max-model-calls 1 `
  --max-stage-seconds 180
```

`max_postprocess_calls` 기본값은 1이다. 단계명·호출 수·tier·실제 모델 ID·시작/종료 시각·소요 시간·상태를 `run.json.model_calls`에 남긴다. 토큰 정보는 CLI가 확실히 제공하지 않으면 기록하지 않는다.

## Patina legacy 모드

Patina는 기본 finalize에서 실행하지 않는다. 기존 호환 옵션과 파일은 삭제하지 않으며, 명시적인 `--legacy-patina`에서만 legacy 후보 생성·점수·선택 흐름을 실행한다. `--no-patina`, `--patina-*` 옵션은 호환성을 위해 유지한다. Patina 보고서가 없는 것은 기본 감사의 실패나 감점 사유가 아니다.

## 최종 산출물과 감사

최종화가 완료되면 다음을 생성한다.

- `draft_final.json`: 최종 답변의 canonical JSON
- `06_자기소개서.md`, `06_자기소개서.docx`
- `12_최종산출물.json`: 위 파일의 상대 경로·SHA-256·선택 원본·생성 시각·후처리 여부·모델 tier/ID·검증 결과
- `run.json.final_artifact`: 동일 manifest 정보

`audit`는 파일 존재 순서로 `draft_humanized.json`, `draft_copyedited.json`, `draft.json`을 선택하지 않는다. `run.json.final_artifact` 또는 `12_최종산출물.json`에 기록된 최종 파일과 SHA-256만 검사하며, 이전 실행의 중간 파일은 무시한다.

감사 점수는 합격 확률이 아니라 내부 규칙 점수다. 출력에는 `internal_validation_score`, `quality_gate`, `human_review_recommended`를 기록하고 기존 `score`와 `recommendation`도 호환성을 위해 유지한다.

## 개인정보·근거 경계

`.career_profile/`, `Chrome 비밀번호.csv`, `학교성적/`, `자격증/`, `경력증명서/`는 기본 제외한다. 개인정보와 취업 자료 본문을 URL·검색어·쿠키·외부 폼으로 전송하지 않는다. V2 답변은 승인된 claim과 공식 근거만 사용한다. 문체 표본과 유튜브 프레임 자료는 전략 자료일 뿐 사실 근거가 아니다.

## 결과 및 검증

관련 단위 테스트와 전체 `pytest`를 실행한다. 실제 Codex 또는 Patina를 부르는 테스트는 fake runner를 사용한다. 원문·수치·부정·인과·문장 수 변경, 변경률 경계, batch fan-out 금지, stale 중간 파일, manifest SHA 불일치, 원자적 저장, 모델 tier, 호출 예산을 검증한다.

공식 공고 탐색의 네트워크 자동화와 브라우저 폼 입력·자동 제출은 아직 구현하지 않는다. 후속 범위와 중단 조건은 `docs/superpowers/plans/2026-07-11-application-automation.md`를 따른다.
