"""Offline-only Saramin Applyin fixture adapter; no browser or network APIs."""
from __future__ import annotations
from hashlib import sha256
from html.parser import HTMLParser
import json,re
from pathlib import Path
from typing import Mapping,Protocol
from ..application_execution import ExecutionAuthorizationV2,LEGACY_AUTHORIZATION_UNUSABLE,claim_fixture_fill_authorization,record_fixture_event

PLATFORM_ID="saramin_applyin"; ADAPTER_ID="saramin_applyin_fixture"; CONTRACT_ID="saramin_applyin_fixture_v1"; CONTRACT_VERSION=1
FIXTURE_ORIGIN="https://sample-company.applyin.invalid"; LIVE_ENABLED=False
FORM_SELECTOR="#applyin-application"; FORM_ACTION=FIXTURE_ORIGIN+"/application/submit"; FORM_METHOD="post"
FIELDS=(("applicant_name","#applicant_name","text",True,40,()),("email","#email","email",True,120,()),("phone","#phone","tel",True,20,()),
 ("recruitment_track","#recruitment_track","select",True,None,("general_admin","finance","customer_support")),("preferred_region","#preferred_region","select",True,None,("seoul","gangwon","nationwide")),
 ("education_summary","#education_summary","textarea",True,500,()),("experience_summary","#experience_summary","textarea",True,1000,()),
 ("motivation","#motivation","textarea",True,1000,()),("competency","#competency","textarea",True,1000,()),("teamwork","#teamwork","textarea",True,1000,()),("career_plan","#career_plan","textarea",True,1000,()),
 ("privacy_consent","#privacy_consent","checkbox",True,None,()),)
CONTROLS=(("save_draft","#save_draft","button"),("final_submit","#final_submit","submit"))
class AdapterBlocked(ValueError): pass
class FixturePage(Protocol):
    def snapshot(self)->dict: ...
    def fill(self,s:str,v:str)->None: ...
    def select_option(self,s:str,v:str)->None: ...
    def check(self,s:str)->None: ...
    def read_value(self,s:str)->str: ...
class _Parser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.form={}; self.fields=[]; self.controls=[]; self.script_count=0; self.iframe_count=0; self.text=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="script": self.script_count+=1
        if tag=="iframe": self.iframe_count+=1
        if tag=="form": self.form={"selector":"#"+a.get("id",""),"action":a.get("action",""),"method":a.get("method","get").casefold()}
        if tag in {"input","textarea","select"}:
            typ="select" if tag=="select" else "textarea" if tag=="textarea" else a.get("type","text").casefold(); ml=a.get("maxlength")
            self.fields.append({"logical_id":a.get("name") or a.get("id"),"selector":"#"+a.get("id",""),"type":typ,"required":"required" in a,"maxlength":int(ml) if ml and ml.isdigit() else None,"options":[],"readonly":"readonly" in a,"disabled":"disabled" in a})
        if tag=="button": self.controls.append({"logical_id":a.get("id"),"selector":"#"+a.get("id",""),"type":a.get("type","submit")})
    def handle_data(self,data): self.text.append(data)
def collect_fixture_schema(html):
    p=_Parser(); p.feed(html)
    for key,body in re.findall(r'<select[^>]+(?:id|name)="([^"]+)"[^>]*>(.*?)</select>',html,flags=re.I|re.S):
        values=re.findall(r'<option[^>]+value="([^"]+)"',body,flags=re.I)
        for f in p.fields:
            if f["logical_id"]==key or f["selector"]=="#"+key: f["options"]=values
    text=" ".join(p.text).casefold()
    return {"platform_id":PLATFORM_ID,"adapter_id":ADAPTER_ID,"contract_id":CONTRACT_ID,"contract_version":CONTRACT_VERSION,"fixture_only":True,"live_enabled":False,
        "fixture_origin":FIXTURE_ORIGIN,"form_selector":p.form.get("selector"),"form_action":p.form.get("action"),"form_method":p.form.get("method"),"fields":p.fields,"controls":p.controls,
        "script_count":p.script_count,"iframe_count":p.iframe_count,"security_markers":[x for x in ("captcha","mfa","otp","password") if x in text]}
def schema_sha256(s): return sha256(json.dumps(s,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def expected_schema(): return {"platform_id":PLATFORM_ID,"adapter_id":ADAPTER_ID,"contract_id":CONTRACT_ID,"contract_version":1,"fixture_only":True,"live_enabled":False,"fixture_origin":FIXTURE_ORIGIN,"form_selector":FORM_SELECTOR,"form_action":FORM_ACTION,"form_method":FORM_METHOD,
 "fields":[{"logical_id":i,"selector":s,"type":t,"required":r,"maxlength":m,"options":list(o),"readonly":False,"disabled":False} for i,s,t,r,m,o in FIELDS],"controls":[{"logical_id":i,"selector":s,"type":t} for i,s,t in CONTROLS],"script_count":0,"iframe_count":0,"security_markers":[]}
def adapter_contract(): return {"platform_id":PLATFORM_ID,"adapter_id":ADAPTER_ID,"contract_id":CONTRACT_ID,"contract_version":1,"fixture_only":True,"live_enabled":False,"exact_fixture_origin":FIXTURE_ORIGIN,"attachment_supported":False}
class FixtureMockPage:
    def __init__(self,schema): self.schema=schema; self.values={}; self.calls=[]
    def snapshot(self): return self.schema
    def fill(self,s,v): self.calls.append(("fill",s)); self.values[s]=v
    def select_option(self,s,v): self.calls.append(("select_option",s)); self.values[s]=v
    def check(self,s): self.calls.append(("check",s)); self.values[s]="true"
    def read_value(self,s): return self.values.get(s,"")
def _pre(page,values,result,auth):
    if not isinstance(auth, ExecutionAuthorizationV2): raise AdapterBlocked(LEGACY_AUTHORIZATION_UNUSABLE)
    schema=page.snapshot()
    if LIVE_ENABLED or schema!=expected_schema(): raise AdapterBlocked("applyin_schema_mismatch")
    digest=schema_sha256(schema)
    if auth.mode!="fill_only" or auth.allowed_origin!="https://sample-company.applyin.invalid:443" or digest!=auth.form_schema_sha256 or digest!=result.form_schema_sha256: raise AdapterBlocked("applyin_authorization_mismatch")
    if set(values)!={f[0] for f in FIELDS}: raise AdapterBlocked("applyin_field_set_mismatch")
    for i,_s,t,r,m,o in FIELDS:
        v=values[i]
        if not isinstance(v,str) or (r and not v): raise AdapterBlocked("required_value_missing")
        if m is not None and len(v)>m: raise AdapterBlocked("value_too_long")
        if o and v not in o: raise AdapterBlocked("select_option_invalid")
        if t=="checkbox" and v.casefold() not in {"true","yes","1"}: raise AdapterBlocked("consent_not_confirmed")
def run_fixture_fill(page:FixturePage,values:Mapping[str,str],package,result,auth,*,executed_at,ledger_path:Path,signing_key:bytes):
    _pre(page,values,result,auth)
    claim_fixture_fill_authorization(package,result,auth,executed_at=executed_at,ledger_path=ledger_path,signing_key=signing_key,adapter_id=ADAPTER_ID,validation_event="applyin_fixture_validation_started")
    records=[]
    try:
        for i,s,t,_r,_m,_o in FIELDS:
            v=values[i]; record_fixture_event(ledger_path,auth,event_type="field_fill_started",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID,logical_field_id=i)
            page.select_option(s,v) if t=="select" else page.check(s) if t=="checkbox" else page.fill(s,v)
            if page.read_value(s)!=("true" if t=="checkbox" else v): raise AdapterBlocked("field_verification_failed")
            record_fixture_event(ledger_path,auth,event_type="field_fill_verified",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID,logical_field_id=i); records.append({"logical_field_id":i,"verified":True,"value_length":len(v)})
        if page.snapshot()!=expected_schema(): raise AdapterBlocked("final_schema_mismatch")
        record_fixture_event(ledger_path,auth,event_type="applyin_fixture_completed",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID)
    except Exception:
        record_fixture_event(ledger_path,auth,event_type="applyin_fixture_failed",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID); raise
    return {"platform_id":PLATFORM_ID,"adapter_id":ADAPTER_ID,"contract_version":1,"package_id":package.package_id,"authorization_id":auth.authorization_id,"status":"filled","fields":records,"events":["applyin_fixture_validation_started","applyin_fixture_completed"]}
