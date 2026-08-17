"""Deterministic target job-analysis compiler.

The compiler is a shadow planning layer. It does not create applicant factual
authority, does not upgrade general occupational priors into target-company
facts, and does not change Golden Path decisions.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .job_analysis_schema import (
    ARCHITECTURE,
    SCHEMA_VERSION,
    BehavioralIndicator,
    ConstructNode,
    JobAnalysisGraph,
    SourceBinding,
    TaskConstructEdge,
    TaskNode,
    job_analysis_graph_to_dict,
)

JOB_ANALYSIS_JSON = "04_직무구성개념.json"
JOB_ANALYSIS_MD = "04_직무구성개념.md"

_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = {
    "지원", "직무", "업무", "기관", "회사", "관련", "필요", "통해", "대한",
    "수행", "담당", "등", "및", "업무를", "업무의",
}

_ACTIONS = (
    "검토", "확인", "점검", "심사", "대조", "분석", "비교", "진단", "분류",
    "작성", "기록", "문서화", "안내", "설명", "상담", "조정", "협의", "협업",
    "연계", "보고", "승인", "운영", "관리", "처리", "대응", "개선", "지원",
)

_CONSTRUCT_FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "key": "criterion_application",
        "label": "기준 기반 오류·예외 판별",
        "definition": "명시된 기준이나 원문과 입력 정보를 대조해 불일치·누락·예외를 구분하고 판단 근거를 유지하는 행동",
        "construct_type": "skill_judgment",
        "cues": ("검토", "확인", "점검", "심사", "대조", "기준", "규정", "적격", "오류", "누락", "예외", "정확"),
        "behavior": "기준 또는 원문과 입력값을 대조해 오류·누락·예외를 구분한다",
        "negative": "기준 확인 없이 경험이나 추정만으로 판단한다",
    },
    {
        "key": "analytical_diagnosis",
        "label": "근거 기반 분석·원인 진단",
        "definition": "자료를 비교·분류·분석해 원인이나 패턴을 구분하고 판단 근거를 설명하는 행동",
        "construct_type": "skill_judgment",
        "cues": ("분석", "비교", "원인", "데이터", "자료", "진단", "통계", "분류"),
        "behavior": "자료를 비교·분류·분석해 원인이나 패턴을 근거와 함께 구분한다",
        "negative": "자료 확인 없이 원인을 단정한다",
    },
    {
        "key": "stakeholder_explanation",
        "label": "이해관계자 설명·안내",
        "definition": "고객·민원인·내부 이해관계자에게 기준, 보완사항, 다음 행동을 정확하게 설명하는 행동",
        "construct_type": "communication_execution",
        "cues": ("안내", "설명", "상담", "고객", "민원", "문의", "보완", "이해관계자"),
        "behavior": "고객 또는 이해관계자에게 기준·보완사항·다음 행동을 정확하게 설명한다",
        "negative": "근거 또는 다음 행동 없이 모호하게 안내한다",
    },
    {
        "key": "coordination",
        "label": "협의·조정",
        "definition": "여러 담당자나 부서의 요구·제약을 확인하고 필요한 협의·연계를 통해 다음 행동을 정하는 행동",
        "construct_type": "coordination",
        "cues": ("조정", "협의", "협업", "연계", "부서", "이해관계", "협력"),
        "behavior": "담당자나 부서의 요구·제약을 확인하고 협의·연계해 다음 행동을 정한다",
        "negative": "상대의 제약을 확인하지 않고 일방적으로 처리한다",
    },
    {
        "key": "boundary_escalation",
        "label": "권한 경계·상향 보고",
        "definition": "판단 권한과 예외 범위를 구분하고 권한 밖 사안을 근거와 함께 보고·승인 요청하는 행동",
        "construct_type": "risk_control",
        "cues": ("보고", "승인", "권한", "예외", "상향", "결재", "책임범위"),
        "behavior": "판단 권한과 예외 범위를 구분하고 권한 밖 사안을 근거와 함께 보고한다",
        "negative": "권한 밖 사안을 임의로 확정한다",
    },
    {
        "key": "documentation",
        "label": "기록·문서화",
        "definition": "판단·처리·결과를 추적 가능한 형태로 작성·기록해 이후 확인이 가능하도록 하는 행동",
        "construct_type": "execution_quality",
        "cues": ("작성", "문서", "기록", "보고서", "정리", "자료화"),
        "behavior": "판단·처리·결과를 추적 가능한 형태로 작성하거나 기록한다",
        "negative": "처리 근거나 변경 내역을 기록하지 않는다",
    },
    {
        "key": "execution_control",
        "label": "실행·운영 통제",
        "definition": "일정·마감·처리상태·운영 조건을 관리해 필요한 작업이 누락되지 않도록 통제하는 행동",
        "construct_type": "execution_control",
        "cues": ("운영", "관리", "일정", "마감", "처리", "진행", "모니터링", "점검"),
        "behavior": "일정·마감·처리상태를 확인하고 필요한 작업이 누락되지 않도록 관리한다",
        "negative": "상태나 마감 확인 없이 작업을 진행한다",
    },
)


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _tokens(text: str) -> set[str]:
    return {
        item.casefold()
        for item in _WORD.findall(text or "")
        if item.casefold() not in _STOP
    }


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _stable_id(prefix: str, *parts: Any, size: int = 16) -> str:
    raw = "\0".join(str(part) for part in parts)
    return f"{prefix}_{sha256(raw.encode('utf-8')).hexdigest()[:size]}"


def _tier(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _posting_source_binding(
    source_family: str,
    index: int,
    text: str,
    *,
    source_locator: str,
) -> SourceBinding:
    source_id = _stable_id("src", "posting", source_family, index, text)
    return SourceBinding(
        source_id=source_id,
        source_family=f"target_posting_{source_family}",
        source_text=text,
        source_locator=source_locator,
        authority_class="target_explicit",
        company_factual_authority=True,
    )


def _research_source_binding(index: int, row: Mapping[str, Any]) -> SourceBinding:
    claim_id = str(row.get("claim_id", "")).strip()
    text = str(row.get("claim", "")).strip()
    source_id = (
        f"research:{claim_id}"
        if claim_id
        else _stable_id("src", "research", index, text)
    )
    return SourceBinding(
        source_id=source_id,
        source_family="target_official_research",
        source_text=text,
        source_locator=f"04_공식근거.json[{index}]",
        authority_class="target_official_context",
        company_factual_authority=row.get("submission_authority") is True,
        claim_id=claim_id,
        claim_type=str(row.get("claim_type", "")),
        source_url=str(row.get("source_url", "")),
        source_tier=_tier(row.get("source_tier")),
        freshness_class=str(row.get("freshness_class", "")),
    )


def _taxonomy_source_binding(index: int, row: Mapping[str, Any]) -> SourceBinding:
    text = str(row.get("label") or row.get("construct") or row.get("text") or "").strip()
    source_id = str(row.get("source_id") or _stable_id("src", "taxonomy", index, text))
    return SourceBinding(
        source_id=source_id,
        source_family=str(row.get("source_family") or "occupational_taxonomy"),
        source_text=text,
        source_locator=str(row.get("source_locator") or f"taxonomy[{index}]"),
        authority_class="taxonomy_prior",
        company_factual_authority=False,
        source_url=str(row.get("source_url", "")),
    )


def _extract_action_object(text: str) -> tuple[str, str]:
    compact = re.sub(r"\s+", " ", text).strip()
    for action in _ACTIONS:
        pos = compact.find(action)
        if pos < 0:
            continue
        before = compact[:pos].strip(" ·,/-")
        after = compact[pos + len(action):].strip(" ·,/-")
        object_text = before[-80:] if before else after[:80]
        return action, object_text
    return "", ""


def _family_matches(text: str) -> list[dict[str, Any]]:
    compact = _norm(text)
    return [
        family
        for family in _CONSTRUCT_FAMILIES
        if any(_norm(cue) in compact for cue in family["cues"])
    ]


def _verified_research_row(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("verification_status", "confirmed")) in {"confirmed", "verified"}
        and not str(row.get("conflict_note", "")).strip()
        and bool(str(row.get("claim", "")).strip())
    )


def _canonical_payload(graph: JobAnalysisGraph) -> dict[str, Any]:
    payload = job_analysis_graph_to_dict(graph)
    payload.pop("graph_id", None)
    return payload


def build_job_analysis_graph(
    posting: Mapping[str, Any] | None,
    research: Sequence[Mapping[str, Any]] = (),
    *,
    target: str = "",
    taxonomy: Sequence[Mapping[str, Any]] = (),
) -> JobAnalysisGraph:
    posting = posting if isinstance(posting, Mapping) else {}
    target = target or str(posting.get("target", "")).strip()

    bindings: dict[str, SourceBinding] = {}
    task_candidates: dict[str, dict[str, Any]] = {}
    constraint_sources: list[tuple[SourceBinding, str]] = []
    explicit_construct_sources: list[tuple[SourceBinding, bool]] = []
    unresolved: list[dict[str, Any]] = []

    def add_binding(binding: SourceBinding) -> None:
        bindings[binding.source_id] = binding

    def add_task(text: str, binding: SourceBinding, criticality: str) -> None:
        label = " ".join(str(text).split()).strip()
        if not label:
            return
        key = _norm(label)
        action, object_text = _extract_action_object(label)
        current = task_candidates.setdefault(
            key,
            {
                "label": label,
                "action": action,
                "object": object_text,
                "criticality": criticality,
                "bindings": set(),
                "constraints": [],
                "inferred_fields": set(),
            },
        )
        current["bindings"].add(binding.source_id)
        if current["criticality"] != "core" and criticality == "core":
            current["criticality"] = "core"

    for key in ("duties",):
        for index, raw in enumerate(posting.get(key, []) or (), 1):
            text = str(raw).strip()
            if not text:
                continue
            binding = _posting_source_binding(
                key,
                index,
                text,
                source_locator=f"00_채용공고분석.json#{key}[{index - 1}]",
            )
            add_binding(binding)
            add_task(text, binding, "core")

    for key in ("competencies", "requirements", "preferred", "preferences"):
        allow_generic = key == "competencies"
        for index, raw in enumerate(posting.get(key, []) or (), 1):
            text = str(raw).strip()
            if not text:
                continue
            binding = _posting_source_binding(
                key,
                index,
                text,
                source_locator=f"00_채용공고분석.json#{key}[{index - 1}]",
            )
            add_binding(binding)
            explicit_construct_sources.append((binding, allow_generic))

    for index, raw in enumerate(posting.get("constraints", []) or (), 1):
        text = str(raw).strip()
        if not text:
            continue
        binding = _posting_source_binding(
            "constraints",
            index,
            text,
            source_locator=f"00_채용공고분석.json#constraints[{index - 1}]",
        )
        add_binding(binding)
        constraint_sources.append((binding, text))

    for index, row in enumerate(research, 1):
        if not isinstance(row, Mapping) or not _verified_research_row(row):
            continue
        claim_type = str(row.get("claim_type", ""))
        if claim_type not in {"job_duty", "risk_or_limit", "selection_criteria"}:
            continue
        binding = _research_source_binding(index - 1, row)
        add_binding(binding)
        text = binding.source_text
        if claim_type == "job_duty":
            add_task(text, binding, "supporting")
        elif claim_type == "risk_or_limit":
            constraint_sources.append((binding, text))
        elif claim_type == "selection_criteria":
            explicit_construct_sources.append((binding, True))

    taxonomy_bindings: list[SourceBinding] = []
    for index, row in enumerate(taxonomy, 1):
        if not isinstance(row, Mapping):
            continue
        binding = _taxonomy_source_binding(index - 1, row)
        if not binding.source_text:
            continue
        add_binding(binding)
        taxonomy_bindings.append(binding)

    # Attach operational constraints conservatively.
    task_rows = list(task_candidates.values())
    for binding, text in constraint_sources:
        text_tokens = _tokens(text)
        scored: list[tuple[int, dict[str, Any]]] = []
        for task in task_rows:
            overlap = len(text_tokens & _tokens(task["label"]))
            if overlap:
                scored.append((overlap, task))
        if scored:
            best_score = max(score for score, _ in scored)
            for score, task in scored:
                if score == best_score:
                    task["constraints"].append(text)
                    task["bindings"].add(binding.source_id)
        elif len(task_rows) == 1:
            task_rows[0]["constraints"].append(text)
            task_rows[0]["bindings"].add(binding.source_id)
        else:
            unresolved.append(
                {
                    "kind": "unattached_operating_constraint",
                    "source_id": binding.source_id,
                    "text": text,
                }
            )

    tasks: list[TaskNode] = []
    for task in sorted(task_rows, key=lambda item: (_norm(item["label"]), item["label"])):
        task_id = _stable_id("task", task["label"], *sorted(task["bindings"]))
        tasks.append(
            TaskNode(
                task_id=task_id,
                label=task["label"],
                action=task["action"],
                object=task["object"],
                work_output="",
                constraints=tuple(sorted(set(task["constraints"]))),
                criticality=task["criticality"],
                entry_expected=True,
                source_binding_ids=tuple(sorted(task["bindings"])),
                inferred_fields=tuple(sorted(task["inferred_fields"])),
            )
        )

    # Accumulate target-supported construct families from task behavior.
    construct_acc: dict[str, dict[str, Any]] = {}
    task_family_strength: dict[tuple[str, str], str] = {}
    for task in tasks:
        direct_families = {f["key"]: f for f in _family_matches(task.label)}
        constraint_families: dict[str, dict[str, Any]] = {}
        for constraint in task.constraints:
            for family in _family_matches(constraint):
                constraint_families[family["key"]] = family
        all_families = {**constraint_families, **direct_families}
        for key, family in all_families.items():
            row = construct_acc.setdefault(
                key,
                {
                    "family": family,
                    "status": "target_supported",
                    "bindings": set(),
                    "task_ids": set(),
                },
            )
            row["bindings"].update(task.source_binding_ids)
            row["task_ids"].add(task.task_id)
            task_family_strength[(task.task_id, key)] = (
                "direct" if key in direct_families else "supported"
            )

    # Explicit target competencies/criteria may strengthen known families.
    generic_explicit: list[tuple[SourceBinding, str]] = []
    for binding, allow_generic in explicit_construct_sources:
        matched = _family_matches(binding.source_text)
        if not matched:
            if allow_generic:
                generic_explicit.append((binding, binding.source_text))
            continue
        for family in matched:
            row = construct_acc.setdefault(
                family["key"],
                {
                    "family": family,
                    "status": "target_explicit",
                    "bindings": set(),
                    "task_ids": set(),
                },
            )
            row["status"] = "target_explicit"
            row["bindings"].add(binding.source_id)

    indicators: list[BehavioralIndicator] = []
    constructs: list[ConstructNode] = []
    family_to_construct_id: dict[str, str] = {}
    for key, row in sorted(construct_acc.items()):
        family = row["family"]
        construct_id = f"construct_{key}"
        family_to_construct_id[key] = construct_id
        indicator_id = f"bi_{key}"
        indicators.append(
            BehavioralIndicator(
                indicator_id=indicator_id,
                construct_id=construct_id,
                behavior=family["behavior"],
                observable=True,
                negative_form=family["negative"],
                source_basis=row["status"],
            )
        )
        constructs.append(
            ConstructNode(
                construct_id=construct_id,
                label=family["label"],
                definition=family["definition"],
                construct_type=family["construct_type"],
                status=row["status"],
                behavioral_indicator_ids=(indicator_id,),
                source_binding_ids=tuple(sorted(row["bindings"])),
            )
        )

    # Preserve explicitly named competencies even when no behavioral family can
    # be deterministically attached. They cannot become core without task edges.
    for binding, text in generic_explicit:
        construct_id = _stable_id("construct_explicit", text)
        constructs.append(
            ConstructNode(
                construct_id=construct_id,
                label=text,
                definition=f"공고 또는 공식 선발 기준에 명시된 역량·요건: {text}",
                construct_type="explicit_unspecified",
                status="target_explicit",
                behavioral_indicator_ids=(),
                source_binding_ids=(binding.source_id,),
            )
        )
        unresolved.append(
            {
                "kind": "explicit_construct_without_behavioral_task_support",
                "construct_id": construct_id,
                "source_id": binding.source_id,
            }
        )

    # Taxonomy priors are represented but never target-confirmed or core.
    for binding in taxonomy_bindings:
        matched = _family_matches(binding.source_text)
        if matched:
            for family in matched:
                construct_id = f"prior_{family['key']}_{sha256(binding.source_id.encode()).hexdigest()[:8]}"
                indicator_id = f"bi_{construct_id}"
                indicators.append(
                    BehavioralIndicator(
                        indicator_id=indicator_id,
                        construct_id=construct_id,
                        behavior=family["behavior"],
                        observable=True,
                        negative_form=family["negative"],
                        source_basis="prior_supported",
                    )
                )
                constructs.append(
                    ConstructNode(
                        construct_id=construct_id,
                        label=family["label"],
                        definition=family["definition"],
                        construct_type=family["construct_type"],
                        status="prior_supported",
                        behavioral_indicator_ids=(indicator_id,),
                        source_binding_ids=(binding.source_id,),
                    )
                )
        else:
            construct_id = _stable_id("prior_construct", binding.source_text)
            constructs.append(
                ConstructNode(
                    construct_id=construct_id,
                    label=binding.source_text,
                    definition=f"일반 직업 taxonomy prior: {binding.source_text}",
                    construct_type="taxonomy_prior",
                    status="prior_supported",
                    behavioral_indicator_ids=(),
                    source_binding_ids=(binding.source_id,),
                )
            )

    edges: list[TaskConstructEdge] = []
    for (task_id, family_key), strength in sorted(task_family_strength.items()):
        construct_id = family_to_construct_id.get(family_key)
        if not construct_id:
            continue
        task = next(item for item in tasks if item.task_id == task_id)
        construct = next(
            item for item in constructs if item.construct_id == construct_id
        )
        edges.append(
            TaskConstructEdge(
                task_id=task_id,
                construct_id=construct_id,
                relation="requires",
                strength=strength,
                source_binding_ids=tuple(
                    sorted(
                        set(task.source_binding_ids)
                        | set(construct.source_binding_ids)
                    )
                ),
            )
        )

    edge_count: dict[str, int] = {}
    direct_count: dict[str, int] = {}
    for edge in edges:
        edge_count[edge.construct_id] = edge_count.get(edge.construct_id, 0) + 1
        if edge.strength == "direct":
            direct_count[edge.construct_id] = direct_count.get(edge.construct_id, 0) + 1

    status_rank = {"target_explicit": 0, "target_supported": 1}
    eligible = [
        construct
        for construct in constructs
        if construct.status in status_rank
        and edge_count.get(construct.construct_id, 0) > 0
    ]
    eligible.sort(
        key=lambda item: (
            status_rank[item.status],
            -direct_count.get(item.construct_id, 0),
            -edge_count.get(item.construct_id, 0),
            item.construct_id,
        )
    )
    core_construct_ids = tuple(item.construct_id for item in eligible[:6])

    if not tasks:
        unresolved.append(
            {
                "kind": "insufficient_job_evidence",
                "message": "공식 채용공고·직무 근거에서 구체적인 task를 확인하지 못했습니다.",
            }
        )
    if not core_construct_ids:
        unresolved.append(
            {
                "kind": "insufficient_construct_evidence",
                "message": "task와 연결된 target-supported construct를 확인하지 못했습니다.",
            }
        )
    if len(eligible) > 8:
        unresolved.append(
            {
                "kind": "construct_set_broad",
                "count": len(eligible),
                "message": "핵심 construct 압축 전 검토가 필요합니다.",
            }
        )

    source = posting.get("source")
    posting_snapshot_id = (
        str(source.get("content_sha256"))
        if isinstance(source, Mapping) and source.get("content_sha256")
        else None
    )

    graph = JobAnalysisGraph(
        schema_version=SCHEMA_VERSION,
        architecture=ARCHITECTURE,
        target=target,
        posting_snapshot_id=posting_snapshot_id,
        source_bindings=tuple(
            sorted(bindings.values(), key=lambda item: item.source_id)
        ),
        tasks=tuple(sorted(tasks, key=lambda item: item.task_id)),
        constructs=tuple(sorted(constructs, key=lambda item: item.construct_id)),
        behavioral_indicators=tuple(
            sorted(indicators, key=lambda item: item.indicator_id)
        ),
        task_construct_edges=tuple(
            sorted(edges, key=lambda item: (item.task_id, item.construct_id))
        ),
        core_construct_ids=core_construct_ids,
        unresolved=tuple(unresolved),
        policy={
            "decision_effect": "none_shadow_mode",
            "factual_authority_granted": False,
            "construct_authority_added": False,
            "taxonomy_prior_is_not_target_fact": True,
            "constructs_require_task_support_for_core": True,
        },
        graph_id="",
    )
    canonical = json.dumps(
        _canonical_payload(graph),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return replace(
        graph,
        graph_id=sha256(canonical.encode("utf-8")).hexdigest()[:20],
    )


def render_job_analysis(graph: JobAnalysisGraph) -> str:
    by_indicator = {
        item.indicator_id: item for item in graph.behavioral_indicators
    }
    lines = [
        "# 직무 과업 × 구성개념 섀도우",
        "",
        "> 현재 생산 판정에 영향을 주지 않는 shadow 분석이다.",
        "",
        f"- target: {graph.target or '-'}",
        f"- graph_id: `{graph.graph_id}`",
        f"- tasks: {len(graph.tasks)}",
        f"- constructs: {len(graph.constructs)}",
        f"- core constructs: {len(graph.core_construct_ids)}",
        "",
        "## 핵심 과업",
        "",
    ]
    if not graph.tasks:
        lines.append("- 확인된 구체 과업 없음")
    for task in graph.tasks:
        constraints = " / ".join(task.constraints) or "-"
        lines.append(
            f"- `{task.task_id}` {task.label} "
            f"(criticality={task.criticality}, constraints={constraints})"
        )
    lines += ["", "## 구성개념", ""]
    core = set(graph.core_construct_ids)
    for construct in graph.constructs:
        marker = "core" if construct.construct_id in core else "shadow"
        lines.append(
            f"### {construct.label} · `{construct.construct_id}`"
        )
        lines.append(f"- status: `{construct.status}` / {marker}")
        lines.append(f"- 정의: {construct.definition}")
        indicator_text = [
            by_indicator[item].behavior
            for item in construct.behavioral_indicator_ids
            if item in by_indicator
        ]
        lines.append(
            "- 행동지표: " + (" / ".join(indicator_text) if indicator_text else "-")
        )
        lines.append(
            "- source bindings: "
            + (", ".join(construct.source_binding_ids) or "-")
        )
        lines.append("")
    lines += ["## 미해결", ""]
    if not graph.unresolved:
        lines.append("- 없음")
    else:
        for row in graph.unresolved:
            lines.append(
                f"- `{row.get('kind', 'unknown')}`: "
                f"{row.get('message') or row.get('text') or row.get('construct_id') or row.get('source_id') or ''}"
            )
    lines += [
        "",
        "## 정책",
        "",
        "- 회사/직무 근거와 지원자 능력 근거는 분리한다.",
        "- taxonomy prior는 target factual authority로 승격하지 않는다.",
        "- task edge가 없는 construct는 core로 자동 승격하지 않는다.",
        "- 이 산출물은 사실 권한을 추가하지 않는다.",
    ]
    return "\n".join(lines)


def write_job_analysis_artifacts(
    run_dir: Path,
    *,
    taxonomy: Sequence[Mapping[str, Any]] = (),
) -> tuple[Path, Path, JobAnalysisGraph]:
    run = run_dir.resolve()
    posting = _read(run / "00_채용공고분석.json", {})
    research = _read(run / "04_공식근거.json", [])
    state = _read(run / "run.json", {})
    if not isinstance(posting, Mapping):
        posting = {}
    if not isinstance(research, list):
        research = []
    if not isinstance(state, Mapping):
        state = {}
    target = str(state.get("target") or posting.get("target") or "").strip()
    graph = build_job_analysis_graph(
        posting,
        tuple(row for row in research if isinstance(row, Mapping)),
        target=target,
        taxonomy=taxonomy,
    )
    json_path = run / JOB_ANALYSIS_JSON
    markdown_path = run / JOB_ANALYSIS_MD
    json_path.write_text(
        json.dumps(
            job_analysis_graph_to_dict(graph),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_job_analysis(graph), encoding="utf-8")
    return json_path, markdown_path, graph
