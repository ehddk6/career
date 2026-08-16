import json
from pathlib import Path

import career_pipeline.narrative_compiler as nc


def _run_fixture(tmp_path: Path):
    run = tmp_path / 'run'
    run.mkdir()
    (run/'run.json').write_text(json.dumps({
        'target':'테스트기관',
        'official_research_domains':['example.com'],
        'questions':[{'index':1,'prompt':'문제를 해결한 경험과 결과를 작성해 주세요','character_limit':500,'count_mode':'spaces_included'}]
    },ensure_ascii=False),encoding='utf-8')
    (run/'00_채용공고분석.json').write_text(json.dumps({'duties':['자료 검토'],'competencies':['정확성']},ensure_ascii=False),encoding='utf-8')
    claim={'claim_id':'clm_1','field':'summary','normalized_value':'오류를 찾아 수정함','status':'confirmed','evidence':[{'source_path':'e.txt'}], 'verification':{'method':'direct_source','scope':'source','contribution':'observed'}}
    exp={'experience_id':'exp_1','title':'자료검증','organization_alias':'','period':None,'role':'담당','situation':'자료 오류가 있었다','actions':['원자료와 입력값을 대조해 오류를 찾았다'],'outcomes':['오류를 수정했다'],'competencies':['정확성'],'claims':[claim],'status':'confirmed','confirmed_at':'2026-08-16T00:00:00+09:00'}
    (run/'02_확정경험원장.json').write_text(json.dumps({'schema_version':2,'generated_at':'2026-08-16T00:00:00+09:00','workspace_root':'.','experiences':[exp]},ensure_ascii=False),encoding='utf-8')
    (run/'03_경험직무매칭.json').write_text(json.dumps([{'question':{'index':1},'candidates':[{'experience_id':'exp_1','total_score':90,'matched_duties':['자료 검토'],'matched_competencies':['정확성']}]}],ensure_ascii=False),encoding='utf-8')
    (run/'04_공식근거.json').write_text('[]',encoding='utf-8')
    return run


def test_compile_run_blueprint_writes_ir(tmp_path):
    run=_run_fixture(tmp_path)
    packet=nc.compile_run_blueprint(run)
    assert packet['questions'][0]['experience']['experience_id']=='exp_1'
    assert (run/'05_답변설계도.json').is_file()
    assert (run/'05_답변설계도.md').is_file()


def test_generation_uses_exact_allowed_claims_and_repairs_typed_material_issue(tmp_path, monkeypatch):
    run=_run_fixture(tmp_path)
    packet=nc.compile_run_blueprint(run)
    blueprint=packet['questions'][0]
    calls=[]
    def runner(stage,prompt,model_id,timeout_ms):
        calls.append(stage)
        if stage.startswith('narrative_critic_after_repair'):
            return {'issues':[]}
        if stage=='narrative_critic':
            return {'issues':[{'question_index':1,'code':'weak_thesis','severity':'MATERIAL','message':'핵심 판단이 늦음','repair_instruction':'첫 문장에서 해결 기준을 말할 것'}]}
        answer='오류를 줄이기 위해 원자료와 입력값의 차이를 먼저 좁혔습니다. 오류를 찾아 수정함이라는 확인된 결과를 바탕으로 같은 기준을 적용했습니다.'
        return {'blueprint_id':blueprint['blueprint_id'],'question_index':1,'answer':answer,'used_claim_ids':['clm_1'],'used_research_ids':[]}
    monkeypatch.setattr(nc,'_deterministic_validation',lambda *args,**kwargs:[])
    responses,report=nc.generate_run_draft(run,packet=packet,model_id='fake-sol',runner=runner,max_repairs=1)
    assert responses[0].experience_refs[0].claim_fields==()
    assert responses[0].experience_refs[0].claim_ids==('clm_1',)
    assert report['semantic_validation']['status']=='passed'
    assert report['deterministic_validation']['status']=='passed'
    assert any(stage.startswith('narrative_repair_1_q1') for stage in calls)


def test_generation_rejects_unapproved_claim_id(tmp_path, monkeypatch):
    run=_run_fixture(tmp_path)
    packet=nc.compile_run_blueprint(run)
    blueprint=packet['questions'][0]
    def runner(stage,prompt,model_id,timeout_ms):
        if stage=='narrative_critic': return {'issues':[]}
        return {'blueprint_id':blueprint['blueprint_id'],'question_index':1,'answer':'답변','used_claim_ids':['made_up'],'used_research_ids':[]}
    monkeypatch.setattr(nc,'_deterministic_validation',lambda *args,**kwargs:[])
    try:
        nc.generate_run_draft(run,packet=packet,model_id='fake-sol',runner=runner,max_repairs=0)
    except nc.NarrativeCompilerError as error:
        assert 'unapproved claim ID' in str(error)
    else:
        raise AssertionError('unapproved claim ID should fail closed')
