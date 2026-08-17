"""Typed schema for target job analysis shadow artifacts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

SCHEMA_VERSION = 1
ARCHITECTURE = "task_construct_graph_shadow_v1"


@dataclass(frozen=True)
class SourceBinding:
    source_id: str
    source_family: str
    source_text: str
    source_locator: str
    authority_class: str
    company_factual_authority: bool
    claim_id: str = ""
    claim_type: str = ""
    source_url: str = ""
    source_tier: int | None = None
    freshness_class: str = ""


@dataclass(frozen=True)
class TaskNode:
    task_id: str
    label: str
    action: str
    object: str
    work_output: str
    constraints: tuple[str, ...]
    criticality: str
    entry_expected: bool
    source_binding_ids: tuple[str, ...]
    inferred_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConstructNode:
    construct_id: str
    label: str
    definition: str
    construct_type: str
    status: str
    behavioral_indicator_ids: tuple[str, ...]
    source_binding_ids: tuple[str, ...]


@dataclass(frozen=True)
class BehavioralIndicator:
    indicator_id: str
    construct_id: str
    behavior: str
    observable: bool
    negative_form: str
    source_basis: str


@dataclass(frozen=True)
class TaskConstructEdge:
    task_id: str
    construct_id: str
    relation: str
    strength: str
    source_binding_ids: tuple[str, ...]


@dataclass(frozen=True)
class JobAnalysisGraph:
    schema_version: int
    architecture: str
    target: str
    posting_snapshot_id: str | None
    source_bindings: tuple[SourceBinding, ...]
    tasks: tuple[TaskNode, ...]
    constructs: tuple[ConstructNode, ...]
    behavioral_indicators: tuple[BehavioralIndicator, ...]
    task_construct_edges: tuple[TaskConstructEdge, ...]
    core_construct_ids: tuple[str, ...]
    unresolved: tuple[Mapping[str, Any], ...]
    policy: Mapping[str, Any]
    graph_id: str


def job_analysis_graph_to_dict(graph: JobAnalysisGraph) -> dict[str, Any]:
    return {
        "schema_version": graph.schema_version,
        "architecture": graph.architecture,
        "target": graph.target,
        "posting_snapshot_id": graph.posting_snapshot_id,
        "source_bindings": [asdict(item) for item in graph.source_bindings],
        "tasks": [
            {
                **asdict(item),
                "constraints": list(item.constraints),
                "source_binding_ids": list(item.source_binding_ids),
                "inferred_fields": list(item.inferred_fields),
            }
            for item in graph.tasks
        ],
        "constructs": [
            {
                **asdict(item),
                "behavioral_indicator_ids": list(item.behavioral_indicator_ids),
                "source_binding_ids": list(item.source_binding_ids),
            }
            for item in graph.constructs
        ],
        "behavioral_indicators": [
            asdict(item) for item in graph.behavioral_indicators
        ],
        "task_construct_edges": [
            {
                **asdict(item),
                "source_binding_ids": list(item.source_binding_ids),
            }
            for item in graph.task_construct_edges
        ],
        "core_construct_ids": list(graph.core_construct_ids),
        "unresolved": [dict(item) for item in graph.unresolved],
        "policy": dict(graph.policy),
        "graph_id": graph.graph_id,
    }
