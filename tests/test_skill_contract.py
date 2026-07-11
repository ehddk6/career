from pathlib import Path


def test_skill_requires_prepare_conflict_gate_official_research_and_finalize():
    text = Path(".agents/skills/career-pipeline/SKILL.md").read_text(
        encoding="utf-8"
    )
    for required in [
        "python -m career_pipeline prepare",
        "03_충돌검사.md",
        "공식 출처",
        "draft.json",
        "08_면접대비팩.md",
        "python -m career_pipeline finalize",
    ]:
        assert required in text


def test_skill_has_ui_metadata_and_output_contract():
    assert Path(
        ".agents/skills/career-pipeline/agents/openai.yaml"
    ).exists()
    contract = Path(
        ".agents/skills/career-pipeline/references/output-contract.md"
    ).read_text(encoding="utf-8")
    assert "evidence_paths" in contract
    assert "꼬리질문" in contract


def test_skill_documents_v2_profile_posting_and_matching_flow():
    text = Path(".agents/skills/career-pipeline/SKILL.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "profile build",
        "profile validate",
        "posting analyze",
        "blocked_profile",
        "blocked_posting",
        "03_경험직무매칭",
        "experience_refs",
    ):
        assert required in text

    contract = Path(
        ".agents/skills/career-pipeline/references/output-contract.md"
    ).read_text(encoding="utf-8")
    assert "experience_refs" in contract
    assert "blocked_validation" in contract
