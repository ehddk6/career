# Narrative Compiler V4: Preference-Optimized Self-Introduction Writing

## Why V4 exists

The pipeline already had strong evidence, character-count, source, and interview-defensibility gates. The remaining failure mode was prose quality: a factually correct answer could still sound like an internal procedure manual, repeat `확인 → 대조 → 기록 → 보고`, or begin with company brochure language.

V4 treats this as an inference-time search and preference-learning problem rather than a bigger-prompt problem.

## Architecture

```text
posting + questions + confirmed experience ledger + official research
        ↓
1. Narrative Blueprint IR
   semantic intent / evidence boundaries / global experience allocation / beat budgets
        ↓
2. Multi-Realization Search (default N=3)
   judgment-centered / scene-rhythm / restrained-natural
        ↓
3. Per-candidate deterministic fact gate
   invalid claims, numbers, contribution scope, source linkage → reject before style judging
        ↓
4. Blind Preference Tournament
   anonymous candidate IDs only
   ranking pass A: normal order
   ranking pass B: reversed order
   aggregate ranks + preference-distance tie break
        ↓
5. Portfolio Critic
   question fidelity / causal logic / company-brochure risk / manual-like job plan /
   cross-answer redundancy / artificial voice
        ↓
6. Targeted Repair
   MATERIAL/HARD spans only
        ↓
7. Final deterministic validation
        ↓
   draft.json
```

The preference judge never sees generation strategy names or model names. Balanced forward/reverse rankings reduce position sensitivity. Factual validity is not delegated to the preference judge; Python validators remain authoritative.

## Prompt design change

V3 used a long wall of negative constraints. V4 sends context first and the actual writing task last, with a short positive prose contract:

- answer the question in the first two sentences;
- make scene, judgment, action, and result flow as an argument;
- center the applicant's criterion rather than company description;
- keep contribution scope exact while writing like a person rather than a regulation;
- vary sentence rhythm naturally;
- use only IDs visibly reflected in the answer.

The model still receives all safety boundaries, but the surface-writing objective is no longer buried under dozens of prohibitions.

## Revealed-preference memory

`career_pipeline.writing_preference` learns from pairwise choices such as:

- Claude answer preferred over GPT answer;
- Gemini answer preferred over GPT answer;
- user's edited answer preferred over the original model answer.

Only aggregate structural metrics are persisted. The preferred/rejected source text itself is **not** saved to the profile, so facts from another model's answer cannot become evidence.

Default profile location:

```text
.career_profile/writing_preference.json
```

Record a preference:

```powershell
python -m career_pipeline.writing_preference record `
  --profile ".career_profile/writing_preference.json" `
  --winner "claude_answer.txt" `
  --loser "gpt_answer.txt" `
  --winner-label claude `
  --loser-label gpt
```

The profile learns tendencies such as sentence-length rhythm, ending diversity, explicit connector density, bureaucratic-action density, abstract-promise density, first-person opening frequency, and paragraph rhythm. Generation receives derived directives, never the original comparison texts.

## Running the compiler

Plan only, no model call:

```powershell
python -m career_pipeline.narrative_compiler --run "career_runs/<run>"
```

High-quality generation:

```powershell
python -m career_pipeline.preference_writer `
  --run "career_runs/<run>" `
  --model-id "<configured GPT model>" `
  --candidates-per-question 3
```

The preference writer compiles the blueprint, performs multi-realization search and writes `draft.json`, the file consumed by `finalize`. It never overwrites an existing draft unless `--force` is supplied.

Use an explicit preference profile when needed:

```powershell
python -m career_pipeline.preference_writer `
  --run "career_runs/<run>" `
  --preference-profile ".career_profile/writing_preference.json" `
  --candidates-per-question 3
```

## Why not simply add more judges?

Multiple same-family LLM judges can make correlated errors. V4 therefore does not create a large panel of role-play judges. It uses one narrow preference rubric with balanced candidate-order permutations, then falls back to deterministic learned-preference distance and explainable style diagnostics when ranks tie.

## Safety boundary

Preference learning changes only surface realization and selection. It cannot:

- authorize a claim;
- authorize a number;
- promote `observed` to personal causation;
- import facts from Claude/Gemini/user-edited comparison texts;
- bypass `validate_draft` or official research validation.

The resulting system separates three questions that should not be conflated:

1. **May we say this?** → deterministic evidence validators.
2. **What should this answer prove?** → Narrative Blueprint.
3. **Which valid wording would this user actually prefer?** → learned preference tournament.
