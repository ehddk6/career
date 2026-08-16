from career_pipeline.answer_blueprint import build_answer_blueprint_packet, classify_question


def _claim(claim_id, field, value, *, contribution='observed', method='direct_source', metric=False):
    verification = {
        'method': method,
        'scope': 'source excerpt',
        'contribution': contribution,
    }
    if metric:
        verification.update({'measurement_period': '2026-01', 'scope': '지원 업무 범위'})
    return {
        'claim_id': claim_id,
        'field': field,
        'normalized_value': value,
        'status': 'confirmed',
        'evidence': [{'source_path': 'evidence.txt', 'paragraph_index': 0, 'source_sha256': 'a'*64, 'excerpt_sha256': 'b'*64}],
        'verification': verification,
    }


def _experience(exp_id, title, action, *, outcome='처리를 마쳤다', claims=None):
    return {
        'experience_id': exp_id,
        'title': title,
        'organization_alias': '',
        'period': None,
        'role': '담당자',
        'situation': f'{title}에서 문제를 발견했다.',
        'actions': [action],
        'outcomes': [outcome],
        'competencies': ['정확성', '문제해결'],
        'claims': claims or [_claim(f'clm_{exp_id}', 'summary', action)],
        'status': 'confirmed',
        'confirmed_at': '2026-08-16T00:00:00+09:00',
    }


def _ledger(*experiences):
    return {'schema_version': 2, 'generated_at': '2026-08-16T00:00:00+09:00', 'workspace_root': '.', 'experiences': list(experiences)}


def _match(q, *rows):
    return {
        'question': {'index': q, 'prompt': f'문항 {q}'},
        'candidates': [
            {
                'experience_id': exp_id,
                'total_score': score,
                'matched_duties': ['자료 검토'],
                'matched_competencies': ['정확성'],
            }
            for exp_id, score in rows
        ],
    }


def _question(index, prompt, limit=600):
    return {'index': index, 'prompt': prompt, 'character_limit': limit, 'count_mode': 'spaces_included', 'minimum_character_limit': None}


def test_classifies_core_question_intents():
    assert classify_question('지원 동기와 입사 후 목표를 작성해 주세요') == 'motivation'
    assert classify_question('새로운 조직에 적응할 때 중요한 태도를 작성해 주세요') == 'adaptation'
    assert classify_question('업무수행계획을 작성해 주세요') == 'job_plan'
    assert classify_question('최근 경제 이슈 한 가지를 선택하여 의견을 작성해 주세요') == 'issue_analysis'


def test_portfolio_optimizer_uses_distinct_experiences_when_fit_is_close():
    exp_a = _experience('exp_a', '자료검증', '원자료와 입력값을 대조해 오류를 찾았다')
    exp_b = _experience('exp_b', '이용자안내', '문의 동선을 관찰해 안내 순서를 바꿨다')
    packet = build_answer_blueprint_packet(
        [
            _question(1, '지원동기와 경험을 작성해 주세요'),
            _question(2, '새로운 조직에 적응한 경험을 작성해 주세요'),
        ],
        target='테스트기관',
        posting={'duties': ['자료 검토', '고객 안내'], 'competencies': ['정확성']},
        ledger=_ledger(exp_a, exp_b),
        matches=[_match(1, ('exp_a', 90), ('exp_b', 88)), _match(2, ('exp_a', 91), ('exp_b', 89))],
    )
    assignment = packet['portfolio']['experience_assignment']
    assert assignment['1'] != assignment['2']
    assert packet['portfolio']['reuse_count'] == 0


def test_portfolio_optimizer_allows_reuse_when_only_one_experience_exists():
    exp_a = _experience('exp_a', '자료검증', '원자료와 입력값을 대조해 오류를 찾았다')
    packet = build_answer_blueprint_packet(
        [_question(1, '경험을 바탕으로 강점을 작성해 주세요'), _question(2, '문제를 해결한 경험을 작성해 주세요')],
        target='테스트기관',
        posting={},
        ledger=_ledger(exp_a),
        matches=[_match(1, ('exp_a', 90)), _match(2, ('exp_a', 92))],
    )
    assert packet['portfolio']['experience_assignment'] == {'1': 'exp_a', '2': 'exp_a'}
    assert packet['portfolio']['reuse_count'] == 1


def test_motivation_blueprint_forbids_brochure_opening_and_budget_sums_to_target():
    exp = _experience('exp_a', '자료검증', '원자료와 입력값을 대조해 오류를 찾았다')
    packet = build_answer_blueprint_packet(
        [_question(1, '우리 기관에 지원한 이유와 직무 기여 방안을 작성해 주세요', 700)],
        target='테스트기관',
        posting={'duties': ['자료 검토'], 'competencies': ['정확성']},
        ledger=_ledger(exp),
        matches=[_match(1, ('exp_a', 90))],
        research_claims=[{'claim_id': 'r1', 'claim': '테스트기관은 자료 검토 업무를 수행한다.', 'claim_type': 'organization_role', 'verification_status': 'confirmed', 'evidence_excerpt': '자료 검토 업무', 'application_use': '문항 1', 'source_url': 'https://example.com', 'checked_at': '2026-08-16'}],
    )
    row = packet['questions'][0]
    assert row['intent'] == 'motivation'
    assert [beat['beat'] for beat in row['beats']][:2] == ['direct_answer', 'personal_criterion']
    assert any('brochure-style' in risk for risk in row['risk_controls'])
    assert sum(beat['character_budget'] for beat in row['beats']) == row['character_plan']['target']


def test_job_plan_blueprint_has_priority_failure_control_and_escalation_not_checklist_only():
    exp = _experience('exp_a', '자료검증', '오류 유형을 나눠 검토 순서를 정했다')
    packet = build_answer_blueprint_packet(
        [_question(1, '입사 후 업무수행계획을 작성해 주세요')],
        target='테스트기관', posting={'duties': ['자료 검토']}, ledger=_ledger(exp)
    )
    row = packet['questions'][0]
    assert row['intent'] == 'job_plan'
    assert [beat['beat'] for beat in row['beats']] == [
        'priority', 'learning_sequence', 'execution_control', 'escalation_rule', 'customer_or_peer_handoff', 'improvement_loop'
    ]
    assert any('checklist manual' in risk for risk in row['risk_controls'])


def test_issue_prompt_enforces_one_issue_and_selects_research_without_experience():
    packet = build_answer_blueprint_packet(
        [_question(1, '최근 경제 이슈 한 가지를 선택하고 원인, 영향, 대응 방안을 작성해 주세요', 1200)],
        target='테스트기관', posting={}, ledger=_ledger(),
        research_claims=[
            {'claim_id': 'r_issue', 'claim': '원재료 가격 변동은 기업의 비용 부담에 영향을 준다.', 'claim_type': 'industry_issue', 'verification_status': 'confirmed', 'evidence_excerpt': '기업 비용 부담', 'application_use': '문항 1', 'source_url': 'https://example.com', 'checked_at': '2026-08-16'},
            {'claim_id': 'r_risk', 'claim': '유동성 악화는 신용 위험을 높일 수 있다.', 'claim_type': 'risk_or_limit', 'verification_status': 'confirmed', 'evidence_excerpt': '신용 위험', 'application_use': '문항 1', 'source_url': 'https://example.com', 'checked_at': '2026-08-16'},
        ],
    )
    row = packet['questions'][0]
    assert row['logic_contract']['selection_cardinality'] == 1
    assert row['experience'] is None
    assert [item['claim_id'] for item in row['research_claims']] == ['r_issue', 'r_risk']
    assert any('exactly one' in risk for risk in row['risk_controls'])


def test_unsafe_metric_is_excluded_and_observed_claim_cannot_be_upgraded_to_causation():
    unsafe_metric = _claim('metric_bad', 'metric:reduction', '30%', contribution='unknown', method='none', metric=True)
    observed = _claim('clm_observed', 'improvement', '안내 순서 개선', contribution='observed')
    exp = _experience('exp_a', '안내개선', '이용자 동선을 관찰해 안내 순서를 바꿨다', claims=[unsafe_metric, observed])
    packet = build_answer_blueprint_packet(
        [_question(1, '문제를 개선한 경험과 결과를 작성해 주세요')],
        target='테스트기관', posting={}, ledger=_ledger(exp), matches=[_match(1, ('exp_a', 90))]
    )
    claims = packet['questions'][0]['experience']['selected_claims']
    assert [item['claim_id'] for item in claims] == ['clm_observed']
    assert claims[0]['causal_language'] == 'observation_only'
