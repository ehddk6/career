# Integrated Strategy Prior — 기존 파이프라인 보존형 연결 계층

`deep_writer`는 확정 경험원장·공식 조사·Narrative Compiler를 계속 사용한다. 문제는 V5 논증 검색 직전에 기존 `05_문항전략`, 유튜브 분석, 과거 지원 이력의 전략 신호가 사라진다는 점이었다. 이 계층은 새 작성기를 다시 만드는 대신 그 연결을 복구한다.

```text
확정 경험원장 ─┐
경험-문항 매칭 ├─> Narrative Compiler ─> Deep Writer ─> validator/finalize
공식 조사 ─────┘             ↑
                            Strategy Prior
                    ┌─────────┼──────────┐
                 기존 문항전략  유튜브 분석  과거 지원 이력/결과
```

## 권한

사실 권한은 기존과 동일하다.

- 지원자 경험·역할·성과·수치·인과: `02_확정경험원장.json`
- 경험 배치: `03_경험직무매칭.json` + Narrative Compiler
- 기관·사업·채용 사실: `00_채용공고분석.json`, `04_공식근거.json`

다음은 전략 전용이다.

- `05_문항전략.md/json`
- `05_작성가이드_유튜브프레임.md`
- `자료조사/자소서_유튜브_프레임분석_*`
- 외부 `자소서 유튜브 정보` 폴더의 freshness
- 과거 run의 experience/claim 사용 빈도
- 검증된 전형 결과 메타데이터
- surface/semantic preference profile

전략 전용 자료는 새로운 사실·동기·수치·성과·인과관계를 만들 수 없다.

## 과거 자기소개서

과거 `draft.json`/`draft_final.json`의 본문은 모델에게 전달하지 않는다. `experience_refs`와 `claim_ids` 사용 빈도만 읽어 반복 가능성을 점검한다. `.career_profile/application_outcomes.json`이 있으면 검증된 강점/약점 신호만 사용할 수 있으며 합격확률로 변환하지 않는다.

## 유튜브

현재 run에 연결된 imported frame analysis를 우선하고 `01_자소서_작성원칙_요약.md`, `02_문항유형별_전략.md`, `03_기관별_적용노트.md`를 읽는다. `04_프레임_근거색인.csv`에서는 지원기관 직접 일치 → company tag → 기관군 순서로 전략을 고른다. 외부 `~/OneDrive/문서/자소서 유튜브 정보` 또는 `CAREER_YOUTUBE_GUIDANCE_ROOT`는 최신성 확인에 사용한다. 영상 문구를 복사하거나 회사 사실로 승격하지 않는다.

## 실행

```powershell
python -m career_pipeline.integrated_writer `
  --run "career_runs/<run>" `
  --writer-model-id "<writer>" `
  --judge-model-id "<judge-a>" `
  --judge-model-id "<judge-b>" `
  --routes 3 `
  --prose-realisations 2

python -m career_pipeline finalize --run "career_runs/<run>"
```

추가 산출물은 `05_통합전략선행정보.json`, `05_통합전략선행정보.md`, `05_통합논증검색_검증.json`이다. 호환성을 위해 `05_논증검색_검증.json`에도 통합 보고서를 기록한다.
