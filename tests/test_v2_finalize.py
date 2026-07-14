import json
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.orchestrator import _load_draft_responses, finalize_run


def test_load_draft_responses_preserves_exact_claim_ids(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "answer": "답변",
                    "evidence_paths": ["career.txt"],
                    "experience_refs": [
                        {
                            "experience_id": "exp-1",
                            "claim_ids": ["claim-1"],
                        }
                    ],
                    "research_refs": [],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    responses, issues = _load_draft_responses(draft_path)

    assert issues == []
    assert responses[0].experience_refs[0].claim_ids == ("claim-1",)
    assert responses[0].experience_refs[0].claim_fields == ()


def prepare_v2_run(run_dir: Path, *, answer: str = "의심 사례 20건을 확인했습니다.") -> None:
    run_dir.mkdir(exist_ok=True)
    state = {
        "status": "ready_for_research",
        "quality_mode": "v2",
        "target": "HUG",
        "questions": [{"index": 1, "prompt": "성과", "character_limit": 600}],
        "selected_experience_ids": ["exp_verify"],
        "posting_snapshot_id": "c" * 64,
    }
    (run_dir / "run.json").write_text(json.dumps(state), encoding="utf-8")
    ledger = {
        "schema_version": 1,
        "generated_at": "2026-06-21T12:00:00+09:00",
        "workspace_root": "C:/career",
        "experiences": [
            {
                "experience_id": "exp_verify",
                "title": "검증 경험",
                "organization_alias": "기관",
                "period": None,
                "role": "자료 검증",
                "situation": "의심 사례 확인",
                "actions": ["자료 교차 확인"],
                "outcomes": ["20건 확인"],
                "competencies": ["정확성"],
                "claims": [
                    {
                        "field": "case_count",
                        "normalized_value": "20건",
                        "status": "confirmed",
                        "evidence": [
                            {
                                "source_path": "career.txt",
                                "paragraph_index": 0,
                                "source_sha256": "a" * 64,
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
    (run_dir / "00_채용공고분석.json").write_text(
        json.dumps(
            {
                "source": {"official_status": "user_attested"},
                "duties": ["보증심사 자료 검토"],
                "competencies": ["정확성"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "03_경험직무매칭.json").write_text("[]", encoding="utf-8")
    (run_dir / "04_기업직무조사.md").write_text(
        "[공식](https://www.khug.or.kr)", encoding="utf-8"
    )
    (run_dir / "05_문항전략.md").write_text("# 전략", encoding="utf-8")
    (run_dir / "08_면접대비팩.md").write_text(
        "# 면접\n"
        "1분 자기소개\n"
        "문항 1\n"
        "30초 답변\n"
        "60초 답변\n"
        "90초 답변\n"
        "꼬리질문\n"
        "압박질문\n"
        "평가 기준\n"
        "근거\n"
        "의심 사례 20건을 확인했습니다.",
        encoding="utf-8",
    )
    (run_dir / "draft.json").write_text(
        json.dumps(
            [
                {
                    "question_index": 1,
                    "answer": answer,
                    "evidence_paths": ["career.txt"],
                    "experience_refs": [
                        {
                            "experience_id": "exp_verify",
                            "claim_fields": ["case_count"],
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_v2_finalize_writes_quality_gate_report(tmp_path: Path):
    prepare_v2_run(tmp_path)

    state = finalize_run(tmp_path)

    assert state["status"] == "complete"
    report = (tmp_path / "07_자기소개서_검토보고서.md").read_text(encoding="utf-8")
    assert "- 경험 원장: 통과" in report
    assert "- 공고 공식성: 통과" in report
    assert "- 경험·문항 매칭: 통과" in report
    assert "- stale 근거: 없음" in report
    assert "경험 근거 1개, 공식 근거 0개" in report


def test_v2_finalize_uses_patina_when_requested(tmp_path: Path, monkeypatch):
    prepare_v2_run(tmp_path)

    def fake_candidates(responses, questions, target_org, **kwargs):
        rewritten = [
            type(response)(
                response.question_index,
                "의심 사례 20건을 직접 확인해 정확도를 높였습니다.",
                response.evidence_paths,
                response.experience_refs,
                response.research_refs,
            )
            for response in responses
        ]
        score = {"total": 90}
        return rewritten, [
            {
                "question_index": 1,
                "selected_variant": "formal",
                "selected_score": score,
                "candidates": [
                    {"variant": "original", "status": "original", "score": score},
                    {"variant": "formal", "status": "humanized", "score": score},
                    {"variant": "narrative", "status": "humanized", "score": score},
                ],
            }
        ]

    monkeypatch.setattr(
        "career_pipeline.orchestrator.generate_and_select_candidates",
        fake_candidates,
    )

    state = finalize_run(tmp_path, humanize=True)

    assert state["status"] == "complete"
    assert state["patina_status"] == "humanized"
    assert state["patina_attempted"] is True
    assert state["patina_applied"] is True
    assert state["patina_summary"]["applied_questions"] == 1
    report = json.loads((tmp_path / "09_patina_report.json").read_text(encoding="utf-8"))
    assert report[0]["selected_variant"] == "formal"
    assert len(report[0]["candidates"]) == 3
    assert (tmp_path / "09_초안후보평가.json").exists()
    assert (tmp_path / "10_품질점수.json").exists()
    final_markdown = (tmp_path / "06_자기소개서.md").read_text(encoding="utf-8")
    assert "의심 사례 20건을 직접 확인해 정확도를 높였습니다." in final_markdown


def test_v2_finalize_runs_copyeditor_before_patina_stage(tmp_path: Path, monkeypatch):
    prepare_v2_run(tmp_path)

    def fake_copyedit(responses, **kwargs):
        edited = [
            type(response)(
                response.question_index,
                "의심 사례 20건을 확인했습니다.",
                response.evidence_paths,
                response.experience_refs,
                response.research_refs,
            )
            for response in responses
        ]
        return edited, [
            {
                "question_index": 1,
                "status": "copyedited",
                "message": "",
                "applied_rules": ["S-1"],
                "change_ratio": 0.1,
            }
        ]

    monkeypatch.setattr(
        "career_pipeline.orchestrator.copyedit_responses",
        fake_copyedit,
    )

    state = finalize_run(tmp_path, copyedit=True, humanize=False)

    assert state["status"] == "complete"
    assert state["copyeditor_attempted"] is True
    assert state["copyeditor_applied"] is True
    assert (tmp_path / "09_copyeditor_report.json").exists()
    assert (tmp_path / "draft_copyedited.json").exists()


def test_finalize_disabled_copyeditor_overwrites_stale_report(tmp_path: Path):
    prepare_v2_run(tmp_path)
    (tmp_path / "09_copyeditor_report.json").write_text(
        json.dumps([{"status": "fallback_backend_error"}]), encoding="utf-8"
    )

    state = finalize_run(tmp_path, copyedit=False, humanize=False)

    report = json.loads((tmp_path / "09_copyeditor_report.json").read_text(encoding="utf-8"))
    assert state["copyeditor_status"] == "disabled"
    assert all(item["status"] == "disabled" for item in report)


def test_v2_finalize_blocks_unapproved_metric_without_writing_document(tmp_path: Path):
    prepare_v2_run(tmp_path, answer="의심 사례 30건을 확인했습니다.")

    state = finalize_run(tmp_path)

    assert state["status"] == "blocked_validation"
    assert state["blocked_stage"] == "finalize"
    assert "unapproved_metric" in {item["code"] for item in state["validation_issues"]}
    assert not (tmp_path / "06_자기소개서.docx").exists()
    assert (tmp_path / "07_자기소개서_검토보고서.md").exists()
    assert main(["finalize", "--run", str(tmp_path)]) == 2


def test_v2_finalize_blocks_malformed_draft_json_with_a_recovery_report(tmp_path: Path):
    prepare_v2_run(tmp_path)
    (tmp_path / "draft.json").write_text("{not valid json", encoding="utf-8")

    state = finalize_run(tmp_path)

    assert state["status"] == "blocked_validation"
    assert state["blocked_stage"] == "finalize"
    assert "invalid_draft_json" in {
        item["code"] for item in state["validation_issues"]
    }
    assert (tmp_path / "07_자기소개서_검토보고서.md").exists()
    assert not (tmp_path / "06_자기소개서.docx").exists()


def test_strict_v2_finalize_accepts_scored_answer_with_official_research_link(tmp_path: Path):
    prepare_v2_run(tmp_path)
    state = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    state["strict_quality"] = True
    state["official_research_domains"] = ["khug.or.kr"]
    state["questions"] = [
        {
            "index": 1,
            "prompt": "HUG 주요 사업과 인턴 기여 방안",
            "character_limit": 600,
        }
    ]
    (tmp_path / "run.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    sentence = (
        "HUG의 전세보증 사업은 임차인의 보증금 반환 위험을 줄인다는 점에서 중요합니다. "
        "저는 의심 사례 20건의 자료를 항목별로 대조하고 담당자와 오류 원인을 확인했습니다. "
        "그 결과 검토 기준을 정리해 누락을 줄였으며, 인턴 과정에서도 보증심사 자료를 정확히 검토하겠습니다. "
    )
    answer = (sentence * 4)[:590]
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
    (tmp_path / "draft.json").write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8"
    )
    official = [
        {
            "claim_id": "hug-jeonse-1",
            "claim": "전세보증금반환보증은 임차인의 보증금 반환을 보호한다.",
            "source_url": "https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp",
            "checked_at": "2026-06-21",
            "evidence_excerpt": "전세보증금의 반환을 책임지는 보증상품",
        }
    ]
    (tmp_path / "04_공식근거.json").write_text(
        json.dumps(official, ensure_ascii=False), encoding="utf-8"
    )

    final = finalize_run(tmp_path)

    assert final["status"] == "complete"
    scores = json.loads((tmp_path / "10_품질점수.json").read_text(encoding="utf-8"))
    assert scores[0]["score"]["total"] >= 65


def test_strict_v2_finalize_blocks_invalid_official_evidence_json(tmp_path: Path):
    prepare_v2_run(tmp_path)
    state = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    state["strict_quality"] = True
    state["official_research_domains"] = ["khug.or.kr"]
    (tmp_path / "run.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "04_공식근거.json").write_text("{}", encoding="utf-8")

    final = finalize_run(tmp_path)

    assert final["status"] == "blocked_validation"
    assert "invalid_research_evidence" in {
        item["code"] for item in final["validation_issues"]
    }


def test_finalize_blocks_pending_evidence_first_research_manifest(tmp_path: Path):
    prepare_v2_run(tmp_path)
    state = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    state["research_policy"] = "evidence-first"
    state["research_method_default"] = "evidence-first-research"
    state["research_method_enforced"] = False
    (tmp_path / "run.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "policy": "evidence-first",
        "skill_name": "evidence-first-research",
        "mode": "ordinary-online",
        "searched_at": "",
        "status": "pending",
        "queries": [],
        "source_families": [],
        "verified_claim_ids": [],
    }
    (tmp_path / "04_리서치실행.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    final = finalize_run(tmp_path)

    assert final["status"] == "blocked_validation"
    assert {
        "invalid_research_status",
        "invalid_research_timestamp",
        "missing_research_queries",
        "missing_research_source_families",
    }.issubset({item["code"] for item in final["validation_issues"]})
