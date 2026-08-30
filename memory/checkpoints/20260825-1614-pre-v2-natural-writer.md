# Checkpoint — 구조적 NRS 근거계약 수정 및 12문항 검증 — 2026-08-25 09:15

## The story so far

The benchmark initially failed because blueprint planning and final research validation used different policies, and the model was trusted to declare evidence IDs. The contract is now unified: the validated argument route determines IDs, approved experience fields map deterministically to selected claims, prose receives contribution/numeric/length limits, and each completed question is checkpointed. The 12-question PRIVATE fluent-Korean shadow benchmark is complete.

## Decided

- NRS remains shadow-only; no production promotion or external submission.
- Official-research requirement is defined once by `research_evidence.needs_research` and reused by blueprint construction and validation.
- Model-declared claim/research IDs are not trusted; route-bound IDs are attached by the program.
- Human preference labels are not inferred; the blind packet remains unlabeled.

## Waiting on the user

- Optional: review `NRS_HUMAN_PREFERENCE_blind.md` and provide one human preference label per question.

## Next first action

Open `career_runs/_audit/NRS_FLUENT_KOREAN_12Q_2026_08_24/preflight.private.json` and `NRS_HUMAN_PREFERENCE_blind.md`, then decide whether to label the blind pairs.

## Tried

- Prompt-only retries: failed because the research requirement was inconsistent between planning and validation.
- Model-selected evidence metadata: failed because valid prose could still omit or misstate reference IDs.
- Route-only experience references without a claim mapping: failed on q03 because the canonical response schema requires selected claim IDs.
- Generic contribution reminders: failed on q03 until the prompt constraint was derived from observed/unknown claim scope.
- Unbounded NRS prose: failed on KOEN q2 because candidates exceeded the character limit or introduced unapproved metrics; numeric/length contracts and one validator-aware repair attempt fixed it.
