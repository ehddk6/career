"""Canonical factual-authority contract shared by writing, interview and audit.

This module is intentionally deterministic.  It never creates facts.  It only
projects already-confirmed applicant/research claims into question-scoped
records and answers one question: what factual content is authorised here?
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
LEGACY_OFFICIAL_SOURCE_TYPES = {"official", "primary", "regulatory", "official_posting"}
SUBMISSION_AUTHORITY_MAX_TIER = 2
_METRIC = re.compile(r"(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|건|명|원|만원|억원|조원|페이지|시간|일|개월|회)")
_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")

def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping): return value.get(key, default)
    return getattr(value, key, default)

def _normal_metric(number: str, unit: str) -> str:
    raw = number.replace(",", "")
    try: numeric = float(raw)
    except ValueError: numeric_text = raw
    else: numeric_text = str(int(numeric)) if numeric.is_integer() else ("%.12g" % numeric)
    return f"{numeric_text}{unit}"

def metric_values(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_normal_metric(m.group("number"), m.group("unit")) for m in _METRIC.finditer(text or "")))

def lexical_tokens(text: str) -> frozenset[str]:
    stop = {"그리고", "하지만", "대한", "관련", "지원", "기관", "회사", "직무", "업무", "경험", "결과", "본인", "제가", "저는"}
    return frozenset(token.casefold() for token in _WORD.findall(text or "") if token.casefold() not in stop)

def _research_raw(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file(): return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list): return {}
    return {str(row.get("claim_id")): dict(row) for row in payload if isinstance(row, Mapping) and row.get("claim_id")}

def _tier(raw: Mapping[str, Any], source_type: str) -> int | None:
    value = raw.get("source_tier")
    if isinstance(value, int) and not isinstance(value, bool): return value
    if isinstance(value, str) and value.strip().isdigit(): return int(value.strip())
    if source_type in LEGACY_OFFICIAL_SOURCE_TYPES: return 1
    return None

def research_is_submission_authority(claim: Any, raw: Mapping[str, Any] | None = None) -> bool:
    raw = raw or {}
    status = str(_get(claim, "verification_status", raw.get("verification_status", ""))).strip().lower()
    if status not in {"confirmed", "verified"}: return False
    if raw.get("submission_authority") is True: return True
    source_type = str(_get(claim, "source_type", raw.get("source_type", ""))).strip().lower()
    tier = _tier(raw, source_type)
    return tier is not None and tier <= SUBMISSION_AUTHORITY_MAX_TIER

@dataclass(frozen=True)
class AuthorityRecord:
    authority_id: str
    source_kind: str
    question_indexes: tuple[int, ...]
    text: str
    metric_values: tuple[str, ...]
    tokens: frozenset[str]
    factual_authority: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class AuthorityContext:
    schema_version: int
    records: tuple[AuthorityRecord, ...]
    def for_question(self, question_index: int) -> tuple[AuthorityRecord, ...]: return tuple(record for record in self.records if question_index in record.question_indexes)
    def metric_values(self, question_index: int | None = None) -> set[str]:
        rows = self.records if question_index is None else self.for_question(question_index)
        return {metric for record in rows if record.factual_authority for metric in record.metric_values}
    def authority_ids(self, question_index: int | None = None) -> set[str]:
        rows = self.records if question_index is None else self.for_question(question_index)
        return {record.authority_id for record in rows if record.factual_authority}

def _experience_lookup(ledger: Any):
    experiences, by_id, by_field = {}, {}, {}
    for exp in _get(ledger, "experiences", ()) or ():
        if str(_get(exp, "status", "")) != "confirmed": continue
        eid = str(_get(exp, "experience_id", ""))
        if not eid: continue
        experiences[eid] = exp
        for claim in _get(exp, "claims", ()) or ():
            if str(_get(claim, "status", "")) != "confirmed": continue
            cid, field_name = str(_get(claim, "claim_id", "")), str(_get(claim, "field", ""))
            if cid: by_id[(eid, cid)] = claim
            if field_name: by_field[(eid, field_name)] = claim
    return experiences, by_id, by_field

def _applicant_record(question_index: int, exp: Any, claim: Any) -> AuthorityRecord:
    eid, cid, field_name = str(_get(exp, "experience_id", "")), str(_get(claim, "claim_id", "")), str(_get(claim, "field", ""))
    value = str(_get(claim, "normalized_value", ""))
    actions = " ".join(str(x) for x in (_get(exp, "actions", ()) or ())); outcomes = " ".join(str(x) for x in (_get(exp, "outcomes", ()) or ()))
    role, situation = str(_get(exp, "role", "")), str(_get(exp, "situation", ""))
    text = " ".join(x for x in (role, situation, actions, outcomes, field_name, value) if x).strip(); verification = _get(claim, "verification", None)
    metadata = {"experience_id": eid, "claim_id": cid, "claim_field": field_name, "normalized_value": value, "verification_method": str(_get(verification, "method", "none")) if verification else "none", "contribution": str(_get(verification, "contribution", "unknown")) if verification else "unknown", "scope": _get(verification, "scope", None) if verification else None, "measurement_period": _get(verification, "measurement_period", None) if verification else None}
    aid = f"applicant:{eid}:{cid or field_name}"
    return AuthorityRecord(aid, "applicant", (question_index,), text, metric_values(" ".join((value, text))), lexical_tokens(text), True, metadata)

def _research_record(question_index: int, claim: Any, raw: Mapping[str, Any]) -> AuthorityRecord:
    cid = str(_get(claim, "claim_id", raw.get("claim_id", ""))); text = str(_get(claim, "claim", raw.get("claim", ""))); excerpt = str(_get(claim, "evidence_excerpt", raw.get("evidence_excerpt", ""))); source_type = str(_get(claim, "source_type", raw.get("source_type", "")))
    metadata = {"claim_id": cid, "claim_type": str(_get(claim, "claim_type", raw.get("claim_type", ""))), "source_url": str(_get(claim, "source_url", raw.get("source_url", ""))), "source_type": source_type, "source_tier": _tier(raw, source_type), "argument_role": raw.get("argument_role"), "support_strength": raw.get("support_strength"), "freshness_class": raw.get("freshness_class"), "application_use": str(_get(claim, "application_use", raw.get("application_use", "")))}
    merged = " ".join(x for x in (text, excerpt) if x)
    return AuthorityRecord(f"research:{cid}", "research", (question_index,), merged, metric_values(merged), lexical_tokens(merged), research_is_submission_authority(claim, raw), metadata)

def build_authority_context(responses: Sequence[Any], ledger: Any, research_claims: Sequence[Any] = (), *, research_raw: Mapping[str, Mapping[str, Any]] | None = None) -> AuthorityContext:
    experiences, by_id, by_field = _experience_lookup(ledger); research_by_id = {str(_get(c, "claim_id", "")): c for c in research_claims if str(_get(c, "claim_id", ""))}; raw_by_id = dict(research_raw or {}); rows = {}
    for response in responses:
        q = int(_get(response, "question_index", 0) or 0)
        for ref in _get(response, "experience_refs", ()) or ():
            eid = str(_get(ref, "experience_id", "")); exp = experiences.get(eid)
            if exp is None: continue
            claim_ids = tuple(_get(ref, "claim_ids", ()) or ()); claim_fields = tuple(_get(ref, "claim_fields", ()) or ()); selected = []
            for cid in claim_ids:
                c = by_id.get((eid, str(cid))); selected.extend([c] if c is not None else [])
            if not claim_ids:
                for field_name in claim_fields:
                    c = by_field.get((eid, str(field_name))); selected.extend([c] if c is not None else [])
            for claim in selected:
                record = _applicant_record(q, exp, claim); previous = rows.get(record.authority_id)
                rows[record.authority_id] = record if previous is None else AuthorityRecord(record.authority_id, record.source_kind, tuple(sorted(set(previous.question_indexes + (q,)))), record.text, record.metric_values, record.tokens, record.factual_authority, record.metadata)
        for cid in _get(response, "research_refs", ()) or ():
            cid = str(cid); claim = research_by_id.get(cid)
            if claim is None: continue
            record = _research_record(q, claim, raw_by_id.get(cid, {})); previous = rows.get(record.authority_id)
            rows[record.authority_id] = record if previous is None else AuthorityRecord(record.authority_id, record.source_kind, tuple(sorted(set(previous.question_indexes + (q,)))), record.text, record.metric_values, record.tokens, record.factual_authority, record.metadata)
    return AuthorityContext(SCHEMA_VERSION, tuple(sorted(rows.values(), key=lambda row: row.authority_id)))

def context_for_run(run_dir: Path, responses: Sequence[Any], ledger: Any) -> AuthorityContext:
    from .research_evidence import load_research_claims
    research_path = run_dir / "04_공식근거.json"; claims = load_research_claims(research_path) if research_path.is_file() else ()
    return build_authority_context(responses, ledger, claims, research_raw=_research_raw(research_path))

def canonical_metric_values_for_responses(run_dir: Path, responses: Sequence[Any], ledger: Any) -> set[str]: return context_for_run(run_dir, responses, ledger).metric_values()
def canonical_metric_values_by_question(run_dir: Path, responses: Sequence[Any], ledger: Any) -> dict[int, set[str]]:
    context = context_for_run(run_dir, responses, ledger); return {int(_get(row, "question_index", 0)): context.metric_values(int(_get(row, "question_index", 0))) for row in responses}
def authority_context_to_dict(context: AuthorityContext) -> dict[str, Any]:
    return {"schema_version": context.schema_version, "records": [{"authority_id": row.authority_id, "source_kind": row.source_kind, "question_indexes": list(row.question_indexes), "text": row.text, "metric_values": list(row.metric_values), "tokens": sorted(row.tokens), "factual_authority": row.factual_authority, "metadata": dict(row.metadata)} for row in context.records]}
