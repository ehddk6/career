from __future__ import annotations

import json
import shutil
from pathlib import Path

from career_pipeline.audit import run_quality_audit
from career_pipeline.orchestrator import finalize_run
from career_pipeline.writing_guidance import attach_writing_guidance


HASH = "a" * 64


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_run(workspace: Path, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    answer = (
        "HUG 금융·기금 직무에서 보증심사 자료 검토는 고객 신뢰와 공공성을 함께 지키는 일이라고 생각합니다. "
        "특히 전세보증금반환보증은 임차인의 보증금 반환 위험을 줄이는 공적 보증이므로, 서류 한 줄의 누락도 고객 불안과 기관 신뢰에 영향을 줄 수 있습니다. "
        "저는 의심 사례 20건을 접수한 뒤 계약서, 납부 내역, 민원 기록을 항목별로 대조하고 오류 원인을 담당자와 확인했습니다. "
        "그 결과 누락 기준을 표로 정리해 검토 흐름을 개선했고, 이후 비슷한 자료를 볼 때도 먼저 기준과 증빙을 나누어 확인했습니다. "
        "이 경험을 바탕으로 HUG에서도 보증 관련 서류를 검토할 때 사실과 추정을 구분하고, 고객에게 필요한 보완 서류와 다음 절차를 쉬운 표현으로 안내하겠습니다. "
        "또한 반복되는 보완 사유는 유형별로 정리해 동료와 공유하고, 심사 과정에서 놓치기 쉬운 항목을 미리 확인하겠습니다. "
        "처리 과정에서는 고객에게 불리하거나 유리한 방향으로 임의 판단하지 않고, 공식 기준과 제출 자료를 대조한 뒤 확인한 내용만 기록하겠습니다. "
        "업무가 몰릴 때도 검토 기준, 보완 사유, 안내 내용을 분리해 남기면 다음 담당자가 같은 자료를 다시 찾는 시간을 줄일 수 있습니다. "
        "빠른 처리보다 다시 확인 가능한 기록을 남기는 태도로 보증 업무의 정확성과 고객 신뢰를 함께 높이겠습니다."
    )
    state = {
        "status": "ready_for_research",
        "quality_mode": "v2",
        "strict_quality": True,
        "root": str(workspace),
        "target": "HUG 금융·기금",
        "official_research_domains": ["khug.or.kr"],
        "questions": [
            {
                "index": 1,
                "prompt": "HUG 주요 사업과 보증심사 업무 기여 방안",
                "character_limit": 800,
            }
        ],
        "selected_experience_ids": ["exp_verify"],
        "posting_snapshot_id": "c" * 64,
        "research_policy": "evidence-first",
        "required_research_skill": "evidence-first-research",
    }
    attach_writing_guidance(workspace, run_dir, state)
    write_json(run_dir / "run.json", state)

    ledger = {
        "schema_version": 1,
        "generated_at": "2026-07-05T11:00:00+09:00",
        "workspace_root": str(workspace),
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
                "confirmed_at": "2026-07-05T11:00:00+09:00",
            }
        ],
    }
    write_json(run_dir / "02_확정경험원장.json", ledger)
    write_json(
        run_dir / "00_채용공고분석.json",
        {
            "organization": "HUG",
            "role": "금융·기금",
            "duties": ["보증심사 자료 검토", "민원 기록 확인"],
            "competencies": ["정확성", "고객 소통"],
            "source": {"official_status": "user_attested"},
        },
    )
    write_json(run_dir / "03_경험직무매칭.json", [])
    (run_dir / "03_경험직무매칭.md").write_text("# 경험직무매칭\n", encoding="utf-8")
    (run_dir / "04_기업직무조사.md").write_text(
        "[HUG 공식](https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp)\n",
        encoding="utf-8",
    )
    (run_dir / "05_문항전략.md").write_text(
        "# 문항전략\n\n- 확정 경험 exp_verify와 공식 HUG 근거만 사용합니다.\n",
        encoding="utf-8",
    )
    official = [
        {
            "claim_id": "hug-jeonse-1",
            "claim": "전세보증금반환보증은 임차인의 보증금 반환 위험을 줄이는 공적 보증이다.",
            "source_url": "https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp",
            "checked_at": "2026-07-05",
            "evidence_excerpt": "전세보증금의 반환을 책임지는 보증상품",
            "source_type": "official",
            "published_at": "2026-06-01",
            "basis_date": "2026-07-05",
            "verification_status": "confirmed",
        }
    ]
    write_json(run_dir / "04_공식근거.json", official)
    write_json(
        run_dir / "04_리서치실행.json",
        {
            "policy": "evidence-first",
            "skill_name": "evidence-first-research",
            "mode": "ordinary-online",
            "searched_at": "2026-07-05T11:00:00+09:00",
            "status": "verified",
            "queries": ["HUG 전세보증금반환보증 공식"],
            "source_families": ["official"],
            "verified_claim_ids": ["hug-jeonse-1"],
        },
    )
    write_json(
        run_dir / "draft.json",
        [
            {
                "question_index": 1,
                "answer": answer,
                "evidence_paths": ["career.txt"],
                "experience_refs": [
                    {"experience_id": "exp_verify", "claim_fields": ["case_count"]}
                ],
                "research_refs": ["hug-jeonse-1"],
            }
        ],
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
        "근거: 의심 사례 20건, HUG 공식 보증 사업\n"
        f"{answer}\n",
        encoding="utf-8",
    )


def main() -> None:
    workspace = Path(__file__).resolve().parents[1]
    base = Path("C:/tmp/career-pipeline-goal-verification-utf8")
    if base.exists():
        shutil.rmtree(base)
    run_dir = base / "run"
    build_run(workspace, run_dir)
    final = finalize_run(
        run_dir,
        copyedit=True,
        humanize=True,
        copyeditor_timeout_ms=45_000,
        patina_timeout_ms=120_000,
        patina_max_retries=1,
    )
    audit = run_quality_audit(run_dir)
    required_artifacts = [
        "05_작성가이드_유튜브프레임.md",
        "06_자기소개서.md",
        "06_자기소개서.docx",
        "07_자기소개서_검토보고서.md",
        "08_면접대비팩.md",
        "09_copyeditor_report.json",
        "09_patina_report.json",
        "10_품질점수.json",
        "11_최종품질감사.json",
        "11_최종품질감사.md",
        "run.json",
    ]
    summary = {
        "run_dir": str(run_dir),
        "final_status": final.get("status"),
        "required_artifacts": {
            name: (run_dir / name).exists() for name in required_artifacts
        },
        "writing_guidance": final.get("writing_guidance"),
        "copyeditor_attempted": final.get("copyeditor_attempted"),
        "copyeditor_status": final.get("copyeditor_status"),
        "copyeditor_applied": final.get("copyeditor_applied"),
        "patina_score_attempted": final.get("patina_score_attempted"),
        "patina_attempted": final.get("patina_attempted"),
        "patina_status": final.get("patina_status"),
        "patina_applied": final.get("patina_applied"),
        "patina_summary": final.get("patina_summary"),
        "audit_score": audit.get("score"),
        "audit_recommendation": audit.get("recommendation"),
        "audit_sections": audit.get("sections"),
        "audit_issues": audit.get("issues"),
    }
    write_json(base / "verification_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
