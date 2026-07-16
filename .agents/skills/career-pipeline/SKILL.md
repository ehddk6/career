---
name: career-pipeline
description: 취업 자료에서 사용자 승인 경험 원장을 만들고 공식 채용공고를 분석한 뒤, 근거가 추적되는 자기소개서와 면접 대비팩을 생성·검증한다.
---

# Career Pipeline

## M5 local operational gate

Use `python -m career_pipeline offline-acceptance` only with explicit local
synthetic inputs: `--workspace`, timezone-aware `--at`,
`--site-valid-until`, and a lowercase test-evidence SHA-256. It may emit human
or canonical JSON output; `--output` is JSON-only. The normal result is exit
`3`, `external_only_blocked`: local synthetic acceptance passed, external
inputs are blocked, live execution is disabled, and submission was not
attempted. Use `python -m career_pipeline status --input <relative-json>` to
read a strict local readiness document or M5 envelope. Do not add or invoke
browser, network, credential, real-PII, upload, click, or submit behavior for
these commands.

V2는 승인된 경험과 공식 공고만 제출 답변의 근거로 사용한다. 자동 추출된 `proposed` 값은 사용자가 확인하기 전까지 확정하지 않는다.

## V2 실행 순서

1. `profile build`로 후보 경험 원장을 만들고 사용자가 승인한 `experience_ledger.json`만 사용한다. 승인본은 `profile validate`로 검사한다.
2. `posting analyze`로 공식 HTTPS 공고 또는 사용자가 공식 원문이라고 확인한 로컬 원문을 분석한다.
3. `prepare`로 공고·경험·문항·조사 상태를 연결한다. `ready_for_research`이면 공식 1차 출처 우선·출처 계층·확인일 기록 원칙으로 조사하고 `04_공식근거.json`, `04_리서치실행.json`을 완성한다. 특정 스킬명은 품질 조건이 아니며 실제 근거와 검증 결과로 판정한다.
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

registry 인덱스는 `.career_profile/posting_registry/`에 저장하고 원문은 별도 snapshot으로 분리한다. `new`, `exact_duplicate`, `content_duplicate`, `changed`, `unchanged`, `expired`, `closed`, `manual_review`를 구분한다. timezone이 없는 마감일과 파싱되지 않은 필수 조건은 합격으로 추정하지 않는다. `expired`, `closed`, `content_duplicate`는 제출 대상 queue에 넣지 않고 상태·이벤트로만 남긴다. 상세 계약은 `docs/posting-discovery-and-registry.md`에 기록한다.

## Phase 4 `review_required` 폼 입력

Phase 4는 `application package`, `application validate`, `application dry-run`으로 지원 패키지와 폼 매핑을 검증한다. 개인정보 값과 로컬 경로는 패키지나 로그에 복사하지 않고 불투명한 resource reference, SHA-256, 필드 키만 기록한다. 실행 시 private JSON과 첨부파일을 다시 명시해 해시를 재검증한다.

폼 어댑터는 읽기 전용 `discover → map → validate`만 수행하고 label/name/role 기반 매핑을 사용한다. CAPTCHA, MFA, 비밀번호, 새 문항, 알 수 없는 필드, 값 길이·첨부 형식 불일치는 계획 생성 전에 중단한다. DOM 변경·파일 업로드·제출 메서드는 제공하지 않으며 `review_required`, queue 승인, dry-run 성공은 실제 입력·제출 승인이나 자동지원 허용을 뜻하지 않는다.

Phase 5 실행 계약은 `application review`의 명시적 승인과 `application authorize`의 exact-origin·모드별 단일 사용 권한을 요구한다. 권한은 package 전체 SHA, 공고·profile·최종 manifest·첨부 manifest·form schema SHA, 승인 주체, 만료 시각과 계약 버전에 묶인다. 변경·만료·취소·재사용·CAPTCHA·MFA·중복 지원은 실행 드라이버 호출 전에 중단한다. Phase 5에는 실제 사이트 Playwright mutation adapter나 live 실행 CLI가 포함되지 않는다.

Phase 6 `jobkorea_jrs_fixture`는 비식별 로컬 fixture와 좁은 mock 인터페이스에서만 fill-only 계약을 검증한다. `live_enabled=false`이며 navigation, click, press, evaluate, attachment, submit, network API를 노출하지 않는다. 실제 JRS 지원서 origin과 기업별 DOM이 확인되기 전에는 live adapter로 취급하지 않는다.

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

`finalize --selection-mode rigorous`는 동결 자료의 `data_package_id`, 버전과 SHA-256을
고정한 뒤 4개 전략(`FACT_FIRST`, `QUESTION_FIRST`, `EXPERIENCE_DIVERSITY`,
`JOB_COMPANY_FIT`)으로 후보를 생성한다. 후보 전략은 익명 심사 입력에서 제거한다. 세 심사 결과는
동일 배점으로 집계하며, 결정론적 오류는 즉시 차단하고 의미적 우려는 `REVIEW_REQUIRED`로
보관한 뒤 원자료 대조로 확정한다. 심사위원 2명 이상이 동일하게 지목한 이식 요소만 최소 합성에
사용하고, 최종 합성본은 기존 1위와 X/Y 전체 버전 비교를 다시 거친다.

`--quality-profile max_quality`는 여기에 `NATURAL_VOICE`, `INTERVIEW_DEFENSE` 후보와
`INTERVIEW_COACH` 심사를 추가한다. 문항별 하위 요구와 적정 글자 범위는 V2 `prepare`가 만든
`05_문항전략.json`에서 읽으며 특정 기관·문항 수·글자 수를 하드코딩하지 않는다. 생성·심사·합성·최종
비교 모델은 `CAREER_MODEL_GENERATION`, `CAREER_MODEL_JUDGE`,
`CAREER_MODEL_SYNTHESIS`, `CAREER_MODEL_COMPARISON`으로 독립 설정하고, 없으면
`CAREER_MODEL_SOL`을 호환 fallback으로 사용한다. 실제 모델명에 `sol` 문자열을 요구하지 않는다.
최대 호출 예산은 31회이며 6개 후보 각각의 결정론적 실패 복구 2회, 항상 수행하는 최종 품질 정제,
결정론적 문체 위험 복구 7회와 X/Y 재비교를 포함한다. 이 모드에서 짧은 문항은 상한의 85%, 긴 문항은 80%를 권장 최소 범위로
검증한다.

통합 계약 신규 초기화는 schema v2를 사용한다. 회사조사는 시장·대체재·최근 실행 결과·전략 성공조건·
직무 영향·조사 종료기준·면접 활용을 추가 검증한다. 면접 답변 카드는 `brief`·`standard`·`detailed`
말하기 버전, 내용/전달 분리 평가, 모르는 질문의 사실 경계를 포함한다. 기존 schema v1 계약은 계속 읽는다.
`contracts build`는 동결된 공고·공식 근거·확정 경험·현재 초안에서 검증 가능한 회사조사와 면접 계약을
자동 조립한다. 기존 파일은 덮어쓰지 않으며, 확인되지 않은 재무·문화·면접 형식은 명시적 미확인 상태로
남긴다. rigorous 최종 선택 뒤에는 제출 claim 참조를 면접 패킷에 다시 연결하고 계약을 재검증한다.
공식 URL을 다시 확인한 경우에는 원문을 복사하지 않고 URL·확인일·상태만 담은 감사 JSON을 만든 뒤
`contracts refresh-sources --run <run> --audit <audit.json>`을 사용한다. 기존 source manifest에 없는 URL,
`VERIFIED`가 아닌 상태, 잘못된 날짜는 차단하며 claim 내용은 이 명령으로 변경하지 않는다.

문체 진단은 AI 작성 여부를 판정하지 않고 `style_risk_score`, `style_reasons`만 기록한다. 검사는 종결·문장 시작·상투 표현·문장 길이 분산·피동·명사화·추상적 다짐·문항 간 중복을 설명 가능한 규칙으로 기록한다. `should_rewrite=false`인 낮은 위험은 감사 감점이 아니라 설명용 경고로 취급한다.

주요 명령은 다음과 같다.

```powershell
python -m career_pipeline profile build --root . --output ".career_profile/experience_ledger.proposed.json"
python -m career_pipeline profile validate --profile ".career_profile/experience_ledger.json"
python -m career_pipeline posting analyze --target "기관 직무" --source "공고.pdf" --official-source --output "career_runs/posting"
python -m career_pipeline prepare --root . --target "기관 직무" --draft "draft.docx" --posting "공고.pdf" --profile ".career_profile/experience_ledger.json" --official-source
python -m career_pipeline finalize --run "career_runs/<run-dir>"
```

`blocked_profile`, `blocked_posting`, `blocked_conflict`, `blocked_validation` 상태는 해당 근거와 `03_충돌검사.md`를 먼저 해결한다. 공고 조사에는 공식 출처를 우선한다.

최종 준비에는 `03_경험직무매칭.json`, `experience_refs`, `04_공식근거.json`, `draft.json`, `08_면접대비팩.md`가 필요하다. 각 `experience_refs`는 답변 본문에서 실제로 사용된 claim이어야 한다. 단, 경제·사회 이슈처럼 외부 사실 분석만 요구하는 문항에는 무관한 경험을 강제로 연결하지 않고 검증된 `research_refs`만 사용한다. `04_공식근거.json`의 각 주장에는 문항 목적과 맞는 `claim_type`과 문항·면접 활용처인 `application_use`를 기록한다. 면접팩에는 1분 자기소개·각 문항별 30/60/90초 답변·꼬리질문과 답변·압박질문과 답변·문항별 근거를 포함한다.

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

Patina는 기본 finalize에서 실행하지 않는다. 기존 호환 옵션과 파일은 삭제하지 않으며, 명시적인 `--legacy-patina`에서만 legacy 후보 생성·점수·선택 흐름을 실행한다. `--no-patina`, `--patina-*` 옵션은 호환성을 위해 유지한다. Patina 보고서가 없는 것은 기본 감사의 실패나 감점 사유가 아니다. 기본 모드 재실행은 이전 legacy 상태를 현재 실행 상태에서 제거한다.

## 최종 산출물과 감사

최종화가 완료되면 다음을 생성한다.

- `draft_final.json`: 최종 답변의 canonical JSON
- `06_자기소개서.md`, `06_자기소개서.docx`
- `12_최종산출물.json`: 위 파일의 상대 경로·SHA-256·선택 원본·생성 시각·후처리 여부·모델 tier/ID·검증 결과
- `07_글자수검증.json`: 문항별 답변 SHA-256·계산 모드·하드 제한·목표 구간·headroom
- `run.json.final_artifact`: 동일 manifest 정보

`audit`는 파일 존재 순서로 `draft_humanized.json`, `draft_copyedited.json`, `draft.json`을 선택하지 않는다. `run.json.final_artifact` 또는 `12_최종산출물.json`에 기록된 최종 파일과 SHA-256만 검사하며, 이전 실행의 중간 파일은 무시한다.

감사 점수는 합격 확률이 아니라 내부 규칙 점수다. 출력에는 `internal_validation_score`, `quality_gate`, `human_review_recommended`를 기록하고 기존 `score`와 `recommendation`도 호환성을 위해 유지한다.

## 개인정보·근거 경계

`.career_profile/`, `Chrome 비밀번호.csv`, `학교성적/`, `자격증/`, `경력증명서/`는 기본 제외한다. 개인정보와 취업 자료 본문을 URL·검색어·쿠키·외부 폼으로 전송하지 않는다. V2 답변은 승인된 claim과 공식 근거만 사용한다. 문체 표본과 유튜브 프레임 자료는 전략 자료일 뿐 사실 근거가 아니다.

## 실제 지원 품질 판정

과거 자기소개서의 `legacy_internal_score`나 감사 점수는 합격 가능성 점수가 아니다. 포트폴리오의 `quality_readiness`는 다음 6개 게이트를 각각 기록한다.

1. 확정 경험 원장
2. 7일 이내 다시 확인한 활성 공식 공고
3. `eligible`로 확정된 지원 자격
4. 완료된 V2 공식 회사·직무 조사
5. 최종 manifest와 감사를 통과한 선택 자기소개서
6. 최종 자기소개서 claim과 연결되어 감사를 통과한 면접팩

여섯 게이트가 모두 통과한 경우에만 `ready`다. 활성 공고는 유효하지만 나머지 검토가 남으면 `review_required`, 공고가 없거나 오래됐으면 `not_ready`다. 차단 사유는 `blocker_codes`와 설명으로 남긴다. 유튜브 작성전략은 `writing_guidance.freshness`로 원본 대비 최신성을 확인하되 계속 전략 자료로만 사용한다.

## Phase 6 platform boundary

공고 discovery platform과 application family를 `career_pipeline/platform_catalog.py`에서 분리한다. Applyin 호스트 suffix는 분류에만 사용하며 실행에는 exact HTTPS origin을 요구한다. `jobkorea_jrs_fixture`와 `saramin_applyin_fixture`는 합성 로컬 HTML 및 mock page 전용이다. `live_enabled=false` 상태에서는 실제 사이트 접속, 로그인, 업로드, 클릭, 제출을 시도하지 않는다. schema drift, CAPTCHA, MFA, script, iframe, 미등록 플랫폼 또는 권한 불일치는 `manual_review` 또는 fail-closed로 처리한다.

Phase 6.5 `site-intake`는 사용자가 제공한 비식별 로컬 HTML을 읽기 전용으로 검사한다. 실제 URL을 요청하지 않으며 fixture 원문·경로·민감값을 결과에 저장하지 않는다. exact origin, fixture SHA, canonical schema SHA와 구조적 validation code만 기록한다. 준비된 계약도 항상 `mutation_enabled=false`, `live_enabled=false`이며 실제 입력 권한을 발급하지 않는다.

### 실사이트 실행 예외 계약

fixture와 일반 `site-intake` 계약은 계속 읽기 전용이다. 별도로 실제 구조를 확인한 exact-tenant 어댑터만 `career_pipeline.live_application`을 사용할 수 있다. 패키지가 `eligible` 및 `ready_for_review`이고, 현재 폼의 exact HTTPS origin·path·action·구조 해시가 모두 일치하며, 사용자가 실행 직전에 확인한 단기 HMAC 권한이 있을 때만 동작한다. 입력과 제출은 서로 다른 권한을 사용한다. 첨부 업로드와 최종 제출은 각각 실행 직전 확인이 필요하다. CAPTCHA, MFA, 새 필드, cross-origin iframe이 나타나면 중단한다. 제출 의도는 클릭 전에 저장하며 결과가 불확실하면 `submission_unverified`로 기록하고 자동 재시도하지 않는다. 첫 실사이트 어댑터 `saramin_applyin_kodit_live`는 확인된 신용보증기금 origin에만 적용하며 Saramin Applyin 전체에 적용하지 않는다.

## 결과 및 검증

관련 단위 테스트와 전체 `pytest`를 실행한다. 실제 Codex 또는 Patina를 부르는 테스트는 fake runner를 사용한다. 원문·수치·부정·인과·문장 수 변경, 변경률 경계, batch fan-out 금지, stale 중간 파일, manifest SHA 불일치, 원자적 저장, 모델 tier, 호출 예산을 검증한다.

일반 사이트 브라우저 자동화는 허용하지 않는다. 실사이트 입력·첨부·제출은 위 exact-tenant 계약과 사용자 실행 직전 확인을 모두 충족할 때만 허용한다. 후속 범위와 중단 조건은 `docs/superpowers/plans/2026-07-11-application-automation.md`를 따른다.
