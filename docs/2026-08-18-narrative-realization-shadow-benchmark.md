# Narrative Realization Search — Shadow Benchmark Integration

This change is intentionally additive. It must not be imported by the canonical
Golden Path during the pilot.

## Files

- `career_pipeline/narrative_realization_shadow.py`
- `career_pipeline/nrs_shadow_benchmark.py`
- `tests/test_narrative_realization_shadow.py`
- `tests/test_nrs_shadow_benchmark.py`

## Existing code to reuse in a real checkout

Do not duplicate existing writer infrastructure. The pilot should reuse:

- `argument_search.validate_route_packet` / already-selected validated route
- `narrative_compiler._validate_generated_payload`
- `narrative_compiler._to_response`
- `preference_writer._candidate_issues`
- `style_diagnostics.diagnose_text`
- `writing_preference.preference_distance`
- the existing Codex model runner

The existing `preference_writer.py` already performs four style-mode
realisations and order-reversed blind ranking. NRS tests a different hypothesis:
whether **rhetorical move order** adds value beyond style-mode variation.

## Recommended real-checkout pilot

1. Checkout current `main` and create a new branch.
2. Copy the two modules and two tests into repository-relative paths.
3. Run focused tests and full regression.
4. For six PRIVATE questions, preserve the already-selected Deep Writer route.
5. Generate 3–4 NRS plans from that exact route.
6. Render each plan with the same writer model and same factual blueprint.
7. Validate every payload through the existing candidate validation path.
8. Keep only valid candidates.
9. Compare the canonical current answer against the best valid NRS answer in a
   blinded A/B human packet.
10. Do not integrate into production unless safety regressions remain zero and
    the human pilot supports the NRS hypothesis.

## Validation commands

```bash
python -m compileall career_pipeline
pytest -q tests/test_narrative_realization_shadow.py tests/test_nrs_shadow_benchmark.py
pytest -q tests/test_deep_writer.py tests/test_reliable_deep_writer.py tests/test_preference_writer.py
pytest -q
```

Then run the repository's existing frozen benchmarks and one PRIVATE shadow
smoke run.

## Hard boundaries

- No production writer change.
- No automatic human labels.
- No unsupported facts or contribution expansion.
- No Multi-Claim work.
- No parser/object-semantics changes.
- PRIVATE benchmark text stays under ignored run audit paths.
