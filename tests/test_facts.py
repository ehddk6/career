from pathlib import Path

from career_pipeline.facts import extract_fact_claims
from career_pipeline.models import ExtractedDocument, SourceRecord


def test_extracts_budget_savings_and_case_count():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        (
            "의료인력 숙박비를 검증해 허위 거래 20건을 적발하고 예산 4천만원을 줄였습니다.",
        ),
    )

    claims = extract_fact_claims([document])

    assert {(claim.field, claim.normalized_value) for claim in claims} >= {
        ("case_count", "20건"),
        ("budget_savings", "40000000원"),
    }
