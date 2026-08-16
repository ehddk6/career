"""Argument-space search primitives for evidence-grounded Korean applications.

This module sits between the existing Narrative Compiler blueprint and prose.
It never creates factual authority. It makes the claim/proof route explicit,
validates support refs, aggregates debiased semantic judges, and selects routes
jointly across the application.
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from statistics import median
from typing import Any, Iterable, Mapping, Sequence
import re

SEMANTIC_DIMENSIONS = (
    "question_fidelity",
    "evidence_defensibility",
    "decision_visibility",
    "causal_coherence",
    "scene_specificity",
    "ownership",
    "fit_naturalness",
    "distinctiveness",
    "replaceability_resistance",
    "voice_potential",
)
DIMENSION_LABELS = {
    "question_fidelity": "문항이 요구한 판단·사례·결과를 직접 증명하는가",
    "evidence_defensibility": "핵심 주장을 실제 근거로 면접에서 방어할 수 있는가",
    "decision_visibility": "무엇을 왜 선택했는지가 드러나는가",
    "causal_coherence": "상황→판단→행동→결과가 자연스럽게 연결되는가",
    "scene_specificity": "실제 장면·제약·대상이 구체적으로 보이는가",
    "ownership": "지원자가 직접 한 행동과 책임 범위가 분명한가",
    "fit_naturalness": "직무 연결이 억지 결론이 아니라 경험에서 이어지는가",
    "distinctiveness": "상투적 모범답안이 아닌가",
    "replaceability_resistance": "다른 지원자가 그대로 제출하기 어려운가",
    "voice_potential": "최종 산문이 사람이 말할 법한 목소리가 될 수 있는가",
}
PROOF_KINDS = (
    "context", "friction", "criterion", "judgment", "action", "outcome",
    "reflection", "organization_fact", "fit_bridge", "tradeoff", "guardrail",
)
REQUIRED = {
    "motivation": ("criterion", "organization_fact", "action", "fit_bridge"),
    "adaptation": ("context", "judgment", "action", "outcome"),
    "collaboration": ("friction", "judgment", "action", "outcome"),
    "problem_solving": ("friction", "judgment", "action", "outcome"),
    "growth": ("friction", "reflection", "action", "outcome"),
    "integrity": ("friction", "criterion", "action", "outcome"),
    "competency": ("context", "action", "outcome", "fit_bridge"),
    "job_plan": ("criterion", "action", "guardrail", "fit_bridge"),
    "issue_analysis": ("friction", "judgment", "tradeoff", "guardrail"),
    "general_experience": ("context", "judgment", "action", "outcome"),
}
CRITICAL = {
    "motivation": ("criterion",), "adaptation": ("judgment", "action"),
    "collaboration": ("friction", "action"), "problem_solving": ("judgment", "action"),
    "growth": ("reflection", "action"), "integrity": ("criterion", "action"),
    "competency": ("action",), "job_plan": ("criterion", "guardrail"),
    "issue_analysis": ("tradeoff",), "general_experience": ("action",),
}
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")

class ArgumentSearchError(ValueError):
    pass

def _ref_texts(blueprint: Mapping[str, Any]) -> dict[str, str]:
    refs: dict[str, str] = {}
    exp = blueprint.get("experience")
    if isinstance(exp, Mapping):
        for key in ("role", "situation"):
            value = str(exp.get(key, "")).strip()
            if value:
                refs[f"experience:{key}"] = value
        for field in ("actions", "outcomes"):
            for i, value in enumerate(exp.get(field, []) or []):
                if str(value).strip():
                    refs[f"experience:{field[:-1]}:{i}"] = str(value).strip()
        for claim in exp.get("selected_claims", []) or []:
            if isinstance(claim, Mapping):
                cid = str(claim.get("claim_id", "")).strip()
                value = str(claim.get("normalized_value", "")).strip()
                if cid and value:
                    refs[f"claim:{cid}"] = value
    for claim in blueprint.get("research_claims", []) or []:
        if isinstance(claim, Mapping):
            cid = str(claim.get("claim_id", "")).strip()
            value = str(claim.get("claim", "")).strip()
            if cid and value:
                refs[f"research:{cid}"] = value
    return refs

def build_story_kernel(blueprint: Mapping[str, Any]) -> dict[str, Any]:
    refs = _ref_texts(blueprint)
    decision = ("판단", "선택", "결정", "우선", "대신", "기준", "먼저", "이유", "때문")
    friction = ("오류", "누락", "갈등", "차이", "부족", "지연", "한계", "제약", "문제", "위험")
    return {
        "support": [{"ref": key, "text": value} for key, value in refs.items()],
        "decision_signal_refs": [key for key, value in refs.items() if any(x in value for x in decision)],
        "friction_signal_refs": [key for key, value in refs.items() if any(x in value for x in friction)],
        "support_count": len(refs),
    }

def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ArgumentSearchError(f"{label} must be a string array")
    return list(value)

def validate_route_packet(
    payload: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    *,
    minimum_routes: int = 2,
    maximum_routes: int = 5,
) -> dict[str, Any]:
    if payload.get("blueprint_id") != blueprint.get("blueprint_id"):
        raise ArgumentSearchError("route blueprint mismatch")
    if payload.get("question_index") != blueprint.get("question_index"):
        raise ArgumentSearchError("route question mismatch")
    rows = payload.get("routes")
    if not isinstance(rows, list) or not minimum_routes <= len(rows) <= maximum_routes:
        raise ArgumentSearchError("invalid route count")
    allowed = set(_ref_texts(blueprint))
    intent = str(blueprint.get("intent", "general_experience"))
    logic = blueprint.get("logic_contract", {})
    need_exp = isinstance(logic, Mapping) and logic.get("experience_mode") == "required"
    need_research = isinstance(logic, Mapping) and logic.get("research_mode") == "required"
    seen: set[str] = set()
    result = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ArgumentSearchError("route must be object")
        rid = str(raw.get("route_id", "")).strip()
        if not rid or rid in seen:
            raise ArgumentSearchError("route_id must be unique")
        seen.add(rid)
        thesis = str(raw.get("thesis", "")).strip()
        if not thesis:
            raise ArgumentSearchError("empty route thesis")
        thesis_refs = _strings(raw.get("thesis_support_refs", []), "thesis_support_refs")
        proof = raw.get("proof_chain")
        if not isinstance(proof, list) or not proof:
            raise ArgumentSearchError("empty proof_chain")
        canonical_proof = []
        all_refs = set(thesis_refs)
        for item in proof:
            if not isinstance(item, Mapping):
                raise ArgumentSearchError("proof item must be object")
            kind = str(item.get("kind", ""))
            if kind not in PROOF_KINDS:
                raise ArgumentSearchError(f"invalid proof kind: {kind}")
            support = _strings(item.get("support_refs", []), "support_refs")
            if set(support) - allowed:
                raise ArgumentSearchError("unsupported proof ref")
            all_refs.update(support)
            canonical_proof.append({"kind": kind, "text": str(item.get("text", "")).strip(), "support_refs": support})
        if set(thesis_refs) - allowed:
            raise ArgumentSearchError("unsupported thesis ref")
        if need_exp and not any(x.startswith(("experience:", "claim:")) for x in all_refs):
            raise ArgumentSearchError("experience support required")
        if need_research and not any(x.startswith("research:") for x in all_refs):
            raise ArgumentSearchError("research support required")
        kinds = {item["kind"] for item in canonical_proof}
        missing = [x for x in REQUIRED.get(intent, REQUIRED["general_experience"]) if x not in kinds]
        critical = bool(set(missing) & set(CRITICAL.get(intent, CRITICAL["general_experience"])))
        exp = blueprint.get("experience")
        exp_id = str(exp.get("experience_id", "")) if isinstance(exp, Mapping) else ""
        distinctive = _strings(raw.get("distinctive_anchor_refs", []), "distinctive_anchor_refs")
        if set(distinctive) - allowed:
            raise ArgumentSearchError("unsupported distinctive ref")
        result.append({
            "route_id": rid,
            "question_index": int(blueprint["question_index"]),
            "intent": intent,
            "experience_id": exp_id or None,
            "argument_posture": str(raw.get("argument_posture", "")).strip() or "unspecified",
            "thesis": thesis,
            "thesis_support_refs": thesis_refs,
            "proof_chain": canonical_proof,
            "closing_move": str(raw.get("closing_move", "")).strip(),
            "evidence_gaps": _strings(raw.get("evidence_gaps", []), "evidence_gaps"),
            "distinctive_anchor_refs": distinctive,
            "all_support_refs": sorted(all_refs),
            "missing_required_kinds": missing,
            "critical_gap": critical,
        })
    return {"blueprint_id": str(blueprint["blueprint_id"]), "question_index": int(blueprint["question_index"]), "routes": result}

def validate_judgement(payload: Mapping[str, Any], route_ids: set[str]) -> list[dict[str, Any]]:
    rows = payload.get("routes")
    if not isinstance(rows, list):
        raise ArgumentSearchError("judge routes missing")
    seen = set()
    out = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ArgumentSearchError("invalid judge row")
        rid = str(row.get("route_id", ""))
        if rid not in route_ids or rid in seen:
            raise ArgumentSearchError("judge route mismatch")
        scores = row.get("scores")
        if not isinstance(scores, Mapping):
            raise ArgumentSearchError("judge scores missing")
        clean = {}
        for dim in SEMANTIC_DIMENSIONS:
            value = scores.get(dim)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
                raise ArgumentSearchError("judge score must be 0..4")
            clean[dim] = value
        out.append({"route_id": rid, "scores": clean, "fatal_issue": bool(row.get("fatal_issue", False))})
        seen.add(rid)
    if seen != route_ids:
        raise ArgumentSearchError("judge did not score every route")
    return out

def aggregate_judgements(
    routes: Sequence[Mapping[str, Any]],
    judgements: Sequence[Sequence[Mapping[str, Any]]],
    *,
    semantic_preference_weights: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    ids = {str(x["route_id"]) for x in routes}
    values = {rid: {dim: [] for dim in SEMANTIC_DIMENSIONS} for rid in ids}
    fatal = Counter()
    for judgement in judgements:
        if {str(x["route_id"]) for x in judgement} != ids:
            raise ArgumentSearchError("inconsistent judgement set")
        for row in judgement:
            rid = str(row["route_id"])
            for dim in SEMANTIC_DIMENSIONS:
                values[rid][dim].append(int(row["scores"][dim]))
            fatal[rid] += int(bool(row.get("fatal_issue")))
    by_id = {str(x["route_id"]): dict(x) for x in routes}
    out = []
    for rid in sorted(ids):
        med = {dim: float(median(values[rid][dim])) for dim in SEMANTIC_DIMENSIONS}
        total = weight_total = disagreement = 0.0
        for dim in SEMANTIC_DIMENSIONS:
            preference = float((semantic_preference_weights or {}).get(dim, 1.0))
            base = 1.45 if dim == "evidence_defensibility" else 1.35 if dim == "question_fidelity" else 1.25 if dim == "replaceability_resistance" else 1.0
            weight = base * max(0.75, min(1.35, preference))
            total += med[dim] * weight
            weight_total += 4.0 * weight
            vals = values[rid][dim]
            disagreement += (max(vals) - min(vals)) / 4.0
        score = 100.0 * total / weight_total if weight_total else 0.0
        score -= min(45.0, fatal[rid] * 18.0)
        if by_id[rid].get("critical_gap"):
            score -= 25.0
        item = dict(by_id[rid])
        item.update({
            "dimension_medians": med,
            "judge_disagreement": round(disagreement / len(SEMANTIC_DIMENSIONS), 4),
            "fatal_judge_votes": int(fatal[rid]),
            "aggregate_score": round(score, 3),
        })
        out.append(item)
    return sorted(out, key=lambda x: (-float(x["aggregate_score"]), float(x["judge_disagreement"]), str(x["route_id"])))

def pareto_frontier(routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dims = ("question_fidelity", "evidence_defensibility", "causal_coherence", "distinctiveness", "replaceability_resistance")
    rows = [dict(x) for x in routes]
    keep = []
    for candidate in rows:
        c = candidate.get("dimension_medians", {})
        dominated = False
        for other in rows:
            if other is candidate:
                continue
            o = other.get("dimension_medians", {})
            if all(float(o.get(d, 0)) >= float(c.get(d, 0)) for d in dims) and any(float(o.get(d, 0)) > float(c.get(d, 0)) for d in dims):
                dominated = True
                break
        if not dominated:
            keep.append(candidate)
    return sorted(keep, key=lambda x: -float(x.get("aggregate_score", 0)))

def _tokens(text: str) -> set[str]:
    return {x.lower() for x in _TOKEN.findall(text)}

def select_portfolio_routes(route_sets: Mapping[int, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    states = [(0.0, {}, Counter(), Counter(), [])]
    for q in sorted(route_sets):
        nxt = []
        for score, selected, exps, postures, signatures in states:
            for route in route_sets[q]:
                penalty = 0.0
                exp = str(route.get("experience_id") or "")
                posture = str(route.get("argument_posture") or "")
                sig = _tokens(str(route.get("thesis", "")) + " " + " ".join(str(x.get("text", "")) for x in route.get("proof_chain", []) if isinstance(x, Mapping)))
                if exp and exps[exp]:
                    penalty += 11.0 + 6.0 * max(0, exps[exp] - 1)
                if posture and postures[posture]:
                    penalty += 5.0 + 3.0 * max(0, postures[posture] - 1)
                for _, old in signatures:
                    if sig and old:
                        sim = len(sig & old) / len(sig | old)
                        if sim >= 0.45:
                            penalty += (sim - 0.35) * 24.0
                ns = dict(selected); ns[q] = str(route["route_id"])
                ne, np = exps.copy(), postures.copy()
                if exp: ne[exp] += 1
                if posture: np[posture] += 1
                nxt.append((score + float(route.get("aggregate_score", 0)) - penalty, ns, ne, np, [*signatures, (q, sig)]))
        nxt.sort(key=lambda x: -x[0])
        states = nxt[:256]
    if not states:
        raise ArgumentSearchError("no portfolio route")
    best = states[0]
    return {"selected": best[1], "score": round(best[0], 3)}

def short_partial_duplicate_pairs(
    answers: Iterable[tuple[int, str]],
    *,
    minimum_substring_chars: int = 18,
    similarity_floor_chars: int = 80,
    similarity_threshold: float = 0.88,
) -> list[dict[str, Any]]:
    """Exact/substring duplication is checked before the legacy 80-char shortcut."""
    normalized = [(i, "".join(_TOKEN.findall(t)).lower()) for i, t in answers if t.strip()]
    out = []
    for pos, (li, left) in enumerate(normalized):
        for ri, right in normalized[pos + 1:]:
            if left == right:
                out.append({"left_index": li, "right_index": ri, "kind": "exact"})
                continue
            if min(len(left), len(right)) >= minimum_substring_chars and (left in right or right in left):
                out.append({"left_index": li, "right_index": ri, "kind": "substring"})
                continue
            if min(len(left), len(right)) >= similarity_floor_chars and SequenceMatcher(None, left, right).ratio() >= similarity_threshold:
                out.append({"left_index": li, "right_index": ri, "kind": "high_similarity"})
    return out
