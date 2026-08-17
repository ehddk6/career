"""BehaviorAtom typed intermediate representation (shadow, observation/audit only).

Deterministic, fail-closed extraction of observable behavior atoms from
confirmed, submission-safe applicant claims.  Atoms never create new applicant
facts: every atom is a lossless projection of already-confirmed claim text,
optionally corroborated by the same experience's action record.

Forbidden projections (never atoms):
- unconfirmed claims, claims with submission issues
- metric/result-only claims and claims containing percentage results (no behavior atoms)
- experience.actions text alone (context-only, without claim backing)
- research/company facts as applicant atoms
- any LLM-invented actor/action/object
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .profile_schema import (
    ClaimVerification,
    EvidenceRef,
    ProfileClaim,
    claim_submission_issues,
)

SCHEMA_VERSION = 1
ARCHITECTURE = "behavior_atom_shadow_v1"
ATOMS_JSON = "05_행동원자.json"

_TAIL = (
    r"(?:했다|했습니다|했으며|했고|했는데|하였으며|하였고|하여|해서|해서는|"
    r"해주었다|해주고|해|함|한|하다|합니다|하는|하며|하고|"
    r"드렸다|드렸습니다|드려|드리며|드리고|주었다|주고|주며)?"
)
_BOUNDARY = r"(?=\s|[,.。·~!?;:)\]\-–]|$)"
_VERB_SPECS: tuple[tuple[str, str], ...] = (
    ("대조", r"대조"),
    ("비교", r"비교"),
    ("검토", r"검토"),
    ("점검", r"점검"),
    ("심사", r"심사"),
    ("확인", r"확인"),
    ("발견", r"발견"),
    ("판별", r"판별"),
    ("파악", r"파악"),
    ("분류", r"분류"),
    ("구분", r"구분"),
    ("선별", r"선별"),
    ("분석", r"분석"),
    ("진단", r"진단"),
    ("취합", r"취합"),
    ("안내", r"안내"),
    ("설명", r"설명"),
    ("상담", r"상담"),
    ("소명", r"소명"),
    ("협의", r"협의"),
    ("조정", r"조정"),
    ("연계", r"연계"),
    ("보고", r"보고"),
    ("승인요청", r"승인\s*(?:을\s*)?요청"),
    ("요청", r"요청"),
    ("기록", r"기록"),
    ("작성", r"작성"),
    ("정리", r"정리"),
    ("수정", r"수정"),
    ("보완", r"보완"),
    ("개선", r"개선"),
    ("관리", r"관리"),
    ("처리", r"처리"),
    ("모니터링", r"모니터링"),
)

_VERB_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (canonical, re.compile(root + _TAIL + _BOUNDARY))
    for canonical, root in _VERB_SPECS
)

_ACTOR_APPLICANT = ("제가", "내가", "저는", "본인이", "직접", "맡아서", "담당하여", "담당했다", "혼자서")
_ACTOR_TEAM = ("팀이", "팀에서", "팀원들이", "팀원이", "우리가", "우리는", "부서가", "동료가", "전체가")
_ACTOR_SHARED = ("함께", "공동으로", "협업하여", "협업해", "공동")

_OBJECT_PREFIX_STRIP = re.compile(r"^(?:하고|하며|하여|해서|하는|후|다음|위해|하기 위해|기준으로|에 따라|에 기반해|에 기반하여|을 바탕으로|를 바탕으로|팀이|제가|내가|우리가|저는|본인이|동료가|부서가)")
_OBJECT_CONNECTOR_SPLIT = re.compile(r"(?:하여|해서|해|하며|하면서|하고|했으며|했고|한 후|후|다음|위해)")
_OBJECT_SUFFIX_STRIP = re.compile(
    r"(?:을|를|과|와|으로|로|에|에서|의|를 기준으로|을 기준으로|을 통해|를 통해|에 대해|에 대한|을 위한|를 위한|에 관한|에 맞춰|을 바탕으로|를 바탕으로)$"
)


@dataclass(frozen=True)
class BehaviorAtom:
    atom_id: str
    applicant_evidence_id: str
    experience_id: str
    claim_id: str
    source_ref_ids: tuple[str, ...]
    actor: str
    action: str
    object: str
    decision_rule: str
    constraint: str
    handoff_or_escalation: str
    result: str
    authority_status: str
    projection_kind: str
    source_text: str
    normalized_signature: str


def _actor(text: str) -> str:
    if any(marker in text for marker in _ACTOR_TEAM):
        return "team"
    if any(marker in text for marker in _ACTOR_APPLICANT):
        return "applicant"
    if any(marker in text for marker in _ACTOR_SHARED):
        return "shared"
    return "unknown"


def _object_before(text: str, start: int) -> str:
    segment = text[max(0, start - 30):start]
    segment = _OBJECT_CONNECTOR_SPLIT.split(segment)[-1]
    fragment = segment.strip(" \t")
    fragment = _OBJECT_PREFIX_STRIP.sub("", fragment)
    fragment = _OBJECT_SUFFIX_STRIP.sub("", fragment)
    return fragment[-12:]


def _match_verbs(text: str) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    for canonical, pattern in _VERB_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(start < span[1] and span[0] < end for _, start, end in matches):
                continue
            matches.append((canonical, span[0], span[1]))
    matches.sort(key=lambda item: (item[1], item[2]))
    return matches


def _profile_claim(claim: Mapping[str, Any]) -> ProfileClaim | None:
    field = str(claim.get("field", "")).strip()
    normalized_value = str(claim.get("normalized_value", "")).strip()
    if not field and not normalized_value:
        return None
    evidence = tuple(
        EvidenceRef(
            source_path=str(item.get("source_path", "")),
            paragraph_index=int(item.get("paragraph_index", 0) or 0),
            source_sha256=str(item.get("source_sha256", "")),
            excerpt_sha256=str(item.get("excerpt_sha256", "")),
        )
        for item in (claim.get("evidence", []) if isinstance(claim.get("evidence", []), list) else [])
        if isinstance(item, Mapping)
    )
    verification = None
    raw_verification = claim.get("verification")
    if isinstance(raw_verification, Mapping):
        verification = ClaimVerification(
            method=str(raw_verification.get("method", "none")),
            baseline=raw_verification.get("baseline"),
            result=raw_verification.get("result"),
            formula=raw_verification.get("formula"),
            measurement_period=raw_verification.get("measurement_period"),
            scope=raw_verification.get("scope"),
            contribution=str(raw_verification.get("contribution", "unknown")),
        )
    return ProfileClaim(
        field=field,
        normalized_value=normalized_value,
        status=str(claim.get("status", "")),
        evidence=evidence,
        claim_id=str(claim.get("claim_id", "")),
        verification=verification,
    )


def _is_metric_claim(claim: Mapping[str, Any]) -> bool:
    field = str(claim.get("field", "")).strip()
    normalized_value = str(claim.get("normalized_value", "")).strip()
    if field.startswith("metric:"):
        return True
    if re.fullmatch(
        r"[\s,]*-?\d+(?:\.\d+)?\s*(?:%|건|명|원|페이지|시간|일|개월|회)[\s]*",
        normalized_value,
    ):
        return True
    if "%" in normalized_value:
        return True
    return False


def _signature(experience_id: str, claim_id: str, action: str, actor: str) -> str:
    raw = f"{experience_id}\0{claim_id}\0{action}\0{actor}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_behavior_atoms(ledger: Mapping[str, Any]) -> dict[str, Any]:
    atoms: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for experience in ledger.get("experiences", []) or []:
        if not isinstance(experience, Mapping):
            continue
        experience_id = str(experience.get("experience_id", ""))
        actions_text = " ".join(str(item) for item in experience.get("actions", []) or [])
        action_verbs = {canonical for canonical, _, _ in _match_verbs(actions_text)}
        for claim in experience.get("claims", []) or []:
            if not isinstance(claim, Mapping):
                continue
            claim_id = str(claim.get("claim_id") or claim.get("field") or "")
            if not claim_id:
                continue
            text = str(claim.get("normalized_value", "")).strip()
            if not text:
                continue
            if _is_metric_claim(claim):
                rejected.append(
                    {
                        "code": "metric_claim_no_behavior",
                        "experience_id": experience_id,
                        "claim_id": claim_id,
                        "source_text": text[:80],
                    }
                )
                continue
            profile = _profile_claim(claim)
            issues = claim_submission_issues(profile) if profile is not None else ("claim_not_confirmed",)
            if issues:
                rejected.append(
                    {
                        "code": "unconfirmed_claim" if str(claim.get("status", "")) != "confirmed" else "claim_submission_issue",
                        "reasons": list(issues),
                        "experience_id": experience_id,
                        "claim_id": claim_id,
                        "source_text": text[:80],
                    }
                )
                continue
            matches = _match_verbs(text)
            if not matches:
                continue
            corroborated = {canonical for canonical, _, _ in matches if canonical in action_verbs}
            single = len(matches) == 1
            for canonical, start, end in matches:
                actor = _actor(text)
                object_text = _object_before(text, start)
                projection_kind = (
                    "source_bound_action"
                    if canonical in corroborated
                    else "atomic_claim_direct"
                    if single
                    else "lossless_claim_projection"
                )
                source_ref_ids = tuple(
                    str(item.get("source_path", ""))
                    for item in (claim.get("evidence", []) if isinstance(claim.get("evidence", []), list) else [])
                    if isinstance(item, Mapping) and str(item.get("source_path", "")).strip()
                )
                raw = f"{experience_id}\0{claim_id}\0{canonical}\0{object_text}\0{actor}"
                atoms.append(
                    {
                        "atom_id": "atom_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
                        "applicant_evidence_id": f"applicant:{experience_id}:{claim_id}",
                        "experience_id": experience_id,
                        "claim_id": claim_id,
                        "source_ref_ids": list(source_ref_ids),
                        "actor": actor,
                        "action": canonical,
                        "object": object_text,
                        "decision_rule": "",
                        "constraint": "",
                        "handoff_or_escalation": "",
                        "result": "",
                        "authority_status": "factual",
                        "projection_kind": projection_kind,
                        "source_text": text[max(0, start - 40):end + 12],
                        "normalized_signature": _signature(experience_id, claim_id, canonical, actor),
                    }
                )
        for canonical, _, _ in _match_verbs(actions_text):
            if canonical not in action_verbs:
                continue
            if not any(
                atom["action"] == canonical and atom["experience_id"] == experience_id
                for atom in atoms
            ):
                rejected.append(
                    {
                        "code": "context_only_action_no_claim",
                        "experience_id": experience_id,
                        "action": canonical,
                        "source_text": actions_text[:80],
                    }
                )
    atoms.sort(key=lambda item: (item["experience_id"], item["claim_id"], item["action"], item["atom_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture": ARCHITECTURE,
        "policy": {"decision_effect": "none_shadow_mode", "factual_authority_granted": False},
        "atoms": atoms,
        "rejected": rejected,
        "summary": {
            "atom_count": len(atoms),
            "rejected_projection_count": len(rejected),
            "source_bound_action_count": sum(1 for item in atoms if item["projection_kind"] == "source_bound_action"),
        },
    }


def _read_ledger(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "02_확정경험원장.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def write_behavior_atoms(
    run_dir: Path, ledger: Mapping[str, Any] | None = None
) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    payload = build_behavior_atoms(ledger if ledger is not None else _read_ledger(run_dir))
    jp = run_dir / ATOMS_JSON
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mp = run_dir / "05_행동원자.md"
    lines = [
        "# 행동 원자 (BehaviorAtom)",
        "",
        "> 관측/감사 전용 그림자 계층이며 생산 선택에 영향을 주지 않는다.",
        "",
        f"- atoms: {payload['summary']['atom_count']} / rejected projections: {payload['summary']['rejected_projection_count']}",
        "",
    ]
    for atom in payload["atoms"]:
        lines.append(f"- `{atom['atom_id']}` {atom['action']} · {atom['object']} · actor={atom['actor']} · {atom['projection_kind']}")
    lines.append("")
    mp.write_text("\n".join(lines), encoding="utf-8")
    return jp, mp, payload