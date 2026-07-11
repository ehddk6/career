from dataclasses import replace
import json
from pathlib import Path

from docx import Document

from career_pipeline.extractors import extract_path
from career_pipeline.inventory import digest_path
from career_pipeline.models import SourceRecord
from career_pipeline.orchestrator import finalize_run, prepare_run
from career_pipeline.profile_builder import build_proposed_ledger
from career_pipeline.profile_schema import ledger_to_dict


QUESTIONS = (
    "지원동기와 인턴 근무 목표를 기술해 주십시오.",
    "문제를 발견하고 개선한 경험을 기술해 주십시오.",
    "팀과 협업한 경험을 기술해 주십시오.",
    "원칙을 지키며 신뢰를 얻은 경험을 기술해 주십시오.",
)


def write_docx(path: Path, *paragraphs: str) -> Path:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)
    return path


def build_and_confirm_fixture_profile(root: Path) -> Path:
    source_path = root / "career.txt"
    source_path.write_text(
        "자료를 교차 확인해 부정수급 의심 20건을 찾고 예산 1,000만원의 누수를 막았습니다.",
        encoding="utf-8",
    )
    source = SourceRecord(
        source_path,
        "career.txt",
        ".txt",
        source_path.stat().st_size,
        digest_path(source_path),
        "use",
    )
    proposed = build_proposed_ledger(root, [extract_path(source)])
    confirmed_experiences = tuple(
        replace(
            experience,
            claims=tuple(replace(claim, status="confirmed") for claim in experience.claims),
            status="confirmed",
            confirmed_at="2026-06-21T12:00:00+09:00",
        )
        for experience in proposed.experiences
    )
    confirmed = replace(proposed, experiences=confirmed_experiences)
    profile_dir = root / ".career_profile"
    profile_dir.mkdir()
    profile = profile_dir / "experience_ledger.json"
    profile.write_text(
        json.dumps(ledger_to_dict(confirmed), ensure_ascii=False), encoding="utf-8"
    )
    return profile


def test_v2_profile_posting_matching_and_finalize(tmp_path: Path):
    profile = build_and_confirm_fixture_profile(tmp_path)
    posting_paragraphs = [
        "기관명",
        "주택도시보증공사",
        "채용분야",
        "금융·기금(강원)",
        "담당업무",
        "도시재생 금융지원 자료 확인 및 안내 업무 보조",
        "필요역량",
        "정확성",
        "자기소개서",
    ]
    for question in QUESTIONS:
        posting_paragraphs.extend([question, "0/600 (글자 수, 공백 포함)"])
    posting = write_docx(tmp_path / "posting.docx", *posting_paragraphs)

    draft_paragraphs: list[str] = []
    for question in QUESTIONS:
        draft_paragraphs.extend([question, "0/600 (글자 수, 공백 포함)"])
    draft = write_docx(tmp_path / "draft.docx", *draft_paragraphs)

    state = prepare_run(
        tmp_path,
        "HUG 금융·기금(강원)",
        draft,
        str(posting),
        "v2-e2e",
        profile=profile,
        official_source=True,
    )

    assert state["status"] == "ready_for_research"
    run_dir = Path(state["run_dir"])
    ledger = json.loads((run_dir / "02_확정경험원장.json").read_text(encoding="utf-8"))
    experience = ledger["experiences"][0]
    claim_fields = [claim["field"] for claim in experience["claims"]]
    evidence_path = experience["claims"][0]["evidence"][0]["source_path"]
    (run_dir / "04_기업직무조사.md").write_text(
        "[HUG 공식](https://www.khug.or.kr)", encoding="utf-8"
    )
    (run_dir / "05_문항전략.md").write_text("# 문항전략", encoding="utf-8")
    (run_dir / "08_면접대비팩.md").write_text(
        "# 면접대비팩\n1분 자기소개\n꼬리질문\n압박질문\n근거",
        encoding="utf-8",
    )
    responses = [
        {
            "question_index": index,
            "answer": "자료를 교차 확인한 경험을 바탕으로 정확하게 업무를 수행하겠습니다.",
            "evidence_paths": [evidence_path],
            "experience_refs": [
                {
                    "experience_id": experience["experience_id"],
                    "claim_fields": claim_fields,
                }
            ],
        }
        for index in range(1, 5)
    ]
    (run_dir / "draft.json").write_text(
        json.dumps(responses, ensure_ascii=False), encoding="utf-8"
    )

    final = finalize_run(run_dir)

    assert final["status"] == "blocked_validation"
    assert {item["code"] for item in final["validation_issues"]}.intersection(
        {"underfilled_answer", "duplicate_answer"}
    )
    assert not (run_dir / "06_자기소개서.docx").exists()
    assert (run_dir / "07_자기소개서_검토보고서.md").exists()
