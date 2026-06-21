# Career Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-local Codex workflow that inventories career documents, blocks on contradictory facts, researches current official sources, generates a validated cover letter in Markdown and DOCX, and produces an interview defense pack.

**Architecture:** A small Python package performs deterministic file inventory, extraction, fact/metric detection, conflict checks, run-state persistence, validation, and DOCX rendering. A repository-local Codex skill orchestrates the Python stages and performs official-source web research plus evidence-bounded synthesis. Every run writes immutable artifacts under `career_runs/<slug-timestamp>/` and can resume from `run.json` plus `fact_overrides.yaml`.

**Tech Stack:** Python 3.11+, dataclasses, argparse, python-docx, pypdf, openpyxl, PyYAML, pytest, repository-local Codex skills.

---

## File Map

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, pytest configuration |
| `career_pipeline/models.py` | Shared immutable data contracts |
| `career_pipeline/inventory.py` | Safe file discovery, exclusions, hashing, duplicate classification |
| `career_pipeline/extractors.py` | DOCX/PDF/XLSX/TXT/Markdown text extraction |
| `career_pipeline/questions.py` | Application-question and character-limit extraction |
| `career_pipeline/facts.py` | Evidence paragraph, metric, field, and context-token extraction |
| `career_pipeline/conflicts.py` | Experience clustering, normalized-value comparison, overrides |
| `career_pipeline/state.py` | Run directory creation, JSON/YAML persistence, resumability |
| `career_pipeline/orchestrator.py` | Prepare/finalize stage coordination |
| `career_pipeline/validation.py` | Character limit, blank response, blind-rule, organization-name, evidence checks |
| `career_pipeline/rendering.py` | Markdown and DOCX rendering |
| `career_pipeline/__main__.py` | Internal CLI used by the Codex skill |
| `.agents/skills/career-pipeline/SKILL.md` | User-facing Codex workflow |
| `.agents/skills/career-pipeline/references/output-contract.md` | Required research, strategy, draft, review, and interview formats |
| `docs/career-pipeline-usage.md` | Installation, invocation, conflict-resolution, and output guide |
| `tests/` | Focused unit and integration tests |

---

### Task 1: Package Scaffold and Shared Contracts

**Files:**
- Create: `pyproject.toml`
- Create: `career_pipeline/__init__.py`
- Create: `career_pipeline/models.py`
- Create: `career_pipeline/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

```python
# tests/test_cli.py
from career_pipeline.__main__ import build_parser


def test_parser_exposes_prepare_and_finalize_commands():
    parser = build_parser()
    prepare = parser.parse_args([
        "prepare", "--root", ".", "--target", "HUG 금융·기금",
        "--draft", "draft.docx",
    ])
    finalize = parser.parse_args(["finalize", "--run", "career_runs/sample"])

    assert prepare.command == "prepare"
    assert prepare.target == "HUG 금융·기금"
    assert finalize.command == "finalize"
```

- [ ] **Step 2: Run the test and verify the import fails**

Run: `python -m pytest tests/test_cli.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'career_pipeline'`.

- [ ] **Step 3: Add package metadata and minimal contracts**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "career-pipeline"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "python-docx>=1.1",
  "pypdf>=5.0",
  "openpyxl>=3.1",
  "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# career_pipeline/models.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class SourceRecord:
    path: Path
    relative_path: str
    extension: str
    size: int
    sha256: str
    status: Literal["use", "excluded", "duplicate", "failed"]
    reason: str = ""


@dataclass(frozen=True)
class ExtractedDocument:
    source: SourceRecord
    text: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Question:
    index: int
    prompt: str
    character_limit: int | None


@dataclass(frozen=True)
class FactClaim:
    source_path: str
    paragraph_index: int
    context: str
    field: str
    raw_value: str
    normalized_value: str
    unit_kind: str
    tokens: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Conflict:
    field: str
    claim_indexes: tuple[int, ...]
    values: tuple[str, ...]
    reason: str
```

```python
# career_pipeline/__main__.py
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--root", required=True)
    prepare.add_argument("--target", required=True)
    prepare.add_argument("--draft", required=True)
    prepare.add_argument("--posting")
    prepare.add_argument("--run-name")
    prepare.add_argument("--resume")
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    print(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the CLI test**

Run: `python -m pytest tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the scaffold**

```bash
git add pyproject.toml career_pipeline tests/test_cli.py
git commit -m "feat: scaffold career pipeline package"
```

---

### Task 2: Safe Inventory, Exclusions, and Duplicate Detection

**Files:**
- Create: `career_pipeline/inventory.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Write failing inventory tests**

```python
# tests/test_inventory.py
from pathlib import Path

from career_pipeline.inventory import build_inventory


def test_inventory_excludes_sensitive_paths_without_reading_them_and_marks_duplicates(tmp_path: Path, monkeypatch):
    (tmp_path / "경험정리").mkdir()
    (tmp_path / "학교성적").mkdir()
    (tmp_path / "경험정리" / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "경험정리" / "b.txt").write_text("same", encoding="utf-8")
    (tmp_path / "학교성적" / "grade.txt").write_text("private", encoding="utf-8")
    (tmp_path / "Chrome 비밀번호.csv").write_text("secret", encoding="utf-8")

    from career_pipeline import inventory
    original_digest = inventory._digest

    def guarded_digest(path):
        assert "Chrome 비밀번호" not in path.name
        assert "학교성적" not in path.parts
        return original_digest(path)

    monkeypatch.setattr(inventory, "_digest", guarded_digest)
    records = build_inventory(tmp_path)
    statuses = {record.relative_path: record.status for record in records}

    assert statuses["학교성적/grade.txt"] == "excluded"
    assert statuses["Chrome 비밀번호.csv"] == "excluded"
    assert sorted(statuses[path] for path in ["경험정리/a.txt", "경험정리/b.txt"]) == [
        "duplicate", "use"
    ]
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest tests/test_inventory.py -v`

Expected: FAIL because `career_pipeline.inventory` does not exist.

- [ ] **Step 3: Implement deterministic inventory rules**

```python
# career_pipeline/inventory.py
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from .models import SourceRecord


SUPPORTED = {".docx", ".pdf", ".xlsx", ".txt", ".md"}
EXCLUDED_DIRS = {"학교성적", "자격증", "경력증명서", ".git", "career_runs"}
EXCLUDED_NAMES = {"Chrome 비밀번호.csv"}


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_inventory(root: Path) -> list[SourceRecord]:
    pending: list[SourceRecord] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        excluded = path.name in EXCLUDED_NAMES or any(part in EXCLUDED_DIRS for part in path.parts)
        supported = path.suffix.lower() in SUPPORTED
        status = "excluded" if excluded or not supported else "use"
        reason = "sensitive/default exclusion" if excluded else ("unsupported" if not supported else "")
        digest = "" if status == "excluded" else _digest(path)
        pending.append(SourceRecord(
            path=path,
            relative_path=relative,
            extension=path.suffix.lower(),
            size=path.stat().st_size,
            sha256=digest,
            status=status,
            reason=reason,
        ))

    by_hash: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(pending):
        if record.status == "use":
            by_hash[record.sha256].append(index)
    for indexes in by_hash.values():
        for index in indexes[1:]:
            record = pending[index]
            pending[index] = SourceRecord(**{
                **record.__dict__, "status": "duplicate", "reason": "same SHA-256"
            })
    return pending
```

- [ ] **Step 4: Run inventory tests**

Run: `python -m pytest tests/test_inventory.py -v`

Expected: PASS.

- [ ] **Step 5: Commit inventory support**

```bash
git add career_pipeline/inventory.py tests/test_inventory.py
git commit -m "feat: inventory career files safely"
```

---

### Task 3: Multi-Format Text Extraction

**Files:**
- Create: `career_pipeline/extractors.py`
- Test: `tests/test_extractors.py`

- [ ] **Step 1: Write failing DOCX, XLSX, and text extraction tests**

```python
# tests/test_extractors.py
from pathlib import Path

from docx import Document
from openpyxl import Workbook

from career_pipeline.extractors import extract_path
from career_pipeline.models import SourceRecord


def record(path: Path) -> SourceRecord:
    return SourceRecord(path, path.name, path.suffix.lower(), path.stat().st_size, "hash", "use")


def test_extracts_docx_paragraphs(tmp_path: Path):
    path = tmp_path / "draft.docx"
    doc = Document()
    doc.add_paragraph("첫 번째 문항")
    doc.add_paragraph("답변 내용")
    doc.save(path)
    result = extract_path(record(path))
    assert result.paragraphs == ("첫 번째 문항", "답변 내용")


def test_extracts_xlsx_cells_and_text(tmp_path: Path):
    path = tmp_path / "interview.xlsx"
    workbook = Workbook()
    workbook.active["B2"] = "면접 전략"
    workbook.active["C4"] = "지원동기"
    workbook.save(path)
    result = extract_path(record(path))
    assert "면접 전략" in result.text
    assert "지원동기" in result.text


def test_extracts_utf8_text(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("경험 근거", encoding="utf-8")
    assert extract_path(record(path)).text == "경험 근거"
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run: `python -m pytest tests/test_extractors.py -v`

Expected: FAIL because `career_pipeline.extractors` does not exist.

- [ ] **Step 3: Implement format dispatch and extraction**

```python
# career_pipeline/extractors.py
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from .models import ExtractedDocument, SourceRecord


def _docx(path):
    document = Document(path)
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if text:
                paragraphs.append(text)
    return paragraphs


def _pdf(path):
    return [text for page in PdfReader(path).pages if (text := (page.extract_text() or "").strip())]


def _xlsx(path):
    workbook = load_workbook(path, read_only=False, data_only=False)
    paragraphs = []
    for sheet in workbook.worksheets:
        paragraphs.append(f"[시트] {sheet.title}")
        for row in sheet.iter_rows():
            values = [str(cell.value).strip() for cell in row if cell.value not in (None, "")]
            if values:
                paragraphs.append(" | ".join(values))
    return paragraphs


def extract_path(source: SourceRecord) -> ExtractedDocument:
    suffix = source.extension
    if suffix == ".docx":
        paragraphs = _docx(source.path)
    elif suffix == ".pdf":
        paragraphs = _pdf(source.path)
    elif suffix == ".xlsx":
        paragraphs = _xlsx(source.path)
    elif suffix in {".txt", ".md"}:
        paragraphs = [source.path.read_text(encoding="utf-8-sig").strip()]
    else:
        raise ValueError(f"unsupported extension: {suffix}")
    clean = tuple(paragraph for paragraph in paragraphs if paragraph)
    return ExtractedDocument(source, "\n".join(clean), clean)
```

- [ ] **Step 4: Add a PDF dispatch test without generating a text PDF**

```python
def test_rejects_unsupported_file(tmp_path: Path):
    path = tmp_path / "image.jpg"
    path.write_bytes(b"jpg")
    try:
        extract_path(record(path))
    except ValueError as error:
        assert "unsupported extension" in str(error)
    else:
        raise AssertionError("unsupported file was accepted")
```

- [ ] **Step 5: Run extraction tests**

Run: `python -m pytest tests/test_extractors.py -v`

Expected: PASS.

- [ ] **Step 6: Commit extraction support**

```bash
git add career_pipeline/extractors.py tests/test_extractors.py
git commit -m "feat: extract career document formats"
```

---

### Task 4: Application Questions and Fact Candidates

**Files:**
- Create: `career_pipeline/questions.py`
- Create: `career_pipeline/facts.py`
- Test: `tests/test_questions.py`
- Test: `tests/test_facts.py`

- [ ] **Step 1: Write failing question extraction tests**

```python
# tests/test_questions.py
from career_pipeline.questions import extract_questions


def test_extracts_four_questions_and_character_limits():
    paragraphs = (
        "우리 공사 체험형 인턴에 지원하게 된 동기를 기술해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
        "HUG의 주요 사업 중 관심 있는 1가지를 선택해 주십시오.",
        "0/600 (글자 수, 공백 포함)",
    )
    questions = extract_questions(paragraphs)
    assert [question.character_limit for question in questions] == [600, 600]
    assert questions[0].prompt.startswith("우리 공사")
```

- [ ] **Step 2: Write failing fact candidate tests**

```python
# tests/test_facts.py
from career_pipeline.facts import extract_fact_claims
from career_pipeline.models import ExtractedDocument, SourceRecord
from pathlib import Path


def test_extracts_budget_savings_and_case_count():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        ("의료인력 숙박비를 검증해 허위 거래 20건을 적발하고 예산 4천만원을 줄였습니다.",),
    )
    claims = extract_fact_claims([document])
    assert {(claim.field, claim.normalized_value) for claim in claims} >= {
        ("case_count", "20건"),
        ("budget_savings", "40000000원"),
    }
```

- [ ] **Step 3: Run both test files and verify failure**

Run: `python -m pytest tests/test_questions.py tests/test_facts.py -v`

Expected: FAIL because the modules do not exist.

- [ ] **Step 4: Implement question extraction**

```python
# career_pipeline/questions.py
import re

from .models import Question


LIMIT = re.compile(r"(?:0\s*/\s*)?(\d{2,4})\s*자")
QUESTION_HINT = re.compile(r"(?:기술|작성|설명|서술|말씀).*?(?:주십시오|주세요|하시오)|\?$" )


def extract_questions(paragraphs: tuple[str, ...]) -> list[Question]:
    questions: list[Question] = []
    pending: str | None = None
    for paragraph in paragraphs:
        limit = LIMIT.search(paragraph)
        if limit and pending:
            questions.append(Question(len(questions) + 1, pending, int(limit.group(1))))
            pending = None
        elif QUESTION_HINT.search(paragraph):
            if pending:
                questions.append(Question(len(questions) + 1, pending, None))
            pending = paragraph
    if pending:
        questions.append(Question(len(questions) + 1, pending, None))
    return questions
```

- [ ] **Step 5: Implement metric normalization and fact extraction**

```python
# career_pipeline/facts.py
import re

from .models import ExtractedDocument, FactClaim


METRIC = re.compile(r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>억\s*원|천만\s*원|만\s*원|원|건|명|%|페이지|일|주|개월|년)")
TOKEN = re.compile(r"[가-힣A-Za-z]{2,}")
STOPWORDS = {"경험", "당시", "결과", "통해", "했습니다", "있습니다", "업무", "대한"}


def _normalize(number: str, unit: str) -> tuple[str, str]:
    value = float(number.replace(",", ""))
    compact = unit.replace(" ", "")
    if compact == "억원":
        return f"{int(value * 100_000_000)}원", "money"
    if compact == "천만원":
        return f"{int(value * 10_000_000)}원", "money"
    if compact == "만원":
        return f"{int(value * 10_000)}원", "money"
    return f"{number.replace(',', '')}{compact}", "percentage" if compact == "%" else compact


def _field(context: str, unit_kind: str) -> str:
    if any(word in context for word in ("절감", "예산", "누수", "낭비", "지켜")) and unit_kind in {"money", "percentage"}:
        return "budget_savings"
    if unit_kind == "건" and any(word in context for word in ("적발", "발견", "확인", "처리")):
        return "case_count"
    if unit_kind in {"일", "주", "개월", "년"}:
        return "duration"
    return f"metric:{unit_kind}"


def extract_fact_claims(documents: list[ExtractedDocument]) -> list[FactClaim]:
    claims = []
    for document in documents:
        for paragraph_index, context in enumerate(document.paragraphs):
            tokens = frozenset(token for token in TOKEN.findall(context) if token not in STOPWORDS)
            for match in METRIC.finditer(context):
                normalized, unit_kind = _normalize(match.group("number"), match.group("unit"))
                claims.append(FactClaim(
                    document.source.relative_path,
                    paragraph_index,
                    context,
                    _field(context, unit_kind),
                    match.group(0),
                    normalized,
                    unit_kind,
                    tokens,
                ))
    return claims
```

- [ ] **Step 6: Run question and fact tests**

Run: `python -m pytest tests/test_questions.py tests/test_facts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit structured intake**

```bash
git add career_pipeline/questions.py career_pipeline/facts.py tests/test_questions.py tests/test_facts.py
git commit -m "feat: structure questions and fact claims"
```

---

### Task 5: Conflict Detection and Explicit Overrides

**Files:**
- Create: `career_pipeline/conflicts.py`
- Test: `tests/test_conflicts.py`

- [ ] **Step 1: Write failing conflict tests**

```python
# tests/test_conflicts.py
from pathlib import Path

from career_pipeline.conflicts import apply_overrides, detect_conflicts
from career_pipeline.models import FactClaim


def claim(path, value, unit, context):
    return FactClaim(path, 0, context, "budget_savings", value, value, unit, frozenset({
        "서울시청", "숙박비", "의료인력", "검증", "예산"
    }))


def test_detects_same_experience_with_different_savings_values():
    claims = [
        claim("a.docx", "40000000원", "money", "서울시청 의료인력 숙박비 검증으로 예산 4천만원 절감"),
        claim("b.docx", "100000000원", "money", "서울시청 의료인력 숙박비 검증으로 예산 1억 원 방지"),
        claim("c.docx", "40%", "percentage", "서울시청 의료인력 숙박비 검증으로 예산 40% 절감"),
    ]
    conflicts = detect_conflicts(claims)
    assert len(conflicts) == 1
    assert set(conflicts[0].values) == {"40000000원", "100000000원", "40%"}


def test_explicit_override_resolves_only_matching_conflict(tmp_path: Path):
    claims = [
        claim("a.docx", "40000000원", "money", "서울시청 의료인력 숙박비 검증으로 예산 4천만원 절감"),
        claim("b.docx", "100000000원", "money", "서울시청 의료인력 숙박비 검증으로 예산 1억 원 방지"),
    ]
    overrides = {"budget_savings:서울시청|숙박비": "40000000원"}
    resolved = apply_overrides(claims, overrides)
    assert [item.normalized_value for item in resolved] == ["40000000원"]
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run: `python -m pytest tests/test_conflicts.py -v`

Expected: FAIL because `career_pipeline.conflicts` does not exist.

- [ ] **Step 3: Implement similarity grouping and overrides**

```python
# career_pipeline/conflicts.py
from collections import defaultdict
from dataclasses import replace

from .models import Conflict, FactClaim


def _similar(left: FactClaim, right: FactClaim) -> bool:
    shared = left.tokens & right.tokens
    return left.field == right.field and len(shared) >= 3


def _cluster(claims: list[FactClaim]) -> list[list[int]]:
    groups: list[list[int]] = []
    for index, claim in enumerate(claims):
        for group in groups:
            if any(_similar(claim, claims[member]) for member in group):
                group.append(index)
                break
        else:
            groups.append([index])
    return groups


def detect_conflicts(claims: list[FactClaim]) -> list[Conflict]:
    conflicts = []
    for group in _cluster(claims):
        values = sorted({claims[index].normalized_value for index in group})
        if len(values) > 1:
            conflicts.append(Conflict(
                claims[group[0]].field,
                tuple(group),
                tuple(values),
                "same field and overlapping experience context have different values",
            ))
    return conflicts


def override_key(claim: FactClaim) -> str:
    anchors = sorted(claim.tokens)[:2]
    return f"{claim.field}:{'|'.join(anchors)}"


def apply_overrides(claims: list[FactClaim], overrides: dict[str, str]) -> list[FactClaim]:
    accepted = []
    for claim in claims:
        expected = overrides.get(override_key(claim))
        if expected is None or claim.normalized_value == expected:
            accepted.append(claim)
    return accepted
```

- [ ] **Step 4: Refine the override key test to use the generated key**

```python
from career_pipeline.conflicts import override_key

# Replace the hard-coded overrides assignment with:
overrides = {override_key(claims[0]): "40000000원"}
```

- [ ] **Step 5: Run conflict tests**

Run: `python -m pytest tests/test_conflicts.py -v`

Expected: PASS.

- [ ] **Step 6: Commit conflict blocking**

```bash
git add career_pipeline/conflicts.py tests/test_conflicts.py
git commit -m "feat: block conflicting career facts"
```

---

### Task 6: Run State and Prepare Orchestration

**Files:**
- Create: `career_pipeline/state.py`
- Create: `career_pipeline/orchestrator.py`
- Modify: `career_pipeline/__main__.py`
- Test: `tests/test_prepare.py`

- [ ] **Step 1: Write a failing blocked-run integration test**

```python
# tests/test_prepare.py
from pathlib import Path
from docx import Document
import yaml

from career_pipeline.conflicts import override_key
from career_pipeline.extractors import extract_path
from career_pipeline.facts import extract_fact_claims
from career_pipeline.inventory import build_inventory
from career_pipeline.orchestrator import prepare_run


def write_docx(path: Path, text: str):
    document = Document()
    document.add_paragraph(text)
    document.save(path)


def test_prepare_writes_artifacts_and_blocks_on_conflict(tmp_path: Path):
    write_docx(tmp_path / "a.docx", "서울시청 의료인력 숙박비 검증으로 예산 4천만원을 줄였습니다.")
    write_docx(tmp_path / "b.docx", "서울시청 의료인력 숙박비 검증으로 예산 1억 원을 지켰습니다.")
    write_docx(tmp_path / "draft.docx", "지원동기를 작성해 주십시오.\n0/600 (글자 수, 공백 포함)")

    state = prepare_run(tmp_path, "HUG 금융·기금", tmp_path / "draft.docx", None, "test")

    assert state["status"] == "blocked"
    assert Path(state["run_dir"], "01_자료목록.md").exists()
    assert Path(state["run_dir"], "02_사실원장.json").exists()
    assert Path(state["run_dir"], "03_충돌검사.md").exists()
    assert not Path(state["run_dir"], "06_자기소개서.md").exists()

    documents = [
        extract_path(item) for item in build_inventory(tmp_path) if item.status == "use"
    ]
    claims = extract_fact_claims(documents)
    savings = next(item for item in claims if item.field == "budget_savings")
    run_dir = Path(state["run_dir"])
    (run_dir / "fact_overrides.yaml").write_text(
        yaml.safe_dump({override_key(savings): "40000000원"}, allow_unicode=True),
        encoding="utf-8",
    )
    resumed = prepare_run(
        tmp_path, "HUG 금융·기금", tmp_path / "draft.docx", None, "test", run_dir
    )
    assert resumed["run_dir"] == str(run_dir)
    assert resumed["status"] == "ready_for_research"
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python -m pytest tests/test_prepare.py -v`

Expected: FAIL because orchestration does not exist.

- [ ] **Step 3: Implement JSON-safe state persistence**

```python
# career_pipeline/state.py
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import re


def resolve_run_dir(root: Path, target: str, run_name: str | None, resume: Path | None) -> Path:
    if resume:
        path = resume.resolve()
        if not (path / "run.json").exists():
            raise FileNotFoundError(f"resume run.json not found: {path}")
        return path
    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", run_name or target).strip("-")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = root / "career_runs" / f"{slug}-{stamp}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_state(run_dir: Path, state: dict) -> None:
    write_json(run_dir / "run.json", state)
```

- [ ] **Step 4: Implement prepare orchestration and reports**

```python
# career_pipeline/orchestrator.py
from dataclasses import asdict
from pathlib import Path
import yaml

from .conflicts import apply_overrides, detect_conflicts, override_key
from .extractors import extract_path
from .facts import extract_fact_claims
from .inventory import build_inventory
from .questions import extract_questions
from .state import resolve_run_dir, write_json, write_state


def _inventory_markdown(records):
    lines = ["# 자료 목록", "", "| 상태 | 파일 | 사유 |", "|---|---|---|"]
    lines.extend(f"| {item.status} | {item.relative_path} | {item.reason} |" for item in records)
    return "\n".join(lines) + "\n"


def _conflict_markdown(conflicts, claims):
    lines = ["# 충돌 검사", ""]
    for number, conflict in enumerate(conflicts, 1):
        lines.extend([f"## 충돌 {number}: {conflict.field}", f"값: {', '.join(conflict.values)}"])
        for index in conflict.claim_indexes:
            claim = claims[index]
            lines.append(f"- `{claim.source_path}`: {claim.context}")
        lines.append(f"- override key: `{override_key(claims[conflict.claim_indexes[0]])}`")
        lines.append("- 확인 질문: 실제 제출에 사용할 값과 근거 파일을 지정해 주세요.")
    return "\n".join(lines) + "\n"


def prepare_run(
    root: Path,
    target: str,
    draft: Path,
    posting: str | None,
    run_name: str | None,
    resume: Path | None = None,
):
    run_dir = resolve_run_dir(root, target, run_name, resume)
    inventory = build_inventory(root)
    documents = []
    for source in inventory:
        if source.status == "use":
            try:
                documents.append(extract_path(source))
            except Exception:
                continue
    claims = extract_fact_claims(documents)
    override_path = run_dir / "fact_overrides.yaml"
    overrides = yaml.safe_load(override_path.read_text(encoding="utf-8")) if override_path.exists() else {}
    accepted = apply_overrides(claims, overrides or {})
    conflicts = detect_conflicts(accepted)
    draft_record = next(item for item in inventory if item.path.resolve() == draft.resolve())
    questions = extract_questions(extract_path(draft_record).paragraphs)

    (run_dir / "01_자료목록.md").write_text(_inventory_markdown(inventory), encoding="utf-8")
    fact_payload = []
    for claim in claims:
        item = asdict(claim)
        item["tokens"] = sorted(claim.tokens)
        fact_payload.append(item)
    write_json(run_dir / "02_사실원장.json", fact_payload)
    (run_dir / "03_충돌검사.md").write_text(_conflict_markdown(conflicts, claims), encoding="utf-8")
    state = {
        "status": "blocked" if conflicts else "ready_for_research",
        "run_dir": str(run_dir),
        "root": str(root),
        "target": target,
        "draft": str(draft),
        "posting": posting,
        "questions": [asdict(question) for question in questions],
        "conflict_count": len(conflicts),
    }
    write_state(run_dir, state)
    return state
```

- [ ] **Step 5: Wire the prepare command**

```python
# career_pipeline/__main__.py: replace main()
from pathlib import Path
from .orchestrator import prepare_run


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "prepare":
        state = prepare_run(
            Path(args.root).resolve(),
            args.target,
            Path(args.draft).resolve(),
            args.posting,
            args.run_name,
            Path(args.resume).resolve() if args.resume else None,
        )
        print(state["run_dir"])
        return 2 if state["status"] == "blocked" else 0
    build_parser().error("finalize requires the synthesis artifacts created in Task 8")
```

- [ ] **Step 6: Run prepare tests**

Run: `python -m pytest tests/test_prepare.py -v`

Expected: PASS.

- [ ] **Step 7: Commit prepare orchestration**

```bash
git add career_pipeline/state.py career_pipeline/orchestrator.py career_pipeline/__main__.py tests/test_prepare.py
git commit -m "feat: prepare resumable career runs"
```

---

### Task 7: Draft Validation Contracts

**Files:**
- Modify: `career_pipeline/models.py`
- Create: `career_pipeline/validation.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: Add the draft response contract in the test**

```python
# tests/test_validation.py
from career_pipeline.models import DraftResponse, Question
from career_pipeline.validation import validate_draft


def test_validation_finds_empty_over_limit_blind_and_wrong_org_answers():
    questions = [Question(1, "지원동기", 20), Question(2, "문제해결", 10)]
    responses = [
        DraftResponse(1, "HUG에서 서울대학교 경험을 살려 기여하겠습니다.", ("경험정리/a.docx",)),
        DraftResponse(2, "", ()),
    ]
    issues = validate_draft(
        questions, responses, target_org="HUG", known_sources={"경험정리/a.docx"}
    )
    codes = {issue.code for issue in issues}
    assert {"over_limit", "blind_term", "empty_answer"} <= codes


def test_validation_flags_other_organization_name():
    questions = [Question(1, "지원동기", 100)]
    responses = [DraftResponse(1, "한국주택금융공사에서 일하고 싶습니다.", ("a.docx",))]
    issues = validate_draft(questions, responses, target_org="HUG", known_sources={"a.docx"})
    assert "other_organization" in {issue.code for issue in issues}


def test_validation_requires_known_evidence_paths():
    questions = [Question(1, "지원동기", 100)]
    responses = [DraftResponse(1, "검증 가능한 답변입니다.", ("없는파일.docx",))]
    issues = validate_draft(questions, responses, target_org="HUG", known_sources={"근거.docx"})
    assert "unknown_evidence" in {issue.code for issue in issues}
```

- [ ] **Step 2: Run and verify missing contracts**

Run: `python -m pytest tests/test_validation.py -v`

Expected: FAIL importing `DraftResponse`.

- [ ] **Step 3: Add draft and issue models**

```python
# career_pipeline/models.py
@dataclass(frozen=True)
class DraftResponse:
    question_index: int
    answer: str
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    question_index: int
    message: str
```

- [ ] **Step 4: Implement deterministic validation**

```python
# career_pipeline/validation.py
from .models import DraftResponse, Question, ValidationIssue


BLIND_TERMS = ("대학교", "대학원", "출신지역", "생년월일", "가족관계")
KNOWN_ORGANIZATIONS = ("국민연금공단", "국민건강보험공단", "한국주택금융공사", "서울교통공사", "IBK기업은행")


def validate_draft(questions, responses, target_org, known_sources):
    by_index = {item.question_index: item.answer.strip() for item in responses}
    issues = []
    for question in questions:
        answer = by_index.get(question.index, "")
        if not answer:
            issues.append(ValidationIssue("empty_answer", question.index, "답변이 비어 있습니다."))
            continue
        if question.character_limit and len(answer) > question.character_limit:
            issues.append(ValidationIssue("over_limit", question.index, f"{len(answer)}/{question.character_limit}자"))
        response = next(item for item in responses if item.question_index == question.index)
        if not response.evidence_paths:
            issues.append(ValidationIssue("missing_evidence", question.index, "근거 파일이 없습니다."))
        for path in response.evidence_paths:
            if path not in known_sources:
                issues.append(ValidationIssue("unknown_evidence", question.index, f"사실 원장에 없는 근거: {path}"))
        for term in BLIND_TERMS:
            if term in answer:
                issues.append(ValidationIssue("blind_term", question.index, f"블라인드 위험 표현: {term}"))
        for organization in KNOWN_ORGANIZATIONS:
            if organization not in target_org and organization in answer:
                issues.append(ValidationIssue("other_organization", question.index, f"타기관명: {organization}"))
    return issues
```

- [ ] **Step 5: Run validation tests**

Run: `python -m pytest tests/test_validation.py -v`

Expected: PASS.

- [ ] **Step 6: Commit validation rules**

```bash
git add career_pipeline/models.py career_pipeline/validation.py tests/test_validation.py
git commit -m "feat: validate cover letter constraints"
```

---

### Task 8: Markdown, DOCX, Review, and Finalize Stage

**Files:**
- Create: `career_pipeline/rendering.py`
- Modify: `career_pipeline/orchestrator.py`
- Modify: `career_pipeline/__main__.py`
- Test: `tests/test_rendering.py`
- Test: `tests/test_finalize.py`

- [ ] **Step 1: Write failing rendering tests**

```python
# tests/test_rendering.py
from docx import Document

from career_pipeline.models import DraftResponse, Question
from career_pipeline.rendering import render_draft_markdown, render_draft_docx


def test_markdown_and_docx_contain_all_questions(tmp_path):
    questions = [Question(1, "지원동기", 600), Question(2, "문제해결", 600)]
    responses = [
        DraftResponse(1, "지원 답변", ("경험정리/a.docx",)),
        DraftResponse(2, "개선 답변", ("경험정리/b.docx",)),
    ]
    markdown = render_draft_markdown(questions, responses)
    output = tmp_path / "draft.docx"
    render_draft_docx(questions, responses, output)

    assert "## 1. 지원동기" in markdown
    assert "개선 답변" in markdown
    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert "지원 답변" in text
    assert "개선 답변" in text
```

- [ ] **Step 2: Write a failing finalize test**

```python
# tests/test_finalize.py
import json
from pathlib import Path

from career_pipeline.orchestrator import finalize_run


def test_finalize_requires_research_strategy_draft_and_interview(tmp_path: Path):
    (tmp_path / "run.json").write_text(json.dumps({
        "status": "ready_for_research",
        "target": "HUG",
        "questions": [{"index": 1, "prompt": "지원동기", "character_limit": 600}],
    }), encoding="utf-8")
    (tmp_path / "draft.json").write_text(json.dumps([
        {
            "question_index": 1,
            "answer": "검증 가능한 지원 답변",
            "evidence_paths": ["경험정리/a.docx"]
        }
    ], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "02_사실원장.json").write_text(json.dumps([
        {"source_path": "경험정리/a.docx"}
    ], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "04_기업직무조사.md").write_text(
        "# 조사\n\n[HUG 공식 홈페이지](https://www.khug.or.kr/)\n", encoding="utf-8"
    )
    (tmp_path / "05_문항전략.md").write_text("# 전략\n", encoding="utf-8")
    (tmp_path / "08_면접대비팩.md").write_text(
        "# 면접대비팩\n\n## 1분 자기소개\n## 꼬리질문\n## 압박질문\n## 근거\n",
        encoding="utf-8",
    )

    state = finalize_run(tmp_path)
    assert state["status"] == "complete"
    assert (tmp_path / "06_자기소개서.md").exists()
    assert (tmp_path / "06_자기소개서.docx").exists()
    assert (tmp_path / "07_자기소개서_검토보고서.md").exists()
```

- [ ] **Step 3: Run tests and verify missing implementation**

Run: `python -m pytest tests/test_rendering.py tests/test_finalize.py -v`

Expected: FAIL because rendering and finalize do not exist.

- [ ] **Step 4: Implement Markdown and DOCX rendering**

```python
# career_pipeline/rendering.py
from pathlib import Path
from docx import Document
from docx.shared import Pt


def render_draft_markdown(questions, responses):
    by_index = {item.question_index: item.answer for item in responses}
    chunks = ["# 자기소개서", ""]
    for question in questions:
        chunks.extend([
            f"## {question.index}. {question.prompt}",
            f"제한: {question.character_limit or '미지정'}자",
            "",
            by_index.get(question.index, ""),
            "",
        ])
    return "\n".join(chunks)


def render_draft_docx(questions, responses, output: Path):
    by_index = {item.question_index: item.answer for item in responses}
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(10.5)
    document.add_heading("자기소개서", level=0)
    for question in questions:
        document.add_heading(f"{question.index}. {question.prompt}", level=1)
        document.add_paragraph(f"제한: {question.character_limit or '미지정'}자")
        document.add_paragraph(by_index.get(question.index, ""))
    document.save(output)
```

- [ ] **Step 5: Implement finalize orchestration**

```python
# career_pipeline/orchestrator.py additions
import json
from .models import DraftResponse, Question, ValidationIssue
from .rendering import render_draft_docx, render_draft_markdown
from .validation import validate_draft


def finalize_run(run_dir: Path):
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    required = ["04_기업직무조사.md", "05_문항전략.md", "08_면접대비팩.md", "draft.json"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing synthesis artifacts: {', '.join(missing)}")
    questions = [Question(**item) for item in state["questions"]]
    draft_data = json.loads((run_dir / "draft.json").read_text(encoding="utf-8"))
    responses = [DraftResponse(
        item["question_index"], item["answer"], tuple(item.get("evidence_paths", []))
    ) for item in draft_data]
    fact_data = json.loads((run_dir / "02_사실원장.json").read_text(encoding="utf-8"))
    known_sources = {item["source_path"] for item in fact_data}
    issues = validate_draft(questions, responses, state["target"], known_sources)
    research = (run_dir / "04_기업직무조사.md").read_text(encoding="utf-8")
    if "http://" not in research and "https://" not in research:
        issues.append(ValidationIssue("missing_research_link", 0, "공식 조사 링크가 없습니다."))
    interview = (run_dir / "08_면접대비팩.md").read_text(encoding="utf-8")
    for section in ("1분 자기소개", "꼬리질문", "압박질문", "근거"):
        if section not in interview:
            issues.append(ValidationIssue("missing_interview_section", 0, f"면접팩 누락: {section}"))
    if issues:
        state.update(status="blocked_validation", validation_issues=[asdict(item) for item in issues])
        write_state(run_dir, state)
        return state
    markdown = render_draft_markdown(questions, responses)
    (run_dir / "06_자기소개서.md").write_text(markdown, encoding="utf-8")
    render_draft_docx(questions, responses, run_dir / "06_자기소개서.docx")
    review_lines = ["# 자기소개서 검토보고서", ""]
    for question, response in zip(questions, responses, strict=True):
        review_lines.append(
            f"- 문항 {question.index}: {len(response.answer)}/{question.character_limit or '미지정'}자, "
            f"근거 {len(response.evidence_paths)}개"
        )
    review_lines.extend(["- 블라인드: 통과", "- 타기관명: 통과", "- 빈 답변: 없음"])
    (run_dir / "07_자기소개서_검토보고서.md").write_text(
        "\n".join(review_lines) + "\n", encoding="utf-8"
    )
    state["status"] = "complete"
    write_state(run_dir, state)
    return state
```

- [ ] **Step 6: Wire the finalize CLI command**

```python
# career_pipeline/__main__.py
from .orchestrator import finalize_run, prepare_run

# inside main()
if args.command == "finalize":
    state = finalize_run(Path(args.run).resolve())
    print(state["status"])
    return 0 if state["status"] == "complete" else 3
```

- [ ] **Step 7: Run rendering and finalize tests**

Run: `python -m pytest tests/test_rendering.py tests/test_finalize.py -v`

Expected: PASS.

- [ ] **Step 8: Commit finalization support**

```bash
git add career_pipeline/rendering.py career_pipeline/orchestrator.py career_pipeline/__main__.py tests/test_rendering.py tests/test_finalize.py
git commit -m "feat: render and validate career outputs"
```

---

### Task 9: Repository-Local Codex Skill

**Files:**
- Create: `.agents/skills/career-pipeline/SKILL.md`
- Create: `.agents/skills/career-pipeline/references/output-contract.md`
- Test: `tests/test_skill_contract.py`

- [ ] **Step 1: Write a failing skill-contract test**

```python
# tests/test_skill_contract.py
from pathlib import Path


def test_skill_requires_prepare_conflict_gate_official_research_and_finalize():
    text = Path(".agents/skills/career-pipeline/SKILL.md").read_text(encoding="utf-8")
    for required in [
        "python -m career_pipeline prepare",
        "03_충돌검사.md",
        "공식 출처",
        "draft.json",
        "08_면접대비팩.md",
        "python -m career_pipeline finalize",
    ]:
        assert required in text
```

- [ ] **Step 2: Run the test and verify the skill is missing**

Run: `python -m pytest tests/test_skill_contract.py -v`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Write the Codex skill workflow**

```markdown
---
name: career-pipeline
description: 취업 폴더의 자기소개서와 경험 자료를 분석하고 최신 공식 자료조사, 자기소개서, 검토보고서, 면접팩을 한 번에 생성한다.
---

# Career Pipeline

## Trigger

Use this skill when the user requests end-to-end job-application analysis, company research, cover-letter drafting, or interview preparation from local career files.

## Required flow

1. Identify target organization/role, posting URL or file, and current draft.
2. Run `python -m career_pipeline prepare --root "<workspace>" --target "<target>" --draft "<draft>" [--posting "<posting>"]`.
3. Read the returned run directory and `run.json`.
4. If status is `blocked`, read `03_충돌검사.md`, ask only the listed confirmation questions, write accepted values to `fact_overrides.yaml`, and rerun `python -m career_pipeline prepare` with the same arguments plus `--resume "<run-dir>"`. Do not draft before resolution.
5. Research the current posting and organization every run. Prefer the original posting, official organization pages, ALIO/government disclosures, regulations, and official reports. Record direct links in `04_기업직무조사.md`.
6. Read `02_사실원장.json`, confirmed overrides, questions, and research. Write `05_문항전략.md` using only confirmed facts.
7. Write `draft.json` exactly as specified in `references/output-contract.md`. Never invent metrics, dates, duties, awards, or credentials.
8. Write `08_면접대비팩.md` from the final claims: 30/60/90-second answers, follow-ups, pressure questions, and source-backed defense notes.
9. Run `python -m career_pipeline finalize --run "<run-dir>"`.
10. If validation blocks, fix only the reported answers and rerun finalize. Report the final artifact paths.

## Privacy

Never read excluded sensitive files unless the user explicitly names a required file. Never put personal data into web queries, URLs, logs, or research artifacts.
```

- [ ] **Step 4: Write the synthesis output contract**

```markdown
# Output Contract

## `04_기업직무조사.md`

For every material claim include an inline Markdown link to the official source. Separate confirmed facts from `[확인 필요]` items.

## `05_문항전략.md`

For each question include classification, selected experience, evidence paths, core message, organization connection, and missing evidence.

## `draft.json`

```json
[
  {
    "question_index": 1,
    "answer": "공백 포함 제한 글자 수 이내의 답변",
    "evidence_paths": ["경험정리/근거문서.docx"]
  }
]
```

Use only confirmed facts from `02_사실원장.json` and `fact_overrides.yaml`. Every response must list one or more exact `source_path` values from the fact ledger.

## `08_면접대비팩.md`

Include a one-minute introduction, question-by-question 30/60/90-second answers, at least three follow-up questions per material claim, pressure questions for metrics/roles, and the exact local evidence file for every defense note.
```

- [ ] **Step 5: Run the skill-contract test**

Run: `python -m pytest tests/test_skill_contract.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the Codex skill**

```bash
git add .agents/skills/career-pipeline tests/test_skill_contract.py
git commit -m "feat: add career pipeline Codex skill"
```

---

### Task 10: Usage Documentation and Resume Workflow

**Files:**
- Create: `docs/career-pipeline-usage.md`
- Test: `tests/test_usage_docs.py`

- [ ] **Step 1: Write a failing documentation smoke test**

```python
# tests/test_usage_docs.py
from pathlib import Path


def test_usage_documents_natural_language_conflicts_resume_and_outputs():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in [
        "자연어 호출",
        "fact_overrides.yaml",
        "재개",
        "06_자기소개서.docx",
        "08_면접대비팩.md",
    ]:
        assert required in text
```

- [ ] **Step 2: Run and verify documentation is missing**

Run: `python -m pytest tests/test_usage_docs.py -v`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Write the usage guide**

The guide must contain these concrete sections and examples:

```markdown
# Career Pipeline 사용법

## 자연어 호출

`HUG 공고와 현재 자소서를 기준으로 자료조사부터 면접팩까지 실행해줘.`

## 명시적 호출

```text
$career-pipeline
대상: HUG 체험형 인턴 금융·기금(강원)
공고: <URL 또는 PDF>
초안: 26-06-21_주택도시보증공사(HUG) 일반전형_금융·기금(강원).docx
```

## 충돌 해결과 재개

`03_충돌검사.md`의 질문에 답하면 Codex가 `fact_overrides.yaml`에 확정값을 기록하고 같은 실행을 재개한다. 원본 파일은 수정하지 않는다.

## 결과물

`04_기업직무조사.md`, `05_문항전략.md`, `06_자기소개서.md`, `06_자기소개서.docx`, `07_자기소개서_검토보고서.md`, `08_면접대비팩.md`, `run.json`.
```

- [ ] **Step 4: Run the documentation test**

Run: `python -m pytest tests/test_usage_docs.py -v`

Expected: PASS.

- [ ] **Step 5: Commit usage documentation**

```bash
git add docs/career-pipeline-usage.md tests/test_usage_docs.py
git commit -m "docs: explain career pipeline workflow"
```

---

### Task 11: Full Test Suite and Real HUG Intake Verification

**Files:**
- Modify only files identified by failing tests
- Create: `tests/test_hug_workspace.py`

- [ ] **Step 1: Run the full automated suite**

Run: `python -m pytest -v`

Expected: all unit and integration tests PASS.

- [ ] **Step 2: Add a real-workspace intake test guarded by an environment variable**

```python
# tests/test_hug_workspace.py
import os
from pathlib import Path
import pytest

from career_pipeline.orchestrator import prepare_run


WORKSPACE = os.getenv("CAREER_PIPELINE_WORKSPACE")


@pytest.mark.skipif(not WORKSPACE, reason="set CAREER_PIPELINE_WORKSPACE for local acceptance")
def test_current_hug_draft_is_detected_and_conflicts_block_generation():
    root = Path(WORKSPACE)
    draft = root / "26-06-21_주택도시보증공사(HUG) 일반전형_금융·기금(강원).docx"
    state = prepare_run(root, "HUG 금융·기금(강원)", draft, None, "hug-acceptance")
    assert len(state["questions"]) == 4
    assert state["status"] == "blocked"
    assert state["conflict_count"] >= 1
```

- [ ] **Step 3: Run the real HUG intake verification**

PowerShell:

```powershell
$env:CAREER_PIPELINE_WORKSPACE=(Get-Location).Path
python -m pytest tests/test_hug_workspace.py -v
```

Expected: PASS, with four questions detected and at least one unresolved fact conflict. Confirm that `Chrome 비밀번호.csv`, `학교성적/`, `자격증/`, and `경력증명서/` appear as excluded in `01_자료목록.md`.

- [ ] **Step 4: Resolve implementation defects exposed by the real intake**

For each failure, add or tighten the smallest focused test first, run it to see the failure, apply the minimal implementation change, and rerun both the focused test and `python -m pytest -v`. Do not change the expected HUG conflict into an automatic value choice.

- [ ] **Step 5: Run CLI smoke tests**

```powershell
python -m career_pipeline --help
python -m career_pipeline prepare --root . --target "HUG 금융·기금(강원)" --draft "26-06-21_주택도시보증공사(HUG) 일반전형_금융·기금(강원).docx" --run-name "hug-smoke"
```

Expected: help exits 0; prepare exits 2, prints a run directory, writes artifacts 1–3 and `run.json`, and writes no draft.

- [ ] **Step 6: Audit the implementation against the design completion criteria**

Check each item in `docs/superpowers/specs/2026-06-21-career-pipeline-design.md#14-완료-기준` against executable evidence:

1. Skill contract test proves explicit invocation instructions.
2. Real HUG intake proves classification and four-question extraction.
3. Conflict tests and CLI exit 2 prove blocking behavior.
4. Skill contract requires current official research and citations.
5. Rendering/finalize tests prove Markdown, DOCX, review, and interview artifacts.
6. Inventory tests and real report prove sensitive exclusion.
7. Full suite plus real intake command prove end-to-end local behavior.

- [ ] **Step 7: Commit acceptance coverage**

```bash
git add tests/test_hug_workspace.py
git commit -m "test: verify HUG career pipeline intake"
```

---

## Final Verification Commands

```powershell
python -m pytest -v
$env:CAREER_PIPELINE_WORKSPACE=(Get-Location).Path
python -m pytest tests/test_hug_workspace.py -v
python -m career_pipeline --help
git status --short
git log --oneline --decorate -12
```

Expected final state:

- All tests pass.
- Real HUG intake detects four application questions.
- Conflicting values block draft generation and produce a confirmation report.
- Sensitive files are excluded without reading their contents into artifacts.
- Repository-local Codex skill and usage documentation exist.
- Working tree is clean after the final acceptance commit.
