# Career Pipeline V2 사용법

Career Pipeline V2는 개인 경험을 먼저 승인 원장으로 고정하고, 공식 채용공고를 구조화한 뒤 문항별 근거가 추적되는 자기소개서와 면접팩을 만든다.

## 초기 준비

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 자연어 호출

```text
이 공고와 현재 자소서를 기준으로 승인 경험 원장부터 최종 검증까지 진행해줘.
```

## 1. 경험 원장 만들기

최초 후보 생성:

```powershell
.\.venv\Scripts\python.exe -m career_pipeline profile build `
  --root . `
  --output ".career_profile/experience_ledger.proposed.json"
```

후보의 경험·수치·근거를 직접 확인한 뒤 `experience_ledger.json`으로 승인한다. 프로그램은 proposed 값을 자동 승인하지 않는다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline profile validate `
  --profile ".career_profile/experience_ledger.json"
```

자료가 바뀌었을 때:

```powershell
.\.venv\Scripts\python.exe -m career_pipeline profile refresh `
  --root . `
  --profile ".career_profile/experience_ledger.json"
```

`profile_review.md`의 재확인 항목이 있으면 승인 원장을 덮어쓰지 말고 사용자 확인부터 받는다.

## Phase 2 초기 자격 판정

Phase 2는 승인된 경험 원장과 공식 공고 분석을 구조화해 자격 판정만 수행합니다. 개인정보 본문은 프로필에 복사하지 않고 원장 경로만 참조합니다.

확인된 경험만 지원자 프로필로 투영합니다.

```powershell
python -m career_pipeline profile applicant `
  --ledger ".career_profile/experience_ledger.json" `
  --profile-id "applicant-local" `
  --output ".career_profile/applicant_profile.json"
```

공고 분석 결과를 `PostingRecord`로 고정합니다. 본문 SHA-256과 공식 출처 상태가 함께 저장됩니다.

```powershell
python -m career_pipeline posting record `
  --target "기관 직무" `
  --source "공고.pdf" `
  --official-source `
  --output "career_runs/posting-record.json"
```

학력·경력·자격증·지역 조건은 명시적으로 구조화된 규칙만 자동 판정합니다.

```powershell
python -m career_pipeline eligibility evaluate `
  --profile ".career_profile/applicant_profile.json" `
  --posting "career_runs/posting-record.json" `
  --output "career_runs/eligibility-decision.json" `
  --evaluation-date "2026-07-11"
```

결과는 `eligible`, `eligible_with_gaps`, `manual_review`, `ineligible` 중 하나이며 `reasons`에는 코드·필드·사용자용 설명을 함께 기록합니다. 정보 부족, 졸업예정, 자격증 유효기간, 지역 제한의 해석 필요, 자연어 조건은 `manual_review`로 보냅니다. 출력 파일은 기본적으로 기존 파일을 덮어쓰지 않으며 의도적으로 교체할 때만 `--force`를 사용합니다. 이 단계에는 브라우저 자동화와 실제 지원서 제출이 없습니다.

실행 디렉터리 내부에만 출력하려면 세 Phase 2 명령에 `--run-dir "career_runs/<run-dir>"`를 추가합니다. 디렉터리 밖 경로와 출력 심볼릭 링크는 거부됩니다.

## Phase 3 공식 공고 탐색과 검토 queue

공식 allowlist 출처를 등록한 뒤 공고를 발견하고 registry와 사용자 검토 queue에 저장합니다. 이번 단계에는 브라우저 자동화·로그인·원서 입력·제출이 없습니다.

```powershell
python -m career_pipeline discovery source-add `
  --root . `
  --organization "공식기관" `
  --type official_list_page `
  --url "https://official.example/jobs" `
  --allow-domain "official.example"

python -m career_pipeline discovery source-list --root .
python -m career_pipeline discovery run `
  --root . `
  --source-id "source-..." `
  --evaluation-time "2026-07-11T18:00:00+09:00" `
  --applicant-profile ".career_profile/applicant_profile.json"

python -m career_pipeline registry list --root .
python -m career_pipeline queue list --root . --status pending
python -m career_pipeline queue decide --root . --queue-id "queue-..." --decision approved
```

registry는 `.career_profile/posting_registry/registry.json`에 인덱스를, `snapshots/`에 원문을, `events.jsonl`에 최소 상태 이벤트를 저장합니다. 공식 출처가 아닌 링크, 다른 도메인 redirect, 로그인·개인정보 페이지, 마감일 또는 timezone이 불명확한 공고는 자동 확정하지 않고 `manual_review` queue로 보냅니다. queue 승인은 실제 원서 제출 승인이 아닙니다.

## Phase 4 `review_required` 지원 패키지와 폼 dry-run

Phase 4 기본 모드는 항상 `review_required`입니다. 개인정보 값은 지원 패키지에 복사하지 않고 `.career_profile`의 별도 private JSON에 보관합니다. 패키지에는 로컬 경로 대신 불투명한 resource reference, SHA-256, 필드 키만 기록합니다. validate와 dry-run 실행 시 private JSON과 첨부파일 경로를 다시 명시해 원본 해시를 검증합니다.

```json
{
  "schema_version": 1,
  "fields": {
    "full_name": "사용자 확인 값",
    "email": "사용자 확인 값",
    "phone": "사용자 확인 값"
  }
}
```

```powershell
python -m career_pipeline application package `
  --root . `
  --run "career_runs/<run-dir>" `
  --profile ".career_profile/applicant_profile.json" `
  --posting "career_runs/posting-record.json" `
  --decision "career_runs/eligibility-decision.json" `
  --private-data ".career_profile/private.json" `
  --attachment "resume=.career_profile/resume.pdf" `
  --output ".career_profile/application_packages/package.json"

python -m career_pipeline application validate `
  --root . `
  --package ".career_profile/application_packages/package.json" `
  --private-data ".career_profile/private.json" `
  --attachment "resume=.career_profile/resume.pdf"

python -m career_pipeline application dry-run `
  --root . `
  --package ".career_profile/application_packages/package.json" `
  --private-data ".career_profile/private.json" `
  --attachment "resume=.career_profile/resume.pdf" `
  --html "tests/fixtures/application_form.html" `
  --output ".career_profile/form-result.json" `
  --evaluation-time "2026-07-12T09:00:00+09:00"
```

`dry-run`은 label/name/role 기반으로 필드를 읽기 전용 매핑하고 로컬 입력 자료와의 호환성만 검증합니다. DOM 입력·클릭·파일 업로드·제출은 수행하지 않습니다. CAPTCHA, MFA, 비밀번호, 새 문항, 알 수 없는 필드, 글자 수 제한, 첨부파일 형식 불일치가 발견되면 계획 생성을 중단합니다. `queue approved`나 `review_required`는 실제 제출 승인 또는 자동지원 허용을 뜻하지 않습니다.

```powershell
$env:CAREER_EXECUTION_SIGNING_KEY = "32바이트 이상의 로컬 비밀 값"

python -m career_pipeline application review `
  --package ".career_profile/application_packages/package.json" `
  --dry-run-result ".career_profile/form-result.json" `
  --decision approved `
  --output ".career_profile/application-review.json" `
  --at "2026-07-12T12:00:00+09:00" `
  --approver-id "local-user"

python -m career_pipeline application authorize `
  --package ".career_profile/application_packages/package.json" `
  --dry-run-result ".career_profile/form-result.json" `
  --review ".career_profile/application-review.json" `
  --allowed-origin "https://jobs.example.or.kr" `
  --mode fill_only `
  --output ".career_profile/execution-authorization.json" `
  --at "2026-07-12T12:01:00+09:00" `
  --expires-at "2026-07-12T13:01:00+09:00" `
  --approver-id "local-user"
```

`fill_only` 권한은 제출 권한으로 승격할 수 없습니다. Phase 5는 승인·만료·취소·단일 사용·durable intent 계약까지만 제공하며 실제 사이트 입력과 제출 CLI는 제공하지 않습니다. 상세 계약은 `docs/application-execution.md`를 따릅니다.

`CAREER_EXECUTION_SIGNING_KEY`는 승인·권한 artifact의 HMAC 검증에만 사용하며 파일, 로그, CLI 출력에 기록하지 않습니다. 값이 없거나 32바이트보다 짧으면 review와 authorize는 실패합니다.

Phase 6의 첫 adapter는 실제 사이트가 아닌 `jobkorea_jrs_fixture` 비식별 계약입니다.

```powershell
python -m career_pipeline application adapter show jobkorea_jrs_fixture
python -m career_pipeline application adapter validate jobkorea_jrs_fixture
python -m career_pipeline application fill-fixture `
  --adapter jobkorea_jrs_fixture `
  --package ".career_profile/application_packages/package.json" `
  --dry-run-result ".career_profile/form-result.json" `
  --authorization ".career_profile/execution-authorization.json" `
  --values ".career_profile/jrs-fixture-values.json" `
  --ledger ".career_profile/execution-ledger.json" `
  --output ".career_profile/jrs-fixture-result.json" `
  --at "2026-07-12T12:05:00+09:00"
python -m career_pipeline application fixture-result --result ".career_profile/jrs-fixture-result.json"
```

이 명령은 저장소 fixture와 메모리 mock만 사용한다. live URL, navigation, attachment, click, submit 옵션은 제공하지 않는다.

## 2. 공식 공고 분석

공식 PDF/DOCX를 사용자가 확인한 경우:

```powershell
.\.venv\Scripts\python.exe -m career_pipeline posting analyze `
  --target "기관 직무" `
  --source "채용공고.pdf" `
  --official-source `
  --output "career_runs/posting-check"
```

공식 URL인 경우:

```powershell
.\.venv\Scripts\python.exe -m career_pipeline posting analyze `
  --target "기관 직무" `
  --source "https://recruit.example.com/posting" `
  --official-domain "recruit.example.com" `
  --output "career_runs/posting-check"
```

URL은 HTTPS만 허용한다. localhost·사설 IP·링크 로컬 주소는 차단하고, 리다이렉트 5회와 응답 20MB를 한도로 둔다.

## 유튜브 프레임 작성전략 자동 연결

`prepare`를 실행하면 `자료조사/자소서_유튜브_프레임분석_*` 중 최신 폴더를 자동으로 찾아 `05_작성가이드_유튜브프레임.md`를 만든다. 이 자료는 자기소개서 문항 해석, 소재 배치, 첫 문장 방향, 강조 순서, 금지 표현 점검에만 사용한다.

중요: 유튜브 프레임 캡처와 OCR 원문은 공식 근거 또는 본인 경험 사실 근거가 아니다. 지원기관의 사실과 수치는 공식 공고·공식 조사 자료에서만 가져오고, 본인 경험의 사실은 확정 경험원장과 사용자 원자료에서만 가져온다. `run.json`에는 이 구분을 `writing_guidance.use_policy = strategy_only_not_factual_evidence`로 남긴다.

## 3. V2 준비와 최종화

```powershell
.\.venv\Scripts\python.exe -m career_pipeline prepare `
  --root . `
  --target "기관 직무" `
  --draft "자기소개서.docx" `
  --posting "채용공고.pdf" `
  --official-source `
  --research-domain "official.example.or.kr" `
  --profile ".career_profile/experience_ledger.json"
```

`run.json` 상태를 확인한다.

- `blocked_profile`: 승인 원장 또는 stale 근거 수정
- `blocked_posting`: 공식성·필수 항목·문항 불일치 수정
- `blocked_conflict`: 확정 값 충돌 수정
- `ready_for_research`: `evidence-first-research` 스킬로 공식 조사 진행

문항별 선택 근거는 `03_경험직무매칭.json`과 `03_경험직무매칭.md`에 있다. 기업조사는 `evidence-first-research`의 SIFT·출처 계층 규칙을 따르며, 공식 1차 출처부터 확인한다. `04_공식근거.json`에는 기관·사업 주장, 공식 URL, 확인일, 근거 문장을 기록한다. `draft.json`은 각 답변에 `experience_refs`, `claim_fields`, `evidence_paths`를 넣고 기관·사업 문항에는 `research_refs`도 넣어야 한다.

```json
[
  {
    "claim_id": "business-1",
    "claim": "답변에 사용할 공식 사업 주장",
    "source_url": "https://official.example.or.kr/page",
    "checked_at": "2026-06-21",
    "evidence_excerpt": "주장을 직접 뒷받침하는 짧은 근거 문장"
  }
]
```

조사 직후 `04_리서치실행.json`의 `status`를 `verified`로 바꾸고 실제 검색 질의·시간·출처 계층·검증한 근거 ID를 기록한다. 이 파일이 `pending`이거나 근거 ID가 빠지면 최종화를 차단한다.

```json
{
  "policy": "evidence-first",
  "skill_name": "evidence-first-research",
  "mode": "ordinary-online",
  "searched_at": "2026-06-22T10:30:00+09:00",
  "status": "verified",
  "queries": ["기관명 사업명 공식"],
  "source_families": ["official"],
  "verified_claim_ids": ["business-1"]
}
```

```powershell
.\.venv\Scripts\python.exe -m career_pipeline finalize --run "career_runs/<run-dir>"
```

제출 전에는 최종 품질 감사를 실행한다. 95점 이상은 `제출권장`, 90점 미만은 보완 필요로 본다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline audit --run "career_runs/<run-dir>"
```

CLI 최종화는 결정론적 검사를 먼저 실행한다. 기본 `--postprocess auto`에서는 문체 진단에서 위험이 확인된 문항만 한 번의 배치 교열로 처리하며, 자연스러운 초안은 모델 호출 0회다. `always`는 모든 문항을 한 번에 처리하고 `never`는 모델 후처리를 생략한다. 배치 실패 시 문항별 재시도 없이 원문으로 복귀한다.

교열 결과는 문장 수·숫자·단위·날짜·기간·인용문·약어·기관명·직무명·부정·인과·글자 수를 재검증한다. 변경률은 12% 초과를 경고로 기록하고 20% 초과는 원문으로 복귀한다. `09_style_diagnostics.json`에는 `style_risk_score`와 `style_reasons`를 기록하며, 이는 AI 작성 여부 점수가 아니다.

모델 tier는 `luna`, `terra`, `sol`이며 실제 ID는 `CAREER_MODEL_LUNA`, `CAREER_MODEL_TERRA`, `CAREER_MODEL_SOL` 환경변수에서 주입한다. 설정되지 않은 ID는 추측하지 않고 `null`로 기록한다. 호출 한도와 단계 시간은 `--max-model-calls`, `--max-postprocess-calls`, `--postprocess-timeout-ms`, `--max-stage-seconds`로 제어한다.

Patina는 기본 실행에서 호출하지 않는다. 기존 흐름이 필요한 경우에만 `--legacy-patina`를 명시한다. `--no-patina`, `--patina-*` 옵션은 호환성을 위해 유지한다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline finalize `
  --run "career_runs/<run-dir>" `
  --legacy-patina `
  --patina-voice-sample ".career_profile/voice_sample.txt" `
  --patina-ai-threshold 30 `
  --patina-max-retries 1 `
  --patina-backend "codex-cli,openai-http"
```

교열 호출 제한시간은 기본 180초다. 필요하면 `--postprocess-timeout-ms 240000`으로 조정한다. `--no-copyeditor`는 `postprocess=never` 호환 옵션이며, `--legacy-patina`를 붙이지 않으면 Patina는 실행되지 않는다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline finalize --run "career_runs/<run-dir>" --postprocess auto
```

`blocked_validation`이면 `07_자기소개서_검토보고서.md`의 해당 항목만 고친다.

### 글자 수와 문항별 품질 게이트

공고의 `공백 포함`·`공백 제외` 표기를 문항마다 저장하고 같은 방식으로 상한과 80% 최소 충족률을 계산한다. 검토보고서와 DOCX에도 계산 방식과 현재 글자 수를 함께 표시한다. 모델 교열 결과가 최소 길이에 미달하거나 상한을 넘으면 선택하지 않는다.

문항 유형에 따라 다음 요소가 빠지면 최종화를 막는다.

- 성장: 출발점 또는 부족한 점, 개선 행동, 결과, 농협·직무 활용
- 의사결정: 검토 정보, 판단 기준, 선택지와 최종 결정
- 신뢰: 맡은 역할, 동료를 대하는 태도·행동, 신뢰를 확인할 결과
- 가치: 가치가 형성된 경험, 지원 조직에서 수행할 역할
- 복합사업: 교육지원·경제·금융 세 사업의 연결 구조와 본인의 기여

네 문항 이상에서는 같은 경험 ID를 여러 답변에 재사용하면 `reused_experience`로 차단한다. 기관별 문항이 요구하는 역량을 분산해 답변 전체가 하나의 포트폴리오가 되도록 하기 위한 규칙이다.

## 다른 기업 적용 예시

회사와 공고만 바뀌어도 개인 경험 원장은 재사용할 수 있다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline profile refresh --root . --profile ".career_profile/experience_ledger.json"
.\.venv\Scripts\python.exe -m career_pipeline posting analyze --target "한국주택금융공사 행정" --source "HF_채용공고.pdf" --official-source --output "career_runs/hf-posting"
.\.venv\Scripts\python.exe -m career_pipeline prepare --root . --target "한국주택금융공사 행정" --draft "HF_자기소개서.docx" --posting "HF_채용공고.pdf" --official-source --profile ".career_profile/experience_ledger.json"
```

기업마다 공고 분석과 경험 매칭은 새로 생성한다. 이전 기업의 조사 문구나 기관명을 복사하지 않는다.

## Legacy 모드

`--profile` 없이 prepare를 실행하는 legacy 모드는 기존 `02_사실원장.json`, `03_충돌검사.md`, `fact_overrides.yaml`, 재개 흐름을 유지한다. 자동 추출값을 직접 사용하므로 V2보다 낮은 품질이다. 기존 실행 호환용으로만 사용하고 새 기업에는 V2를 권장한다.

## 결과물

- `00_채용공고분석.json`, `00_채용공고분석.md`: 공식성·업무·문항
- `01_자료목록.md`: 사용·제외·실패 파일
- `02_확정경험원장.json`: 제출에 사용할 수 있는 승인 경험
- `03_경험직무매칭.json`, `03_경험직무매칭.md`: 문항별 후보·점수 구성·금지 주장
- `04_기업직무조사.md`, `05_문항전략.md`
- `05_작성가이드_유튜브프레임.md`: 유튜브 프레임 기반 작성전략 참고자료. 공식 근거로 사용하지 않는다.
- `04_공식근거.json`: 공식 주장·URL·확인일·근거 문장과 `research_refs` 원장
- `04_리서치실행.json`: evidence-first 실행 정책·질의·시간·출처 계층·검증 근거 ID
- `06_자기소개서.md`, `06_자기소개서.docx`
- `07_자기소개서_검토보고서.md`, `08_면접대비팩.md`
- `09_style_diagnostics.json`: 문항별 설명 가능한 문체 위험과 후처리 대상
- `09_copyeditor_report.json`: 단일 배치 교열·적용 규칙·변경률·복귀 사유
- `09_patina_report.json`, `09_초안후보평가.json`: `--legacy-patina`에서만 생성되는 호환 산출물
- `10_품질점수.json`: 최종 선택 답변의 100점 품질표
- `11_최종품질감사.json`, `11_최종품질감사.md`: 자기소개서·기업조사·면접팩·문체 안전성 종합 감사
- `draft_final.json`: 감사가 참조하는 canonical 최종 답변
- `draft_copyedited.json`: 실제 교열이 적용된 경우의 호환 산출물
- `12_최종산출물.json`: 최종 파일 경로·SHA-256·선택 원본·검증·모델 메타데이터
- `run.json`

기존 자기소개서와 개인 원본 파일은 수정하지 않는다. `.career_profile/`과 `career_runs/`는 Git 추적 및 기본 자료 인벤토리에서 제외된다.

## 충돌 해결과 재개

legacy 실행의 `blocked_conflict`는 `03_충돌검사.md`를 확인하고 `fact_overrides.yaml`에 승인 값을 기록한 뒤 `--resume`으로 재개한다.
