from pathlib import Path


def test_usage_documents_natural_language_conflicts_resume_and_outputs():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in [
        "자연어 호출",
        "fact_overrides.yaml",
        "재개",
        "06_자기소개서.docx",
        "08_면접대비팩.md",
    ]:
        assert required in text


def test_usage_documents_v2_other_company_and_legacy_quality_difference():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in (
        "profile build",
        "profile refresh",
        "profile validate",
        "posting analyze",
        "--official-source",
        "--official-domain",
        "다른 기업",
        "03_경험직무매칭.json",
        "legacy",
        "낮은 품질",
    ):
        assert required in text


def test_usage_documents_patina_default_and_opt_out():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in ("Patina", "--no-patina", "09_patina_report.json"):
        assert required in text


def test_usage_documents_candidates_quality_scores_and_research_links():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in (
        "--research-domain",
        "04_공식근거.json",
        "research_refs",
        "09_초안후보평가.json",
        "10_품질점수.json",
        "11_최종품질감사.json",
        "career_pipeline audit",
    ):
        assert required in text


def test_usage_documents_phase2_eligibility_flow():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in (
        "profile applicant",
        "posting record",
        "eligibility evaluate",
        "eligible_with_gaps",
        "manual_review",
        "브라우저 자동화와 실제 지원서 제출이 없습니다",
    ):
        assert required in text


def test_usage_documents_phase3_discovery_registry_queue_flow():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    for required in (
        "discovery source-add",
        "discovery run",
        "registry list",
        "queue list",
        "manual_review",
        "queue 승인은 실제 원서 제출 승인이 아닙니다",
    ):
        assert required in text


def test_usage_documents_phase4_review_required_flow():
    text = Path("docs/career-pipeline-usage.md").read_text(encoding="utf-8")
    contract = Path("docs/phase4-output-contract.md").read_text(encoding="utf-8")
    for required in (
        "application package",
        "application validate",
        "application dry-run",
        "review_required",
        "CAPTCHA",
        "MFA",
    ):
        assert required in text
    assert "제출 버튼 감지는 기록하되 클릭하지 않는다" in contract
