# PR #4 Shadow Validation Summary (2026-08-18)

- 검증 대상 HEAD: `4b1ee34fabf3a36e65c613d65978945e2a24a0e3` (`codex/behavior-ir-correctness-repair`)
- 작업 성격: **SHADOW-only 검증**. production writer selection, Reliable Judge, Golden Path pass/block, interview scoring, Evidence Portfolio selection, Multi-Claim semantics는 변경하지 않는다.
- 개인정보 경계: `career_runs/`는 `.gitignore` 대상이다. 실제 atomic claim·회사명·개인 수치·source excerpt는 이 문서나 Git에 기록하지 않는다. 37-run 감사 수치는 집계값만 기재한다.

## 최종 판정

```
PR4_SHADOW_MERGE_READY + OBJECT_SEMANTICS_PRODUCTION_HOLD
```

- shadow 코드(parser-first object semantics + 3-way audit)는 merge 가능.
- semantic DIRECT를 production으로 승격하지 않는다. 특히 `방식 / 역할 / 항목 / 문의 / 질문`을 단독 DIRECT alias로 취급하는 정책은 유지하지 않는다.

## 1. Repository validation (실제 checkout)

- `python -m compileall -q career_pipeline`: 통과
- targeted pytest (10개 파일): **84 passed / 0 failed / 0 skipped**
- full pytest: **818 passed / 0 failed / 7 skipped**

## 2. Frozen benchmark (expectation 약화 없음)

- combined 26 case (기존 18 + behavior-IR correctness 8): **26/26 passed, failed 0, expectation_pass_rate 1.0**
- 모든 frozen rate 1.0: direct_precision_guard / disagreement_detection / taxonomy_boundary / benign_relation_invariance / v2_direct_precision / v2_direct_recall / contribution_safety / source_bound_atom_safety / object_order_invariance / counter_semantics
- `15_구성개념불일치벤치마크.json`을 실제 실행 결과(26-case combined)로 재생성했다.
- 참고: raw legacy runner(어댑터 없음)는 18 case 중 1건(`context-action-unbound-001`)이 source-bound fail-closed 계약에 따라 실패한다. 이는 correctness 수리(3e05f0d)의 의도된 동작이며, benchmark 모듈이 원본 fixture hash 검증 후 EvidenceRef overlay를 적용하는 문서화된 어댑터 경로가 정식 기준이다. production extraction은 이 어댑터를 사용하지 않는다.

## 3. PRIVATE 37-run 3-way audit (집계값)

| 지표 | current v2 | parser-v2 exact | parser-v2 semantic |
|---|---|---|---|
| direct | 0 | 0 | 25 |
| partial | 1051 | 758 | 726 |
| inferred | 19 | 193 | 200 |
| none | 1581 | 2707 | 2707 |
| direct_run_count | 0 | 0 | 5 |
| A (lexical_high_construct_weak) | 218 | 149 | 149 |
| B (construct_direct_not_selected) | 0 | 0 | 0 |

Parser diagnostics: evaluated_evidence 632 / parser_span 444 / parser_recovered_no_current_atom_claim 17 / parser_suppressed_current_atom 392 / object_span_change 532

Recovery: recovered_exact_direct 0 / recovered_semantic_direct 25 (전부 `bounded_semantic_only`) / authority_blocked_semantic_candidate 7 (fail-closed 정상 차단)

Safety (recovered 후보 기준): context_only 0 / unconfirmed 0 (confirmed claim만 평가) / research_as_applicant 0 (verified authority gate) / taxonomy_escalation 0 (전부 target_explicit) / actor_scope 0 / contribution_scope 0 / false_direct 0 (audit 게이트 기준, 최종은 human review)

## 4. 중복 제거 관찰 (검토 시 중요)

- recovered DIRECT 25건은 서로 다른 5개 run에 걸쳐 동일 5개 고유 evidence가 반복된 구조다 (중복 제거 시 5건, 단일 documentation 영역에 집중).
- 따라서 "25건 direct 회복"을 독립 25건으로 해석하지 않는다. 모델 adjudication 기준 유효율은 약 4/5 수준이며, 사람 gold label 전까지 production 승격 근거로 사용하지 않는다.

## 5. 다음 단계

1. semantic matcher는 production 승격 금지 유지.
2. 다음 버전은 verb-aware documentation semantics로 좁힌다: `작성/기록/메모` 계열은 폭넓게, `정리`는 materialized artifact marker(일정표/배치안/계획표/체크리스트/초안/문서/표/내역)가 있을 때만 DIRECT, `정리 + 방식/역할/항목`만 있으면 PARTIAL 유지.
3. 해당 frozen case 고정 후 동일 37-run 재감사로 unique precision을 90% 이상 목표로 검증.
4. Multi-Claim Proof는 계속 보류 (B=0 유지, recovered DIRECT가 단일 영역 집중 → selection lens/Blueprint 승격 근거 없음).
