---
name: career-pipeline
description: 취업 자료에서 사용자 승인 경험 원장을 만들고 공식 채용공고를 분석한 뒤, 근거가 추적되는 자기소개서와 면접 대비팩을 생성·검증한다. 다른 기업 적용, 자소서 검토, 공고 분석, 면접 준비 요청에 사용한다.
---

# Career Pipeline

V2는 승인된 경험과 공식 공고만 제출 답변의 근거로 사용한다. 자동 추출된 `proposed` 값은 사용자가 확인하기 전까지 절대 확정하지 않는다.

## 필수 입력

- 지원 기관·기업과 직무
- 공식 HTTPS 공고 URL 또는 사용자가 공식 원문이라고 확인한 PDF/DOCX
- 작성 중인 자기소개서 DOCX
- 취업 자료 작업공간

## V2 실행 순서

1. 최초 1회 후보 경험 원장을 만든다.

```powershell
python -m career_pipeline profile build --root "<workspace>" --output "<workspace>/.career_profile/experience_ledger.proposed.json"
```

후보를 사용자에게 보여주고 경험·수치·근거를 확인받는다. 사용자 승인 없이 `proposed`를 `confirmed`로 바꾸지 않는다. 승인본은 `.career_profile/experience_ledger.json`으로 저장하고 검증한다.

```powershell
python -m career_pipeline profile validate --profile "<workspace>/.career_profile/experience_ledger.json"
```

기존 승인 원장이 있으면 먼저 갱신 검사를 실행한다.

```powershell
python -m career_pipeline profile refresh --root "<workspace>" --profile "<workspace>/.career_profile/experience_ledger.json"
```

2. 공식 공고를 독립 분석한다. 로컬 파일을 사용하면서 사용자가 공식 원문이라고 확인한 경우에만 `--official-source`를 붙인다. 임의로 공식 파일이라고 표시하지 않는다.

```powershell
python -m career_pipeline posting analyze --target "<target>" --source "<posting.pdf>" --official-source --output "<analysis-dir>"
```

공식 URL은 `--official-domain`을 사용한다.

```powershell
python -m career_pipeline posting analyze --target "<target>" --source "https://jobs.example.com/posting" --official-domain "jobs.example.com" --output "<analysis-dir>"
```

3. V2 준비를 실행한다.

```powershell
python -m career_pipeline prepare --root "<workspace>" --target "<target>" --draft "<draft>" --posting "<posting>" --profile "<workspace>/.career_profile/experience_ledger.json" --official-source
```

URL이면 `--official-source` 대신 `--official-domain`을 사용한다. 상태별로 다음처럼 처리한다.

- `blocked_profile`: `profile_review.md`와 이슈를 사용자에게 확인받는다.
- `blocked_posting`: 공식성, 필수 항목, 공고·초안 문항 차이를 해결한다.
- `blocked_conflict`: 동일 근거의 확정 값 충돌을 해결한다.
- `ready_for_research`: 반드시 아래의 Evidence-first 기업조사를 실행한 뒤 진행한다.

4. `00_채용공고분석.*`, `02_확정경험원장.json`, `03_경험직무매칭.*`을 읽는다. `03_경험직무매칭`의 추천 이유와 사용 금지 주장을 지킨다.

준비 단계에서 `자료조사/자소서_유튜브_프레임분석_*` 폴더가 있으면 최신 폴더를 자동으로 찾아 `05_작성가이드_유튜브프레임.md`와 `run.json`의 `writing_guidance`에 연결한다. 이 자료는 문항 해석, 소재 배치, 첫 문장 방향, 강조 순서, 금지 표현 점검을 위한 작성 전략으로만 사용한다. 공식 근거, 경험 사실 근거, `research_refs`, `experience_refs`에는 넣지 않는다.

5. `ready_for_research` 상태에서는 반드시 `evidence-first-research` 스킬을 사용한다. 해당 스킬을 찾거나 읽을 수 없으면 일반 검색으로 대체하지 말고 작업을 중단해 사용자에게 알린다. 스킬의 SIFT·출처 계층·검증/잠정 구분 규칙을 지키고, 기업의 공식 홈페이지·공식 채용공고·공시 등 공식 출처와 1차 출처를 우선한다.

조사가 끝나면 `04_기업직무조사.md`, `04_공식근거.json`, `04_리서치실행.json`, `05_문항전략.md`를 작성한다. `04_리서치실행.json`은 다음 필드를 모두 기록한다.

```json
{
  "policy": "evidence-first",
  "skill_name": "evidence-first-research",
  "mode": "ordinary-online",
  "searched_at": "2026-06-22T10:30:00+09:00",
  "status": "verified",
  "queries": ["기관명 사업명 공식"],
  "source_families": ["official"],
  "verified_claim_ids": ["claim-id"]
}
```

`status`가 `verified`가 아니거나 공식 근거 ID가 실행 기록에 포함되지 않으면 최종 완료를 막는다. [output contract](references/output-contract.md)에 따라 `draft.json`의 각 답변에 `experience_refs`, `research_refs`, `evidence_paths`를 기록한다.

6. `08_면접대비팩.md`를 작성한다. 승인 원장에 없는 수치·기간·역할을 추가하지 않는다.

7. 최종 검증을 실행한다. CLI는 기본적으로 im-ai-copyeditor 교열을 먼저 실행하고, Patina 점수를 측정한 뒤 필요한 문항만 Patina 후보를 생성한다.

```powershell
python -m career_pipeline finalize --run "<run-dir>"
```

`blocked_validation`이면 `07_자기소개서_검토보고서.md`와 `run.json`의 `validation_issues`만 고친 뒤 다시 실행한다. `complete`일 때만 완료로 보고한다.

8. 제출 전 최종 품질 감사를 실행한다. 95점 이상을 제출권장, 90점 미만을 보완 필요로 본다.

```powershell
python -m career_pipeline audit --run "<run-dir>"
```

## im-ai-copyeditor + Patina 적용 판정

- 순서는 `사실 검증 → im-ai-copyeditor 통합 교열 → Patina 점수 → 30점 초과 문항만 Patina 재작성 → 최종 검증`이다.
- im-ai-copyeditor는 전체 문항을 한 번의 배치 호출로 처리한다. 문항별 문장 수·수치·고유명사·인용·부정·인과·변경률을 다시 검증한다.
- 변경률 50% 초과, 문장 수 변경 또는 의미 앵커 변경 시 해당 문항은 교열 전 원문으로 복귀한다.
- `copyeditor_attempted`와 `copyeditor_applied`를 구분하며, 결과는 `09_copyeditor_report.json`에 기록한다.

- Patina는 AI 특유의 반복·균일한 문장 구조를 줄이는 후처리 도구다. 사실과 문항 적합성을 대신 만들지 않는다.
- `patina doctor`가 통과해야 실행 가능하다. 백엔드 오류·길이 초과·수치 변경 시 원문으로 안전하게 되돌린다.
- `patina_attempted=true`는 호출했다는 뜻이고 `patina_applied=true`는 Patina 후보가 실제 최종안으로 선택됐다는 뜻이다. 둘을 같은 의미로 보고하지 않는다.
- 글자 수 제한 문항은 Patina가 문장을 늘릴 여지를 고려해 최초 초안을 상한의 88~92%로 작성한다. 실행 보고서의 `headroom_target_met`로 준수 여부를 확인한다. Patina 결과가 상한을 넘으면 의미를 바꾸지 않는 등록된 축약만 적용하고, 여전히 넘으면 원문으로 복귀한다.
- 최종 후보는 기본 30점 이하를 목표로 `patina --score --exit-on 30` 게이트를 통과해야 한다. 점수 호출이 실패하거나 모든 후보가 기준을 넘으면 검증되지 않은 Patina 문장을 채택하지 않는다.
- 사용자가 직접 쓴 1~3개 단락을 `.career_profile/voice_sample.txt`에 저장하면 자동으로 `--voice-sample`을 적용한다. 사용자 원문이 아닌 AI 초안이나 탈락 자소서를 음성 표본으로 추정해 만들지 않는다.
- 수치 외에도 인용문, 대문자 고유명사, 부정·인과 표지, 기관·직무 핵심어를 의미 앵커로 검사한다. 변경되면 원문으로 복귀한다.
- 기본 백엔드는 인증된 `codex-cli`이며 재시도 1회를 사용한다. 추가 인증 백엔드가 있으면 `--patina-backend "codex-cli,openai-http"`처럼 명시적 폴백 체인을 지정한다.
- `09_patina_report.json`에서 문항별 `selected_variant`와 `patina_applied`를 확인한다. 모든 문항이 `original`이면 Patina가 최종 문체에 적용된 것이 아니다.

```powershell
python -m career_pipeline finalize --run "<run-dir>" `
  --patina-voice-sample ".career_profile/voice_sample.txt" `
  --patina-ai-threshold 30 `
  --patina-max-retries 1 `
  --patina-backend "codex-cli"
```

긴급하게 한국어 교열만 끄려면 `--no-copyeditor`, Patina만 끄려면 `--no-patina`를 사용한다. 기본 실행에서는 둘 다 켠다.

## Legacy 모드

`--profile` 없이 `python -m career_pipeline prepare`를 실행하면 기존 `02_사실원장.json`과 `03_충돌검사.md` 흐름을 유지한다. 자동 추출값에 의존하므로 V2보다 낮은 품질이며, 새 기업 적용에는 V2를 우선한다.

## 개인정보와 URL 보안

- `.career_profile/`, `Chrome 비밀번호.csv`, `학교성적/`, `자격증/`, `경력증명서/`는 기본 제외한다.
- 취업 자료 본문과 개인정보를 URL, 검색어, 쿠키, 외부 폼으로 전송하지 않는다.
- URL은 HTTPS만 허용하며 localhost·사설 IP·링크 로컬 주소를 거부한다.
- 리다이렉트는 최대 5회, 응답은 20MB로 제한한다.

## 완료 확인

- `00_채용공고분석.json`, `00_채용공고분석.md`
- `02_확정경험원장.json`
- `03_경험직무매칭.json`, `03_경험직무매칭.md`
- `04_기업직무조사.md`, `05_문항전략.md`
- `04_공식근거.json`, `04_리서치실행.json`
- `06_자기소개서.md`, `06_자기소개서.docx`
- `07_자기소개서_검토보고서.md`, `08_면접대비팩.md`
- `09_copyeditor_report.json`, `09_patina_report.json`
- `11_최종품질감사.json`, `11_최종품질감사.md`
- `run.json`
