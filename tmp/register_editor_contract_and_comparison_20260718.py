from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "career_pipeline/writing_editor_prompt.md"
sha = hashlib.sha256(PROMPT.read_bytes()).hexdigest()
RUNS = [
    ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610",
    ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609",
    ROOT / "career_runs/kinfa-2026-youth-intern-youtube-guidance-20260717-20260717-120439-677326",
    ROOT / "career_runs/kodit-experience-block-superior-20260717-20260717-002217-485456",
]

for run in RUNS:
    contract = {
        "schema_version": 1,
        "contract_type": "project_writing_editor",
        "source": "career_pipeline/writing_editor_prompt.md",
        "source_sha256": sha,
        "status": "registered",
        "default_strength": "standard",
        "applied_by": "career_pipeline.copyeditor_adapter._editor_contract",
        "evidence_boundary": "editing_policy_only; never research_refs or experience_refs",
        "preserved_fields": [
            "numbers", "dates", "periods", "roles", "achievements", "organization_names",
            "job_titles", "proper_nouns", "quotations", "polarity", "causality", "sentence_order",
        ],
    }
    (run / "10_글쓰기편집계약.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_path = run / "run.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["writing_editor_contract"] = contract
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

report = ROOT / "career_runs/comparison_external_vs_career_pipeline_20260718.md"
report.write_text(f"""# 외부 자기소개서와 Career Pipeline 비교

## 비교 범위

비교 대상은 사용자가 제공한 `클로드가 쓴 2위.docx`, `키미가 쓴 자소서.docx`, `조합_최종_주금공.docx`, `최종 지피티 주금공.docx`, `제미나이 최종 주금공.docx`, `제미나이가 수정한 서민금융진흥원.docx`, `제미나이가 수정한 신용보증기금.docx`, `클로드본 지피티 결합 1위.docx`, `지피티가 최종 판단한 자소서.docx`와 Career Pipeline의 주택금융공사·용산구시설관리공단·서민금융진흥원 run이다.

## 확인된 장점

- 외부 문서의 강점은 제목형 소제목, 짧은 결론 문장, 장면 중심 서술, 기관별 지원동기와 기여 계획을 빠르게 읽히게 만든 점이다.
- `지피티가 최종 판단한 자소서.docx`는 기관별 문항을 한 문서에 묶고, KINFA·신용보증기금·주택금융공사의 직무 연결을 선명하게 배치했다.
- `클로드가 쓴 2위.docx`와 `클로드본 지피티 결합 1위.docx`는 제목과 장면 전환이 자연스럽고, 고객 안내·갈등 조정 장면의 읽기성이 좋다.
- Kimi·Gemini 문서는 문항 원문과 소제목을 함께 보여 주어 편집자가 문항 누락을 확인하기 쉽다.

## Career Pipeline이 유지한 기준

- 사용자가 승인한 경험 원장의 confirmed claim만 최종 답변 근거로 사용했다.
- 기관 사실은 공식 조사 claim으로만 연결하고, 유튜브·글쓰기 편집 자료는 전략으로만 추적했다.
- 외부 문서에 등장하는 `20건`, `1주일 단축`, `90세`, `50명`, `5곳`, `150명→180명` 등은 현재 승인 원장에서 `needs_verification`인 수치가 섞여 있어 최종 답변에 자동 이식하지 않았다.
- 주택금융공사·용산구시설관리공단·서민금융진흥원 최종본은 문항 제한, 면접 방어, claim 추적과 문서 manifest까지 검증했다.
- 용산구시설관리공단은 제공된 외부 문서에 동일 직무 비교본이 없어 Career Pipeline 최종본을 독립 기준으로 평가했다.

## 결론

외부 문서의 제목·장면·문장 리듬은 참고할 수 있지만, 사실·수치·성과를 그대로 결합하지 않는다. 앞으로의 편집은 새 공통 계약 `career_pipeline/writing_editor_prompt.md`를 사용한다. 이 계약은 저자의 목소리와 의미를 보존하고, 필수·권장·선택 수정을 구분하며, 승인 경험과 공식 근거 밖의 사실을 추가하지 않도록 `copyeditor_adapter`의 단일·배치 교열 프롬프트에 연결되어 있다.

프롬프트 계약 SHA-256: `{sha}`
""", encoding="utf-8")
print(report)
print(sha)
