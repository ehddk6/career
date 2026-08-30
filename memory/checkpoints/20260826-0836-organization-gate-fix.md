# Checkpoint — 자연스러운 자기소개서 writer v2 회귀 실행 — 2026-08-26 08:27

## The story so far

The former 12문항 benchmark is preserved but invalid as writer-efficacy evidence because it leaked audit-style prose. v2 separates renderable proof from validation-only guardrails, uses actor-aware contribution checks, a lean outcome-first Korean self-introduction prompt, a genre gate, equal 3×2 candidate budgets, counterbalanced candidate selection, and a 9-item holdout promotion gate. The R10 live 12-question regression resumed: q01–q03 were safely reused from valid checkpoints, and q04 passed after a source-complete route fallback fixed the route-planner failure. q05 is currently generating candidates in the same direct process.

## Decided

- NRS remains shadow-only; production default cannot change automatically.
- The old `NRS_FLUENT_KOREAN_12Q_2026_08_24` 6:6 result remains preserved but is marked `invalid_for_writer_efficacy: genre_contract_failure` in new v2 metadata.
- Actual writer equality is calculated from the common prompt-template hash, backend, resolved model (null when unavailable), candidate count, retry budget, reference binding, and genre contract.
- If every planner route has a critical gap despite a source-complete blueprint, both arms use one deterministic route built only from the approved claim, action, and research references.
- No permanent Ballast rule was created; the proposed user rule remains unapproved.

## Waiting on the user

- None.

## Next first action

Keep the active direct process for `NRS_NATURAL_SELF_INTRO_V2_MEDIUM_R10_REGRESSION_12Q_2026_08_25` running; after it exits, inspect all 12 checkpoints, preflight, manifest, then run the preregistered 9-question holdout only if regression passes.

## Tried

- Earlier R1–R9 runs retained as audit history: initial launch reliability issues, then contribution-validation false positives, and finally planner-critical-gap failures were fixed without deleting their artifacts.
- Route planning for the fourth ordinal regression item failed even though its source blueprint was complete; the deterministic source-complete fallback now validates against the same authorized references and has a dedicated test.
