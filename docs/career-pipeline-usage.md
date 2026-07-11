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

CLI 최종화는 먼저 im-ai-copyeditor로 전체 문항을 한 번에 한국어 교열한다. 문항별 문장 수·수치·인용문·고유명사·부정·인과·기관 핵심어와 변경률을 다시 검사하며, 문장 수가 달라지거나 변경률이 50%를 넘으면 해당 문항만 원문으로 복귀한다.

교열본이 Patina 30점 이하이면 추가 재작성 없이 채택한다. 30점을 넘은 문항만 원문과 Patina 변형 두 개로 세 후보를 만들고, 사실성·기관 특화도·행동과 성과·직무 연결·차별성·자연스러움을 평가해 선발한다. 최초 초안은 상한의 88~92%를 목표로 하며 `headroom_target_met`에 기록한다. Patina가 상한을 넘으면 의미 보존형 축약을 적용하고, 그래도 넘으면 교열본으로 복귀한다.

선택 후보는 기본적으로 `patina --score --exit-on 30` 검사를 통과해야 한다. 점수 호출이 실패하거나 모든 후보가 30점을 넘으면 Patina 결과를 채택하지 않는다. `run.json`의 `patina_attempted`는 호출 여부, `patina_applied`는 실제 최종안 채택 여부다. 모든 문항의 `selected_variant`가 `original`이면 Patina는 최종 문체에 적용되지 않은 것이다. 긴급하게 Patina를 생략해야 할 때만 `--no-patina`를 붙인다.

Patina 호출 제한시간은 후보당 기본 180초다. 느린 환경에서는 `--patina-timeout-ms 240000`처럼 조정할 수 있다.

사용자가 직접 쓴 1~3개 단락을 `.career_profile/voice_sample.txt`에 두면 자동으로 문체 표본을 사용한다. 다른 파일은 자동으로 사람 글이라고 추정하지 않는다. 추가 인증 백엔드가 있을 때는 쉼표로 폴백 체인을 지정할 수 있다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline finalize `
  --run "career_runs/<run-dir>" `
  --patina-voice-sample ".career_profile/voice_sample.txt" `
  --patina-ai-threshold 30 `
  --patina-max-retries 1 `
  --patina-backend "codex-cli,openai-http"
```

한국어 교열 호출 제한시간은 기본 180초다. 필요하면 `--copyeditor-timeout-ms 240000`으로 조정한다. `--no-copyeditor`는 한국어 교열만, `--no-patina`는 Patina 단계만 끈다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline finalize --run "career_runs/<run-dir>" --no-patina
```

`blocked_validation`이면 `07_자기소개서_검토보고서.md`의 해당 항목만 고친다.

### 글자 수와 문항별 품질 게이트

공고의 `공백 포함`·`공백 제외` 표기를 문항마다 저장하고 같은 방식으로 상한과 80% 최소 충족률을 계산한다. 검토보고서와 DOCX에도 계산 방식과 현재 글자 수를 함께 표시한다. Patina 후보가 더 높은 문체 점수를 받아도 최소 길이에 미달하거나 상한을 넘으면 선택하지 않는다.

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
- `09_patina_report.json`: 문항별 인간화 적용·원문 복귀 사유
- `09_copyeditor_report.json`: 문항별 한국어 교열·적용 규칙·변경률·복귀 사유
- `09_초안후보평가.json`: 문항당 세 후보와 구성 점수·선택 결과
- `10_품질점수.json`: 최종 선택 답변의 100점 품질표
- `11_최종품질감사.json`, `11_최종품질감사.md`: 자기소개서·기업조사·면접팩·문체 안전성 종합 감사
- `draft_humanized.json`: Patina 검증을 통과한 최종 답변 원본
- `draft_copyedited.json`: im-ai-copyeditor 검증을 통과한 교열본
- `run.json`

기존 자기소개서와 개인 원본 파일은 수정하지 않는다. `.career_profile/`과 `career_runs/`는 Git 추적 및 기본 자료 인벤토리에서 제외된다.

## 충돌 해결과 재개

legacy 실행의 `blocked_conflict`는 `03_충돌검사.md`를 확인하고 `fact_overrides.yaml`에 승인 값을 기록한 뒤 `--resume`으로 재개한다.
