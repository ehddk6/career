# PRODUCT TRUTH — career-nrs-shadow-pilot

Rule: every entry carries evidence, a date, and the date it was last checked against the code. External claims may be sourced only from Implemented. Code states are not blended: implemented / wired / operational / verified.

## Implemented

- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** NRS v2 is the default prose strategy and retains fact, actor, and self-introduction genre gates. Evidence: `career_pipeline/deep_writer.py`, `career_pipeline/integrated_writer.py`, `career_pipeline/nrs_paired_reconstruction.py`, `docs/2026-08-29-nrs-production-default.md`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** The golden path preserves stage fingerprints and blocks stale interview reuse after final-draft changes. Evidence: `career_pipeline/golden_path.py`, `career_pipeline/golden_path_converged.py`, `tests/test_golden_path.py`, `tests/test_golden_path_acceptance.py`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** Interview intelligence compiles a final-draft claim graph, standardized/adaptive questions, and aggregate-only weakness profiles. Evidence: `career_pipeline/interview_intelligence/`, `tests/test_interview_intelligence.py`, `tests/test_interview_calibration.py`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** Eligibility evaluators handle structured education, experience, certification, location, and work-authorization rules. Evidence: `career_pipeline/eligibility.py`, `tests/test_eligibility.py`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** The base CLI exposes the converged golden path through `workflow start/resume/status/migrate-plan`, and the system benchmark supports explicit `off`, `report`, and `required` policies. Evidence: `career_pipeline/__main__.py`, `career_pipeline/workflow.py`, `career_pipeline/system_benchmark.py`, `tests/test_workflow.py`, `tests/test_system_benchmark.py`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** Final self-introduction audit blocks generic motivation, internal-report diction, and missing required metric proof bundles even when generation uses a fallback or rigorous selection. Evidence: `career_pipeline/quality.py`, `career_pipeline/self_introduction_genre.py`, `career_pipeline/audit.py`, `tests/test_quality.py`, `tests/test_audit.py`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** Application packages preserve an independent submission preflight status and explicit credential-to-attachment bindings; selected expired credentials and missing evidence block readiness, while unselected expired credentials can be excluded. Evidence: `career_pipeline/submission_preflight.py`, `career_pipeline/application_package.py`, `tests/test_submission_preflight.py`, `tests/test_application_package.py`.
- **관찰됨 · n=68 local historical runs · 2026-08-30:** 56 runs declare V2 strict quality; 37 contain official research, 31 drafts, 27 final manifests, and 29 legacy interview packs. Limits: one user's July–August 2026 local run archive; not representative of external success.

## Not implemented

- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** Ordinary experience-ledger projection does not populate education, certifications, or locations. Evidence: `career_pipeline/eligibility.py::applicant_profile_from_ledger`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** Ordinary posting-analysis projection does not parse eligibility rules or publication/deadline dates; it emits manual-review custom rules. Evidence: `career_pipeline/eligibility.py::posting_record_from_analysis`.
- **관찰됨 · 2026-08-30 · last checked 2026-08-30:** The safe research retriever has no repository caller, and the golden path waits for externally completed research artifacts. Evidence: negative repository search for `retrieve_research_source`, `career_pipeline/golden_path.py`.
- **관찰됨 · n=68 local historical runs · 2026-08-30:** No run contains NRS selection, interview-intelligence, golden-path, or system-benchmark artifacts. Limits: historical local runs predate some changes; this proves lack of observed adoption, not inability to run.

## Permanently excluded

<!-- User-confirmed exclusions only; link the ledger decision. -->
