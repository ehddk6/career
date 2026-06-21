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
