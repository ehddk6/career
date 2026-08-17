"""Adversarial system benchmark for authority safety and evaluation invariance."""
from __future__ import annotations
import json,re
from pathlib import Path
from typing import Any,Callable,Mapping,Sequence
from .assertion_compiler import compile_response_assertions
from .authority_contract import AuthorityContext
Validator=Callable[[int,str,AuthorityContext],Mapping[str,Any]];REPORT_FILE="14_시스템불변성벤치마크.json"
def default_validator(q:int,text:str,context:AuthorityContext)->dict[str,Any]:
    rows=compile_response_assertions(q,text,context);unsafe=any(r["authority_status"]=="unsupported" or r["contradicts"] for r in rows);return {"safe":not unsafe,"assertions":rows}
def unsupported_metric_insertion(text:str)->str:return text.rstrip()+" 추가로 987654건을 단독으로 달성했습니다."
def ownership_escalation(text:str)->str:return text.replace("팀이","제가 단독으로",1) if "팀이" in text else text.rstrip()+" 이 성과는 제가 단독으로 달성했습니다."
def benign_whitespace(text:str)->str:return "  ".join(text.split())
def benign_clause_order(text:str)->str:
    parts=[p.strip() for p in re.split(r"(?<=[.!?])\s+",text) if p.strip()];return " ".join(reversed(parts)) if len(parts)>1 else text
def run_case(case:Mapping[str,Any],context:AuthorityContext,validator:Validator=default_validator)->dict[str,Any]:
    q=int(case["question_index"]);base=str(case["answer"]);baseline=dict(validator(q,base,context));mutations=[("unsupported_metric",unsupported_metric_insertion(base),False),("ownership_escalation",ownership_escalation(base),False),("whitespace",benign_whitespace(base),True),("sentence_order",benign_clause_order(base),True)];rows=[];ud=ut=bs=bt=0
    for name,text,benign in mutations:
        result=dict(validator(q,text,context));same=result.get("safe")==baseline.get("safe")
        if benign:bt+=1;bs+=int(same)
        else:ut+=1;ud+=int(result.get("safe") is False)
        rows.append({"mutation":name,"benign":benign,"safe":result.get("safe"),"invariant_to_baseline":same})
    return {"case_id":case.get("case_id"),"baseline_safe":baseline.get("safe"),"mutations":rows,"metrics":{"unsafe_detection_rate":round(ud/max(1,ut),3),"benign_invariance_rate":round(bs/max(1,bt),3)}}
def run_benchmark(cases:Sequence[Mapping[str,Any]],contexts:Mapping[str,AuthorityContext])->dict[str,Any]:
    rows=[run_case(c,contexts[str(c.get("case_id",""))]) for c in cases];unsafe=sum(r["metrics"]["unsafe_detection_rate"] for r in rows)/max(1,len(rows));benign=sum(r["metrics"]["benign_invariance_rate"] for r in rows)/max(1,len(rows));return {"schema_version":1,"architecture":"authority_invariance_system_benchmark_v1","cases":rows,"summary":{"case_count":len(rows),"mean_unsafe_detection_rate":round(unsafe,3),"mean_benign_invariance_rate":round(benign,3)}}
def benchmark_run(run_dir:Path)->dict[str,Any]:
    from .authority_contract import _research_raw,build_authority_context
    from .interview_intelligence.schema import _resolve_draft_path
    from .profile_schema import load_ledger
    from .research_evidence import load_research_claims
    run_dir=run_dir.resolve();draft=_resolve_draft_path(run_dir);payload=json.loads(draft.read_text(encoding="utf-8"));responses=[dict(r) for r in payload if isinstance(r,Mapping)];ledger=load_ledger(run_dir/"02_확정경험원장.json");rp=run_dir/"04_공식근거.json";research=load_research_claims(rp);context=build_authority_context(responses,ledger,research,research_raw=_research_raw(rp));cases=[{"case_id":f"q{r['question_index']}","question_index":int(r["question_index"]),"answer":str(r["answer"])} for r in responses if isinstance(r.get("question_index"),int) and isinstance(r.get("answer"),str)];report=run_benchmark(cases,{c["case_id"]:context for c in cases});report["source_final_draft"]=str(draft);(run_dir/REPORT_FILE).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return report
def main(argv:Sequence[str]|None=None)->int:
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--run",required=True,type=Path);args=p.parse_args(argv);report=benchmark_run(args.run);print(json.dumps(report["summary"],ensure_ascii=False));s=report["summary"];return 0 if s.get("mean_unsafe_detection_rate",0)>=1 and s.get("mean_benign_invariance_rate",0)>=0.9 else 3
if __name__=="__main__":raise SystemExit(main())
