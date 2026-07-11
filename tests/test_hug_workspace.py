from pathlib import Path
from docx import Document
from dataclasses import replace
from datetime import datetime, timezone
import json

from career_pipeline.orchestrator import prepare_run
from career_pipeline.profile_schema import load_ledger
from career_pipeline.quality import validate_profile_gate
from career_pipeline.extractors import extract_path
from career_pipeline.inventory import digest_path
from career_pipeline.models import SourceRecord
from career_pipeline.profile_builder import build_proposed_ledger
from career_pipeline.profile_schema import ledger_to_dict


def _write_docx(path, *paragraphs):
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def test_synthetic_hug_draft_with_conflicting_savings_blocks_generation(tmp_path):
    evidence = tmp_path / 'experiences'
    evidence.mkdir()
    (evidence / 'career_a.txt').write_text(
        'HUG 4,000만원 예산절감',
        encoding='utf-8-sig',
    )
    (evidence / 'career_b.txt').write_text(
        'HUG 1,000만원 예산절감',
        encoding='utf-8-sig',
    )
    _write_docx(
        tmp_path / 'posting.docx',
        '기관명', '주택도시보증공사',
        '채용분야', '금융기금(강원)',
        '담당업무', '주택청약 접수 창구 관리',
        '필요역량', '정확성 소통력',
        '자기소개서',
        '지원동기를 작성해 주십시오',
        '0/600 (글자 수, 공백 포함)',
    )
    _write_docx(
        tmp_path / 'draft.docx',
        '지원동기를 작성해 주십시오',
        '0/600 (글자수 제한 포함)',
    )

    state = prepare_run(
        tmp_path, 'HUG 금융기금(강원)',
        tmp_path / 'draft.docx',
        str(tmp_path / 'posting.docx'),
        'synthetic-hug',
        official_source=True,
    )

    assert state['conflict_count'] >= 1
    assert '| use |' in (Path(state['run_dir']) / '01_자료목록.md').read_text(encoding='utf-8')


def test_approved_profile_passes_v2_profile_gate_with_synthetic_ledger(tmp_path):
    career = tmp_path / 'career.txt'
    career.write_text(
        '부정수급 의심 20건을 찾고 예산 1,000만원의 누수를 막았습니다',
        encoding='utf-8-sig',
    )
    source = SourceRecord(
        career, 'career.txt', '.txt', career.stat().st_size,
        digest_path(career), 'use',
    )
    proposed = build_proposed_ledger(tmp_path, [extract_path(source)])
    confirmed = replace(
        proposed,
        experiences=tuple(
            replace(
                exp,
                status='confirmed',
                confirmed_at=datetime.now(timezone.utc).isoformat(),
                claims=tuple(replace(c, status='confirmed') for c in exp.claims),
            )
            for exp in proposed.experiences
        ),
    )
    profile = tmp_path / 'profile.json'
    profile.write_text(
        json.dumps(ledger_to_dict(confirmed), ensure_ascii=False, indent=2) + chr(10),
        encoding='utf-8',
    )
    ledger = load_ledger(profile)

    issues = validate_profile_gate(
        ledger,
        selected_experience_ids={item.experience_id for item in ledger.experiences},
    )

    assert not issues
