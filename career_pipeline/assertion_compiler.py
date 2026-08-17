"""Context-preserving final-assertion compiler. It verifies; it never creates authority."""
from __future__ import annotations
from hashlib import sha256
import json,re
from pathlib import Path
from typing import Any,Mapping,Sequence
from .authority_contract import AuthorityContext,AuthorityRecord,authority_context_to_dict,build_authority_context,lexical_tokens,metric_values
SCHEMA_VERSION=1; ASSERTION_JSON="12_주장컴파일.json"; ASSERTION_MD="12_주장컴파일.md"
_SENTENCE=re.compile(r"(?<=[.!?。！？])\s+|\n+"); _CLAUSE=re.compile(r"\s*(?:,|;| 그리고 | 또한 | 하지만 | 반면 | 따라서 | 그 결과 )\s*")
_CAUSAL=("때문","덕분","통해","결과","따라","영향","기여","개선","증가","감소","절감","향상","달성","해결"); _OWN=("제가","저는","직접","단독","주도","제 역할"); _CAUSE_VERBS=("달성","개선","증가","감소","절감","향상","해결")
def _get(v:Any,k:str,d:Any=None)->Any:return v.get(k,d) if isinstance(v,Mapping) else getattr(v,k,d)
def _split(text:str)->list[str]:return [re.sub(r"\s+"," ",x).strip() for x in _SENTENCE.split(text or "") if x.strip()]
def _clauses(sentence:str)->list[str]:
    pieces=[x.strip() for x in _CLAUSE.split(sentence) if x.strip()]
    if len(pieces)<=1:return [sentence.strip()]
    out=[];buf=""
    for p in pieces:
        candidate=(buf+" "+p).strip() if buf else p
        if len(candidate)<18:buf=candidate;continue
        out.append(candidate);buf=""
    if buf:
        if out:out[-1]=(out[-1]+" "+buf).strip()
        else:out.append(buf)
    return out or [sentence.strip()]
def _score(text:str,row:AuthorityRecord)->float:
    tokens=lexical_tokens(text)
    if not tokens or not row.tokens:return 0.0
    return len(tokens&row.tokens)/max(1,min(len(tokens),8))
def _kind(text:str,support:Sequence[AuthorityRecord])->str:
    if metric_values(text):return "metric"
    if any(c in text for c in _CAUSAL):return "causal"
    kinds={r.source_kind for r in support};return "applicant_fact" if kinds=={"applicant"} else "research_fact" if kinds=={"research"} else "synthesis"
def compile_response_assertions(question_index:int,answer:str,context:AuthorityContext)->list[dict[str,Any]]:
    records=[r for r in context.for_question(question_index) if r.factual_authority];assertions=[];sentences=_split(answer)
    for si,sentence in enumerate(sentences,1):
        for ci,clause in enumerate(_clauses(sentence),1):
            metrics=set(metric_values(clause));ranked=sorted(((round(_score(clause,r),4),r) for r in records),key=lambda x:(-x[0],x[1].authority_id));support=[r for score,r in ranked if score>=0.18][:4];authorised={m for r in support for m in r.metric_values}
            if metrics and not metrics.issubset(authorised):
                merged=[];seen=set()
                for r in support+[r for r in records if metrics&set(r.metric_values)]:
                    if r.authority_id not in seen:seen.add(r.authority_id);merged.append(r)
                support=merged;authorised={m for r in support for m in r.metric_values}
            causal=any(c in clause for c in _CAUSAL);app=[r for r in support if r.source_kind=="applicant"];caused=any(str(r.metadata.get("contribution"))=="caused" for r in app);contradictions=[];unsupported=sorted(metrics-authorised)
            if unsupported:contradictions.append("unsupported_metric:"+",".join(unsupported))
            ownership_overclaim=causal and any(c in clause for c in _OWN) and any(str(r.metadata.get("contribution","unknown")) in {"observed","unknown"} for r in app) and any(v in clause for v in _CAUSE_VERBS)
            if ownership_overclaim:contradictions.append("ownership_overclaim_risk")
            status="unsupported" if (unsupported or ownership_overclaim) else "needs_review" if (not support or (causal and not caused)) else "bounded_interpretation" if len(support)>1 and _kind(clause,support)=="synthesis" else "supported"
            aid="ast_"+sha256(f"{question_index}\0{si}\0{ci}\0{clause}".encode()).hexdigest()[:18]
            assertions.append({"assertion_id":aid,"question_index":question_index,"source_sentence_index":si,"source_sentence":sentence,"atomic_text":clause,"context_before":sentences[si-2] if si>1 else "","context_after":sentences[si] if si<len(sentences) else "","assertion_type":_kind(clause,support),"supported_by":[r.authority_id for r in support],"support_scores":{r.authority_id:score for score,r in ranked if r in support},"contradicts":contradictions,"metric_values":sorted(metrics),"causal_scope":"verified_caused" if causal and caused else "bounded_not_verified" if causal else "not_causal","question_scope":[question_index],"authority_status":status})
    return assertions
def compile_assertion_report(responses:Sequence[Any],context:AuthorityContext)->dict[str,Any]:
    rows=[]
    for response in responses:rows+=compile_response_assertions(int(_get(response,"question_index",0)),str(_get(response,"answer","")),context)
    statuses={};types={}
    for row in rows:statuses[row["authority_status"]]=statuses.get(row["authority_status"],0)+1;types[row["assertion_type"]]=types.get(row["assertion_type"],0)+1
    return {"schema_version":SCHEMA_VERSION,"architecture":"context_preserving_assertion_compiler_v1","authority_contract":authority_context_to_dict(context),"assertions":rows,"summary":{"total":len(rows),"by_status":statuses,"by_type":types,"unsupported":statuses.get("unsupported",0),"needs_review":statuses.get("needs_review",0),"hard_contradictions":sum(bool(r["contradicts"]) for r in rows)}}
def write_assertion_artifacts(run_dir:Path,*,draft_path:Path|None=None):
    from .interview_intelligence.schema import _resolve_draft_path
    from .profile_schema import load_ledger
    from .research_evidence import load_research_claims
    from .authority_contract import _research_raw
    run_dir=run_dir.resolve();draft=_resolve_draft_path(run_dir,draft_path);payload=json.loads(draft.read_text(encoding="utf-8"));responses=[dict(r) for r in payload if isinstance(r,Mapping)];ledger=load_ledger(run_dir/"02_확정경험원장.json");rp=run_dir/"04_공식근거.json";research=load_research_claims(rp);context=build_authority_context(responses,ledger,research,research_raw=_research_raw(rp));report=compile_assertion_report(responses,context);report["source_final_draft"]=str(draft);jp,mp=run_dir/ASSERTION_JSON,run_dir/ASSERTION_MD;jp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");lines=["# 최종 주장 컴파일","",f"- 총 주장: {report['summary']['total']}",f"- unsupported: {report['summary']['unsupported']}",f"- needs_review: {report['summary']['needs_review']}",""]
    for r in report["assertions"]:lines += [f"## {r['assertion_id']} · 문항 {r['question_index']}",f"- 상태: `{r['authority_status']}` / 유형: `{r['assertion_type']}`",f"- 주장: {r['atomic_text']}",f"- 근거: {', '.join(r['supported_by']) or '-'}",f"- causal_scope: {r['causal_scope']}",f"- 이슈: {', '.join(r['contradicts']) or '-'}",""]
    mp.write_text("\n".join(lines),encoding="utf-8");return jp,mp,report
