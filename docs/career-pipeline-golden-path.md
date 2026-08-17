# Career Pipeline Golden Path

## 목적

Career Pipeline의 문제는 기능 부족보다 **강한 계층을 우회할 수 있는 실행 경로**였다. `prepare`, Research Intelligence, Integrated Writer, `finalize`, legacy 면접팩, Interview Intelligence, `audit`가 각각 존재해도 사용자가 오래된 중간 산출물을 직접 재사용하면 최신 권한·검증 계층을 건너뛸 수 있다.

Golden Path는 이를 단순 순차 호출이 아니라 **content-addressed stage contract**로 해결한다.

```text
confirmed profile + official posting
        ↓
prepare
        ↓
research coverage + execution verification
        ↓
integrated argument search
        ↓
strict legacy interview-pack gate
        ↓
finalize
        ↓
final-draft / interview-pack freshness gate
        ↓
structured-adaptive interview intelligence
        ↓
final audit
```

어떤 downstream 단계도 upstream보다 factual authority를 늘릴 수 없다.

## 핵심 차이

### 1. 파일 존재가 아니라 SHA를 본다

각 단계의 입력·출력 SHA를 `13_골든패스.json`에 기록한다. 경험원장, 공고, 회사근거, research execution, strategy prior, 최종 draft가 바뀌면 해당 입력 fingerprint가 달라지고 downstream cache를 재사용하지 않는다.

따라서 다음은 더 이상 동일한 상태가 아니다.

```text
04_공식근거.json 변경
→ 예전 draft.json 존재
→ 그대로 finalize
```

Golden Path에서는 공식근거 SHA가 바뀌면 writing fingerprint가 바뀌므로 Integrated Writer를 다시 실행해야 한다.

### 2. Research coverage만 통과해도 부족하다

`04_근거커버리지.json`이 ready여도 `04_리서치실행.json`이 `verified`가 아니면 writing으로 넘어가지 않는다. 검색 계획을 만들었거나 claim 파일이 있다는 사실 자체를 실제 조사 완료로 보지 않는다.

상태는 `waiting_for_research`가 되며, agent/human이 공식 근거 조사와 execution 기록을 완성한 뒤 같은 run을 `resume`한다.

### 3. Legacy 면접팩 검증은 항상 strict다

Golden Path는 `validate_interview_pack(..., strict=True)` 계약을 별도로 강제한다. 30/60/90초 단계화, 꼬리/압박 질문과 답변, 근거 ID 연결, final answer alignment를 통과해야 `finalize`에 들어간다.

수치 허용 범위는 두 권한 채널의 합집합이다.

- 현재 문항에서 참조한 confirmed applicant claim 수치
- 현재 문항에서 참조한 confirmed official research claim 수치

회사 공식 수치를 개인 경험 수치로 잘못 차단하지 않지만, 다른 문항/다른 claim의 수치를 자유롭게 재사용할 수도 없다.

### 4. Finalize가 답변을 바꾸면 기존 면접팩을 stale로 본다

rigorous selection 또는 postprocess가 `draft.json`과 다른 final draft를 만들었는데 `08_면접대비팩.md`의 SHA가 finalize 이전과 같으면 즉시 `waiting_for_interview_pack_refresh`로 멈춘다.

이는 `_link_final_claims_to_interview_pack()`로 ID만 새로 붙었다고 해서 예전 면접 답변 문장까지 최신이라고 간주하는 문제를 막는다.

면접팩을 final draft 기준으로 다시 작성·수정한 뒤 resume하면 strict final alignment gate를 다시 거친다.

### 5. Interview Intelligence는 final draft 이후에만 확정된다

`08_면접지능설계.json`은 final draft SHA, 확정 경험원장, 공식 research, `run.json`, cross-session aggregate weakness profile의 fingerprint에 묶인다.

이 중 하나가 바뀌거나 질문은행/설계 JSON이 임의 수정되면 plan을 재컴파일한다.

### 6. Audit가 최종 완료 조건이다

Golden Path의 `complete`는 단순히 `finalize` 성공을 뜻하지 않는다.

```text
quality_gate == pass
AND internal_validation_score >= 90
```

이어야 한다. 아니면 `review_required`로 남는다.

## 상태 머신

- `blocked_prepare`: profile/posting/matching 단계 문제
- `waiting_for_research`: coverage, conflict, execution verification 미완료
- `blocked_writing`: Integrated Writer deterministic/semantic validation 실패
- `waiting_for_interview_pack`: legacy 면접팩 없음
- `waiting_for_interview_pack_fix`: pre-final strict 면접팩 실패
- `blocked_finalize`: finalize 실패
- `waiting_for_interview_pack_refresh`: final draft와 legacy 면접팩 stale/alignment 문제
- `review_required`: audit gate 또는 90점 기준 미달
- `complete`: 모든 golden-path contract 통과

## 사용법

새 run 시작:

```powershell
python -m career_pipeline.golden_path start `
  --root . `
  --target "기관 직무" `
  --draft "지원서.docx" `
  --posting "공고.pdf" `
  --profile ".career_profile/experience_ledger.json" `
  --official-source
```

Research 단계에서 멈췄으면 공식자료를 조사·ingest한 뒤:

```powershell
python -m career_pipeline.golden_path resume `
  --run "career_runs/<run-folder>" `
  --writer-model-id "<writer>" `
  --judge-model-id "<judge-a>" `
  --judge-model-id "<judge-b>"
```

현재 상태:

```powershell
python -m career_pipeline.golden_path status --run "career_runs/<run-folder>"
```

`--no-cache`는 upstream이 같아도 derived 단계 재실행이 필요한 진단 상황에서만 사용한다.

## 왜 완전 자동화하지 않았는가

Golden Path가 research browsing이나 legacy 면접팩 작성을 조용히 발명해서 채우면 다시 factual-authority 문제가 생긴다. 따라서 현재는 외부 조사와 사람이 읽는 면접팩을 **명시적인 continuation boundary**로 둔다.

Agent가 조사할 수는 있지만 공식 근거 ingestion + coverage + execution verification을 통과해야 한다. 면접팩도 final draft와 authoritative refs에 맞게 생성/수정되어야 한다.

## 이번 단계에서 해결한 구조적 부채

1. 최신 Research Intelligence 우회
2. `04_리서치실행.json` pending인데 writer로 이동
3. 오래된 `draft.json`·interview plan 재사용
4. legacy 면접 strictness가 호출 경로에 따라 약해지는 문제
5. rigorous/postprocess 이후 stale 면접팩 문제
6. finalization 완료를 전체 파이프라인 완료로 오인하는 문제

## 다음 연구·개발 우선순위

Golden Path 이후에는 **empirical benchmark harness**가 P1이다. 기능을 더 늘리기보다 실제 과거 지원 건을 동결 corpus로 만들고 다음을 blind 비교해야 한다.

- V4/V5/V6/현재 Golden Path + 외부 강한 모델
- 사용자 pairwise preference
- deterministic factual error rate
- 회사·직무 특이성
- claim-defense 가능성
- 문항 충실도
- 면접 weak-dimension 전후 변화

실제 서류/면접 결과 metadata는 calibration과 진단에만 쓰고 합격확률 추정으로 변환하지 않는다.
