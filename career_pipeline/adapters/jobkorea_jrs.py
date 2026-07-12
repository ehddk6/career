"""Offline-only JobKorea JRS contract adapter. No navigation or network APIs."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import Mapping, Protocol

from ..application_execution import ExecutionAuthorizationV2, LEGACY_AUTHORIZATION_UNUSABLE, claim_fixture_fill_authorization, record_fixture_event

ADAPTER_ID="jobkorea_jrs_fixture"; CONTRACT_VERSION=1; SITE_FAMILY="JobKorea JRS"
SITE_SCHEMA="jobkorea_jrs_fixture_v1"; LIVE_ENABLED=False
EXPECTED_FORM="#jrs-application"; EXPECTED_ACTION="https://jrs.fixture.invalid/application/submit"
FIELDS=(
 ("applicant_name","#applicant_name","text",True,40,()),("email","#email","email",True,120,()),
 ("phone","#phone","tel",True,20,()),("recruitment_track","#recruitment_track","select",True,None,("general_admin","finance","it")),
 ("work_region","#work_region","select",True,None,("seoul","gangwon","nationwide")),
 ("motivation","#motivation","textarea",True,1000,()),("problem_solving","#problem_solving","textarea",True,1000,()),
 ("teamwork","#teamwork","textarea",True,1000,()),("career_plan","#career_plan","textarea",True,1000,()),
 ("privacy_consent","#privacy_consent","checkbox",True,None,()),)
CONTROLS=(("save_draft","#save_draft","button"),("final_submit","#final_submit","submit"))

class AdapterBlocked(ValueError): pass
class FixtureFillPage(Protocol):
    def snapshot(self)->dict: ...
    def fill(self,selector:str,value:str)->None: ...
    def select_option(self,selector:str,value:str)->None: ...
    def check(self,selector:str)->None: ...
    def read_value(self,selector:str)->str: ...

class _Parser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.form=None; self.fields=[]; self.controls=[]; self.scripts=0; self.iframes=0; self.select=None; self.text=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="script": self.scripts+=1
        if tag=="iframe": self.iframes+=1
        if tag=="form": self.form={"selector":"#"+a.get("id","") ,"action":a.get("action","")}
        if tag in {"input","textarea","select"}:
            typ="select" if tag=="select" else "textarea" if tag=="textarea" else a.get("type","text").lower(); ml=a.get("maxlength")
            item={"logical_id":a.get("name") or a.get("id"),"selector":"#"+a.get("id",""),"type":typ,"required":"required" in a,"maxlength":int(ml) if ml and ml.isdigit() else None,"options":[],"readonly":"readonly" in a,"disabled":"disabled" in a}
            self.fields.append(item)
            if tag=="select": self.select=item
        if tag=="button": self.controls.append({"logical_id":a.get("id"),"selector":"#"+a.get("id",""),"type":a.get("type","submit")})
    def handle_endtag(self,tag):
        if tag=="select": self.select=None
    def handle_startendtag(self,tag,attrs): self.handle_starttag(tag,attrs)
    def handle_data(self,data): self.text.append(data)
    def handle_entityref(self,name): pass
    def handle_charref(self,name): pass
    def unknown_decl(self,data): pass
    def handle_comment(self,data): pass
    def handle_pi(self,data): pass
    def handle_decl(self,decl): pass

def collect_fixture_schema(html:str)->dict:
    p=_Parser(); p.feed(html)
    # HTMLParser does not expose option attributes through data callbacks, so parse values narrowly.
    import re
    blocks=re.findall(r'<select[^>]+(?:id|name)="([^"]+)"[^>]*>(.*?)</select>',html,flags=re.I|re.S)
    for key,body in blocks:
        values=re.findall(r'<option[^>]+value="([^"]+)"',body,flags=re.I)
        for f in p.fields:
            if f["logical_id"]==key or f["selector"]=="#"+key: f["options"]=values
    return {"adapter_id":ADAPTER_ID,"contract_version":CONTRACT_VERSION,"site_schema":SITE_SCHEMA,
        "form_selector":(p.form or {}).get("selector"),"form_action":(p.form or {}).get("action"),
        "fields":p.fields,"controls":p.controls,"script_count":p.scripts,"iframe_count":p.iframes,
        "security_markers":[m for m in ("captcha","mfa","otp","verification code") if m in " ".join(p.text).casefold()]}
def fixture_schema_sha256(schema:dict)->str: return sha256(json.dumps(schema,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def expected_schema()->dict:
    return {"adapter_id":ADAPTER_ID,"contract_version":CONTRACT_VERSION,"site_schema":SITE_SCHEMA,"form_selector":EXPECTED_FORM,"form_action":EXPECTED_ACTION,
        "fields":[{"logical_id":i,"selector":s,"type":t,"required":r,"maxlength":m,"options":list(o),"readonly":False,"disabled":False} for i,s,t,r,m,o in FIELDS],
        "controls":[{"logical_id":i,"selector":s,"type":t} for i,s,t in CONTROLS],"script_count":0,"iframe_count":0,"security_markers":[]}
def adapter_contract()->dict: return {"adapter_id":ADAPTER_ID,"contract_version":CONTRACT_VERSION,"site_family":SITE_FAMILY,"site_schema":SITE_SCHEMA,"live_enabled":LIVE_ENABLED,"public_portal_origin":"https://jrs.jobkorea.co.kr","actual_application_origin":None,"fixture_only":True}

class FixtureMockPage:
    def __init__(self,schema): self._schema=schema; self.values={}; self.calls=[]
    def snapshot(self): return self._schema
    def fill(self,s,v): self.calls.append(("fill",s)); self.values[s]=v
    def select_option(self,s,v): self.calls.append(("select_option",s)); self.values[s]=v
    def check(self,s): self.calls.append(("check",s)); self.values[s]="true"
    def read_value(self,s): return self.values.get(s,"")

def _prevalidate(page,values,result,authorization):
    if not isinstance(authorization, ExecutionAuthorizationV2): raise AdapterBlocked(LEGACY_AUTHORIZATION_UNUSABLE)
    if LIVE_ENABLED or authorization.mode!="fill_only": raise AdapterBlocked("fixture_scope_invalid")
    schema=page.snapshot(); expected=expected_schema()
    if schema!=expected: raise AdapterBlocked("fixture_schema_mismatch")
    digest=fixture_schema_sha256(schema)
    if digest!=result.form_schema_sha256 or digest!=authorization.form_schema_sha256: raise AdapterBlocked("authorized_schema_mismatch")
    if set(values)!={x[0] for x in FIELDS}: raise AdapterBlocked("field_set_mismatch")
    for logical,selector,typ,required,limit,options in FIELDS:
        value=values[logical]
        if not isinstance(value,str) or (required and not value): raise AdapterBlocked("required_value_missing")
        if limit is not None and len(value)>limit: raise AdapterBlocked("value_too_long")
        if options and value not in options: raise AdapterBlocked("select_option_invalid")
        if typ=="checkbox" and value.casefold() not in {"true","yes","1","동의"}: raise AdapterBlocked("consent_not_confirmed")

def run_fixture_fill(page:FixtureFillPage,values:Mapping[str,str],package,result,authorization,*,executed_at,ledger_path:Path,signing_key:bytes)->dict:
    _prevalidate(page,values,result,authorization)
    claim_fixture_fill_authorization(package,result,authorization,executed_at=executed_at,ledger_path=ledger_path,signing_key=signing_key,adapter_id=ADAPTER_ID)
    records=[]
    try:
        for logical,selector,typ,_required,_limit,_options in FIELDS:
            value=values[logical]; record_fixture_event(ledger_path,authorization,event_type="field_fill_started",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID,logical_field_id=logical)
            if typ=="select": page.select_option(selector,value)
            elif typ=="checkbox": page.check(selector)
            else: page.fill(selector,value)
            if page.read_value(selector)!=("true" if typ=="checkbox" else value): raise AdapterBlocked("field_verification_failed")
            record_fixture_event(ledger_path,authorization,event_type="field_fill_verified",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID,logical_field_id=logical)
            records.append({"logical_field_id":logical,"verified":True,"value_length":len(value)})
        if page.snapshot()!=expected_schema(): raise AdapterBlocked("final_schema_mismatch")
        record_fixture_event(ledger_path,authorization,event_type="fill_fixture_completed",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID)
    except Exception:
        record_fixture_event(ledger_path,authorization,event_type="fill_fixture_failed",occurred_at=executed_at,signing_key=signing_key,adapter_id=ADAPTER_ID)
        raise
    return {"adapter_id":ADAPTER_ID,"contract_version":CONTRACT_VERSION,"package_id":package.package_id,"authorization_id":authorization.authorization_id,"status":"filled","fields":records,"events":["fill_fixture_validation_started","fill_fixture_completed"]}
