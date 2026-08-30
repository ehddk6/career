# memory/ — career-nrs-shadow-pilot brain

Purpose: this folder is the durable memory for career-nrs-shadow-pilot. Conversations forget; this folder does not. What is recorded here survives topic changes, session resets, and context compaction.

## File map

| File | What | Write rule |
|---|---|---|
| `DECISIONS.md` | Confirmed decisions | Append-only. Supersede protocol — never edit past entries |
| `OPEN-QUESTIONS.md` | Unresolved items awaiting a decision, and readings in force the user has not confirmed | Two tables. Close each row with a link to the resolving decision, or drop it |
| `SESSION-LOG.md` | What happened, per working session | Append, dated |
| `PRODUCT-TRUTH.md` | What the product actually does | Evidence + date only. Three sections: implemented / not / excluded |
| `CHECKPOINT.md` | Current thirty-second return point | Replace only after archiving the outgoing version |
| `goal/` | Active goal skeletons and completion checks | Update by diff; preserve superseded cuts |
| `checkpoints/` | Archived return points | Append new checkpoints; do not rewrite history |

## Operating principles

1. **Record in-session.** Decisions and important facts are written the moment they appear, not at the end. Zero loss.
2. **User-confirmed vs AI-proposed are always distinguished.** A proposal the user has not confirmed is not a decision. It is registered in OPEN-QUESTIONS.md as `assumed` when work relies on it.
3. **Claims carry labels:** confirmed / observed / assumed / hearsay / unknown.
4. **External product claims require truth-file evidence.**
5. **Unresolved things get registered**, not remembered.
