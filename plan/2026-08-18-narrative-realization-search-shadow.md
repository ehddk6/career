# PLAN — Narrative Realization Search Shadow Validation

Updated: 2026-08-18
Base repository: `ehddk6/career`
Verified base main: `1e1a3f24a604443c46e0bf699ccf7c5b7c41b625`
Scope: additive shadow benchmark only; no canonical writer integration

## Objective

Test whether structurally different rhetorical move orderings improve human preference while holding the validated blueprint, selected argument route, factual evidence, ownership limits, and model family constant.

NRS is not a new writer stack. It must reuse the existing writer/validator machinery and must not duplicate `preference_writer.py` style modes, candidate validation, duplicate rejection, blind ranking, preference distance, portfolio critic, or minimal repair.

## Allowed changes

Add only:

- `career_pipeline/narrative_realization_shadow.py`
- `career_pipeline/nrs_shadow_benchmark.py`
- `tests/test_narrative_realization_shadow.py`
- `tests/test_nrs_shadow_benchmark.py`
- `docs/2026-08-18-narrative-realization-shadow-benchmark.md`
- this PLAN

Do not modify production writer, judge, gate, finalizer, Golden Path, object-semantics, parser, Multi-Claim, or preference-memory behavior.

## Safety contracts

- NRS may reorder only proof already present in the selected validated route.
- Unsupported friction, tradeoff, outcome, motive, criterion, or ownership must not be synthesized.
- Unsupported plan families must fail closed; route-order control is allowed when no orthogonal supported opening exists.
- Generated candidates must pass the existing payload and candidate validation boundaries before human comparison.
- Human review fields remain null until a person supplies them.
- PRIVATE benchmark artifacts remain under ignored run/audit paths and are never committed.
- Canonical Golden Path behavior must remain unchanged when NRS is not invoked.

## Validation sequence

1. `python -m compileall career_pipeline`
2. `pytest -q tests/test_narrative_realization_shadow.py tests/test_nrs_shadow_benchmark.py`
3. `pytest -q tests/test_deep_writer.py tests/test_reliable_deep_writer.py`
4. `pytest -q tests/test_preference_writer.py`
5. `pytest -q`
6. Run the existing frozen benchmarks.
7. Confirm no production imports from NRS and no canonical monkey patch.
8. Confirm no PRIVATE files are tracked.
9. Confirm canonical no-change behavior when the shadow benchmark is not invoked.

## Pilot after validation

Prepare six PRIVATE question pairs using the same blueprint, selected route, factual evidence, and writer model. Generate 3–4 supported NRS plans per question, keep only candidates that pass existing safety validation, and expose only a blinded baseline-vs-NRS A/B pair to the human reviewer.

Human-only fields: `preferred`, `sounds_like_me`, `more_specific_memorable`, `more_natural_korean`, `more_interview_speakable`, `reject_both`, and `notes`.

The engineering continuation gate is NRS preference of at least 60% among non-tied pairs with zero safety regression. This is not a hiring-success probability.

## Current execution boundary

The current runtime can inspect and write GitHub through the connected GitHub app, but it does not have a writable repository checkout or `gh`, and direct shell access to GitHub is unavailable. Therefore the additive branch can be created from the verified main tree, but repository-native full pytest, frozen benchmarks, PRIVATE dry-run, and Golden Path no-change execution must not be reported as passed until they are run in a real checkout or CI.
