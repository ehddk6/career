"""Evidence-to-Signal convergence layer for the Career Pipeline Golden Path.

Keeps proven legacy modules but makes them consume one canonical authority
contract, injects evidence-portfolio planning, and verifies final assertions.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
from typing import Any,Mapping
from . import golden_path as gp
from .assertion_compiler import ASSERTION_JSON,write_assertion_artifacts
from .authority_contract import canonical_metric_values_for_responses,research_is_submission_authority
from .evidence_portfolio import build_evidence_portfolio,portfolio_for_stage,write_evidence_portfolio
from .research_contract import ensure_canonical_research_pack
CONVERGENCE_VERSION="evidence_to_signal_contract_v1";_BASE_DEFAULT_SERVICES=gp.default_services;_BASE_RUN_AUTHORITY_VIEW=gp._run_authority_view
def _hash_json(v):return sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def _authority_view(run:Path)->dict[str,Any]:
    value=dict(_BASE_RUN_AUTHORITY_VIEW(run));value["contract_convergence_version"]=CONVERGENCE_VERSION;return value
def _raw_research(run:Path)->dict[str,dict[str,Any]]:
    path=run/"04_공식근거.json"
    if not path.is_file():return {}
    try:p=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError):return {}
    return {str(r.get("claim_id")):dict(r) for r in p if isinstance(r,Mapping) and r.get("claim_id")} if isinstance(p,list) else {}
def _compat_research_score(run:Path,audit_module:Any,original:Any):
    raw=_raw_research(run);submission={cid for cid,row in raw.items() if research_is_submission_authority(row,row)};stable={cid for cid,row in raw.items() if cid in submission and str(row.get("freshness_class","")) in {"stable","posting_bound"}}
    def wrapped(run_dir,state,questions,responses):
        _,issues=original(run_dir,state,questions,responses);filtered=[]
        for issue in issues:
            msg=str(getattr(issue,"message",""));code=str(getattr(issue,"code",""))
            if code=="weak_source_type" and any(cid in msg for cid in submission):continue
            if code=="missing_source_date" and any(cid in msg for cid in stable):continue
            filtered.append(issue)
        return audit_module._deduct(25,filtered),filtered
    return wrapped
def _augment_audit(run:Path,audit_module:Any,payload:dict[str,Any])->dict[str,Any]:
    path=run/ASSERTION_JSON
    if not path.is_file():return payload
    try:report=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError):return payload
    summary=report.get("summary",{}) if isinstance(report,Mapping) else {};unsupported=int(summary.get("unsupported",0) or 0) if isinstance(summary,Mapping) else 0;needs=int(summary.get("needs_review",0) or 0) if isinstance(summary,Mapping) else 0;issues=list(payload.get("issues",[])) if isinstance(payload.get("issues"),list) else [];sections=payload.get("sections",{}) if isinstance(payload.get("sections"),Mapping) else {};cover=sections.get("cover_letter",{}) if isinstance(sections,Mapping) else {};penalty=0
    if unsupported:issues.append({"category":"assertion","code":"unsupported_final_assertion","severity":"high","message":f"최종 답변에 authority contract가 지지하지 못한 주장이 {unsupported}개 있습니다.","question_index":0});penalty+=8
    if needs:issues.append({"category":"assertion","code":"causal_scope_review_required","severity":"medium","message":f"인과·기여 범위를 추가 확인해야 하는 주장이 {needs}개 있습니다.","question_index":0});penalty+=4
    if penalty and isinstance(cover,dict):cover["score"]=max(0,int(cover.get("score",0))-penalty)
    total=sum(int(s.get("score",0)) for s in sections.values() if isinstance(s,Mapping));payload.update(issues=issues,score=total,internal_validation_score=total,quality_gate="fail" if any(isinstance(r,Mapping) and r.get("severity")=="high" for r in issues) else "pass",human_review_recommended=bool(issues),recommendation="내부검증 우수" if total>=95 else "내부검증 통과" if total>=90 else "내부검증 보완 필요",assertion_compiler={"unsupported":unsupported,"needs_review":needs,"artifact":ASSERTION_JSON});(run/"11_최종품질감사.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");(run/"11_최종품질감사.md").write_text(audit_module.render_quality_audit(payload),encoding="utf-8");return payload
def converged_services()->gp.GoldenPathServices:
    base=_BASE_DEFAULT_SERVICES()
    def research_gate(run):
        report=dict(base.research_gate(run));ensure_canonical_research_pack(run);report["contract_convergence"]=CONVERGENCE_VERSION;return report
    def strategy_fingerprint(run):return _hash_json({"base":base.strategy_fingerprint(run),"evidence_portfolio":build_evidence_portfolio(run),"contract":CONVERGENCE_VERSION})
    def write_draft(run,config):
        _,_,portfolio=write_evidence_portfolio(run);import career_pipeline.integrated_writer as iw;original=iw.strategy_prior_for_stage
        def with_portfolio(packet,stage):
            result=dict(original(packet,stage));result["evidence_portfolio"]=portfolio_for_stage(portfolio,stage);return result
        iw.strategy_prior_for_stage=with_portfolio
        try:report=dict(base.write_draft(run,config))
        finally:iw.strategy_prior_for_stage=original
        report["evidence_portfolio"]={"artifact":"05_근거포트폴리오.json","weighted_signal_coverage":portfolio.get("summary",{}).get("weighted_signal_coverage"),"factual_authority_granted":False};return report
    def finalize(run,config):
        import career_pipeline.orchestrator as orchestrator
        original=orchestrator.referenced_claim_values;orchestrator.referenced_claim_values=lambda responses,ledger:canonical_metric_values_for_responses(run,responses,ledger)
        try:return base.finalize(run,config)
        finally:orchestrator.referenced_claim_values=original
    def compile_interview(run):
        _,_,assertions=write_assertion_artifacts(run);plan=dict(base.compile_interview(run));plan["assertion_compiler"]={"artifact":ASSERTION_JSON,"summary":assertions.get("summary",{}),"policy":"diagnostic_and_audit_gate_never_factual_authority"};path=run/"08_면접지능설계.json"
        if path.is_file():path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return plan
    def audit(run):
        ensure_canonical_research_pack(run)
        if not (run/ASSERTION_JSON).is_file():write_assertion_artifacts(run)
        import career_pipeline.audit as audit_module
        ov,ors=audit_module.referenced_claim_values,audit_module._research_score;audit_module.referenced_claim_values=lambda responses,ledger:canonical_metric_values_for_responses(run,responses,ledger);audit_module._research_score=_compat_research_score(run,audit_module,ors)
        try:payload=dict(base.audit(run))
        finally:audit_module.referenced_claim_values=ov;audit_module._research_score=ors
        return _augment_audit(run,audit_module,payload)
    return gp.GoldenPathServices(research_gate=research_gate,strategy_fingerprint=strategy_fingerprint,write_draft=write_draft,interview_gate=base.interview_gate,finalize=finalize,resolve_final_draft=base.resolve_final_draft,compile_interview=compile_interview,audit=audit)
def main(argv:list[str]|None=None)->int:
    os,ov=gp.default_services,gp._run_authority_view;gp.default_services=converged_services;gp._run_authority_view=_authority_view
    try:return gp.main(argv)
    finally:gp.default_services=os;gp._run_authority_view=ov
if __name__=="__main__":raise SystemExit(main())
