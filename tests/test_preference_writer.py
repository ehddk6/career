import json
from pathlib import Path

import career_pipeline.preference_writer as pw


def _packet():
    return {
        'packet_id': 'pkt',
        'target': '테스트기관',
        'portfolio': {'cross_answer_rules': []},
        'questions': [{
            'blueprint_id': 'bp1',
            'question_index': 1,
            'prompt': '문제를 해결한 경험을 작성해 주세요',
            'intent': 'problem_solving',
            'logic_contract': {'experience_mode': 'required', 'research_mode': 'optional'},
            'character_plan': {'maximum': 500, 'count_mode': 'spaces_included'},
            'beats': [],
            'experience': {
                'experience_id': 'exp1',
                'selected_claims': [{
                    'claim_id': 'clm1', 'field': 'summary',
                    'normalized_value': '오류를 찾아 수정함',
                    'evidence_paths': [],
                }],
            },
            'research_claims': [],
            'portfolio_constraints': [],
            'risk_controls': [],
            'interview_defense_questions': [],
        }],
        'experience_ledger_schema_version': 2,
    }


def _run(tmp_path: Path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'run.json').write_text(json.dumps({
        'target': '테스트기관', 'root': str(tmp_path),
        'official_research_domains': [],
        'questions': [{'index': 1, 'prompt': '문제를 해결한 경험을 작성해 주세요', 'character_limit': 500}],
    }, ensure_ascii=False), encoding='utf-8')
    (run / '02_확정경험원장.json').write_text('{}', encoding='utf-8')
    return run


def _answer(blueprint_id, text):
    return {
        'blueprint_id': blueprint_id,
        'question_index': 1,
        'answer': text,
        'used_claim_ids': ['clm1'],
        'used_research_ids': [],
    }


def test_balanced_blind_tournament_reverses_presentation_order():
    bp = _packet()['questions'][0]
    candidates = [
        {'candidate_id': 'CA', 'payload': _answer('bp1', 'A 답변'), 'realisation_mode': 'a'},
        {'candidate_id': 'CB', 'payload': _answer('bp1', 'B 답변'), 'realisation_mode': 'b'},
        {'candidate_id': 'CC', 'payload': _answer('bp1', 'C 답변'), 'realisation_mode': 'c'},
    ]
    prompts=[]
    def runner(stage,prompt,model_id,timeout_ms):
        prompts.append(prompt)
        # B wins regardless of the displayed order.
        return {'ranking': [
            {'candidate_id':'CB','score':95,'reason':'구체적'},
            {'candidate_id':'CA','score':85,'reason':'보통'},
            {'candidate_id':'CC','score':75,'reason':'일반적'},
        ]}
    calls=[]
    winner, report = pw._blind_tournament(
        blueprint=bp, candidates=candidates, preference_profile=None,
        model_id='fake', timeout_ms=1, runner=runner, calls=calls,
    )
    assert winner['candidate_id']=='CB'
    assert report['position_consistent'] is True
    assert len(prompts)==2
    assert prompts[0].index('CA') < prompts[0].index('CC')
    assert prompts[1].index('CC') < prompts[1].index('CA')


def test_draft_prompt_is_context_then_principles_then_task():
    bp=_packet()['questions'][0]
    prompt=pw._draft_prompt(
        bp,_packet(),prior_answers=[],mode=pw.REALISATION_MODES[0],
        preference_profile={'comparison_count':1,'directives':['연결어를 줄인다.']},
    )
    assert prompt.index('<context>') < prompt.index('<writing_principles>') < prompt.index('<task>')
    assert '연결어를 줄인다.' in prompt
    assert 'judgment_centered' in prompt


def test_generation_uses_three_realisations_then_blind_ranking(tmp_path, monkeypatch):
    run=_run(tmp_path)
    packet=_packet()
    monkeypatch.setattr(pw,'_candidate_issues',lambda *a,**k:[])
    monkeypatch.setattr(pw,'_portfolio_issues',lambda *a,**k:[])
    stages=[]
    def runner(stage,prompt,model_id,timeout_ms):
        stages.append(stage)
        if stage.startswith('preference_generate'):
            n=int(stage.rsplit('_',1)[1])
            return _answer('bp1',f'후보 {n}의 구체적인 판단과 행동을 담은 답변입니다.')
        if stage.startswith('preference_rank'):
            import re
            ids=list(dict.fromkeys(re.findall(r'"candidate_id":\s*"(C[A-F0-9]+)"',prompt)))
            return {'ranking':[{'candidate_id':cid,'score':100-i,'reason':'rank'} for i,cid in enumerate(ids)]}
        if stage.startswith('preference_critic'):
            return {'issues':[]}
        raise AssertionError(stage)
    responses,report=pw.generate_preference_optimized_draft(
        run,packet=packet,model_id='fake',candidates_per_question=3,runner=runner,max_repairs=0,
    )
    assert len(responses)==1
    assert len([s for s in stages if s.startswith('preference_generate')])==3
    assert len([s for s in stages if s.startswith('preference_rank')])==2
    assert report['architecture']=='preference_optimized_multi_realisation_v1'
    assert len(report['candidate_selection'][0]['candidates']) == 3
