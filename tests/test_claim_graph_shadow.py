from types import SimpleNamespace

from career_pipeline.claim_graph import build_claim_graph
from career_pipeline.proof_shadow import build_proof_shadow_report


def _response(
    *,
    experience_id="exp-1",
    claim_id="clm-1",
    research_refs=(),
):
    return SimpleNamespace(
        question_index=1,
        experience_refs=(
            SimpleNamespace(
                experience_id=experience_id,
                claim_ids=(claim_id,),
                claim_fields=(),
            ),
        ),
        research_refs=tuple(research_refs),
    )


def _claim(
    value: str,
    *,
    claim_id="clm-1",
    contribution="observed",
):
    return SimpleNamespace(
        field="experience_summary",
        normalized_value=value,
        status="confirmed",
        claim_id=claim_id,
        evidence=(
            SimpleNamespace(
                source_path="fixture.txt",
                paragraph_index=0,
                source_sha256="a" * 64,
                excerpt_sha256="b" * 64,
            ),
        ),
        verification=SimpleNamespace(
            method="direct_source",
            baseline=None,
            result=None,
            formula=None,
            measurement_period=None,
            scope="source excerpt",
            contribution=contribution,
        ),
    )


def _ledger(claim, *, outcome="처리량 50건을 기록했습니다."):
    return SimpleNamespace(
        experiences=(
            SimpleNamespace(
                experience_id="exp-1",
                status="confirmed",
                role="자료 검토 지원",
                situation="마감 전 누락 여부를 점검했습니다.",
                actions=("원문과 입력값을 대조했습니다.",),
                outcomes=(outcome,),
                claims=(claim,),
            ),
        )
    )


def test_context_metric_does_not_widen_atomic_metric_authority():
    graph = build_claim_graph(
        [_response()],
        _ledger(_claim("원문과 입력값을 대조했습니다.")),
    )
    node = graph.by_id()["applicant:exp-1:clm-1"]

    assert node.label.metric_values == ()
    assert "50건" in " ".join(node.context)

    report = build_proof_shadow_report(
        {
            "assertions": [
                {
                    "assertion_id": "ast-1",
                    "question_index": 1,
                    "atomic_text": "제가 처리량 50건을 기록했습니다.",
                    "authority_status": "supported",
                    "supported_by": ["applicant:exp-1:clm-1"],
                }
            ]
        },
        graph,
    )
    row = report["assertions"][0]
    assert row["unsupported_atomic_metrics"] == ["50건"]
    assert "unsupported_atomic_metric" in row["warnings"]
    assert row["shadow_status"] == "atomic_metric_review_required"
    assert report["decision_effect"] == "none_shadow_mode"


def test_applicant_contribution_ceiling_is_preserved():
    graph = build_claim_graph(
        [_response()],
        _ledger(
            _claim(
                "원문과 입력값을 대조했습니다.",
                contribution="contributed",
            )
        ),
    )
    node = graph.by_id()["applicant:exp-1:clm-1"]
    assert node.label.contribution_ceiling == "contributed"
    assert node.label.subject == "applicant"
    assert node.label.factual_authority is True


def test_research_excerpt_is_context_not_atomic_metric_authority():
    research = SimpleNamespace(
        claim_id="research-1",
        claim="기관은 신청 서류를 검토합니다.",
        evidence_excerpt="지난해 신청 100건을 별도로 분석했습니다.",
        source_url="https://official.example.test/role",
        source_type="official_program_page",
        checked_at="2026-08-17",
        published_at="2026-08-01",
        basis_date="2026-08-01",
        verification_status="verified",
        claim_type="organization_role",
        application_use="문항 1",
    )
    graph = build_claim_graph(
        [_response(research_refs=("research-1",))],
        _ledger(_claim("원문과 입력값을 대조했습니다."), outcome=""),
        (research,),
        research_raw={
            "research-1": {
                "claim_id": "research-1",
                "claim": research.claim,
                "evidence_excerpt": research.evidence_excerpt,
                "source_type": "official_program_page",
                "source_tier": 1,
                "submission_authority": True,
                "freshness_class": "stable",
                "basis_date": "2026-08-01",
            }
        },
    )
    node = graph.by_id()["research:research-1"]
    assert node.label.metric_values == ()
    assert node.context == ("지난해 신청 100건을 별도로 분석했습니다.",)
    assert node.label.factual_authority is True


def test_missing_existing_support_id_is_visible_but_not_promoted_to_proof():
    graph = build_claim_graph(
        [_response()],
        _ledger(_claim("원문과 입력값을 대조했습니다.")),
    )
    report = build_proof_shadow_report(
        {
            "assertions": [
                {
                    "assertion_id": "ast-2",
                    "question_index": 1,
                    "atomic_text": "원문과 입력값을 대조했습니다.",
                    "authority_status": "supported",
                    "supported_by": ["applicant:missing:claim"],
                }
            ]
        },
        graph,
    )
    row = report["assertions"][0]
    assert row["provenance_closed"] is False
    assert row["semantic_proof_closed"] is False
    assert row["shadow_status"] == "missing_graph_support"
    assert "support_id_missing_from_claim_graph" in row["warnings"]


def test_context_only_overlap_is_reported_without_blocking():
    graph = build_claim_graph(
        [_response()],
        _ledger(_claim("원문과 입력값을 대조했습니다.")),
    )
    report = build_proof_shadow_report(
        {
            "assertions": [
                {
                    "assertion_id": "ast-3",
                    "question_index": 1,
                    "atomic_text": "마감 전 누락 여부를 점검했습니다.",
                    "authority_status": "supported",
                    "supported_by": ["applicant:exp-1:clm-1"],
                }
            ]
        },
        graph,
    )
    row = report["assertions"][0]
    assert "context_only_support_risk" in row["warnings"]
    assert row["semantic_proof_closed"] is False
    assert report["decision_effect"] == "none_shadow_mode"
