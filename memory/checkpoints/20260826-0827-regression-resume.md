# Checkpoint — 자연스러운 자기소개서 writer v2 구현 — 2026-08-25 16:14

## The story so far

The former 12문항 benchmark is preserved but invalid as writer-efficacy evidence because it leaked audit-style prose. v2 now separates renderable proof from validation-only guardrails, uses actor-aware contribution checks, a lean outcome-first Korean self-introduction prompt, a genre gate, equal 3×2 candidate budgets, counterbalanced candidate selection, and a 9-item holdout promotion gate. All tests pass. A live 12-item v2 regression run was started in a new audit directory, but its first Codex CLI call did not respond within the configured limit and was safely stopped before any checkpoint or blind pair was written.

## Decided

- NRS remains shadow-only; production default cannot change automatically.
- The old `NRS_FLUENT_KOREAN_12Q_2026_08_24` 6:6 result remains preserved but is marked `invalid_for_writer_efficacy: genre_contract_failure` in new v2 metadata.
- Actual writer equality is calculated from the common prompt-template hash, backend, resolved model (null when unavailable), candidate count, retry budget, reference binding, and genre contract.
- No permanent Ballast rule was created; the proposed user rule remains unapproved.

## Waiting on the user

- None for implementation. A fresh live regression/holdout needs the Codex CLI `exec` call to return normally.

## Next first action

Rerun `run_twelve_question_benchmark` against `career_runs/_audit/NRS_NATURAL_SELF_INTRO_V2_REGRESSION_12Q_2026_08_25` only after confirming the local Codex CLI can complete one `exec` call; retain the existing protocol and let the runner archive/recreate the partial q01 source snapshot.

## Tried

- Live v2 regression at 2026-08-25 16:00: the first local `codex exec` subprocess remained silent beyond its configured 5-minute model window; the exact process tree started by this task was stopped. No completed question checkpoint or blind packet was produced.
