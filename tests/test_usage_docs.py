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
