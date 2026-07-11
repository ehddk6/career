import json
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.artifacts import write_final_artifact_manifest
from career_pipeline.audit import run_quality_audit


HASH = "a" * 64


def write_submission_ready_run(run_dir: Path) -> None:
    run_dir.mkdir(exist_ok=True)
    root = run_dir / "workspace"
    profile_dir = root / ".career_profile"
    profile_dir.mkdir(parents=True)
    (profile_dir / "voice_sample.txt").write_text(
        "저는 자료를 먼저 확인하고 기준을 정리한 뒤, 상대가 바로 이해할 수 있게 설명하는 방식으로 일합니다.",
        encoding="utf-8",
    )
    state = {
        "status": "complete",
        "quality_mode": "v2",
        "strict_quality": True,
        "root": str(root),
        "target": "HUG 금융·기금",
        "patina_status": "not_needed",
        "patina_voice_sample_used": str(profile_dir / "voice_sample.txt"),
        "official_research_domains": ["khug.or.kr"],
        "questions": [
            {
                "index": 1,
                "prompt": "HUG 주요 사업과 보증심사 업무 기여 방안",
                "character_limit": 600,
            }
        ],
    }
    (run_dir / "run.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    ledger = {
        "schema_version": 1,
        "generated_at": "2026-06-21T12:00:00+09:00",
        "workspace_root": str(root),
        "experiences": [
            {
                "experience_id": "exp_verify",
                "title": "자료 검증 경험",
                "organization_alias": "기관",
                "period": None,
                "role": "자료 검증",
                "situation": "보증 관련 의심 사례 확인",
                "actions": ["자료 대조", "오류 원인 확인", "검토 기준 정리"],
                "outcomes": ["20건 확인"],
                "competencies": ["정확성", "고객 소통"],
                "claims": [
                    {
                        "field": "case_count",
                        "normalized_value": "20건",
                        "status": "confirmed",
                        "evidence": [
                            {
                                "source_path": "career.txt",
                                "paragraph_index": 0,
                                "source_sha256": HASH,
                                "excerpt_sha256": "b" * 64,
                            }
                        ],
                    }
                ],
                "status": "confirmed",
                "confirmed_at": "2026-06-21T12:00:00+09:00",
            }
        ],
    }
    (run_dir / "02_확정경험원장.json").write_text(
        json.dumps(ledger, ensure_ascii=False), encoding="utf-8"
    )
    posting = {
        "duties": ["보증심사 자료 검토", "민원 기록 확인"],
        "competencies": ["정확성", "고객 소통"],
        "source": {"official_status": "user_attested"},
    }
    (run_dir / "00_채용공고분석.json").write_text(
        json.dumps(posting, ensure_ascii=False), encoding="utf-8"
    )
    answer = (
        "HUG 금융·기금 직무에서 전세보증금반환보증은 임차인의 보증금 반환 위험을 줄이는 공적 보증입니다. "
        "저는 의심 사례 20건을 접수한 뒤 계약서, 납부 내역, 민원 기록을 항목별로 대조하고 오류 원인을 담당자와 확인했습니다. "
        "그 결과 누락 기준을 표로 정리해 검토 흐름을 개선했고, 보증심사 자료 검토 업무에서도 같은 방식으로 위험 신호를 먼저 확인하겠습니다. "
        "또한 확인된 사실과 추정을 분리해 기록하고, 고객에게는 필요한 서류와 다음 절차를 쉬운 표현으로 안내하겠습니다. "
        "이 경험을 바탕으로 HUG의 보증 업무에서 정확성과 고객 신뢰를 함께 높이겠습니다."
    )
    draft = [
        {
            "question_index": 1,
            "answer": answer,
            "evidence_paths": ["career.txt"],
            "experience_refs": [
                {"experience_id": "exp_verify", "claim_fields": ["case_count"]}
            ],
            "research_refs": ["hug-jeonse-1"],
        }
    ]
    (run_dir / "draft_humanized.json").write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "draft.json").write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8"
    )
    official = [
        {
            "claim_id": "hug-jeonse-1",
            "claim": "전세보증금반환보증은 임차인의 보증금 반환 위험을 줄이는 공적 보증이다.",
            "source_url": "https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp",
            "checked_at": "2026-06-21",
            "evidence_excerpt": "전세보증금의 반환을 책임지는 보증상품",
            "source_type": "official",
            "published_at": "2026-06-01",
            "basis_date": "2026-06-21",
            "verification_status": "confirmed",
        }
    ]
    (run_dir / "04_공식근거.json").write_text(
        json.dumps(official, ensure_ascii=False), encoding="utf-8"
    )
    research_execution = {
        "policy": "evidence-first",
        "skill_name": "evidence-first-research",
        "mode": "ordinary-online",
        "searched_at": "2026-06-21T12:00:00+09:00",
        "status": "verified",
        "queries": ["HUG 전세보증금반환보증 공식"],
        "source_families": ["official"],
        "verified_claim_ids": ["hug-jeonse-1"],
    }
    (run_dir / "04_리서치실행.json").write_text(
        json.dumps(research_execution, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "04_기업직무조사.md").write_text(
        "[HUG 공식](https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp)",
        encoding="utf-8",
    )
    (run_dir / "08_면접대비팩.md").write_text(
        "# 면접대비팩\n"
        "1분 자기소개\n"
        "문항 1\n"
        "30초 답변\n"
        "60초 답변\n"
        "90초 답변\n"
        "꼬리질문\n"
        "압박질문\n"
        "평가 기준\n"
        "근거: 의심 사례 20건, HUG 공식 보증 사업\n",
        encoding="utf-8",
    )
    (run_dir / "09_copyeditor_report.json").write_text(
        json.dumps([{"question_index": 1, "status": "unchanged"}]),
        encoding="utf-8",
    )
    (run_dir / "09_patina_report.json").write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "selected_variant": "copyedited",
                    "ai_score_gate": "passed",
                    "patina_applied": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "draft_final.json").write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "06_자기소개서.md").write_text("# 자기소개서\n", encoding="utf-8")
    (run_dir / "06_자기소개서.docx").write_bytes(b"test docx artifact")
    state["final_artifact"] = write_final_artifact_manifest(
        run_dir,
        selected_source="draft",
        postprocess_attempted=False,
        postprocess_applied=False,
        model_tier=None,
        model_id=None,
        validation={"status": "passed", "issues": []},
    )
    (run_dir / "run.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )


def test_quality_audit_scores_submission_ready_run(tmp_path: Path):
    write_submission_ready_run(tmp_path)

    audit = run_quality_audit(tmp_path)

    assert audit["score"] >= 95
    assert audit["recommendation"] == "제출권장"
    assert (tmp_path / "11_최종품질감사.json").exists()
    assert (tmp_path / "11_최종품질감사.md").exists()


def test_audit_cli_returns_success_for_90_or_higher(tmp_path: Path):
    write_submission_ready_run(tmp_path)

    assert main(["audit", "--run", str(tmp_path)]) == 0


def test_legacy_audit_uses_its_fact_ledger_for_evidence_paths(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    state_path = tmp_path / "run.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["quality_mode"] = "legacy"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "02_확정경험원장.json").unlink()
    (tmp_path / "02_사실원장.json").write_text(
        json.dumps([{"source_path": "career.txt"}], ensure_ascii=False),
        encoding="utf-8",
    )

    audit = run_quality_audit(tmp_path)

    assert "unknown_evidence" not in {item["code"] for item in audit["issues"]}


def test_audit_ignores_stale_humanized_file_when_manifest_points_to_final(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    (tmp_path / "draft_humanized.json").write_text(
        json.dumps([{"question_index": 1, "answer": "오래된 중간 산출물"}], ensure_ascii=False),
        encoding="utf-8",
    )

    audit = run_quality_audit(tmp_path)

    assert "invalid_final_artifact" not in {item["code"] for item in audit["issues"]}
    assert audit["score"] >= 95


def test_audit_fails_when_final_manifest_sha_changes(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    (tmp_path / "draft_final.json").write_text("[]", encoding="utf-8")

    audit = run_quality_audit(tmp_path)

    assert "invalid_final_artifact" in {item["code"] for item in audit["issues"]}
    assert audit["quality_gate"] == "fail"


def test_audit_rejects_manifest_path_outside_run_directory(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    state_path = tmp_path / "run.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["final_artifact"]["markdown_path"] = str(tmp_path.parent / "outside.md")
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    audit = run_quality_audit(tmp_path)

    assert "invalid_final_artifact" in {item["code"] for item in audit["issues"]}
