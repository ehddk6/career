"""Career Pipeline 데이터 모델. SourceRecord, Question, DraftResponse, ValidationIssue 등을 정의합니다."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .character_count import CharacterCountMode


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
    count_mode: CharacterCountMode = "spaces_included"


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
class ExperienceClaimRef:
    experience_id: str
    claim_fields: tuple[str, ...]


@dataclass(frozen=True)
class DraftResponse:
    question_index: int
    answer: str
    evidence_paths: tuple[str, ...]
    experience_refs: tuple[ExperienceClaimRef, ...] = ()
    research_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    question_index: int
    message: str
