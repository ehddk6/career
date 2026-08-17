"""Converge Research Intelligence output with legacy audit without inventing facts."""
from __future__ import annotations
import json,re
from pathlib import Path
from typing import Any,Mapping
from .authority_contract import research_is_submission_authority

def _read(path:Path,default:Any)->Any:
    if not path.is_file(): return default
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError):return default

def _question_indexes(text:str)->list[int]: return sorted({int(v) for v in re.findall(r"문항\s*(\d+)",text or "")})
def _coverage_map(coverage:Mapping[str,Any])->dict[str,set[int]]:
    result={}
    for question in coverage.get("questions",[]) or []:
        if not isinstance(question,Mapping) or not isinstance(question.get("question_index"),int):continue
        index=int(question["question_index"])
        for slot in question.get("slots",[]) or []:
            if isinstance(slot,Mapping):
                for cid in slot.get("accepted_claim_ids",[]) or []:result.setdefault(str(cid),set()).add(index)
    return result

def canonical_research_appendix(run_dir:Path)->str:
    claims=_read(run_dir/"04_공식근거.json",[]); coverage=_read(run_dir/"04_근거커버리지.json",{}); conflicts=_read(run_dir/"04_근거충돌.json",{})
    claims=claims if isinstance(claims,list) else []; coverage=coverage if isinstance(coverage,Mapping) else {}; conflicts=conflicts if isinstance(conflicts,Mapping) else {}; mapped=_coverage_map(coverage)
    authoritative=[row for row in claims if isinstance(row,Mapping) and research_is_submission_authority(row,row)]
    lines=["","## 확인된 사실",""]
    if authoritative:
        for row in authoritative:
            cid=str(row.get("claim_id","")); role=str(row.get("argument_role",row.get("claim_type",""))); source=str(row.get("source_url","")); lines.append(f"- `{cid}` [{role}] {row.get('claim','')}"+(f" — {source}" if source else ""))
    else:lines.append("- 제출 사실 권한을 가진 공식 근거가 아직 없습니다.")
    lines += ["","## 해석","","- 자동 사실 추론 없음. 이 구역은 사실 권한을 추가하지 않으며, 지원자 해석은 최종 답변의 논증 계층에서만 작성합니다.","","## 확인 필요",""]
    unresolved=[str(x) for x in conflicts.get("unresolved_groups",[]) or []]; missing=[]
    for question in coverage.get("questions",[]) or []:
        if not isinstance(question,Mapping):continue
        for slot in question.get("slots",[]) or []:
            if isinstance(slot,Mapping) and slot.get("required") and slot.get("status")!="pass":missing.append(f"문항 {question.get('question_index')}:{slot.get('argument_role')}({slot.get('status')})")
    if not unresolved and not missing:lines.append("- 없음")
    else:
        lines += [f"- 미해결 근거충돌: {v}" for v in unresolved]; lines += [f"- 미충족 조사슬롯: {v}" for v in missing]
    lines += ["","## 문항·면접 활용 맵",""]
    if not authoritative:lines.append("- 아직 매핑할 제출 권한 근거 없음")
    for row in authoritative:
        cid=str(row.get("claim_id","")); indexes=set(mapped.get(cid,set())); indexes.update(_question_indexes(str(row.get("application_use","")))); scope=" · ".join(f"문항 {i}" for i in sorted(indexes)) or str(row.get("application_use","")).strip() or "검토 필요"; lines.append(f"- `{cid}` → {scope} · 면접 방어 가능")
    return "\n".join(lines).rstrip()+"\n"

def ensure_canonical_research_pack(run_dir:Path)->Path:
    path=run_dir/"04_기업직무조사.md"; text=path.read_text(encoding="utf-8") if path.is_file() else "# 기업·직무 조사팩\n"; marker="<!-- canonical-research-contract:v1 -->"
    if marker in text:text=text.split(marker,1)[0].rstrip()+"\n"
    path.write_text(text.rstrip()+"\n\n"+marker+"\n"+canonical_research_appendix(run_dir),encoding="utf-8"); return path
