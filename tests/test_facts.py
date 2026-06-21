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


def test_generic_year_is_not_treated_as_employment_period():
    source = SourceRecord(Path("posting.txt"), "posting.txt", ".txt", 1, "hash", "use")
    document = ExtractedDocument(source, "", ("2026년 채용공고",))

    claims = extract_fact_claims([document])

    assert claims[0].field == "metric:년"


def test_calendar_year_in_employment_context_is_not_a_duration():
    source = SourceRecord(Path("career.docx"), "career.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(source, "", ("2025년 서울시청에서 근무했습니다.",))

    claims = extract_fact_claims([document])

    assert claims[0].field == "metric:년"


def test_metric_tokens_use_nearby_context_instead_of_the_whole_paragraph():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        (
            "숙박비 영수증을 검증해 예산 4천만원을 절감했습니다. "
            + "서로 무관한 설명 " * 30
            + "전화 업무를 40% 줄였습니다.",
        ),
    )

    claims = extract_fact_claims([document])
    savings = next(item for item in claims if item.normalized_value == "40000000원")
    phone = next(item for item in claims if item.normalized_value == "40%")

    assert "숙박비" in savings.tokens
    assert "숙박비" not in phone.tokens
    assert phone.field == "metric:percentage"


def test_invoice_amount_is_not_mistaken_for_the_savings_result():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        (
            "1억 원의 예산 누수를 막았습니다. 특정 고시원의 청구액 50만 원을 확인했습니다.",
        ),
    )

    claims = extract_fact_claims([document])
    by_value = {claim.normalized_value: claim for claim in claims}

    assert by_value["100000000원"].field == "budget_savings"
    assert by_value["500000원"].field == "metric:money"


def test_seniority_and_task_deadline_are_not_employment_periods():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        (
            "서울시청 근무 당시 20년 차 주무관과 협업했습니다.",
            "국민연금공단 인턴 당시 서류를 2일 안에 정리했습니다.",
        ),
    )

    claims = extract_fact_claims([document])

    assert all(claim.field != "employment_period" for claim in claims)


def test_processed_volume_is_separate_from_detected_case_count():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        (
            "700건의 영수증 중 부정수급 의심 사례 20건을 적발했습니다.",
            "숙박비 자료 약 2,000건을 처리했습니다.",
        ),
    )

    claims = extract_fact_claims([document])
    by_value = {claim.normalized_value: claim.field for claim in claims}

    assert by_value["700건"] == "processed_case_count"
    assert by_value["2000건"] == "processed_case_count"
    assert by_value["20건"] == "case_count"


def test_speed_reduction_percentage_is_not_budget_savings():
    source = SourceRecord(Path("a.docx"), "a.docx", ".docx", 1, "hash", "use")
    document = ExtractedDocument(
        source,
        "",
        (
            "예산 1,000만 원의 누수를 막고 전체 검증 속도를 25% 단축했습니다.",
        ),
    )

    claims = extract_fact_claims([document])
    by_value = {claim.normalized_value: claim.field for claim in claims}

    assert by_value["10000000원"] == "budget_savings"
    assert by_value["25%"] == "metric:percentage"
