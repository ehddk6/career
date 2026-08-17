"""Whole-application Evidence x Job-Signal portfolio optimiser. Planning only."""
from __future__ import annotations
import json,re
from pathlib import Path
from typing import Any,Mapping
SCHEMA_VERSION=1;PORTFOLIO_JSON="05_근거포트폴리오.json";PORTFOLIO_MD="05_근거포트폴리오.md";_WORD=re.compile(r"[가-힣A-Za-z0-9]{2,}");_STOP={"지원","직무","업무","기관","회사","관련","경험","역량","필요","통해","대한","문항","설명"}
def _tokens(text:str)->set[str]:return {x.casefold() for x in _WORD.findall(text or "") if x.casefold() not in _STOP}
def _read(path:Path,default:Any)->Any:
    if not path.is_file():return default
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError):return default
def _signals(posting:Mapping[str,Any],state:Mapping[str,Any])->list[dict[str,Any]]:
    values=[]
    for key,weight in (("duties",1.0),("competencies",1.15),("preferred",0.8),("requirements",0.9)):
        for raw in posting.get(key,[]) or []:
            text=str(raw).strip()
            if text:values.append((key,text,weight))
    for q in state.get("questions",[]) or []:
        if isinstance(q,Mapping) and str(q.get("prompt","")).strip():values.append(("question",str(q["prompt"]),0.75))
    seen=set();rows=[]
    for source,text,weight in values:
        norm=re.sub(r"\s+","",text).casefold()
        if not norm or norm in seen:continue
        seen.add(norm);rows.append({"signal_id":f"sig_{len(rows)+1}","source":source,"label":text[:160],"weight":weight,"tokens":sorted(_tokens(text))})
        if len(rows)>=16:break
    return rows
def _candidates(ledger:Mapping[str,Any],research:list[Any])->list[dict[str,Any]]:
    rows=[]
    for exp in ledger.get("experiences",[]) if isinstance(ledger,Mapping) else []:
        if not isinstance(exp,Mapping) or exp.get("status")!="confirmed":continue
        eid=str(exp.get("experience_id",""));base=" ".join(str(exp.get(k,"")) for k in ("title","role","situation"))+" "+" ".join(str(x) for x in exp.get("actions",[])+exp.get("outcomes",[])+exp.get("competencies",[]))
        for claim in exp.get("claims",[]) or []:
            if not isinstance(claim,Mapping) or claim.get("status")!="confirmed":continue
            cid=str(claim.get("claim_id") or claim.get("field") or "");v=claim.get("verification",{}) if isinstance(claim.get("verification"),Mapping) else {};method=str(v.get("method","none"));contribution=str(v.get("contribution","unknown"));text=(base+" "+str(claim.get("field",""))+" "+str(claim.get("normalized_value",""))).strip();defensibility=1.0+(0.35 if method not in {"","none"} else 0)+(0.35 if contribution in {"caused","contributed"} else 0);risk=(0.45 if contribution in {"observed","unknown"} else 0)+(0.25 if "%" in str(claim.get("normalized_value","")) and method!="before_after" else 0)
            rows.append({"evidence_id":f"applicant:{eid}:{cid}","source_kind":"applicant","experience_id":eid,"tokens":sorted(_tokens(text)),"defensibility":round(defensibility,3),"risk":round(risk,3),"factual_authority_granted":False})
    for claim in research:
        if not isinstance(claim,Mapping) or str(claim.get("verification_status","confirmed")) not in {"confirmed","verified"}:continue
        try:tier=int(claim.get("source_tier",5))
        except (TypeError,ValueError):tier=5
        if tier>2 and claim.get("submission_authority") is not True:continue
        cid=str(claim.get("claim_id",""));text=str(claim.get("claim",""))+" "+str(claim.get("evidence_excerpt",""));fresh=str(claim.get("freshness_class","unknown"));rows.append({"evidence_id":f"research:{cid}","source_kind":"research","tokens":sorted(_tokens(text)),"defensibility":round(1.15+max(0,(2-tier)*0.12),3),"risk":0.35 if fresh in {"unknown","stale"} else 0.1 if fresh in {"current","posting_bound","stable"} else 0.2,"factual_authority_granted":False})
    return rows
def _rel(c:Mapping[str,Any],s:Mapping[str,Any])->float:
    ct,st=set(c.get("tokens",[])),set(s.get("tokens",[]));return len(ct&st)/max(1,min(len(st),8)) if ct and st else 0.0
def build_evidence_portfolio(run_dir:Path,*,max_per_question:int=2)->dict[str,Any]:
    run_dir=run_dir.resolve();state=_read(run_dir/"run.json",{});posting=_read(run_dir/"00_채용공고분석.json",{});ledger=_read(run_dir/"02_확정경험원장.json",{});research=_read(run_dir/"04_공식근거.json",[]);state=state if isinstance(state,Mapping) else {};posting=posting if isinstance(posting,Mapping) else {};ledger=ledger if isinstance(ledger,Mapping) else {};research=research if isinstance(research,list) else [];signals=_signals(posting,state);candidates=_candidates(ledger,research);usage={};assignments=[];covered=set()
    for q in state.get("questions",[]) or []:
        if not isinstance(q,Mapping) or not isinstance(q.get("index"),int):continue
        qi=int(q["index"]);qt=_tokens(str(q.get("prompt","")));scored=[]
        for c in candidates:
            ss={s["signal_id"]:round(_rel(c,s),3) for s in signals};weighted=sum(ss[s["signal_id"]]*float(s["weight"]) for s in signals);qo=len(qt&set(c.get("tokens",[])))/max(1,min(len(qt),8)) if qt else 0;score=weighted+qo*1.1+float(c.get("defensibility",1))*0.75-float(c.get("risk",0))*0.8-usage.get(str(c["evidence_id"]),0)*0.35;scored.append((score,c,ss))
        scored.sort(key=lambda x:(-x[0],str(x[1]["evidence_id"])));chosen=[];seen_exp=set()
        for score,c,ss in scored:
            if score<=0:continue
            exp=str(c.get("experience_id",""))
            if exp and exp in seen_exp and len(chosen)+1<max_per_question:continue
            top=[sid for sid,val in sorted(ss.items(),key=lambda x:(-x[1],x[0])) if val>0][:4];chosen.append({"evidence_id":c["evidence_id"],"source_kind":c["source_kind"],"planning_score":round(score,3),"covered_signal_ids":top,"factual_authority_granted":False});usage[str(c["evidence_id"])]=usage.get(str(c["evidence_id"]),0)+1;covered.update(top);seen_exp.add(exp) if exp else None
            if len(chosen)>=max_per_question:break
        assignments.append({"question_index":qi,"preferred_evidence":chosen})
    total=sum(float(s["weight"]) for s in signals) or 1;cov=sum(float(s["weight"]) for s in signals if s["signal_id"] in covered)
    return {"schema_version":SCHEMA_VERSION,"architecture":"evidence_job_signal_portfolio_v1","policy":"planning_only_never_factual_authority","signals":signals,"assignments":assignments,"summary":{"signal_count":len(signals),"candidate_count":len(candidates),"covered_signal_count":len(covered),"weighted_signal_coverage":round(cov/total,3),"reused_evidence_ids":sorted([eid for eid,count in usage.items() if count>1])},"factual_authority_granted":False}
def portfolio_for_stage(plan:Mapping[str,Any],stage:str)->dict[str,Any]:
    m=re.search(r"(?:^|_)q(\d+)(?:_|$)",stage);q=int(m.group(1)) if m else None;result={"policy":plan.get("policy"),"factual_authority_granted":False,"summary":plan.get("summary",{}),"signals":[{"signal_id":s.get("signal_id"),"label":s.get("label"),"weight":s.get("weight")} for s in plan.get("signals",[]) if isinstance(s,Mapping)]}
    if q is not None:result["question_index"]=q;result["assignment"]=next((r for r in plan.get("assignments",[]) if isinstance(r,Mapping) and r.get("question_index")==q),{})
    else:result["assignments"]=plan.get("assignments",[])
    return result
def write_evidence_portfolio(run_dir:Path):
    plan=build_evidence_portfolio(run_dir);jp,mp=run_dir/PORTFOLIO_JSON,run_dir/PORTFOLIO_MD;jp.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");lines=["# 근거 × 직무신호 포트폴리오","","> 계획 계층이며 사실 권한을 추가하지 않는다.","",f"- weighted signal coverage: {plan['summary']['weighted_signal_coverage']}",""]
    for row in plan["assignments"]:
        lines.append(f"## 문항 {row['question_index']}");lines += [f"- `{x['evidence_id']}` → {', '.join(x['covered_signal_ids'])} (score={x['planning_score']})" for x in row["preferred_evidence"]];lines.append("")
    mp.write_text("\n".join(lines),encoding="utf-8");return jp,mp,plan
