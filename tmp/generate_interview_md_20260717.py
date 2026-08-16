from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    (
        ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610",
        "한국주택금융공사",
        "hf-selection-criteria-20260717",
    ),
    (
        ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609",
        "용산구시설관리공단",
        "yongsan-selection-criteria-20260717",
    ),
    (
        ROOT / "career_runs/kinfa-2026-youth-intern-youtube-guidance-20260717-20260717-120439-677326",
        "서민금융진흥원",
        "kinfa-selection-criteria-20260717",
    ),
]


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]+\]", "", text)).strip()


def cut(text: str, size: int) -> str:
    text = compact(text)
    if len(text) <= size:
        return text
    part = text[:size]
    stop = max(part.rfind("."), part.rfind("다."), part.rfind("니다."))
    return part[: stop + 1] if stop > size // 2 else part.rstrip() + "…"


for run, company, selection_id in RUNS:
    draft = json.loads((run / "draft.json").read_text(encoding="utf-8"))
    first = compact(draft[0]["answer"])
    lines = [
        f"# {company} 면접 대비팩",
        "",
        "## 1분 자기소개",
        "",
        cut(first, 360),
        "",
        "## 평가 기준",
        "",
        f"- 공식 전형 기준: `{selection_id}`",
        "- 모든 답변은 승인 경험 원장의 confirmed claim과 공식 기관 근거 범위에서만 말한다.",
        "- 최종 판단·승인 권한을 주장하지 않고 확인·기록·보고·안내 행동으로 답한다.",
    ]
    for row in draft:
        i = row["question_index"]
        answer = compact(row["answer"])
        refs = ", ".join(
            claim
            for ref in row.get("experience_refs", [])
            for claim in ref.get("claim_ids", [])
        )
        research = ", ".join(row.get("research_refs", [])) or "공식 근거 직접 인용 없음"
        lines.extend([
            "",
            f"## 문항 {i}",
            "",
            f"30초 답변: {cut(answer, 160)}",
            "",
            f"60초 답변: {cut(answer, 300)}",
            "",
            f"90초 답변: {cut(answer, 470)}",
            "",
            "꼬리질문: 이 경험에서 본인이 직접 한 행동은 무엇이며, 같은 상황이 다시 생기면 무엇을 먼저 확인하겠습니까?",
            "",
            f"꼬리답변: 직접 행동은 원장 claim `{refs}` 범위의 확인·대조·설명·제안·기록입니다. 다시 한다면 적용 기준과 원자료를 먼저 확인하고, 예외는 담당자에게 근거와 함께 보고하겠습니다.",
            "",
            "압박질문: 결과를 과장한 것 아닙니까? 입사 후 실제로 그 업무를 할 수 있다고 장담합니까?",
            "",
            "압박답변: 팀의 최종 결과와 제 직접 행동을 구분하겠습니다. 확인된 행동과 변화만 말하고 승인되지 않은 수치는 사용하지 않습니다. 배치업무를 단정하지 않고 공식 직무 범위에서 자료 확인·기록·보고와 고객 안내부터 정확히 수행하겠습니다.",
            "",
            "근거: " + ", ".join(
                [f"`{ref['experience_id']}`" for ref in row.get("experience_refs", [])]
                + [f"`{item}`" for item in row.get("research_refs", [])]
                + [f"`{refs}`"]
            ),
        ])
    lines.extend([
        "",
        "## 공통 방어 원칙",
        "",
        "- 모르는 사실은 추정하지 않고 확인한 공식 자료의 범위를 먼저 밝힌다.",
        "- 수치의 산식·기준일·개인 기여 범위가 확인되지 않으면 숫자로 단정하지 않는다.",
        "- 고객정보와 문서의 불일치는 원자료 위치, 확인한 사실, 남은 확인 사항으로 나누어 보고한다.",
    ])
    (run / "08_면접대비팩.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(run / "08_면접대비팩.md")
