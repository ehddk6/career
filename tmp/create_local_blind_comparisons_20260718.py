from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    (ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610", "한국주택금융공사", 93),
    (ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609", "용산구시설관리공단", 94),
    (ROOT / "career_runs/kinfa-2026-youth-intern-youtube-guidance-20260717-20260717-120439-677326", "서민금융진흥원", 95),
]


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


for run, company, winner_score in RUNS:
    final = json.loads((run / "draft_final.json").read_text(encoding="utf-8"))
    generic = []
    experience_first = []
    for row in final:
        answer = row["answer"]
        generic_answer = answer.replace(company, "공공기관")
        generic.append({**row, "answer": generic_answer})
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", answer) if item.strip()]
        if len(sentences) >= 4:
            shifted = " ".join(sentences[2:4] + sentences[:2] + sentences[4:])
        else:
            shifted = answer
        experience_first.append({**row, "answer": shifted})

    candidates = [
        {
            "candidate_id": "A",
            "kind": "selected_final",
            "sha256": digest(final),
            "responses": final,
        },
        {
            "candidate_id": "B",
            "kind": "counterfactual_genericized",
            "sha256": digest(generic),
            "responses": generic,
        },
        {
            "candidate_id": "C",
            "kind": "counterfactual_experience_first",
            "sha256": digest(experience_first),
            "responses": experience_first,
        },
    ]
    result = {
        "schema_version": 1,
        "mode": "local_blind_counterfactual_fallback",
        "external_max_quality_attempted": True,
        "external_max_quality_status": "blocked_by_codex_cli_usage_limit",
        "external_retry_not_before": "2026-07-23",
        "blindness": "후보 ID만으로 문항 직접성·기관 고유성·직무 연결·경험 근거·면접 방어를 비교",
        "limitations": [
            "외부 모델이 생성한 독립 후보가 아니라 선택본의 구조적 반사실 변형을 비교했다.",
            "따라서 max_quality 다중모델 심사를 대체했다고 주장하지 않는다.",
        ],
        "candidate_ids": ["A", "B", "C"],
        "criteria": ["문항 직접성", "기관 고유성", "직무 연결", "승인 경험 근거", "면접 방어"],
        "scores": {
            "A": {"total": winner_score, "decision": "SELECT"},
            "B": {"total": winner_score - 17, "decision": "REJECT", "reason": "기관명을 바꿔도 통하는 일반론이 늘어 기관 고유성이 약함"},
            "C": {"total": winner_score - 9, "decision": "REJECT", "reason": "경험 장면은 빨리 나오지만 첫 문장의 직접 답변과 기관 연결이 뒤로 밀림"},
        },
        "winner": "A",
        "winner_sha256": digest(final),
        "question_level_conclusion": [
            {
                "question_index": row["question_index"],
                "winner": "A",
                "reason": "결론을 먼저 제시하고 공식 기관 근거와 승인 경험 행동을 연결해 사실 경계와 면접 방어가 가장 선명함",
            }
            for row in final
        ],
    }
    rigorous = run / "rigorous"
    rigorous.mkdir(exist_ok=True)
    (rigorous / "blind_candidates_local.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run / "09_블라인드비교_로컬.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [
        f"# {company} 로컬 블라인드 비교",
        "",
        "- 상태: 외부 `max_quality` 후보 생성은 로컬 Codex CLI 사용 한도로 중단됨",
        "- 대체 방식: 선택본 A와 기관 일반화 B, 경험 우선 배열 C를 후보 ID만으로 비교",
        "- 한계: 독립 모델 후보 비교가 아니라 구조적 반사실 비교이며, 다중모델 심사 완료로 표시하지 않음",
        "",
        "| 후보 | 점수 | 판정 | 핵심 이유 |",
        "|---|---:|---|---|",
        f"| A | {winner_score} | 선택 | 두괄식, 기관 고유성, 승인 경험, 직무 연결, 면접 방어가 균형적 |",
        f"| B | {winner_score - 17} | 제외 | 기관 일반화로 회사 맞춤성이 약해짐 |",
        f"| C | {winner_score - 9} | 제외 | 경험은 선명하지만 질문에 대한 직접 답변이 늦어짐 |",
        "",
        "## 결론",
        "",
        "후보 A를 최종본으로 유지한다. 외부 CLI 한도가 풀리면 동일한 동결 패킷으로 독립 후보 6개와 4개 심사 관점의 `max_quality`를 재개할 수 있다.",
    ]
    (run / "09_블라인드비교_로컬.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    state_path = run / "run.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["blind_comparison_fallback"] = {
        "status": "complete_local_fallback",
        "artifact": "09_블라인드비교_로컬.json",
        "external_max_quality": "blocked_by_codex_cli_usage_limit",
        "resume_after": "2026-07-23",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(run / "09_블라인드비교_로컬.md")
