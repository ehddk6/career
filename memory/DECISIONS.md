# DECISIONS — append-only ledger

Rules: only user-confirmed decisions are recorded. Nothing is edited or deleted. A changed decision gets a new entry that `supersedes D-xxx`, and the old entry receives exactly one added line: `→ superseded by D-yyy (date)`. Sequential ids are never reused.

---

## D-001 · Adopt the ballast memory structure — 2026-08-30 (user, project improvement analysis)

This project uses `memory/` as its durable brain: decisions in this ledger, unresolved items in OPEN-QUESTIONS, per-session notes in SESSION-LOG. Standing decisions are followed without relitigating; changes use the supersede protocol.

## D-002 · Use NRS v2 as the production-default self-introduction writer — 2026-08-29 (user, chat)

The default prose strategy is `nrs_v2`. The established `deep_route` writer remains a genre-gated fallback. Existing benchmark artifacts remain historical evidence and do not override production safety gates.

## D-003 · Implement the P0 operational-convergence package — 2026-08-30 (AI-proposed, user-confirmed)

The user approved the proposed P0 package with “그럼 진행해”. The base CLI now exposes the converged golden path through `workflow start/resume/status/migrate-plan`; the migration plan is read-only; and system benchmarking has explicit `off`, `report`, and `required` modes. Existing execution folders remain untouched.

## D-004 · Use the 2026 Seoul Facilities Corporation office internship as the first production run — 2026-08-30 (user, chat)

The user supplied the active 2026 Seoul Facilities Corporation youth experiential internship posting and explicitly requested the office role with “사무로 작성해, 이전 작업 다 하고”. This posting is the first end-to-end production NRS run under D-002 and D-003. No application submission or credential inference is authorized by this decision.
