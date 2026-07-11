from dataclasses import dataclass

from .models import Question


OFFICIAL_STATUSES = {"verified_domain", "user_attested", "unverified"}


@dataclass(frozen=True)
class PostingSourceMetadata:
    kind: str
    location: str
    retrieved_at: str
    content_sha256: str
    official_status: str
    content_type: str

    def __post_init__(self) -> None:
        if self.official_status not in OFFICIAL_STATUSES:
            raise ValueError(f"unknown official status: {self.official_status}")


@dataclass(frozen=True)
class LoadedPosting:
    metadata: PostingSourceMetadata
    extension: str
    content: bytes


@dataclass(frozen=True)
class PostingAnalysis:
    schema_version: int
    target: str
    source: PostingSourceMetadata
    organization: str
    role: str
    locations: tuple[str, ...]
    duties: tuple[str, ...]
    competencies: tuple[str, ...]
    requirements: tuple[str, ...]
    preferences: tuple[str, ...]
    questions: tuple[Question, ...]
    constraints: tuple[str, ...]
    uncertainties: tuple[str, ...]
