import json
from pathlib import Path

from docx import Document

from career_pipeline.inventory import digest_path
from career_pipeline.orchestrator import prepare_run
from career_pipeline.profile_builder import excerpt_sha256


def write_docx(path: Path, *paragraphs: str) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def write_profile(
    root: Path,
    source: Path,
    *,
    experience_status: str = "confirmed",
    claim_value: str = "20건",
    include_proposed: bool = True,
    duplicate_value: str | None = None,
) -> Path:
    reference = {
        "source_path": source.relative_to(root).as_posix(),
        "paragraph_index": 0,
        "source_sha256": digest_path(source),
        "excerpt_sha256": excerpt_sha256("자료를 교차 확인해 의심 사례 20건을 발견했습니다."),
    }
    claims = [
        {
            "field": "case_count",
            "normalized_value": claim_value,
            "status": "confirmed" if experience_status == "confirmed" else experience_status,
            "evidence": [reference],
        }
    ]
    if include_proposed:
        claims.append(
            {
                "field": "raw_proposed",
                "normalized_value": "사용금지",
                "status": "proposed",
                "evidence": [reference],
            }
        )
    if duplicate_value:
        claims.append(
            {
                "field": "case_count",
                "normalized_value": duplicate_value,
                "status": "confirmed",
                "evidence": [reference],
            }
        )
    payload = {
        "schema_version": 1,
        "generated_at": "2026-06-21T12:00:00+09:00",
        "workspace_root": root.as_posix(),
        "experiences": [
            {
                "experience_id": "exp_verify",
                "title": "자료 검증",
                "organization_alias": "기관",
                "period": None,
                "role": "자료 확인",
                "situation": "의심 사례 점검",
                "actions": ["자료 교차 확인"],
                "outcomes": ["의심 사례 20건 발견"],
                "competencies": ["정확성"],
                "claims": claims,
                "status": experience_status,
                "confirmed_at": "2026-06-21T12:00:00+09:00" if experience_status == "confirmed" else None,
            }
        ],
    }
    profile_dir = root / ".career_profile"
    profile_dir.mkdir(exist_ok=True)
    path = profile_dir / "experience_ledger.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def setup_sources(root: Path, *, posting_question: str = "지원동기를 작성해 주십시오."):
    career = root / "career.txt"
    career.write_text(
        "자료를 교차 확인해 의심 사례 20건을 발견했습니다.", encoding="utf-8"
    )
    posting = root / "posting.docx"
    write_docx(
        posting,
        "기관명",
        "주택도시보증공사",
        "채용분야",
        "금융·기금",
        "담당업무",
        "신청 자료 확인",
        "자기소개서",
        posting_question,
        "0/600 (글자 수, 공백 포함)",
    )
    draft = root / "draft.docx"
    write_docx(draft, "지원동기를 작성해 주십시오.", "0/600 (글자 수, 공백 포함)")
    return career, posting, draft


def run_v2(root: Path, profile: Path, posting: Path, draft: Path, name: str):
    return prepare_run(
        root,
        "HUG 금융·기금",
        draft,
        str(posting),
        name,
        profile=profile,
        official_source=True,
    )


def write_frame_guidance(root: Path) -> Path:
    source_dir = root / "자료조사" / "자소서_유튜브_프레임분석_2026-07-03"
    source_dir.mkdir(parents=True)
    (source_dir / "01_자소서_작성원칙_요약.md").write_text(
        "# 작성 원칙\n\n- 문항을 먼저 유형화합니다.\n", encoding="utf-8"
    )
    (source_dir / "02_문항유형별_전략.md").write_text(
        "# 문항 전략\n\n- 지원동기는 기관 이해로 연결합니다.\n", encoding="utf-8"
    )
    (source_dir / "03_기관별_적용노트.md").write_text(
        "# 기관 노트\n\n- 공공기관은 현장성과 책임을 강조합니다.\n", encoding="utf-8"
    )
    (source_dir / "05_문장_근거색인.csv").write_text(
        "video,frame,text\nsample,1,유튜브 예시 문장은 사실 근거가 아닙니다.\n",
        encoding="utf-8",
    )
    return source_dir


def test_v2_prepare_writes_confirmed_profile_posting_and_matching_artifacts(tmp_path: Path):
    career, posting, draft = setup_sources(tmp_path)
    profile = write_profile(tmp_path, career)
    write_frame_guidance(tmp_path)

    state = run_v2(tmp_path, profile, posting, draft, "v2-ready")
    run_dir = Path(state["run_dir"])

    assert state["status"] == "ready_for_research"
    assert state["quality_mode"] == "v2"
    assert state["research_policy"] == "evidence-first"
    assert state["research_method_default"] == "evidence-first-research"
    assert state["research_method_enforced"] is False
    for name in (
        "00_채용공고분석.json",
        "00_채용공고분석.md",
        "02_확정경험원장.json",
        "03_경험직무매칭.json",
        "03_경험직무매칭.md",
        "04_공식근거.json",
        "04_리서치실행.json",
    ):
        assert (run_dir / name).exists()
    manifest = json.loads(
        (run_dir / "04_리서치실행.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "pending"
    assert manifest["skill_name"] == "evidence-first-research"
    snapshot = (run_dir / "02_확정경험원장.json").read_text(encoding="utf-8")
    assert "raw_proposed" not in snapshot
    assert "사용금지" not in snapshot
    assert state["official_research_domains"] == ["khug.or.kr"]
    guidance = state["writing_guidance"]
    assert guidance["status"] == "available"
    assert guidance["kind"] == "youtube_frame_strategy"
    assert guidance["use_policy"] == "strategy_only_not_factual_evidence"
    guidance_path = run_dir / "05_작성가이드_유튜브프레임.md"
    assert guidance["artifact"] == guidance_path.relative_to(tmp_path).as_posix()
    assert guidance_path.exists()
    guidance_text = guidance_path.read_text(encoding="utf-8")
    assert "공식 근거 또는 경험 사실 근거로 사용하지 않습니다." in guidance_text
    assert "유튜브 예시 문장" not in snapshot


def test_v2_prepare_reports_profile_posting_conflict_and_question_blockers(tmp_path: Path):
    career, posting, draft = setup_sources(tmp_path)

    stale_profile = write_profile(tmp_path, career, experience_status="stale")
    stale = run_v2(tmp_path, stale_profile, posting, draft, "v2-stale")
    assert stale["status"] == "blocked_profile"

    profile = write_profile(tmp_path, career)
    unverified = prepare_run(
        tmp_path,
        "HUG",
        draft,
        str(posting),
        "v2-unverified",
        profile=profile,
        official_source=False,
    )
    assert unverified["status"] == "blocked_posting"

    conflict_profile = write_profile(
        tmp_path, career, duplicate_value="30건", include_proposed=False
    )
    conflict = run_v2(tmp_path, conflict_profile, posting, draft, "v2-conflict")
    assert conflict["status"] == "blocked_conflict"

    mismatch_posting = tmp_path / "mismatch.docx"
    write_docx(
        mismatch_posting,
        "기관명", "기관", "채용분야", "직무", "담당업무", "자료 확인",
        "자기소개서", "입사 후 목표를 작성해 주십시오.", "0/600 (글자 수, 공백 포함)",
    )
    profile = write_profile(tmp_path, career)
    mismatch = run_v2(tmp_path, profile, mismatch_posting, draft, "v2-mismatch")
    assert mismatch["status"] == "blocked_posting"


def test_legacy_prepare_records_legacy_quality_mode(tmp_path: Path):
    _, _, draft = setup_sources(tmp_path)

    state = prepare_run(tmp_path, "HUG", draft, None, "legacy")

    assert state["quality_mode"] == "legacy"
    assert state["research_policy"] == "evidence-first"
    assert state["research_method_default"] == "evidence-first-research"
    assert state["research_method_enforced"] is False
