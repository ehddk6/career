from career_pipeline.job_analysis_compiler import build_job_analysis_graph


def _posting(**overrides):
    payload = {
        "target": "테스트공사 행정",
        "source": {"content_sha256": "a" * 64},
        "duties": ["신청 서류를 공식 기준과 대조해 적격 여부를 검토한다."],
        "competencies": ["정확성"],
        "requirements": [],
        "preferred": [],
        "constraints": [],
    }
    payload.update(overrides)
    return payload


def test_job_analysis_is_deterministic_and_source_bound():
    first = build_job_analysis_graph(_posting(), [], target="테스트공사 행정")
    second = build_job_analysis_graph(_posting(), [], target="테스트공사 행정")

    assert first.graph_id == second.graph_id
    assert first.tasks
    assert first.source_bindings
    assert all(task.source_binding_ids for task in first.tasks)
    assert all(construct.source_binding_ids for construct in first.constructs)
    assert all(
        construct_id
        in {edge.construct_id for edge in first.task_construct_edges}
        for construct_id in first.core_construct_ids
    )
    assert first.policy["factual_authority_granted"] is False
    assert first.policy["construct_authority_added"] is False


def test_job_duty_research_can_add_task_but_organization_only_claim_cannot():
    research = [
        {
            "claim_id": "job-1",
            "claim": "행정 담당자는 신청 서류를 검토하고 보완 사항을 안내한다.",
            "claim_type": "job_duty",
            "verification_status": "verified",
            "submission_authority": True,
            "source_url": "https://official.example.test/job",
            "source_tier": 1,
        },
        {
            "claim_id": "org-1",
            "claim": "테스트공사는 공공서비스를 제공한다.",
            "claim_type": "organization_role",
            "verification_status": "verified",
            "submission_authority": True,
            "source_url": "https://official.example.test/about",
            "source_tier": 1,
        },
    ]
    graph = build_job_analysis_graph(
        _posting(duties=[]),
        research,
        target="테스트공사 행정",
    )

    labels = [task.label for task in graph.tasks]
    assert any("신청 서류" in label for label in labels)
    assert not any("공공서비스" in label for label in labels)


def test_generic_explicit_competency_without_task_support_is_not_core():
    graph = build_job_analysis_graph(
        _posting(duties=[], competencies=["성실성과 열정"]),
        [],
        target="테스트공사 행정",
    )

    generic = [
        construct
        for construct in graph.constructs
        if construct.label == "성실성과 열정"
    ]
    assert len(generic) == 1
    assert generic[0].status == "target_explicit"
    assert generic[0].construct_id not in graph.core_construct_ids
    assert any(
        row.get("kind")
        == "explicit_construct_without_behavioral_task_support"
        for row in graph.unresolved
    )


def test_risk_or_limit_attaches_as_constraint_without_becoming_applicant_evidence():
    graph = build_job_analysis_graph(
        _posting(),
        [
            {
                "claim_id": "risk-1",
                "claim": "서류 검토에서 권한 밖 예외는 담당자에게 보고해야 한다.",
                "claim_type": "risk_or_limit",
                "verification_status": "verified",
                "submission_authority": True,
                "source_url": "https://official.example.test/rule",
                "source_tier": 1,
            }
        ],
        target="테스트공사 행정",
    )

    assert any(
        "권한 밖 예외" in constraint
        for task in graph.tasks
        for constraint in task.constraints
    )
    assert any(
        construct.construct_id == "construct_boundary_escalation"
        for construct in graph.constructs
    )


def test_taxonomy_prior_never_becomes_target_fact_or_core_by_itself():
    graph = build_job_analysis_graph(
        _posting(duties=[], competencies=[]),
        [],
        target="테스트공사 행정",
        taxonomy=[
            {
                "source_id": "ncs:sample",
                "source_family": "ncs",
                "label": "기준에 따라 자료를 검토하고 오류를 확인한다",
                "source_locator": "NCS sample",
            }
        ],
    )

    prior_bindings = [
        binding
        for binding in graph.source_bindings
        if binding.authority_class == "taxonomy_prior"
    ]
    assert prior_bindings
    assert all(
        binding.company_factual_authority is False
        for binding in prior_bindings
    )
    prior_constructs = [
        construct
        for construct in graph.constructs
        if construct.status == "prior_supported"
    ]
    assert prior_constructs
    assert all(
        construct.construct_id not in graph.core_construct_ids
        for construct in prior_constructs
    )
