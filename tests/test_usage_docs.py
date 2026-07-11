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
