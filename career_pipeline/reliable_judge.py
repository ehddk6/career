"""Position-swapped, perturbation-aware pairwise judging with explicit abstention."""
from __future__ import annotations
import json,re
from typing import Any,Callable,Mapping,Sequence
ModelRunner=Callable[[str,str,str,int],dict[str,Any]|str];VALID={"A","B","TIE","ABSTAIN"}
def _parse(v):
    if isinstance(v,Mapping):return dict(v)
    text=str(v).strip();m=re.search(r"\{.*\}",text,re.S);p=json.loads(m.group(0) if m else text)
    if not isinstance(p,dict):raise ValueError("judge response must be an object")
    return p
def _prompt(a,b,rubric,role):return json.dumps({"task":"pairwise application-quality comparison","role":role,"rules":["Use only supplied candidate text and rubric.","Do not infer facts not supplied.","Prefer TIE when materially equivalent.","Use ABSTAIN when evidence is insufficient or unstable.","Return JSON only."],"rubric":dict(rubric),"candidate_A":a,"candidate_B":b,"output_schema":{"preference":"A|B|TIE|ABSTAIN","reason":"short rubric-grounded reason","confidence":"0..1"}},ensure_ascii=False,separators=(",",":"))
def _canon(pref,orientation):
    pref=str(pref).upper()
    if pref not in VALID:return "ABSTAIN"
    if pref in {"TIE","ABSTAIN"}:return pref
    return pref if orientation=="AB" else ("B" if pref=="A" else "A")
def _summary(rows):
    counts={k:0 for k in VALID}
    for r in rows:counts[r["canonical_preference"]]+=1
    decisive=counts["A"]+counts["B"];winner="A" if counts["A"]>counts["B"] else "B" if counts["B"]>counts["A"] else None;margin=abs(counts["A"]-counts["B"])/decisive if decisive else 0;pairs={}
    for r in rows:pairs.setdefault((r["model_id"],r["rubric_variant"],r["role"]),{})[r["orientation"]]=r["canonical_preference"]
    flips=sum(1 for p in pairs.values() if p.get("AB") in {"A","B"} and p.get("BA") in {"A","B"} and p["AB"]!=p["BA"]);paired=sum(1 for p in pairs.values() if "AB" in p and "BA" in p);flip=flips/paired if paired else 0;ab=(counts["TIE"]+counts["ABSTAIN"])/max(1,len(rows));stable=bool(winner) and margin>=0.5 and flip<=0.15 and ab<=0.4
    return {"counts":counts,"winner":winner,"decisive_margin":round(margin,3),"position_flip_rate":round(flip,3),"abstain_or_tie_rate":round(ab,3),"stable":stable}
def compare_candidates(candidate_a:str,candidate_b:str,*,rubric:Mapping[str,Any],model_ids:Sequence[str],runner:ModelRunner,timeout_ms:int=180000)->dict[str,Any]:
    if not model_ids:raise ValueError("model_ids must not be empty")
    variants=[("evidence_first","structured_reviewer",rubric),("question_first","skeptical_reviewer",dict(reversed(list(rubric.items()))))];rows=[]
    for round_index,(variant,role,current) in enumerate(variants,1):
        for model_id in model_ids:
            for orientation in ("AB","BA"):
                left,right=(candidate_a,candidate_b) if orientation=="AB" else (candidate_b,candidate_a);p=_parse(runner(f"reliable_judge_{variant}_{orientation.lower()}",_prompt(left,right,current,role),model_id,timeout_ms));pref=str(p.get("preference","ABSTAIN")).upper();rows.append({"round":round_index,"model_id":model_id,"rubric_variant":variant,"role":role,"orientation":orientation,"raw_preference":pref,"canonical_preference":_canon(pref,orientation),"reason":str(p.get("reason","")),"confidence":p.get("confidence")})
        summary=_summary(rows)
        if summary["stable"]:break
    summary=_summary(rows);return {"schema_version":1,"protocol":"sequential_position_swapped_pairwise_v1","status":"decided" if summary["stable"] else "evaluation_uncertain","summary":summary,"judgments":rows,"factual_authority_granted":False}
def resolve_comparison_graph(comparisons:Sequence[Mapping[str,Any]])->dict[str,Any]:
    edges={};uncertain=[]
    for row in comparisons:
        a,b=str(row.get("candidate_a","")),str(row.get("candidate_b",""));winner=row.get("winner")
        if winner not in {a,b}:uncertain.append((a,b));continue
        loser=b if winner==a else a;edges.setdefault(winner,set()).add(loser);edges.setdefault(loser,set())
    visited=set();active=set();cycles=[]
    def dfs(node,path):
        if node in active:cycles.append(path[path.index(node):]+[node] if node in path else path+[node]);return
        if node in visited:return
        active.add(node);path.append(node)
        for nxt in sorted(edges.get(node,set())):dfs(nxt,path)
        path.pop();active.remove(node);visited.add(node)
    for node in sorted(edges):dfs(node,[])
    indegree={n:0 for n in edges}
    for targets in edges.values():
        for t in targets:indegree[t]=indegree.get(t,0)+1
    leaders=sorted([n for n,d in indegree.items() if d==0]);return {"status":"evaluation_uncertain" if cycles or uncertain or len(leaders)!=1 else "decided","leaders":leaders,"cycles":cycles,"uncertain_pairs":uncertain,"edges":{k:sorted(v) for k,v in edges.items()}}
