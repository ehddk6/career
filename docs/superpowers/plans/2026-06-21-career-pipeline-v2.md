# Career Pipeline V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local approved experience ledger and source-backed posting analyzer, then use both to produce explainable question-to-experience matches and stricter quality gates.

**Architecture:** Add focused profile, posting, matching, and quality modules around the existing deterministic pipeline. Confirmed profile claims remain the only source of truth; posting snapshots are immutable run artifacts; existing profile-free commands continue in `legacy` mode.

**Tech Stack:** Python 3.11+, standard library `urllib`, `html.parser`, `ipaddress`, `socket`, dataclasses, python-docx, pypdf, PyYAML, pytest.

---

## Execution preflight

Use `superpowers:using-git-worktrees` before implementation. In the isolated worktree run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Expected baseline: `37 passed` when `CAREER_PIPELINE_WORKSPACE` is set for the local acceptance test, or `36 passed, 1 skipped` without it. Do not stage or modify the user's existing root `.gitignore` whitespace change.

## File map

### New production modules

- `career_pipeline/profile_schema.py`: profile dataclasses, JSON parsing, serialization, validation errors.
- `career_pipeline/profile_builder.py`: evidence-block discovery, stable experience IDs, proposed ledger generation.
- `career_pipeline/profile_refresh.py`: evidence re-extraction, file/excerpt hash checks, stale and review reporting.
- `career_pipeline/posting_schema.py`: posting source metadata and structured posting dataclasses.
- `career_pipeline/posting_loader.py`: safe URL/local loading and immutable source snapshots.
- `career_pipeline/posting_parser.py`: section classification, requirements, questions, constraints, uncertainties.
- `career_pipeline/matching.py`: question classification, explainable scoring, reuse penalty, Markdown/JSON output.
- `career_pipeline/quality.py`: profile, posting, matching, and final response gates.
- `career_pipeline/source_policy.py`: one shared rule for evidence vs. research/posting/internal sources.

### Modified production modules

- `career_pipeline/inventory.py:10-99`: exclude `.career_profile`, expose file hashing for profile evidence.
- `career_pipeline/questions.py:1-26`: support more limit patterns and question/limit reconciliation.
- `career_pipeline/models.py:1-62`: add V2 draft evidence references without breaking legacy responses.
- `career_pipeline/orchestrator.py:66-226`: load V2 inputs, write analysis/matching artifacts, add state gates.
- `career_pipeline/validation.py:29-88`: validate V2 experience/claim references and exact metric values.
- `career_pipeline/__main__.py:7-43`: profile/posting subcommands and blocked-state exit codes.
- `.gitignore`: add `.career_profile/` while preserving the existing local blank-line change outside feature commits.
- `.agents/skills/career-pipeline/SKILL.md`: V2 natural-language and command flow.
- `.agents/skills/career-pipeline/references/output-contract.md`: V2 artifact and evidence-reference contract.
- `docs/career-pipeline-usage.md`: setup, profile lifecycle, posting analysis, migration, troubleshooting.

### New tests and fixtures

- `tests/test_profile_schema.py`
- `tests/test_profile_builder.py`
- `tests/test_profile_refresh.py`
- `tests/test_profile_cli.py`
- `tests/test_posting_loader.py`
- `tests/test_posting_parser.py`
- `tests/test_posting_cli.py`
- `tests/test_matching.py`
- `tests/test_quality.py`
- `tests/test_v2_prepare.py`
- `tests/test_v2_finalize.py`
- `tests/fixtures/hug_posting_excerpt.html`

---

### Task 1: Profile schema and private storage boundary

**Files:**
- Create: `career_pipeline/profile_schema.py`
- Create: `career_pipeline/source_policy.py`
- Modify: `career_pipeline/inventory.py:10-33`
- Modify: `.gitignore`
- Test: `tests/test_profile_schema.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Write failing schema tests**

Add tests that prove confirmed claims require evidence, proposed claims cannot be used, and JSON error paths are reported.

```python
from career_pipeline.profile_schema import (
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
    ProfileValidationError,
    load_ledger,
    validate_ledger,
)


def test_confirmed_claim_requires_hashed_evidence():
    claim = ProfileClaim(
        field="budget_savings",
        normalized_value="10000000원",
        status="confirmed",
        evidence=(),
    )
    ledger = ExperienceLedger(
        schema_version=1,
        generated_at="2026-06-21T12:00:00+09:00",
        workspace_root="C:/career",
        experiences=(
            Experience(
                experience_id="exp_123",
                title="숙박비 검증",
                organization_alias="지자체",
                period=None,
                role="증빙 검토",
                situation="금액 불일치",
                actions=("교차 확인",),
                outcomes=("예산 누수 방지",),
                competencies=("정확성",),
                claims=(claim,),
                status="confirmed",
                confirmed_at="2026-06-21T12:00:00+09:00",
            ),
        ),
    )

    with pytest.raises(ProfileValidationError) as error:
        validate_ledger(ledger)

    assert "experiences[0].claims[0].evidence" in str(error.value)
```

- [ ] **Step 2: Write failing privacy-boundary test**

Extend `tests/test_inventory.py`:

```python
(tmp_path / ".career_profile").mkdir()
(tmp_path / ".career_profile" / "experience_ledger.json").write_text(
    "{}", encoding="utf-8"
)

records = build_inventory(tmp_path)
paths = {record.relative_path for record in records}

assert ".career_profile/" in paths
assert ".career_profile/experience_ledger.json" not in paths
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_schema.py tests/test_inventory.py -q
```

Expected: import failure for `career_pipeline.profile_schema` and missing `.career_profile/` exclusion.

- [ ] **Step 4: Implement schema dataclasses and validators**

Create immutable dataclasses with explicit JSON conversion.

```python
PROFILE_STATUSES = {"proposed", "confirmed", "rejected", "stale"}
CLAIM_STATUSES = {"proposed", "confirmed", "rejected", "stale", "unknown"}


@dataclass(frozen=True)
class EvidenceRef:
    source_path: str
    paragraph_index: int
    source_sha256: str
    excerpt_sha256: str


@dataclass(frozen=True)
class ProfileClaim:
    field: str
    normalized_value: str
    status: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class Experience:
    experience_id: str
    title: str
    organization_alias: str
    period: dict | None
    role: str
    situation: str
    actions: tuple[str, ...]
    outcomes: tuple[str, ...]
    competencies: tuple[str, ...]
    claims: tuple[ProfileClaim, ...]
    status: str
    confirmed_at: str | None


@dataclass(frozen=True)
class ExperienceLedger:
    schema_version: int
    generated_at: str
    workspace_root: str
    experiences: tuple[Experience, ...]
```

`validate_ledger` must collect all errors and raise one `ProfileValidationError`. A confirmed experience must contain at least one confirmed claim or one non-metric evidence-backed narrative, every confirmed claim must have evidence, hashes must be lowercase 64-character SHA-256 values, experience IDs must be unique, and only declared statuses are accepted.

- [ ] **Step 5: Centralize source policy and hashing**

Create:

```python
NON_EVIDENCE_PARTS = {"자료조사", "입사지원서(양식)", "docs", ".agents"}
NON_EVIDENCE_NAMES = ("직무기술서", "채용공고")


def is_evidence_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return not any(part in NON_EVIDENCE_PARTS for part in path.parts) and not any(
        marker in path.name for marker in NON_EVIDENCE_NAMES
    )
```

Rename `_digest` to public `digest_path` and keep `_digest = digest_path` as a compatibility alias for existing tests. Add `.career_profile` to `EXCLUDED_DIRS` and `.career_profile/` to `.gitignore`.

- [ ] **Step 6: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_schema.py tests/test_inventory.py -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```powershell
git add .gitignore career_pipeline/profile_schema.py career_pipeline/source_policy.py career_pipeline/inventory.py tests/test_profile_schema.py tests/test_inventory.py
git commit -m "feat: add approved experience ledger schema"
```

---

### Task 2: Proposed experience ledger builder

**Files:**
- Create: `career_pipeline/profile_builder.py`
- Modify: `career_pipeline/facts.py:96-130`
- Test: `tests/test_profile_builder.py`

- [ ] **Step 1: Write failing builder tests**

```python
def test_build_proposed_ledger_groups_claims_by_evidence_block(tmp_path):
    source = SourceRecord(
        tmp_path / "career.docx",
        "career.docx",
        ".docx",
        1,
        "a" * 64,
        "use",
    )
    document = ExtractedDocument(
        source,
        "",
        (
            "숙박비 영수증을 교차 확인해 부정수급 의심 20건을 찾고 "
            "예산 1,000만원의 누수를 막았습니다.",
        ),
    )

    ledger = build_proposed_ledger(Path("C:/career"), [document])

    assert len(ledger.experiences) == 1
    experience = ledger.experiences[0]
    assert experience.status == "proposed"
    assert {claim.normalized_value for claim in experience.claims} == {
        "20건",
        "10000000원",
    }
    assert all(claim.status == "proposed" for claim in experience.claims)
```

Add a second test proving two claims in different paragraphs become separate candidates and an identical rebuild produces the same `experience_id`.

- [ ] **Step 2: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_builder.py -q
```

Expected: missing `profile_builder` module.

- [ ] **Step 3: Implement stable IDs and evidence hashes**

```python
def stable_experience_id(
    source_path: str, paragraph_index: int, tokens: frozenset[str]
) -> str:
    anchors = "|".join(sorted(tokens)[:4])
    payload = f"{Path(source_path).as_posix()}\0{paragraph_index}\0{anchors}"
    return "exp_" + sha256(payload.encode("utf-8")).hexdigest()[:16]


def excerpt_sha256(context: str) -> str:
    normalized = " ".join(context.split())
    return sha256(normalized.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implement candidate grouping**

`build_proposed_ledger` must:

1. Filter documents with `is_evidence_path`.
2. Extract fact claims once.
3. Group by `(source_path, paragraph_index)`.
4. Create one proposed experience per evidence block containing claims.
5. Derive a conservative title from the source stem and paragraph index, not an invented semantic claim.
6. Store the original paragraph as `situation`; leave actions/outcomes empty unless action/result sentences are explicitly detected.
7. Store `source_sha256` and normalized excerpt hash on every evidence reference.

Use explicit cue functions:

```python
ACTION_CUES = ("확인", "분석", "정리", "개선", "활용", "대조", "안내")
OUTCOME_CUES = ("결과", "달성", "감소", "증가", "절감", "적발", "완료")
```

Do not infer organization names or dates when they are absent.

- [ ] **Step 5: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_builder.py tests/test_facts.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add career_pipeline/profile_builder.py career_pipeline/facts.py tests/test_profile_builder.py
git commit -m "feat: build proposed experience ledgers"
```

---

### Task 3: Profile refresh and stale evidence reporting

**Files:**
- Create: `career_pipeline/profile_refresh.py`
- Test: `tests/test_profile_refresh.py`

- [ ] **Step 1: Write failing refresh tests**

```python
def test_refresh_marks_changed_evidence_stale_without_mutating_confirmed_ledger(
    tmp_path,
):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원을 절감했습니다.", encoding="utf-8")
    ledger = confirmed_ledger_for(source, paragraph_index=0)
    source.write_text("예산 2,000만원을 절감했습니다.", encoding="utf-8")

    review = refresh_profile(tmp_path, ledger)

    assert ledger.experiences[0].status == "confirmed"
    assert review.items[0].status == "stale"
    assert review.items[0].reason == "source_sha256_changed"
```

Add missing-file, paragraph-index-out-of-range, excerpt-changed, and unchanged-evidence tests.

- [ ] **Step 2: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_refresh.py -q
```

Expected: missing module.

- [ ] **Step 3: Implement review models and refresh**

```python
@dataclass(frozen=True)
class ProfileReviewItem:
    experience_id: str
    source_path: str
    status: str
    reason: str


@dataclass(frozen=True)
class ProfileReview:
    generated_at: str
    items: tuple[ProfileReviewItem, ...]
```

`refresh_profile(root, ledger)` must resolve each evidence path under `root`, reject path traversal, compare file hashes, re-extract the referenced paragraph, compare excerpt hashes, and return review items. It must never write or mutate the confirmed ledger.

- [ ] **Step 4: Add Markdown and proposed-diff output**

Implement `render_profile_review(review)` with sections `변경 없음`, `재확인 필요`, and `근거 없음`. Implement `write_refresh_outputs(profile_dir, review, proposed_ledger)` using existing UTF-8 JSON helpers.

- [ ] **Step 5: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_refresh.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add career_pipeline/profile_refresh.py tests/test_profile_refresh.py
git commit -m "feat: detect stale career evidence"
```

---

### Task 4: Profile CLI lifecycle

**Files:**
- Modify: `career_pipeline/__main__.py:7-43`
- Test: `tests/test_profile_cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing parser tests**

```python
def test_parser_exposes_profile_build_refresh_and_validate():
    parser = build_parser()

    build = parser.parse_args(
        ["profile", "build", "--root", ".", "--output", "profile.json"]
    )
    refresh = parser.parse_args(
        ["profile", "refresh", "--root", ".", "--profile", "profile.json"]
    )
    validate = parser.parse_args(
        ["profile", "validate", "--profile", "profile.json"]
    )

    assert build.profile_command == "build"
    assert refresh.profile_command == "refresh"
    assert validate.profile_command == "validate"
```

- [ ] **Step 2: Write failing command integration tests**

Use `monkeypatch` for command handlers and assert exit codes: build `0`, valid profile `0`, invalid profile `4`, refresh with stale items `2`.

- [ ] **Step 3: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_cli.py tests/test_cli.py -q
```

Expected: parser rejects `profile`.

- [ ] **Step 4: Implement nested profile subcommands**

Add:

```python
profile = subparsers.add_parser("profile")
profile_commands = profile.add_subparsers(
    dest="profile_command", required=True
)
```

Route commands through small functions `run_profile_build`, `run_profile_refresh`, and `run_profile_validate`. Build must use inventory/extractors and save the proposed ledger. Refresh must write review artifacts next to the confirmed profile. Validate prints `valid` only after schema and evidence-shape validation.

- [ ] **Step 5: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_cli.py tests/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add career_pipeline/__main__.py tests/test_profile_cli.py tests/test_cli.py
git commit -m "feat: add profile lifecycle commands"
```

---

### Task 5: Posting schemas and safe source loader

**Files:**
- Create: `career_pipeline/posting_schema.py`
- Create: `career_pipeline/posting_loader.py`
- Test: `tests/test_posting_loader.py`

- [ ] **Step 1: Write failing local-source tests**

```python
def test_load_local_pdf_requires_official_attestation(tmp_path):
    path = tmp_path / "posting.pdf"
    path.write_bytes(b"%PDF fixture")

    with pytest.raises(PostingSourceError, match="official"):
        load_posting_source(path, official_source=False)


def test_load_local_docx_records_user_attested_status(tmp_path):
    path = make_docx(tmp_path / "posting.docx", "담당업무: 고객 안내")

    loaded = load_posting_source(path, official_source=True)

    assert loaded.metadata.official_status == "user_attested"
    assert loaded.metadata.content_sha256 == digest_path(path)
```

- [ ] **Step 2: Write failing URL safety tests**

```python
@pytest.mark.parametrize(
    "url",
    [
        "http://example.or.kr/posting",
        "https://localhost/posting",
        "https://127.0.0.1/posting",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_validate_public_https_url_rejects_unsafe_targets(url):
    with pytest.raises(PostingSourceError):
        validate_public_https_url(url, resolver=fake_resolver)
```

Add tests for official-domain mismatch, 20MB size limit, unsupported content type, and redirect validation using injected resolver/transport objects. Tests must not access the network.

- [ ] **Step 3: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_posting_loader.py -q
```

Expected: missing modules.

- [ ] **Step 4: Implement posting source models**

```python
@dataclass(frozen=True)
class PostingSourceMetadata:
    kind: str
    location: str
    retrieved_at: str
    content_sha256: str
    official_status: str
    content_type: str


@dataclass(frozen=True)
class LoadedPosting:
    metadata: PostingSourceMetadata
    extension: str
    content: bytes
```

Allowed official statuses are `verified_domain`, `user_attested`, and `unverified`.

- [ ] **Step 5: Implement URL validation and loading**

Use `urlsplit`, `ipaddress.ip_address`, and `socket.getaddrinfo`. Accept a resolver and transport parameter for tests. Reject usernames/passwords in URLs. Match official domains exactly or as subdomains:

```python
def host_matches_official_domain(host: str, domain: str) -> bool:
    host = host.rstrip(".").lower()
    domain = domain.rstrip(".").lower()
    return host == domain or host.endswith("." + domain)
```

Read at most `20 * 1024 * 1024 + 1` bytes and reject oversized responses. Use a redirect handler that calls the same URL validator for every destination. Do not forward custom cookies or local content.

- [ ] **Step 6: Implement immutable snapshots**

`write_posting_snapshot(run_dir, loaded)` creates `00_채용공고원문/source.<ext>` with `xb` mode so an existing snapshot is never overwritten. If the same hash already exists, reuse it; if the bytes differ, raise `PostingSourceError`.

- [ ] **Step 7: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_posting_loader.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```powershell
git add career_pipeline/posting_schema.py career_pipeline/posting_loader.py tests/test_posting_loader.py
git commit -m "feat: load verified posting sources safely"
```

---

### Task 6: Posting parser and question reconciliation

**Files:**
- Create: `career_pipeline/posting_parser.py`
- Modify: `career_pipeline/questions.py:1-26`
- Test: `tests/test_posting_parser.py`
- Modify: `tests/test_questions.py`
- Create: `tests/fixtures/hug_posting_excerpt.html`

- [ ] **Step 1: Add a minimal official-posting fixture**

Store only the public fields needed for deterministic tests:

```html
<!doctype html>
<html lang="ko">
  <body>
    <h1>체험형 청년인턴 채용공고</h1>
    <h2>채용분야</h2>
    <p>금융·기금(강원)</p>
    <h2>담당업무</h2>
    <ul><li>도시재생 금융지원 관련 안내 등 업무 보조</li></ul>
    <h2>지원자격</h2>
    <p>공고일 기준 지원자격을 충족한 자</p>
    <h2>자기소개서</h2>
    <p>지원동기와 인턴 근무 목표를 기술해 주십시오.</p>
    <p>0/600 (글자 수, 공백 포함)</p>
  </body>
</html>
```

- [ ] **Step 2: Write failing parser tests**

```python
def test_parse_posting_extracts_role_duty_requirement_and_question():
    loaded = loaded_html_fixture("hug_posting_excerpt.html")

    analysis = parse_posting(loaded, target="HUG 금융·기금(강원)")

    assert analysis.role == "금융·기금(강원)"
    assert analysis.duties == ("도시재생 금융지원 관련 안내 등 업무 보조",)
    assert analysis.requirements == ("공고일 기준 지원자격을 충족한 자",)
    assert analysis.questions[0].character_limit == 600
```

Add tests for PDF/DOCX block input, missing duties, uncertainty collection, and question mismatch.

- [ ] **Step 3: Extend question limit patterns**

Add tests and support for `600자 이내`, `최대 600자`, `600 bytes`, and limits on the same line as a question. Keep current patterns passing.

- [ ] **Step 4: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_posting_parser.py tests/test_questions.py -q
```

Expected: parser module missing and new limit cases failing.

- [ ] **Step 5: Implement HTML visible-text extraction**

Subclass `HTMLParser`, ignore `script`, `style`, `noscript`, and preserve headings/list/table-cell boundaries as separate blocks. Decode with the response charset when provided and UTF-8 fallback.

- [ ] **Step 6: Implement section parsing**

```python
SECTION_MARKERS = {
    "role": ("채용분야", "모집분야", "직무"),
    "duties": ("담당업무", "직무내용", "주요업무"),
    "requirements": ("지원자격", "응시자격"),
    "preferences": ("우대사항", "가점사항"),
    "questions": ("자기소개서", "지원서 문항"),
    "constraints": ("유의사항", "블라인드", "작성 시 유의"),
}
```

Create `PostingAnalysis` with tuples for every repeated field. Do not silently fill missing required fields from the target label. Record missing organization/role/duties in `uncertainties`.

- [ ] **Step 7: Implement question reconciliation**

```python
def reconcile_questions(
    posting_questions: tuple[Question, ...],
    draft_questions: tuple[Question, ...],
) -> QuestionReconciliation:
    ...
```

When one side is empty, use the other. When both exist, normalized prompts and character limits must match in order; otherwise return mismatch rows for the blocker report.

- [ ] **Step 8: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_posting_parser.py tests/test_questions.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```powershell
git add career_pipeline/posting_parser.py career_pipeline/questions.py tests/test_posting_parser.py tests/test_questions.py tests/fixtures/hug_posting_excerpt.html
git commit -m "feat: parse structured job postings"
```

---

### Task 7: Posting CLI and analysis artifacts

**Files:**
- Modify: `career_pipeline/__main__.py:7-43`
- Create: `tests/test_posting_cli.py`
- Modify: `career_pipeline/state.py:26-34`

- [ ] **Step 1: Write failing parser test**

```python
def test_parser_exposes_posting_analyze():
    args = build_parser().parse_args(
        [
            "posting",
            "analyze",
            "--target",
            "HUG 금융·기금(강원)",
            "--source",
            "posting.html",
            "--official-source",
            "--output",
            "career_runs/test",
        ]
    )
    assert args.posting_command == "analyze"
```

- [ ] **Step 2: Write failing command artifact test**

Use the HTML fixture and assert the command writes:

- `00_채용공고원문/source.html`
- `00_채용공고분석.json`
- `00_채용공고분석.md`

The Markdown must show official status, extracted duties, questions, and uncertainties.

- [ ] **Step 3: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_posting_cli.py -q
```

Expected: parser rejects `posting`.

- [ ] **Step 4: Implement posting command routing**

Add nested `posting analyze`. Make `--official-domain` repeatable and `--official-source` boolean. Reject simultaneous URL attestation flags that contradict the source type. Print the output directory and return `2` when official status is unverified or required fields are missing; otherwise return `0`.

- [ ] **Step 5: Implement deterministic Markdown rendering**

Render sections in this order: source, target, duties, competencies, requirements, preferences, questions, constraints, uncertainties. Links must be ordinary Markdown and no internal tool tokens may appear.

- [ ] **Step 6: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_posting_cli.py tests/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add career_pipeline/__main__.py career_pipeline/state.py tests/test_posting_cli.py tests/test_cli.py
git commit -m "feat: add posting analysis command"
```

---

### Task 8: Explainable experience matching

**Files:**
- Create: `career_pipeline/matching.py`
- Test: `tests/test_matching.py`

- [ ] **Step 1: Write failing scoring tests**

```python
def test_confirmed_evidence_and_duty_overlap_rank_best_experience():
    ledger = ledger_with(
        confirmed_experience(
            "exp_verify",
            competencies=("데이터 검증", "정확성"),
            actions=("자료 교차 확인",),
        ),
        confirmed_experience(
            "exp_customer",
            competencies=("고객 안내",),
            actions=("절차 설명",),
        ),
    )
    posting = posting_with(
        duties=("신청 자료 확인",),
        competencies=("정확성",),
    )
    question = Question(1, "문제를 발견하고 개선한 경험", 600)

    matches = match_questions(ledger, posting, [question])

    assert matches[0].candidates[0].experience_id == "exp_verify"
    assert matches[0].candidates[0].evidence_score == 40
    assert "정확성" in matches[0].candidates[0].matched_competencies
```

Add tests for proposed/stale exclusion, question-type fit, zero token overlap, top-three limit, deterministic ties, and 15-point reuse penalty.

- [ ] **Step 2: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_matching.py -q
```

Expected: missing module.

- [ ] **Step 3: Implement question classification and token normalization**

```python
QUESTION_TYPES = {
    "motivation": ("지원동기", "지원하게 된 동기", "입사 후"),
    "problem_solving": ("문제", "개선", "새로운 접근", "변화"),
    "collaboration": ("협업", "갈등", "팀"),
    "trust": ("책임감", "성실", "신뢰", "원칙"),
}
```

Use normalized Korean/ASCII tokens and a small explicit synonym map stored in the module. Do not use embeddings or external calls.

- [ ] **Step 4: Implement score components**

Return a dataclass carrying each component separately:

```python
@dataclass(frozen=True)
class MatchCandidate:
    experience_id: str
    total_score: int
    evidence_score: int
    duty_score: int
    competency_score: int
    question_fit_score: int
    reuse_penalty: int
    matched_duties: tuple[str, ...]
    matched_competencies: tuple[str, ...]
    allowed_claims: tuple[str, ...]
    blocked_claims: tuple[str, ...]
```

Cap components at 40/25/20/15. Sort by total score descending, then experience ID ascending. Apply reuse penalty only in the recommended allocation pass, not the raw candidate list.

- [ ] **Step 5: Implement JSON and Markdown renderers**

Markdown must show why each candidate ranked, confirmed facts that may be used, and unavailable claims. Never label the score as probability.

- [ ] **Step 6: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_matching.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add career_pipeline/matching.py tests/test_matching.py
git commit -m "feat: match approved experiences to posting questions"
```

---

### Task 9: V2 prepare quality gates and state transitions

**Files:**
- Create: `career_pipeline/quality.py`
- Modify: `career_pipeline/orchestrator.py:66-136`
- Modify: `career_pipeline/__main__.py:24-43`
- Test: `tests/test_quality.py`
- Test: `tests/test_v2_prepare.py`
- Modify: `tests/test_prepare.py`

- [ ] **Step 1: Write failing quality-gate tests**

```python
def test_profile_gate_blocks_stale_claim_selected_for_matching():
    issues = validate_profile_gate(
        ledger_with(stale_experience("exp_stale")),
        selected_experience_ids={"exp_stale"},
    )
    assert issues[0].code == "stale_profile_evidence"


def test_posting_gate_blocks_unverified_source():
    issues = validate_posting_gate(
        posting_with(official_status="unverified")
    )
    assert issues[0].code == "unverified_posting"
```

- [ ] **Step 2: Write failing V2 prepare tests**

Create an approved ledger, official local posting fixture, and draft DOCX. Assert V2 prepare writes:

- `00_채용공고분석.json`
- `00_채용공고분석.md`
- `02_확정경험원장.json`
- `03_경험직무매칭.json`
- `03_경험직무매칭.md`

Assert status `ready_for_research`, `quality_mode == "v2"`, and no raw proposed claim appears in the confirmed snapshot.

Add separate tests for `blocked_profile`, `blocked_posting`, `blocked_conflict`, question mismatch, and legacy mode.

- [ ] **Step 3: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality.py tests/test_v2_prepare.py tests/test_prepare.py -q
```

Expected: missing quality module and prepare rejecting `--profile` flow.

- [ ] **Step 4: Refactor evidence filtering**

Replace the inline research/description exclusion in `prepare_run` with `is_evidence_path`. Keep legacy claim extraction behavior unchanged.

- [ ] **Step 5: Add V2 prepare parameters**

Use keyword-only optional parameters to avoid breaking existing calls:

```python
def prepare_run(
    root: Path,
    target: str,
    draft: Path,
    posting: str | None,
    run_name: str | None,
    resume: Path | None = None,
    *,
    profile: Path | None = None,
    official_domains: tuple[str, ...] = (),
    official_source: bool = False,
) -> dict:
```

Legacy mode executes the current path and records `quality_mode: legacy`. V2 mode validates profile, analyzes posting, reconciles questions, matches experiences, writes V2 artifacts, and records `quality_mode: v2`.

- [ ] **Step 6: Implement blocked states and CLI exits**

All `blocked_*` states return exit code 2. Existing saved status `blocked` is normalized to `blocked_conflict` on resume. State includes `blocked_stage` and a list of issue dictionaries with code, message, and artifact path.

- [ ] **Step 7: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality.py tests/test_v2_prepare.py tests/test_prepare.py tests/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```powershell
git add career_pipeline/quality.py career_pipeline/orchestrator.py career_pipeline/__main__.py tests/test_quality.py tests/test_v2_prepare.py tests/test_prepare.py tests/test_cli.py
git commit -m "feat: enforce v2 profile and posting gates"
```

---

### Task 10: V2 final-answer evidence validation

**Files:**
- Modify: `career_pipeline/models.py:52-62`
- Modify: `career_pipeline/validation.py:29-88`
- Modify: `career_pipeline/orchestrator.py:138-226`
- Test: `tests/test_v2_finalize.py`
- Modify: `tests/test_validation.py`
- Modify: `tests/test_finalize.py`

- [ ] **Step 1: Write failing V2 draft validation tests**

V2 `draft.json` entries add:

```json
{
  "question_index": 1,
  "answer": "답변",
  "experience_refs": [
    {
      "experience_id": "exp_verify",
      "claim_fields": ["budget_savings", "case_count"]
    }
  ],
  "evidence_paths": ["career.docx"]
}
```

Test that unknown experience IDs, proposed claims, missing claim fields, and an answer containing `2,000만원` when the referenced confirmed value is `1,000만원` produce validation issues.

- [ ] **Step 2: Write failing finalize report test**

Also assert that any V2 evidence-validation issue persists the run state as
`blocked_validation`, records `blocked_stage: finalize`, and returns CLI exit
code 2 without writing a final document.

Assert V2 finalize adds these lines to `07_자기소개서_검토보고서.md`:

```text
- 경험 원장: 통과
- 공고 공식성: 통과
- 경험·문항 매칭: 통과
- stale 근거: 없음
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_v2_finalize.py tests/test_validation.py tests/test_finalize.py -q
```

Expected: V2 references ignored and report lines missing.

- [ ] **Step 4: Extend draft models without breaking legacy**

```python
@dataclass(frozen=True)
class ExperienceClaimRef:
    experience_id: str
    claim_fields: tuple[str, ...]


@dataclass(frozen=True)
class DraftResponse:
    question_index: int
    answer: str
    evidence_paths: tuple[str, ...]
    experience_refs: tuple[ExperienceClaimRef, ...] = ()
```

Legacy runs may omit `experience_refs`; V2 runs require at least one per answer.

- [ ] **Step 5: Implement exact metric checks**

Build an allowed normalized-value set from the referenced confirmed claims. Extract metrics from each answer using the current fact regex and reject values whose normalized form is not allowed for the referenced claim fields. Do not reject character-limit numbers in question prompts because only answer text is scanned.

- [ ] **Step 6: Enforce interview-pack claims**

In V2 mode, scan `08_면접대비팩.md` for numeric claims and require each to appear in the union of referenced confirmed profile claims. Keep the current required-section checks.

When V2 evidence validation fails, transition to `blocked_validation`, record
`blocked_stage: finalize`, preserve the validation report as the recovery
artifact, and do not write a final document. Keep legacy failure behavior
unchanged.

- [ ] **Step 7: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_v2_finalize.py tests/test_validation.py tests/test_finalize.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```powershell
git add career_pipeline/models.py career_pipeline/validation.py career_pipeline/orchestrator.py tests/test_v2_finalize.py tests/test_validation.py tests/test_finalize.py
git commit -m "feat: validate v2 draft claims against approved facts"
```

---

### Task 11: Skill and user documentation migration

**Files:**
- Modify: `.agents/skills/career-pipeline/SKILL.md`
- Modify: `.agents/skills/career-pipeline/references/output-contract.md`
- Modify: `docs/career-pipeline-usage.md`
- Modify: `tests/test_skill_contract.py`
- Modify: `tests/test_usage_docs.py`

- [ ] **Step 1: Write failing documentation contract tests**

```python
def test_skill_documents_v2_profile_posting_and_matching_flow():
    text = Path(".agents/skills/career-pipeline/SKILL.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "profile build",
        "profile validate",
        "posting analyze",
        "blocked_profile",
        "blocked_posting",
        "03_경험직무매칭",
        "experience_refs",
    ):
        assert required in text
```

Add equivalent usage-document assertions and ensure legacy mode is explicitly labeled lower quality.

- [ ] **Step 2: Run tests and verify failure**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_skill_contract.py tests/test_usage_docs.py -q
```

Expected: new V2 terms missing.

- [ ] **Step 3: Update local skill workflow**

Document the exact order:

1. Build or refresh profile.
2. Stop for user confirmation until profile validates.
3. Analyze official posting.
4. Resolve posting blocker.
5. Run V2 prepare and read matching output.
6. Research and synthesize only from confirmed references.
7. Finalize and report complete artifacts.

The skill must forbid automatically confirming proposed claims or marking a local posting official without user attestation.

- [ ] **Step 4: Update output contract and usage guide**

Add V2 JSON examples containing `experience_refs`, state troubleshooting, URL security limits, local file attestation, legacy migration, and a complete other-company command example.

- [ ] **Step 5: Validate the skill**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe `
  'C:\Users\ehddk\.codex\skills\.system\skill-creator\scripts\quick_validate.py' `
  '.agents\skills\career-pipeline'
```

Expected: `Skill is valid!`

- [ ] **Step 6: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_skill_contract.py tests/test_usage_docs.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add .agents/skills/career-pipeline/SKILL.md .agents/skills/career-pipeline/references/output-contract.md docs/career-pipeline-usage.md tests/test_skill_contract.py tests/test_usage_docs.py
git commit -m "docs: explain career pipeline v2 workflow"
```

---

### Task 12: End-to-end V2 regression and completion audit

**Files:**
- Modify: `tests/test_hug_workspace.py`
- Create: `tests/test_v2_end_to_end.py`
- Modify: `pyproject.toml` only if pytest markers are needed; do not add runtime dependencies.

- [ ] **Step 1: Write deterministic V2 end-to-end test**

The test must create temporary evidence DOCX files, approve a generated profile fixture, use `hug_posting_excerpt.html`, create a four-question draft, run V2 prepare, write source-backed synthesis artifacts, and finalize.

```python
def test_v2_profile_posting_matching_and_finalize(tmp_path):
    profile = build_and_confirm_fixture_profile(tmp_path)
    posting = Path("tests/fixtures/hug_posting_excerpt.html").resolve()
    draft = make_four_question_draft(tmp_path / "draft.docx")

    state = prepare_run(
        tmp_path,
        "HUG 금융·기금(강원)",
        draft,
        str(posting),
        "v2-e2e",
        profile=profile,
        official_source=True,
    )

    assert state["status"] == "ready_for_research"
    write_valid_v2_synthesis(Path(state["run_dir"]))
    final = finalize_run(Path(state["run_dir"]))
    assert final["status"] == "complete"
```

- [ ] **Step 2: Extend real HUG acceptance carefully**

Keep the existing legacy acceptance assertion. Add a separate opt-in V2 acceptance path that uses the local approved profile only when `CAREER_PIPELINE_PROFILE` is set. It must not create or confirm the user's profile automatically.

- [ ] **Step 3: Run the complete suite without local acceptance variables**

```powershell
Remove-Item Env:CAREER_PIPELINE_WORKSPACE -ErrorAction SilentlyContinue
Remove-Item Env:CAREER_PIPELINE_PROFILE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all deterministic tests pass and local acceptance tests are skipped.

- [ ] **Step 4: Run current HUG legacy acceptance**

```powershell
$env:CAREER_PIPELINE_WORKSPACE='C:\Users\ehddk\OneDrive\문서\취업'
.\.venv\Scripts\python.exe -m pytest tests/test_hug_workspace.py -q
```

Expected: legacy HUG acceptance passes, detects four questions, and preserves conflict gating.

- [ ] **Step 5: Run compile, diff, and skill checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q career_pipeline
git diff --check
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe `
  'C:\Users\ehddk\.codex\skills\.system\skill-creator\scripts\quick_validate.py' `
  '.agents\skills\career-pipeline'
git status --short
```

Expected: no compile or whitespace errors, valid skill, and only intended changes before the final commit.

- [ ] **Step 6: Audit spec coverage**

Confirm with direct evidence:

- `.career_profile/` is ignored and excluded from inventory.
- Confirmed claims require valid hashes.
- Refresh never mutates confirmed profile.
- URL loader blocks private targets and oversized responses.
- Posting artifacts preserve source hash and official status.
- Matching explains score components and blocked claims.
- V2 prepare produces all new artifacts and states.
- V2 finalize rejects unsupported metrics.
- Legacy commands and current HUG run still work.
- No runtime dependency was added.

- [ ] **Step 7: Commit final regression coverage**

```powershell
git add tests/test_hug_workspace.py tests/test_v2_end_to_end.py pyproject.toml
git commit -m "test: verify career pipeline v2 end to end"
```

- [ ] **Step 8: Use verification-before-completion and finishing-a-development-branch**

Run the fresh full verification command, read its complete output, then follow `superpowers:finishing-a-development-branch`. Do not claim completion or merge while any test, skill validation, profile gate, or posting gate fails.
