from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from career_pipeline.models import DraftResponse, Question
from career_pipeline.quality import (
    STRICT_MIN_ANSWER_SCORE,
    STRICT_MIN_AVERAGE_SCORE,
    score_answer_quality,
    validate_answer_quality,
)


ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "submission_ready_drafts"
OUT_JSON = ROOT / "submission_ready_re_evaluation_20260705.json"
OUT_CSV = ROOT / "submission_ready_re_evaluation_20260705.csv"
OUT_MD = ROOT / "submission_ready_re_evaluation_20260705.md"


ORG_HINTS = [
    ("NH농협은행", ("NH농협은행", "농협은행")),
    ("지역농협", ("지역농협", "농축협", "농·축협", "지농")),
    ("국민연금공단", ("국민연금공단", "NPS")),
    ("국민건강보험공단", ("국민건강보험공단", "건보", "h·well")),
    ("건강보험심사평가원", ("건강보험심사평가원", "HIRA", "심사평가원")),
    ("한국주택금융공사", ("한국주택금융공사", "HF")),
    ("주택도시보증공사", ("주택도시보증공사", "HUG")),
    ("IBK기업은행", ("IBK기업은행", "기업은행")),
    ("신한은행", ("신한은행",)),
    ("우리은행", ("우리은행",)),
    ("하나은행", ("하나은행",)),
    ("하나저축은행", ("하나저축은행",)),
    ("서울교통공사", ("서울교통공사", "Seoul Metro", "서교공", "매트로")),
    ("한국도로공사서비스", ("한국도로공사서비스",)),
    ("사회보장정보원", ("사회보장정보원", "ssis", "서시서")),
    ("신용보증기금", ("신용보증기금", "KODIT")),
    ("신용보증재단중앙회", ("신용보증재단중앙회", "KOREG")),
    ("한국공정거래조정원", ("공정거래조정원", "KOFAIR")),
    ("서울특별시농수산식품공사", ("서울특별시농수산식품공사", "SAFFC")),
    ("흥국생명", ("흥국생명",)),
    ("해양박물관", ("해양박물관",)),
]

JOB_TERMS = {
    "NH농협은행": ("고객 상담", "금융상품 설명", "서류 검토", "창구 업무", "신뢰"),
    "지역농협": ("조합원", "지역 고객", "창구 업무", "서류 검토", "생활금융"),
    "국민연금공단": ("제도 안내", "민원 응대", "자료 검토", "행정 처리", "공공성"),
    "국민건강보험공단": ("제도 안내", "민원 응대", "공정성", "행정 처리", "기록 정확성"),
    "건강보험심사평가원": ("심사", "평가", "자료 검토", "기록 정확성", "공정성"),
    "한국주택금융공사": ("주택금융", "상담", "서류 검토", "공공성", "고객 설명"),
    "주택도시보증공사": ("보증", "심사", "리스크", "서류 검토", "주거 안정"),
    "IBK기업은행": ("중소기업", "금융", "고객 상담", "서류 검토", "여신"),
    "신한은행": ("고객 신뢰", "금융소비자 보호", "상담", "내부통제", "서류"),
    "우리은행": ("지역 고객", "상담", "금융서비스", "책임", "서류"),
    "하나은행": ("손님", "상담", "금융상품", "확인 절차", "서류"),
    "하나저축은행": ("서민금융", "기업금융", "서류 검토", "리스크", "상담"),
    "서울교통공사": ("시민 안전", "고객 응대", "현장 규정", "상황 대응", "서비스"),
    "한국도로공사서비스": ("고객 안내", "민원 응대", "서비스 품질", "안전", "현장"),
    "사회보장정보원": ("복지", "정보시스템", "데이터 정확성", "사용자 안내", "공공"),
    "신용보증기금": ("중소기업", "보증", "정책금융", "심사", "리스크"),
    "신용보증재단중앙회": ("소상공인", "보증", "지역", "자료 검토", "재단"),
    "한국공정거래조정원": ("분쟁조정", "공정", "자료 검토", "당사자", "설명"),
    "서울특별시농수산식품공사": ("유통", "행정", "현장", "민원", "공공"),
    "흥국생명": ("보험", "고객", "상품 설명", "영업기획", "자료"),
    "해양박물관": ("관람객 안내", "전시 운영", "교육", "자료 정리", "안전"),
    "지원기관": ("고객 안내", "자료 검토", "행정 처리", "민원 응대", "정확성"),
}

RISK_TERMS = (
    "허위",
    "적발",
    "1억",
    "사상 최대",
    "사상 처음",
    "최초",
    "전년 대비",
    "은행장",
    "사장",
    "경영진",
    "급증",
    "4,000",
    "3만",
    "0건",
    "반려율",
    "누수",
)

ISSUE_LABELS = {
    "missing_target": "기관명이 답변에 직접 드러나지 않음",
    "missing_action": "본인 행동이 약함",
    "missing_result": "결과 또는 변화가 약함",
    "missing_job_connection": "직무 연결어가 부족함",
    "similar_to_other_answer": "문항 간 표현이 비슷함",
    "abstract_expression": "추상적 다짐이 반복됨",
    "underfilled_answer": "분량이 부족함",
    "low_quality_score": "문항 점수가 제출 기준보다 낮음",
    "low_average_quality_score": "문서 평균 점수가 제출 기준보다 낮음",
}


def infer_org(file_name: str, text: str) -> str:
    for org, hints in ORG_HINTS:
        if any(hint in file_name for hint in hints):
            return org
    haystack = text
    for org, hints in ORG_HINTS:
        if any(hint in haystack for hint in hints):
            return org
    return "지원기관"


def body_text(markdown: str) -> str:
    return markdown.split("## 자기소개서 본문", 1)[-1].strip()


def parse_questions(markdown: str) -> tuple[list[Question], list[DraftResponse]]:
    body = body_text(markdown)
    parts = re.split(r"(?m)^###\s+문항\s+(\d+)\s*$", body)
    questions: list[Question] = []
    responses: list[DraftResponse] = []
    if len(parts) == 1:
        clean = re.sub(r"^#.*$", "", body, flags=re.MULTILINE).strip()
        questions.append(Question(1, "자기소개서 본문", None))
        responses.append(DraftResponse(1, clean, ("submission_ready",)))
        return questions, responses

    for i in range(1, len(parts), 2):
        index = int(parts[i])
        section = parts[i + 1].strip()
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        if not lines:
            continue
        prompt = lines[0]
        answer = "\n".join(lines[1:]).strip()
        limit_values = [int(item) for item in re.findall(r"(\d{2,4})\s*자", prompt)]
        limit = max(limit_values) if limit_values else None
        questions.append(Question(index, prompt, limit))
        responses.append(DraftResponse(index, answer, ("submission_ready",)))
    return questions, responses


def recommendation(avg: float, validation_issue_count: int, risk_count: int) -> str:
    if risk_count:
        return "사실성 재점검"
    if avg >= 90 and validation_issue_count == 0:
        return "제출권장"
    if avg >= 85:
        return "제출가능"
    if avg >= 75:
        return "부분보완"
    return "재작성권장"


def summarize_issues(question_rows: list[dict], validation_codes: list[str], risks: list[str]) -> str:
    counter: Counter[str] = Counter()
    for row in question_rows:
        counter.update(row["score"]["issues"])
    counter.update(validation_codes)
    counter.update(f"risk:{risk}" for risk in risks)
    if not counter:
        return "없음"
    labels: list[str] = []
    for code, _ in counter.most_common(5):
        if code.startswith("risk:"):
            labels.append(f"위험 표현 잔여({code[5:]})")
        else:
            labels.append(ISSUE_LABELS.get(code, code))
    return "; ".join(labels)


def main() -> None:
    results: list[dict] = []
    for path in sorted(INPUT_DIR.glob("*.md")):
        markdown = path.read_text(encoding="utf-8")
        body = body_text(markdown)
        org = infer_org(path.name, body)
        questions, responses = parse_questions(markdown)
        job_terms = JOB_TERMS.get(org, ())
        question_rows = []
        for question in questions:
            response = next((item for item in responses if item.question_index == question.index), None)
            if response is None:
                continue
            peer_answers = tuple(
                item.answer for item in responses if item.question_index != response.question_index
            )
            score = score_answer_quality(
                question,
                response.answer,
                org,
                job_terms=job_terms,
                peer_answers=peer_answers,
            )
            question_rows.append(
                {
                    "question_index": question.index,
                    "prompt": question.prompt,
                    "chars_no_space": len(re.sub(r"\s+", "", response.answer)),
                    "score": asdict(score),
                }
            )
        validation = validate_answer_quality(
            questions,
            responses,
            org,
            job_terms=job_terms,
            minimum_score=STRICT_MIN_ANSWER_SCORE,
            average_minimum_score=STRICT_MIN_AVERAGE_SCORE,
        )
        validation_codes = [issue.code for issue in validation]
        risk_hits = sorted({term for term in RISK_TERMS if term in body})
        avg = round(
            sum(row["score"]["total"] for row in question_rows) / len(question_rows),
            1,
        ) if question_rows else 0.0
        results.append(
            {
                "file": path.name,
                "organization": org,
                "question_count": len(question_rows),
                "average_score": avg,
                "recommendation": recommendation(avg, len(validation), len(risk_hits)),
                "issue_summary": summarize_issues(question_rows, validation_codes, risk_hits),
                "validation_issues": [asdict(issue) for issue in validation],
                "risk_terms_remaining": risk_hits,
                "questions": question_rows,
            }
        )

    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file",
                "organization",
                "question_count",
                "average_score",
                "recommendation",
                "issue_summary",
                "risk_terms_remaining",
            ],
        )
        writer.writeheader()
        for row in results:
            writer.writerow(
                {
                    "file": row["file"],
                    "organization": row["organization"],
                    "question_count": row["question_count"],
                    "average_score": row["average_score"],
                    "recommendation": row["recommendation"],
                    "issue_summary": row["issue_summary"],
                    "risk_terms_remaining": ", ".join(row["risk_terms_remaining"]),
                }
            )

    counts = Counter(row["recommendation"] for row in results)
    lines = [
        "# 제출용 자기소개서 재평가 결과",
        "",
        "- 평가일: 2026-07-05",
        "- 대상: 외부검증 반영 제출용 자기소개서 42개",
        "- 기준: Career Pipeline 품질점수 체계(사실성, 기관 특화도, 행동/결과, 직무연결, 차별성, 자연스러움)",
        "- 제한: 개별 최신 공고 원문을 run 단위로 붙인 평가는 아니므로, 공고명·직렬·글자 수는 최종 제출 직전 별도 대조 필요",
        "",
        "## 종합",
        "",
        f"- 제출권장: {counts.get('제출권장', 0)}개",
        f"- 제출가능: {counts.get('제출가능', 0)}개",
        f"- 부분보완: {counts.get('부분보완', 0)}개",
        f"- 재작성권장: {counts.get('재작성권장', 0)}개",
        f"- 사실성 재점검: {counts.get('사실성 재점검', 0)}개",
        "",
        "## 문서별 결과",
        "",
        "| 순번 | 기관 | 평균점수 | 판정 | 주요 보완점 | 파일 |",
        "|---:|---|---:|---|---|---|",
    ]
    for i, row in enumerate(results, 1):
        lines.append(
            f"| {i} | {row['organization']} | {row['average_score']} | {row['recommendation']} | "
            f"{row['issue_summary']} | {row['file']} |"
        )
    lines.extend(
        [
            "",
            "## 다음 처리 기준",
            "",
            "- `제출권장`: 기관명, 전형명, 글자 수만 공고 원문과 대조",
            "- `제출가능`: 제출 가능하나 문항별 중복 표현 또는 직무 연결어를 한 번 더 다듬으면 좋음",
            "- `부분보완`: 행동-결과 또는 기관 특화 문장을 1~2문장 보강 권장",
            "- `재작성권장`: 문항 요구와 답변 구조를 다시 잡는 편이 안전",
            "- `사실성 재점검`: 숫자·최신 표현·기관 발언을 공식 근거와 다시 대조",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
