# Evidence-to-Signal Compiler — Contract Convergence

## 문제 재정의
Career Pipeline의 목표는 문장을 많이 생성하는 것이 아니라 **확정 근거에서 직무에 유효한 신호를 선택하고, 그 신호를 서류·면접·검증 전 구간에서 과장 없이 보존하는 것**이다.

상위 불변조건은 네 가지다.
1. **Authority Conservation** — downstream은 upstream보다 사실 권한을 늘릴 수 없다.
2. **Semantic Entailment** — 최종 주장의 사실 의미는 question-scoped authority가 지지해야 한다.
3. **Evaluation Invariance** — 위치·순서·rubric 표현 변경만으로 평가가 뒤집히면 승자를 확정하지 않는다.
4. **Portfolio Coverage** — 문항별 점수 합이 아니라 전체 지원서의 핵심 직무신호 coverage를 최적화한다.

## Contract Convergence
`career_pipeline.authority_contract`가 applicant/research authority와 question-scoped metric을 한 번 정의한다. 기본 V2는 `career_pipeline.golden_path_converged`다. 레거시 `orchestrator.py`와 `audit.py`는 대규모 재작성하지 않고 기본 Golden Path 서비스 경계에서 같은 contract를 주입받는다. 직접 legacy CLI 실행은 compatibility path다.

Research Intelligence의 원문 구조는 보존하면서 `research_contract`가 `확인된 사실 / 해석 / 확인 필요 / 문항·면접 활용 맵`을 canonical appendix로 만든다. 새 사실이나 날짜를 만들지 않고 `04_공식근거.json`, coverage, conflict만 다시 렌더링한다.

## Assertion Compiler
최종 prose를 source sentence와 주변 문맥을 보존한 assertion으로 다시 컴파일한다. 각 assertion은 `source_sentence`, `context_before/after`, `atomic_text`, `assertion_type`, `supported_by`, `metric_values`, `contradicts`, `causal_scope`, `question_scope`, `authority_status`를 가진다. Unsupported metric은 hard defect다. 인과 표현이 있으나 confirmed contribution boundary가 `caused`가 아니면 `needs_review`로 남긴다. 무조건 가장 작은 claim으로 쪼개지 않고 verifier가 판단 가능한 단위와 원문맥을 함께 보존한다.

## Evidence Portfolio Optimizer
문장을 쓰기 전에 Evidence × Job-Signal Matrix를 만든다.

```text
maximize signal coverage + defensibility + target relevance + distinctiveness
minimize unsupported risk + causal-overclaim risk + evidence reuse
```

`05_근거포트폴리오.json`은 authority ID와 signal label만 writer의 strategy context에 전달하며 `factual_authority_granted=false`다.

## Reliable Judge
Single-shot 점수를 최종 진실로 쓰지 않는다. A/B와 B/A position swap을 먼저 실행하고 불안정하면 rubric 순서·reviewer role perturbation을 추가한다. TIE/ABSTAIN을 허용하고 position flip, margin, abstention을 계산한다. 여러 pair의 comparison graph에 cycle이 있으면 `evaluation_uncertain`을 반환한다.

## System Benchmark
모델 benchmark보다 시스템 불변성을 측정한다. Unsupported metric insertion과 ownership escalation은 차단되어야 하고, whitespace/order 같은 benign perturbation은 판정이 유지되어야 한다. `career-pipeline-benchmark --run <run>`은 finalized run에 대해 `14_시스템불변성벤치마크.json`을 만든다.

## 기본 실행
```powershell
python -m career_pipeline.golden_path_converged start --root . --target "기관 직무" --draft "지원서.docx" --posting "공고.pdf" --profile ".career_profile/experience_ledger.json" --official-source
python -m career_pipeline.golden_path_converged resume --run "career_runs\<run>"
```

## 연구 원칙
Evaluator-aware claim decomposition 연구의 시사점대로 claim atomicity는 작을수록 좋은 것이 아니라 verifier가 정확히 판정할 수 있는 단위로 조절한다. Context-preserving decomposition처럼 source context를 함께 남긴다. LLM judge의 위치 편향과 prompt/rubric perturbation 불안정성 때문에 position swap과 explicit uncertainty를 사용한다. 이 연구 근거는 설계 원칙일 뿐 채용 합격 확률이나 factual authority를 제공하지 않는다.
