import json
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.artifacts import write_final_artifact_manifest
from career_pipeline.audit import _responses_from_payload, run_quality_audit


HASH = "a" * 64


def test_audit_preserves_v2_claim_ids_from_final_payload():
    responses = _responses_from_payload([
        {
            "question_index": 1,
            "answer": "자료를 확인했습니다.",
            "evidence_paths": ["career.txt"],
            "experience_refs": [{
                "experience_id": "exp_1",
                "claim_fields": [],
                "claim_ids": ["clm_1"],
            }],
            "research_refs": [],
        }
    ])

    assert responses[0].experience_refs[0].claim_ids == ("clm_1",)


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
            "claim_type": "program_or_service",
            "application_use": "문항 1의 기관 역할 설명과 면접 근거",
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
        "# 기업·직무 조사\n\n"
        "## 확인된 사실\n\n"
        "- [HUG 공식](https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp)\n\n"
        "## 해석\n\n- 보증심사에서는 자료 확인과 고객 안내가 연결된다.\n\n"
        "## 확인 필요\n\n- 실제 배치 업무는 입사 전 확인한다.\n\n"
        "## 문항·면접 활용 맵\n\n- `hug-jeonse-1`: 문항 1과 면접 답변의 기관 역할 근거로 사용한다.\n",
        encoding="utf-8",
    )
    (run_dir / "08_면접대비팩.md").write_text(
        "# 면접대비팩\n\n"
        "## 1분 자기소개\n\n"
        "저는 자료의 기준과 출처를 먼저 확인하고 상대가 이해하기 쉽게 설명하는 사람입니다. 의심 사례를 접수한 뒤 계약서와 납부 내역을 대조해 오류 원인을 찾았고, 누락 기준을 표로 정리해 검토 흐름을 개선했습니다. HUG에서도 확인된 사실과 추정을 구분해 보증심사의 정확성과 고객 신뢰를 함께 높이겠습니다.\n\n"
        "## 문항 1 대응\n\n"
        "- 30초 답변: 의심 사례 20건의 계약서와 납부 내역을 대조해 오류 원인을 찾고, 누락 기준을 표로 정리해 검토 흐름을 개선했습니다.\n"
        "- 60초 답변: 의심 사례 20건을 접수한 뒤 계약서, 납부 내역, 민원 기록을 항목별로 대조했습니다. 오류 원인을 담당자와 확인하고 누락 기준을 표로 정리해 검토 흐름을 개선했습니다. HUG에서도 같은 방식으로 보증심사 자료의 위험 신호를 먼저 확인하겠습니다.\n"
        "- 90초 답변: 의심 사례 20건을 접수한 뒤 계약서, 납부 내역, 민원 기록을 항목별로 대조했습니다. 오류 원인을 담당자와 확인하고 누락 기준을 표로 정리해 검토 흐름을 개선했습니다. 확인된 사실과 추정을 구분해 기록하고 고객에게 필요한 서류와 다음 절차를 설명했습니다. HUG에서도 보증심사 자료의 위험 신호를 먼저 확인하고, 불일치는 근거와 함께 보고해 정확성과 고객 신뢰를 높이겠습니다.\n"
        "- 꼬리질문: 누락 기준을 어떤 순서로 정리했습니까?\n"
        "- 꼬리답변: 계약서와 납부 내역의 필수 항목을 먼저 정하고, 민원 기록에서 반복된 오류를 추가해 확인 순서를 만들었습니다.\n"
        "- 압박질문: 꼼꼼하게 확인하다가 처리 속도가 느려지면 어떻게 합니까?\n"
        "- 압박답변: 마감과 위험도를 기준으로 우선순위를 정하고, 판단이 필요한 불일치는 즉시 담당자에게 보고해 정확성과 속도를 함께 관리하겠습니다.\n"
        "- 평가 기준: 자료 확인의 구체성과 고객 설명의 명확성\n"
        "- 근거: exp_verify / hug-jeonse-1 / 의심 사례 20건 / HUG 공식 보증 사업\n",
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
    assert audit["recommendation"] == "내부검증 우수"
    assert (tmp_path / "11_최종품질감사.json").exists()
    assert (tmp_path / "11_최종품질감사.md").exists()


def test_audit_keeps_nonactionable_style_warning_without_score_penalty(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    (tmp_path / "09_style_diagnostics.json").write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "style_risk_score": 1,
                    "style_reasons": ["같은 종결 표현 3회 이상 반복"],
                    "should_rewrite": False,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit = run_quality_audit(tmp_path)

    assert audit["sections"]["style_safety"]["score"] == 15
    assert audit["sections"]["style_safety"]["style_warning_score"] == 1
    assert audit["sections"]["style_safety"]["actionable_style_items"] == 0
    assert "style_risk_detected" not in {item["code"] for item in audit["issues"]}


def test_audit_penalizes_actionable_style_risk(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    (tmp_path / "09_style_diagnostics.json").write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "style_risk_score": 3,
                    "style_reasons": ["같은 문장 시작 표현 반복"],
                    "should_rewrite": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit = run_quality_audit(tmp_path)

    assert audit["sections"]["style_safety"]["score"] < 15
    assert audit["sections"]["style_safety"]["actionable_style_items"] == 1
    assert "style_risk_detected" in {item["code"] for item in audit["issues"]}


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


def test_audit_flags_research_claim_missing_from_usage_map(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    (tmp_path / "04_기업직무조사.md").write_text(
        "# 조사\n\n[공식](https://www.khug.or.kr/official)",
        encoding="utf-8",
    )

    audit = run_quality_audit(tmp_path)
    codes = {item["code"] for item in audit["issues"]}

    assert "research_section_missing" in codes
    assert "research_claim_not_mapped" in codes


def test_audit_blocks_interview_pack_not_linked_to_answer_evidence_ids(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    path = tmp_path / "08_면접대비팩.md"
    text = path.read_text(encoding="utf-8").replace(
        "exp_verify / hug-jeonse-1 / ", ""
    )
    path.write_text(text, encoding="utf-8")

    audit = run_quality_audit(tmp_path)

    assert "interview_evidence_not_linked" in {
        item["code"] for item in audit["issues"]
    }
    assert audit["quality_gate"] == "fail"


def test_audit_flags_research_claim_mapped_to_wrong_question(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    path = tmp_path / "04_기업직무조사.md"
    text = path.read_text(encoding="utf-8").replace(
        "문항 1과 면접 답변", "문항 2와 면접 답변"
    )
    path.write_text(text, encoding="utf-8")

    audit = run_quality_audit(tmp_path)

    assert "research_claim_not_mapped_to_question" in {
        item["code"] for item in audit["issues"]
    }


def test_audit_accepts_grouped_and_range_question_mapping(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    path = tmp_path / "04_기업직무조사.md"
    original = path.read_text(encoding="utf-8")

    path.write_text(
        original.replace("문항 1과 면접 답변", "문항 1·2·3과 면접 답변"),
        encoding="utf-8",
    )
    grouped = run_quality_audit(tmp_path)
    assert "research_claim_not_mapped_to_question" not in {
        item["code"] for item in grouped["issues"]
    }

    path.write_text(
        original.replace("문항 1과 면접 답변", "문항 1-3과 면접 답변"),
        encoding="utf-8",
    )
    ranged = run_quality_audit(tmp_path)
    assert "research_claim_not_mapped_to_question" not in {
        item["code"] for item in ranged["issues"]
    }


def test_audit_requires_every_research_claim_in_company_research_document(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    evidence_path = tmp_path / "04_공식근거.json"
    claims = json.loads(evidence_path.read_text(encoding="utf-8"))
    claims.append(
        {
            "claim_id": "selection-1",
            "claim": "면접은 기본인성과 직무능력을 평가한다.",
            "source_url": "https://www.khug.or.kr/recruit",
            "checked_at": "2026-06-21",
            "evidence_excerpt": "기본인성 및 직무능력을 평가한다.",
            "source_type": "official_posting",
            "published_at": "2026-06-01",
            "basis_date": "2026-06-21",
            "verification_status": "verified",
            "claim_type": "selection_criteria",
            "application_use": "전체 문항과 면접 평가 기준에 활용",
        }
    )
    evidence_path.write_text(
        json.dumps(claims, ensure_ascii=False), encoding="utf-8"
    )
    execution_path = tmp_path / "04_리서치실행.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["verified_claim_ids"].append("selection-1")
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False), encoding="utf-8"
    )

    audit = run_quality_audit(tmp_path)

    assert "research_claim_not_documented" in {
        item["code"] for item in audit["issues"]
    }


def test_audit_links_official_selection_criteria_to_interview_pack(tmp_path: Path):
    write_submission_ready_run(tmp_path)
    evidence_path = tmp_path / "04_공식근거.json"
    claims = json.loads(evidence_path.read_text(encoding="utf-8"))
    claims.append(
        {
            "claim_id": "selection-1",
            "claim": "면접은 기본인성과 직무능력을 평가한다.",
            "source_url": "https://www.khug.or.kr/recruit",
            "checked_at": "2026-06-21",
            "evidence_excerpt": "기본인성 및 직무능력을 평가한다.",
            "source_type": "official_posting",
            "published_at": "2026-06-01",
            "basis_date": "2026-06-21",
            "verification_status": "verified",
            "claim_type": "selection_criteria",
            "application_use": "전체 문항과 면접 평가 기준에 활용",
        }
    )
    evidence_path.write_text(
        json.dumps(claims, ensure_ascii=False), encoding="utf-8"
    )
    execution_path = tmp_path / "04_리서치실행.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["verified_claim_ids"].append("selection-1")
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False), encoding="utf-8"
    )
    research_path = tmp_path / "04_기업직무조사.md"
    research_path.write_text(
        research_path.read_text(encoding="utf-8")
        + "\n- 전체 문항·면접 / `selection-1`: 기본인성·직무능력 평가\n",
        encoding="utf-8",
    )

    audit = run_quality_audit(tmp_path)

    assert "interview_selection_criteria_not_linked" in {
        item["code"] for item in audit["issues"]
    }
