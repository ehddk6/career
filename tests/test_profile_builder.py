from pathlib import Path

from career_pipeline.models import ExtractedDocument, SourceRecord
from career_pipeline.profile_builder import build_proposed_ledger


def document(tmp_path: Path, relative_path: str, *paragraphs: str) -> ExtractedDocument:
    source = SourceRecord(
        path=tmp_path / Path(relative_path).name,
        relative_path=relative_path,
        extension=Path(relative_path).suffix,
        size=1,
        sha256="a" * 64,
        status="use",
    )
    return ExtractedDocument(source, "\n".join(paragraphs), tuple(paragraphs))


def test_build_proposed_ledger_groups_claims_by_evidence_block(tmp_path: Path):
    source = document(
        tmp_path,
        "career.docx",
        "숙박비 영수증을 교차 확인해 부정수급 의심 20건을 찾고 "
        "예산 1,000만원의 누수를 막았습니다.",
    )

    ledger = build_proposed_ledger(Path("C:/career"), [source])

    assert len(ledger.experiences) == 1
    experience = ledger.experiences[0]
    assert experience.status == "proposed"
    assert {claim.normalized_value for claim in experience.claims} == {
        "20건",
        "10000000원",
    }
    assert all(claim.status == "proposed" for claim in experience.claims)
    assert all(claim.evidence[0].source_sha256 == "a" * 64 for claim in experience.claims)


def test_separate_paragraphs_create_stable_separate_experience_ids(tmp_path: Path):
    source = document(
        tmp_path,
        "경험정리/career.docx",
        "영수증을 확인해 의심 사례 20건을 발견했습니다.",
        "자료를 분석해 예산 1,000만원을 절감했습니다.",
    )

    first = build_proposed_ledger(tmp_path, [source])
    second = build_proposed_ledger(tmp_path, [source])

    assert len(first.experiences) == 2
    assert first.experiences[0].experience_id != first.experiences[1].experience_id
    assert [item.experience_id for item in first.experiences] == [
        item.experience_id for item in second.experiences
    ]
    assert first.experiences[0].title == "career 문단 1"
    assert first.experiences[0].organization_alias == ""


def test_builder_ignores_non_evidence_documents(tmp_path: Path):
    posting = document(tmp_path, "자료조사/채용공고.pdf", "채용 인원 20명")

    ledger = build_proposed_ledger(tmp_path, [posting])

    assert ledger.experiences == ()


def test_builder_prefers_dedicated_experience_folder_over_workspace_templates(tmp_path: Path):
    template = document(
        tmp_path,
        "금융 면접 템플릿.docx",
        "자료를 확인하고 결과를 정리했습니다.",
    )
    experience = document(
        tmp_path,
        "경험정리/career.docx",
        "민원 안내 담당으로 문의 유형을 분석해 안내 순서를 개선했습니다.",
    )

    ledger = build_proposed_ledger(tmp_path, [template, experience])

    assert len(ledger.experiences) == 1
    assert ledger.experiences[0].title == "career 문단 1"


def test_builder_prefers_editable_sources_and_limits_candidates_per_source(tmp_path: Path):
    editable = document(
        tmp_path,
        "경험정리/career.docx",
        *(f"자료를 확인해 {index}건을 정리하고 결과를 개선했습니다." for index in range(40)),
    )
    duplicate_pdf = document(
        tmp_path,
        "경험정리/career.pdf",
        "자료를 확인해 99건을 정리하고 결과를 개선했습니다.",
    )

    ledger = build_proposed_ledger(tmp_path, [editable, duplicate_pdf])

    assert len(ledger.experiences) == 30
    assert {
        claim.evidence[0].source_path
        for experience in ledger.experiences
        for claim in experience.claims
    } == {"경험정리/career.docx"}


def test_builder_structures_qualitative_experience_without_numbers(tmp_path: Path):
    source = document(
        tmp_path,
        "경험정리/career.docx",
        "민원 안내 담당으로 반복 문의가 발생하는 상황을 확인했습니다. "
        "담당자들과 문의 유형을 분석하고 안내 순서를 개선했습니다. "
        "그 결과 응대 기준을 통일하고 고객의 신뢰를 얻었습니다.",
    )

    ledger = build_proposed_ledger(tmp_path, [source])

    assert len(ledger.experiences) == 1
    experience = ledger.experiences[0]
    assert "민원 안내 담당" in experience.role
    assert any("분석" in action for action in experience.actions)
    assert any("신뢰" in outcome for outcome in experience.outcomes)
    assert {"문제 해결", "협업", "신뢰"}.intersection(experience.competencies)
    assert {claim.field for claim in experience.claims} == {"experience_summary"}


def test_builder_groups_explicit_star_section_with_multi_paragraph_evidence(tmp_path: Path):
    source = document(
        tmp_path,
        "경험정리/career.docx",
        "2️⃣ 서울시청 코로나19 지원",
        "✅ Situation (상황):",
        "숙박비 지원 증빙의 신뢰성이 부족하다는 문제를 발견했습니다.",
        "✅ Action (실행):",
        "영수증과 임대인의 증빙 금액을 대조해 불일치 사례를 분류했습니다.",
        "부동산 앱으로 시세 검증 절차를 추가했습니다.",
        "✅ Result (결과):",
        "부정수급 20건을 적발하고 처리 기간을 1주일 단축했습니다.",
        "📌 어필",
        "포인트: 정확성과 문제 해결",
    )

    ledger = build_proposed_ledger(tmp_path, [source])

    assert len(ledger.experiences) == 1
    experience = ledger.experiences[0]
    assert experience.title == "2️⃣ 서울시청 코로나19 지원"
    summary = next(claim for claim in experience.claims if claim.field == "experience_summary")
    assert len(summary.evidence) == 4
    assert "20건" not in summary.normalized_value
    assert "1주일" not in summary.normalized_value
    assert {claim.normalized_value for claim in experience.claims if claim.field != "experience_summary"} == {
        "20건", "1주"
    }
    assert any("대조" in action for action in experience.actions)


def test_explicit_blocks_survive_candidate_cap_and_do_not_duplicate_paragraphs(tmp_path: Path):
    source = document(
        tmp_path,
        "경험정리/career.docx",
        *(f"자료를 확인해 {index}건을 정리하고 결과를 개선했습니다." for index in range(40)),
        "🔹 4.",
        "반포한강공원 행사 운영",
        "✅ 출석부 미기재와 물품 혼선을 분석했습니다.",
        "✅ 온라인 출석부를 제안해 진행 흐름을 개선했습니다.",
        "📌 활용",
    )

    ledger = build_proposed_ledger(tmp_path, [source])

    assert len(ledger.experiences) == 30
    blocks = [item for item in ledger.experiences if "반포한강공원" in item.title]
    assert len(blocks) == 1
    assert any("온라인 출석부" in action for action in blocks[0].actions)
