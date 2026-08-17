from career_pipeline.construct_portfolio import build_construct_portfolio
from career_pipeline.job_analysis_compiler import build_job_analysis_graph


def _graph():
    posting = {
        "target": "테스트공사 행정",
        "source": {"content_sha256": "a" * 64},
        "duties": ["신청 서류를 공식 기준과 원문에 대조해 누락과 예외를 검토한다."],
        "competencies": [],
        "requirements": [],
        "preferred": [],
        "constraints": [],
    }
    return build_job_analysis_graph(posting, [], target="테스트공사 행정")


def _ledger(
    atomic="원문과 입력값을 대조해 누락을 구분했습니다.",
    *,
    actions=None,
    claim_status="confirmed",
    second_claim=None,
):
    claims = [
        {
            "field": "experience_summary",
            "normalized_value": atomic,
            "status": claim_status,
            "claim_id": "clm-1",
            "verification": {
                "method": "direct_source",
                "contribution": "contributed",
            },
        }
    ]
    if second_claim is not None:
        claims.append(
            {
                "field": "experience_summary",
                "normalized_value": second_claim,
                "status": "confirmed",
                "claim_id": "clm-2",
                "verification": {
                    "method": "direct_source",
                    "contribution": "contributed",
                },
            }
        )
    return {
        "experiences": [
            {
                "experience_id": "exp-1",
                "status": "confirmed",
                "title": "행정지원",
                "role": "자료 검토",
                "situation": "마감 전 신청 자료를 확인했습니다.",
                "actions": list(actions or []),
                "outcomes": [],
                "claims": claims,
            }
        ]
    }


def _state():
    return {
        "questions": [
            {
                "index": 1,
                "prompt": "행정 직무에서 본인의 강점을 구체적으로 설명해 주십시오.",
            }
        ]
    }


def test_atomic_behavior_can_form_direct_link_without_adding_authority():
    payload = build_construct_portfolio(
        _graph(),
        _ledger(),
        evidence_portfolio={"assignments": []},
        run_state=_state(),
    )

    direct = [
        row for row in payload["links"] if row["relation"] == "direct"
    ]
    assert direct
    assert all(row["atomic_match"] for row in direct)
    assert all(
        row["factual_authority_granted"] is False for row in direct
    )
    assert all(
        row["construct_authority_added"] is False for row in direct
    )


def test_keyword_only_overlap_does_not_become_direct():
    payload = build_construct_portfolio(
        _graph(),
        _ledger("기준 역량과 정확성을 중요하게 생각했습니다."),
        evidence_portfolio={"assignments": []},
        run_state=_state(),
    )

    rows = [
        row
        for row in payload["links"]
        if row["construct_id"] == "construct_criterion_application"
    ]
    assert all(row["relation"] != "direct" for row in rows)


def test_behavior_present_only_in_experience_context_is_at_most_partial():
    payload = build_construct_portfolio(
        _graph(),
        _ledger(
            "자료를 정리했습니다.",
            actions=["원문과 입력값을 대조해 누락을 구분했습니다."],
        ),
        evidence_portfolio={"assignments": []},
        run_state=_state(),
    )

    rows = [
        row
        for row in payload["links"]
        if row["evidence_id"] == "applicant:exp-1:clm-1"
        and row["construct_id"] == "construct_criterion_application"
    ]
    assert rows
    assert all(row["relation"] != "direct" for row in rows)
    assert any(row["context_match"] for row in rows)


def test_unconfirmed_claim_is_ignored():
    payload = build_construct_portfolio(
        _graph(),
        _ledger(claim_status="needs_verification"),
        evidence_portfolio={"assignments": []},
        run_state=_state(),
    )

    assert payload["summary"]["candidate_count"] == 0
    assert payload["links"] == []


def test_research_portfolio_item_is_never_applicant_construct_evidence():
    current = {
        "assignments": [
            {
                "question_index": 1,
                "preferred_evidence": [
                    {
                        "evidence_id": "research:job-1",
                        "source_kind": "research",
                        "planning_score": 4.0,
                        "covered_signal_ids": ["sig_1"],
                    }
                ],
            }
        ]
    }
    payload = build_construct_portfolio(
        _graph(),
        _ledger(),
        evidence_portfolio=current,
        run_state=_state(),
    )

    assert all(
        not str(row["evidence_id"]).startswith("research:")
        for row in payload["links"]
    )
    assert payload["policy"]["research_is_not_applicant_evidence"] is True


def test_matrix_is_deterministic():
    kwargs = {
        "evidence_portfolio": {"assignments": []},
        "run_state": _state(),
    }
    first = build_construct_portfolio(_graph(), _ledger(), **kwargs)
    second = build_construct_portfolio(_graph(), _ledger(), **kwargs)
    assert first["matrix_id"] == second["matrix_id"]
    assert first == second


def test_shadow_records_lexical_selected_but_construct_weak_disagreement():
    current = {
        "assignments": [
            {
                "question_index": 1,
                "preferred_evidence": [
                    {
                        "evidence_id": "applicant:exp-1:clm-1",
                        "source_kind": "applicant",
                        "planning_score": 5.2,
                        "covered_signal_ids": ["sig_1"],
                    }
                ],
            }
        ]
    }
    payload = build_construct_portfolio(
        _graph(),
        _ledger("행정 업무에 성실하게 참여했습니다.", actions=[]),
        evidence_portfolio=current,
        run_state=_state(),
    )

    assert any(
        row["kind"] == "lexical_high_construct_weak"
        for row in payload["disagreements"]
    )


def test_shadow_records_direct_construct_evidence_not_selected():
    current = {
        "assignments": [
            {
                "question_index": 1,
                "preferred_evidence": [
                    {
                        "evidence_id": "applicant:exp-1:clm-1",
                        "source_kind": "applicant",
                        "planning_score": 4.0,
                        "covered_signal_ids": ["sig_1"],
                    }
                ],
            }
        ]
    }
    payload = build_construct_portfolio(
        _graph(),
        _ledger(
            "행정 업무에 성실하게 참여했습니다.",
            second_claim="원문과 입력값을 대조해 누락을 구분했습니다.",
        ),
        evidence_portfolio=current,
        run_state=_state(),
    )

    assert any(
        row["kind"] == "construct_direct_not_selected"
        and row["evidence_id"] == "applicant:exp-1:clm-2"
        for row in payload["disagreements"]
    )
