# Evidence-First Company Research Compiler

## Why this layer exists

The previous pipeline had a strong downstream research validator but a weak upstream research planner. `prepare` could create an empty `04_공식근거.json` and a pending execution record, while the agent still had to decide ad hoc what to search. That creates three failure modes: brochure facts are collected instead of argument-useful facts, current and historical facts are mixed, and a lexically similar claim can be selected even when it does not play the right argumentative role.

This layer moves company research to the same architecture used for applicant evidence: requirements first, evidence ledger second, prose last.

```text
posting + questions
  -> Research Requirement Compiler
  -> dynamic Source Registry / hierarchy
  -> external browsing or safe snapshots
  -> normalized Research Claim ledger
  -> temporal + source authority metadata
  -> conservative Conflict Resolver
  -> question-specific Coverage Matrix
  -> adaptive stop / next-query plan
  -> research Argument Router
  -> Narrative Compiler
  -> Integrated / Deep Writer
  -> existing finalize validators
```

The new code does not grant factual authority to model knowledge, legacy prose, strategy priors, search snippets, or non-authoritative sources.

## Artifacts

A run may now contain:

- `04_리서치계획.json`: question-specific slots that must be proven before drafting.
- `04_리서치출처.json`: dynamic official-domain registry and source hierarchy.
- `04_공식근거.json`: the existing claim ledger, enriched with semantic/temporal/source metadata.
- `04_근거충돌.json`: explicit same-subject conflict resolution.
- `04_근거커버리지.json`: PASS/MISSING/WEAK coverage by question and argument role.
- `04_리서치원문/`: optional safe source snapshots.
- `04_기업직무조사.md`: human-readable research pack regenerated from the artifacts above.

## Research slots

The planner compiles the question before search. Examples:

- motivation: `organization_differentiator`, `real_operating_role`, optional `current_priority`, `stakeholder_problem`
- job plan: `real_operating_role`, `operating_constraint`, optional `current_priority`
- issue analysis: `issue_mechanism`, `institution_response`, `policy_tradeoff`

Mixed questions keep multiple matched intents and merge non-duplicate slots. A prompt that asks both motivation and an after-joining plan therefore cannot silently lose one side of the research requirement.

## Source hierarchy

The registry distinguishes source authority instead of treating every URL as equivalent:

- Tier 0: posting, job description, law/regulation, official disclosure
- Tier 1: annual/business report, IR, official service/program page
- Tier 2: press release, newsroom, official blog/interview
- Tier 3: government, regulator, related public body
- Tier 4: reputable news, context/discovery only
- Tier 5: community, personal blog, video, discovery only

Only official Tier 0-2 sources are marked as submission factual authority by the new source classifier. Tier 3 may be strong contextual authority for issue analysis but is not automatically treated as the target organization's own statement. Tier 4-5 never become submission factual authority merely because they are persuasive or recent.

The old hard-coded organization-domain table remains only as compatibility seed data. `source-add --official` can extend the run registry dynamically; the resulting official domains are written back into `run.json` so the existing final validator consumes the same allowlist.

## Temporal semantics

`checked_at` means when the researcher inspected the source; it does not mean the underlying fact is current. Claims can now carry:

- `published_at`
- `basis_date`
- `effective_from`
- `effective_to`
- `freshness_class`: `current`, `posting_bound`, `stable`, `historical`, `unknown`, or `stale`

Coverage for current/posting-bound slots fails closed when freshness is unknown or stale. The workspace never upgrades a volatile fact to current merely because it was checked today or merely because `published_at`/`basis_date` exists.

## Conflicts

Claims are considered conflicting only when they explicitly share `conflict_group` or `subject_key`. This conservative rule prevents unrelated facts from being collapsed into a false conflict.

When conflicting texts exist, the resolver ranks them by verification status, support strength, freshness, source tier, and then effective/published recency. A top tie with different claim text remains `unresolved` and blocks the integrated writer instead of guessing.

## Coverage and adaptive stopping

Coverage is question-specific. A claim passes a slot only when it is verified, not superseded, sufficiently supported, within the slot's source-tier limit, temporally suitable, and assigned to the exact required `argument_role`. Claim type alone cannot satisfy a different slot.

When every required slot passes and no unresolved conflict remains, `stop_research=true`. Otherwise `next_queries` contains only the missing required research needs. This prevents both shallow one-page research and wasteful open-ended browsing.

## Argument routing

The legacy Narrative Compiler is preserved. Before `integrated_writer` calls Deep Writer, `research_router.py` replaces lexical-only research picks with the exact coverage-approved claims for each question. The rest of the blueprint, applicant evidence contract, argument search, preference learning, and finalize boundary remain intact.

This means a job-plan question can receive both an actual-duty claim and an operating-constraint claim even if a legacy lexical selector would have selected only a generic job-duty fact.

## Commands

Initialize or refresh the deterministic research plan:

```powershell
python -m career_pipeline.research_workspace init --run "career_runs\<run-folder>"
python -m career_pipeline.research_workspace status --run "career_runs\<run-folder>"
```

Register a newly verified official source/domain:

```powershell
python -m career_pipeline.research_workspace source-add `
  --run "career_runs\<run-folder>" `
  --url "https://www.example.go.kr/business" `
  --source-type official_program_page `
  --publisher "Example 기관" `
  --official
```

After a browsing/model step extracts claim candidates into a JSON array, ingest them through the authority boundary:

```powershell
python -m career_pipeline.research_claim_extractor `
  --run "career_runs\<run-folder>" `
  --input "research_claim_candidates.json"
```

Then rerun status. The integrated writer fails closed until required coverage is ready:

```powershell
python -m career_pipeline.integrated_writer `
  --run "career_runs\<run-folder>" `
  --writer-model-id "<writer>" `
  --judge-model-id "<judge>"
```

## Non-goals

- This layer does not claim that a model can determine truth from prose alone.
- It does not make snippets, blogs, or strategy priors factual evidence.
- It does not auto-resolve semantic conflicts without an explicit same-subject key.
- It does not mark research execution as completed merely because a plan or query list exists.
- Existing final deterministic validators remain authoritative.
