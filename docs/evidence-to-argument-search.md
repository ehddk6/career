# Evidence-to-Argument Search V5

## Why the earlier preference writer was still shallow

The previous `preference_writer` improved surface realization, but it still searched mostly over *wording of one preselected argument*. That creates four systematic failure modes:

1. **Wrong proof, polished prose** — if the chosen thesis/story is weak, three stylistic realizations only produce three polished versions of the same weak idea.
2. **Generator–judge correlation** — when one model writes and judges its own candidates, correlated blind spots and self-style preference can survive.
3. **Surface-only personalization** — sentence length, endings and connector frequency cannot represent why a user preferred a response with a sharper decision, stronger ownership, or a less replaceable story.
4. **Repair after commitment** — a critic that only rewrites prose cannot recover when the actual error is the selected argument route.

V5 changes the unit of search from **sentence** to **argument route**.

## Research-backed design principle

High-quality controlled generation is easier when content selection/planning and surface realization are separated. The repository therefore treats these as different contracts rather than asking one model call to simultaneously choose evidence, invent structure, write prose, and judge itself.

A second principle is that LLM judges are not neutral instruments. Order/position bias and self-preference are treated as system risks. Route judging therefore uses fixed semantic dimensions, multiple evaluator roles, balanced presentation order, median aggregation, and optionally heterogeneous judge model IDs.

A third principle is personalization by *revealed preference*. If the user says a Claude/Gemini/Qwen/human answer is better than a GPT answer, that winner is the label. The model is not allowed to reverse the user's choice. It may only explain which fixed semantic dimensions distinguish the winner; only aggregate preference weights are retained.

## Architecture

```text
confirmed evidence + official research
        ↓
existing Narrative Blueprint
        ↓
Story Kernel (deterministic support refs)
        ↓
ARGUMENT ROUTE SEARCH
  - thesis
  - argument posture
  - proof chain
  - support refs per proof step
  - evidence gaps
  - distinctive anchors
        ↓
route contract validation
        ↓
multi-role route judges
  hiring manager
  skeptical interviewer
  narrative editor
  × balanced order
  × optional heterogeneous model IDs
        ↓
dimension medians + disagreement
        ↓
Pareto frontier
        ↓
JOINT PORTFOLIO ROUTE SEARCH
  - experience reuse penalty
  - argument-posture reuse penalty
  - semantic-signature repetition penalty
        ↓
selected routes only
        ↓
2 route-bound prose realizations
        ↓
deterministic evidence validation
        ↓
blind prose selection
        ↓
portfolio critic
        ↓
structural defect? ── yes → substitute another route, regenerate, re-critic
        │
        no
        ↓
surface-only defect? ── yes → minimal surface repair
        ↓
final deterministic validation
        ↓
draft.json
```

The important invariant is:

> A weak argument is replaced at the argument layer. It is not cosmetically repaired at the prose layer.

## Semantic dimensions

Route and prose evaluation use a fixed schema:

- `question_fidelity`
- `evidence_defensibility`
- `decision_visibility`
- `causal_coherence`
- `scene_specificity`
- `ownership`
- `fit_naturalness`
- `distinctiveness`
- `replaceability_resistance`
- `voice_potential`

This deliberately separates "well written" from "worth saying."

## Story kernel and evidence gaps

`argument_search.build_story_kernel()` turns the selected blueprint evidence into addressable support refs such as:

```text
experience:situation
experience:action:0
experience:outcome:0
claim:<claim_id>
research:<claim_id>
```

Argument plans can reference only these refs. If the prompt requires a decision, trade-off, criterion or reflection that cannot be defended from the available material, V5 records a gap instead of silently manufacturing psychological motives.

When no defensible route survives, the writer fails closed and creates:

- `05_서사정보공백.json`
- `05_서사정보공백.md`

The correct response to missing story information is **more evidence**, not more eloquent hallucination.

## Portfolio optimization

Selecting the best answer independently for every question can still produce a bad application: same experience, same thesis posture and same action vocabulary repeated four times.

`select_portfolio_routes()` jointly optimizes the entire set. A locally second-best route can win if it makes the whole application more varied and informative.

## Semantic preference memory

Surface rhythm remains in:

```text
.career_profile/writing_preference.json
```

Argument preference is separate:

```text
.career_profile/semantic_writing_preference.json
```

Example:

```powershell
python -m career_pipeline.semantic_preference record `
  --profile ".career_profile/semantic_writing_preference.json" `
  --winner "claude_answer.txt" `
  --loser "gpt_answer.txt" `
  --winner-label claude `
  --loser-label gpt `
  --model-id "<configured evaluator>"
```

The user already supplied the preference label (`winner`). The evaluator only classifies *why* the winner was preferred across the fixed semantic dimensions. Raw answer text is not persisted in the semantic profile.

Weights are deliberately shrunk toward 1.0. One comparison is evidence, not a permanent rule.

## Writer

```powershell
python -m career_pipeline.deep_writer `
  --run "career_runs/<run>" `
  --writer-model-id "<writer>" `
  --judge-model-id "<judge-a>" `
  --judge-model-id "<judge-b>" `
  --routes 3 `
  --prose-realisations 2
```

If judge IDs are omitted, the writer model is reused with role/order debiasing and the report says `same_model_role_ensemble`. When at least one judge differs from the writer, it says `heterogeneous_model_ids`.

For a high-stakes final application, heterogeneous judges are preferable when they are available because they reduce correlated generator/judge failure. The writer does not assume that a different provider is automatically better; the benefit is evaluation diversity.

Output:

- `draft.json`
- `05_논증검색_검증.json`
- optional `05_서사정보공백.*` when evidence is insufficient

Then run the existing `finalize` path. Existing factual, metric, causality, research-source, count-mode, and artifact validation remains authoritative.

## Qwen review disposition

The supplied Qwen audit was evaluated against the actual repository rather than applied wholesale.

### Accepted with modification: short partial duplicate detection

Qwen correctly identified that the legacy quality gate skips `SequenceMatcher` when the shorter normalized answer is under 80 characters. That creates a real false-negative class.

The literal proposed patch used a 40-character substring floor, while its own test example's copied phrase is shorter than that after normalization. V5 therefore implements the concept with an 18-character minimum in the deep path and tests the supplied edge-case shape. This check runs **before** the 80-character similarity shortcut.

### Deferred: HMAC helper refactor

The proposed helper is reasonable cleanup, but authorization contracts are a security boundary. Refactoring them without a contract-by-contract behavioral equivalence suite creates more risk than value and is unrelated to the current writing-quality bottleneck. Keep it for a dedicated hardening change.

### Deferred as blocking CI: Ruff + Mypy + Bandit on the entire tree

Adding all three as immediate blocking checks without a repository baseline can turn pre-existing lint/type debt into an unrelated red build. Introduce them incrementally (baseline or changed-files first) in a dedicated CI hardening change. Existing tests remain the release gate for this writing architecture.

### Partially accepted: hallucination fallback policy

The evidence-grounded fail-closed principle already exists and V5 strengthens it with explicit argument-support refs and an evidence-gap artifact. Arbitrary 30-second endpoint and 20MB/60-second file limits were not adopted because those constants were not derived from the current contracts or measured failure data.

## Deliberate non-goals

- Do not infer hiring probability from the internal quality score.
- Do not treat one LLM judge as human ground truth.
- Do not store Claude/Gemini/GPT answer text in preference memory.
- Do not fuse attractive sentences from incompatible routes without a valid evidence contract.
- Do not invent motives, stakes, trade-offs, metrics, or causality to make an answer "deeper."

The purpose of V5 is not maximal eloquence. It is **maximal persuasive specificity within verified evidence**.
