from pathlib import Path

import career_pipeline.editor_contract as editor_contract


def test_editor_contract_includes_human_self_intro_execution_prompt():
    editor_contract.load_editor_contract.cache_clear()

    value = editor_contract.load_editor_contract()

    assert "사실 안전성은 기본 조건일 뿐" in value
    assert "배움→확인→기록→보고" in value
    assert "경제·사회 이슈 문항은 보고서 목차처럼" in value


def test_editor_contract_keeps_base_when_focused_prompt_is_missing(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        editor_contract,
        "HUMAN_SELF_INTRO_PROMPT",
        tmp_path / "missing.md",
    )
    editor_contract.load_editor_contract.cache_clear()

    value = editor_contract.load_editor_contract()

    assert "저자의 목소리 보존" in value
    assert "confirmed claim" in value
    editor_contract.load_editor_contract.cache_clear()


def test_editor_contract_resolves_reordering_and_plan_question_exceptions():
    editor_contract.load_editor_contract.cache_clear()

    value = editor_contract.load_editor_contract()

    assert "합성·재작성 단계에서는 문항 순서를 보존" in value
    assert "문항 자체가 업무수행계획을 요구하면 계획 문장을 더 쓸 수" in value
