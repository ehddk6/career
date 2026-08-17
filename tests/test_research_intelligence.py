from career_pipeline.research_conflicts import resolve_research_conflicts
from career_pipeline.research_coverage import build_research_coverage
from career_pipeline.research_planner import compile_research_plan
from career_pipeline.research_source_registry import build_source_registry, classify_source
from career_pipeline.research_workspace import enrich_claim_metadata


def test_motivation_compiles_argument_slots_before_search():
    plan = compile_research_plan(
        [{"index": 1, "prompt": "우리 기관에 지원한 동기와 입사 후 하고 싶은 일을 작성하시오."}],
        target="테스트공사 행정",
    )
    question = plan["questions"][0]
    roles = [slot["argument_role"] for slot in question["slots"]]
    assert question["intent"] == "motivation"
    assert roles[:2] == ["organization_differentiator", "real_operating_role"]
    assert all(slot["suggested_query"].startswith("테스트공사 행정") for slot in question["slots"])


def test_source_hierarchy_separates_official_submission_authority():
    registry = build_source_registry("테스트공사", explicit_domains=["example.go.kr"])
    official = classify_source(
        "https://www.example.go.kr/business", source_type="official_program_page", registry=registry
    )
    news = classify_source(
        "https://news.example.com/article", source_type="reputable_news", registry=registry
    )
    assert official["official"] is True
    assert official["submission_authority"] is True
    assert news["source_tier"] == 4
    assert news["submission_authority"] is False


def test_conflict_resolver_prefers_direct_current_lower_tier_claim():
    claims = [
        {
            "claim_id": "old", "claim": "지원한도는 1억원이다", "conflict_group": "limit",
            "verification_status": "verified", "support_strength": "direct", "freshness_class": "historical",
            "source_tier": 1, "published_at": "2025-01-01",
        },
        {
            "claim_id": "new", "claim": "지원한도는 2억원이다", "conflict_group": "limit",
            "verification_status": "verified", "support_strength": "direct", "freshness_class": "current",
            "source_tier": 1, "published_at": "2026-07-01",
        },
    ]
    report = resolve_research_conflicts(claims)
    assert report["status"] == "resolved"
    assert report["conflicts"][0]["winner_claim_id"] == "new"
    assert report["losing_claim_ids"] == ["old"]


def test_required_coverage_fails_closed_then_stops_when_filled():
    plan = compile_research_plan(
        [{"index": 1, "prompt": "지원동기를 작성하시오."}], target="테스트공사"
    )
    empty = build_research_coverage(plan, [], {})
    assert empty["status"] == "needs_research"
    assert empty["stop_research"] is False

    claims = [
        {
            "claim_id": "r1", "claim": "고유 정책 기능", "claim_type": "organization_role",
            "argument_role": "organization_differentiator", "verification_status": "verified",
            "support_strength": "direct", "source_tier": 1, "freshness_class": "stable",
            "application_use": "문항 1",
        },
        {
            "claim_id": "r2", "claim": "행정 직무는 심사 자료를 검토한다", "claim_type": "job_duty",
            "argument_role": "real_operating_role", "verification_status": "verified",
            "support_strength": "direct", "source_tier": 0, "freshness_class": "current",
            "application_use": "문항 1",
        },
    ]
    full = build_research_coverage(plan, claims, {})
    assert full["status"] == "ready"
    assert full["stop_research"] is True


def test_legacy_claim_metadata_is_enriched_without_changing_claim_text():
    plan = compile_research_plan(
        [{"index": 1, "prompt": "직무수행계획을 작성하시오."}], target="테스트공사"
    )
    original = {
        "claim_id": "job-1",
        "claim": "고객 신청서류를 검토한다",
        "claim_type": "job_duty",
        "evidence_excerpt": "신청서류 검토 및 보완 안내",
        "verification_status": "confirmed",
    }
    enriched = enrich_claim_metadata([original], plan)[0]
    assert enriched["claim"] == original["claim"]
    assert enriched["argument_role"] == "real_operating_role"
    assert enriched["support_strength"] == "direct"
    assert "문항 1" in enriched["application_use"]


def test_router_replaces_lexical_research_pick_with_coverage_approved_claims():
    from career_pipeline.research_router import route_research_into_blueprint

    packet = {
        "packet_id": "base",
        "questions": [{
            "question_index": 1,
            "research_claims": [{"claim_id": "wrong", "claim": "brochure"}],
            "risk_controls": [],
        }],
    }
    report = {
        "claims": [
            {"claim_id": "r1", "claim": "고유 기능", "claim_type": "organization_role", "argument_role": "organization_differentiator"},
            {"claim_id": "r2", "claim": "실제 업무", "claim_type": "job_duty", "argument_role": "real_operating_role"},
        ],
        "coverage": {
            "status": "ready", "coverage_ratio": 1.0,
            "questions": [{
                "question_index": 1, "research_required": True, "ready": True,
                "slots": [
                    {"argument_role": "organization_differentiator", "required": True, "status": "pass", "accepted_claim_ids": ["r1"]},
                    {"argument_role": "real_operating_role", "required": True, "status": "pass", "accepted_claim_ids": ["r2"]},
                ],
            }],
        },
        "conflicts": {"status": "resolved"},
    }
    routed = route_research_into_blueprint(packet, report)
    ids = [item["claim_id"] for item in routed["questions"][0]["research_claims"]]
    assert ids == ["r1", "r2"]
    assert routed["questions"][0]["research_intelligence"]["coverage_status"] == "ready"


def test_same_claim_type_cannot_fill_a_different_argument_role():
    plan = compile_research_plan(
        [{"index": 1, "prompt": "직무수행계획을 작성하시오."}], target="테스트공사"
    )
    claims = [{
        "claim_id": "job-only", "claim": "서류를 검토한다", "claim_type": "job_duty",
        "argument_role": "real_operating_role", "verification_status": "verified",
        "support_strength": "direct", "source_tier": 0, "freshness_class": "posting_bound",
        "application_use": "문항 1",
    }]
    coverage = build_research_coverage(plan, claims, {})
    slots = {item["argument_role"]: item for item in coverage["questions"][0]["slots"]}
    assert slots["real_operating_role"]["status"] == "pass"
    assert slots["operating_constraint"]["status"] != "pass"
    assert coverage["stop_research"] is False


def test_dated_volatile_claim_is_not_assumed_current():
    plan = compile_research_plan(
        [{"index": 1, "prompt": "직무수행계획을 작성하시오."}], target="테스트공사"
    )
    raw = {
        "claim_id": "risk-1", "claim": "현재 오류 통제 기준", "claim_type": "risk_or_limit",
        "evidence_excerpt": "오류 통제 기준", "published_at": "2024-01-01",
        "source_type": "official_program_page", "verification_status": "confirmed",
    }
    enriched = enrich_claim_metadata([raw], plan)[0]
    assert enriched["freshness_class"] == "unknown"
    assert enriched["source_tier"] == 1


def test_non_authoritative_source_is_downgraded_at_claim_ingestion():
    from career_pipeline.research_claim_extractor import normalize_research_claim

    registry = build_source_registry("테스트공사", explicit_domains=["example.go.kr"])
    claim = normalize_research_claim(
        {
            "claim_id": "news-1",
            "claim": "최근 사업 방향에 관한 기사 주장",
            "claim_type": "program_or_service",
            "source_url": "https://news.example.com/article",
            "source_type": "reputable_news",
            "evidence_excerpt": "기사 본문",
            "verification_status": "verified",
        },
        registry=registry,
        checked_at="2026-08-17",
    )
    assert claim["source_tier"] == 4
    assert claim["verification_status"] == "contextual"
    assert "authority_note" in claim
