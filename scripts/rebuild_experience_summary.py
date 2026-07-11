from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "jasoseo_all_review_20260705"
EXPERIENCE_DIR = ROOT / "\uacbd\ud5d8\uc815\ub9ac"
OLD_INTRO_DIR = ROOT / "\uc608\uc804 \uc790\uae30\uc18c\uac1c\uc11c"
TARGET_DOCS = OUT_DIR / "target_documents.txt"


EXPERIENCE_THEMES = {
    "서울시청 코로나19 지원/숙박비 검증": (
        "서울시청",
        "숙박",
        "고시원",
        "290",
        "의료진",
        "숙박비",
        "급여 산정",
    ),
    "국민연금공단 인턴/기초연금 자료 정리": (
        "국민연금",
        "기초연금",
        "VLOOKUP",
        "공시지가",
        "수급",
        "연금액",
        "스프레드시트",
    ),
    "도서관/서가·문의 개선": (
        "해맞이",
        "도서관",
        "서가",
        "대출",
        "도서",
        "문의",
        "키워드",
    ),
    "은행·새마을금고/고령 고객 응대": (
        "새마을",
        "90세",
        "전자금융",
        "태블릿",
        "서명",
        "시각",
        "청각",
    ),
    "자원봉사·일정/업무 시스템화": (
        "자원봉사",
        "일정",
        "구글",
        "캘린더",
        "50%",
        "90%",
        "만족도",
        "시스템",
    ),
    "급여 산정·엑셀 자동화/협업": (
        "급여",
        "엑셀",
        "자동화",
        "수기",
        "주무관",
        "30%",
        "오류",
    ),
}


RISKY_CLAIMS = (
    "1억",
    "적발",
    "허위",
    "사상 최대",
    "최초",
    "4,000",
    "3만",
    "0건",
    "반려율",
    "누수",
)


def docx_text(path: Path) -> list[str]:
    document = Document(path)
    paragraphs = [p.text.strip().replace("\xa0", " ") for p in document.paragraphs]
    return [p for p in paragraphs if p]


def collect_experience_sources() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(EXPERIENCE_DIR.glob("*.docx"), key=lambda p: p.name):
        paragraphs = docx_text(path)
        records.append(
            {
                "file": path.name,
                "relpath": str(path.relative_to(ROOT)),
                "paragraph_count": len(paragraphs),
                "paragraphs": paragraphs,
            }
        )
    return records


def theme_hits(paragraphs: list[str], cues: tuple[str, ...]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for index, paragraph in enumerate(paragraphs):
        score = sum(cue in paragraph for cue in cues)
        if score >= 2:
            hits.append((index, paragraph))
    return hits


def compact_evidence(hits: list[tuple[int, str]], limit: int = 7) -> list[dict[str, object]]:
    compact: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, paragraph in hits:
        text = re.sub(r"\s+", " ", paragraph).strip()
        key = text[:80]
        if key in seen:
            continue
        seen.add(key)
        compact.append({"paragraph_index": index, "excerpt": text[:420]})
        if len(compact) >= limit:
            break
    return compact


def classify_confidence(evidence: list[dict[str, object]]) -> str:
    joined = " ".join(str(item["excerpt"]) for item in evidence)
    has_action = any(cue in joined for cue in ("확인", "정리", "대조", "안내", "개선", "제안"))
    has_result = any(cue in joined for cue in ("결과", "감소", "증가", "단축", "완료", "상승"))
    return "높음" if has_action and has_result else "중간" if evidence else "낮음"


def build_curated_experiences(sources: list[dict[str, object]]) -> list[dict[str, object]]:
    experiences: list[dict[str, object]] = []
    for theme, cues in EXPERIENCE_THEMES.items():
        source_rows = []
        all_evidence: list[dict[str, object]] = []
        for source in sources:
            hits = theme_hits(source["paragraphs"], cues)
            evidence = compact_evidence(hits)
            if evidence:
                source_rows.append(
                    {
                        "source": source["relpath"],
                        "hit_count": len(hits),
                        "evidence": evidence,
                    }
                )
                for item in evidence:
                    all_evidence.append({"source": source["relpath"], **item})
        joined = " ".join(item["excerpt"] for item in all_evidence)
        risk_hits = sorted({term for term in RISKY_CLAIMS if term in joined})
        experiences.append(
            {
                "experience_id": "proposed_" + re.sub(r"[^0-9A-Za-z가-힣]+", "_", theme).strip("_"),
                "theme": theme,
                "status": "proposed",
                "confidence": classify_confidence(all_evidence),
                "recommended_use": recommended_use(theme),
                "safe_angle": safe_angle(theme),
                "risk_or_verification_needed": risk_hits,
                "sources": source_rows,
            }
        )
    return experiences


def curated_ledger(experiences: list[dict[str, object]]) -> dict[str, object]:
    ledger_items = []
    for item in experiences:
        evidence_refs = []
        for source in item["sources"]:
            for evidence in source["evidence"][:3]:
                evidence_refs.append(
                    {
                        "source_path": source["source"],
                        "paragraph_index": evidence["paragraph_index"],
                        "excerpt": evidence["excerpt"],
                    }
                )
        ledger_items.append(
            {
                "experience_id": item["experience_id"],
                "title": item["theme"],
                "status": "proposed",
                "recommended_use": item["recommended_use"],
                "safe_angle": item["safe_angle"],
                "risk_or_verification_needed": item["risk_or_verification_needed"],
                "evidence": evidence_refs,
            }
        )
    return {
        "schema": "career_experience_curated_proposed.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workspace_root": str(ROOT),
        "status_note": "사용자 확인 전까지 confirmed가 아닌 proposed 후보입니다.",
        "experiences": ledger_items,
    }


def recommended_use(theme: str) -> list[str]:
    mapping = {
        "서울시청 코로나19 지원/숙박비 검증": ["원칙·윤리", "자료 검증", "공공성", "정확성"],
        "국민연금공단 인턴/기초연금 자료 정리": ["직무역량", "데이터 정리", "행정 효율", "민원 안내"],
        "도서관/서가·문의 개선": ["문제해결", "고객 관찰", "협업", "현장 개선"],
        "은행·새마을금고/고령 고객 응대": ["고객응대", "포용 금융", "눈높이 설명", "서비스"],
        "자원봉사·일정/업무 시스템화": ["운영 개선", "일정 조율", "업무 효율", "지원 업무"],
        "급여 산정·엑셀 자동화/협업": ["협업", "업무 자동화", "정확성", "세대 간 조율"],
    }
    return mapping.get(theme, [])


def safe_angle(theme: str) -> str:
    mapping = {
        "서울시청 코로나19 지원/숙박비 검증": "금액 단정이나 적발 표현보다, 이상 징후를 확인해 담당자에게 보고하고 검토 기준을 정리한 경험으로 쓰는 편이 안전합니다.",
        "국민연금공단 인턴/기초연금 자료 정리": "스프레드시트·자료 분류·우선순위 표시로 담당자가 바로 판단할 수 있게 만든 경험으로 활용합니다.",
        "도서관/서가·문의 개선": "수치가 불확실하면 문의 감소·동선 개선 등 정성 결과 중심으로 쓰고, 협업 부담을 나눈 과정을 강조합니다.",
        "은행·새마을금고/고령 고객 응대": "고령 고객의 이해 속도에 맞춰 설명하고 절차를 끝까지 도운 눈높이 소통 경험으로 쓰기 좋습니다.",
        "자원봉사·일정/업무 시스템화": "50%, 90%, 80% 등 수치는 증빙 전에는 완화하고, 일정 안내와 조정 업무를 표준화한 경험으로 씁니다.",
        "급여 산정·엑셀 자동화/협업": "자동화 자체보다 기존 수기 검토의 장점을 존중하며 이중 점검 구조를 만든 협업 경험으로 쓰는 편이 안전합니다.",
    }
    return mapping.get(theme, "")


def old_intro_coverage() -> dict[str, object]:
    old_files = sorted(OLD_INTRO_DIR.rglob("*"))
    old_content_files = [
        p for p in old_files if p.is_file() and p.suffix.lower() in {".html", ".json", ".txt"}
    ]
    target_text = TARGET_DOCS.read_text(encoding="utf-8") if TARGET_DOCS.exists() else ""
    included = []
    not_included = []
    for path in old_content_files:
        stem = path.name
        if stem in target_text or path.stem in target_text:
            included.append(str(path.relative_to(ROOT)))
        else:
            not_included.append(str(path.relative_to(ROOT)))
    grouped = Counter()
    for path in old_content_files:
        name = path.name
        if "metadata" in name or name.endswith(".json"):
            grouped["metadata/json"] += 1
        elif name.endswith(".html"):
            grouped["html"] += 1
        elif name.endswith(".txt"):
            grouped["txt"] += 1
        else:
            grouped["other"] += 1
    return {
        "old_folder": str(OLD_INTRO_DIR.relative_to(ROOT)),
        "content_file_count": len(old_content_files),
        "file_type_counts": dict(grouped),
        "included_in_42_target_documents": included,
        "not_included_count": len(not_included),
        "not_included_examples": not_included[:30],
        "conclusion": "지난 42개 제출권장화 대상에는 예전 자기소개서 폴더의 과거 PDF 변환본/HTML 자료가 포함되지 않았습니다.",
    }


def render_markdown(experiences: list[dict[str, object]], coverage: dict[str, object]) -> str:
    lines = [
        "# 경험정리 재정리 및 예전 자기소개서 포함 여부",
        "",
        f"- 작성일: {datetime.now().strftime('%Y-%m-%d')}",
        "- 원본 보호: 원본 DOCX/PDF/HTML은 수정하지 않음",
        "- 상태 원칙: 아래 경험은 `proposed` 후보이며, 제출 답변의 확정 근거로 쓰려면 사용자 확인이 필요함",
        "",
        "## 예전 자기소개서 포함 여부",
        "",
        f"- 예전 자기소개서 폴더 콘텐츠 파일: {coverage['content_file_count']}개",
        f"- 지난 42개 제출권장화 대상에 포함된 예전 자기소개서 파일: {len(coverage['included_in_42_target_documents'])}개",
        f"- 결론: {coverage['conclusion']}",
        "",
        "### 파일 유형",
        "",
    ]
    for key, value in coverage["file_type_counts"].items():
        lines.append(f"- {key}: {value}개")
    lines.extend(
        [
            "",
            "## 핵심 경험 후보",
            "",
        ]
    )
    for index, item in enumerate(experiences, 1):
        lines.extend(
            [
                f"### {index}. {item['theme']}",
                "",
                f"- 상태: {item['status']}",
                f"- 근거 신뢰도: {item['confidence']}",
                f"- 추천 활용 문항: {', '.join(item['recommended_use'])}",
                f"- 안전한 작성 방향: {item['safe_angle']}",
                f"- 재확인 필요한 표현: {', '.join(item['risk_or_verification_needed']) if item['risk_or_verification_needed'] else '없음'}",
                "",
                "근거 위치:",
            ]
        )
        for source in item["sources"][:4]:
            lines.append(f"- {source['source']} · 관련 문단 {source['hit_count']}개")
            for evidence in source["evidence"][:3]:
                lines.append(
                    f"  - 문단 {evidence['paragraph_index']}: {evidence['excerpt']}"
                )
        lines.append("")
    lines.extend(
        [
            "## 제출 답변에 반영할 때의 우선순위",
            "",
            "1. 금융·공공기관 공통 핵심 경험: 국민연금공단 자료 정리, 서울시청 검증, 고령 고객 응대",
            "2. 문제해결·협업 문항: 도서관 개선, 급여 산정·엑셀 자동화, 자원봉사 일정 시스템화",
            "3. 숫자 사용 원칙: 20건처럼 여러 자소서에서 반복되고 원자료에 남은 수치는 보수적으로 사용 가능하나, 금액·0건·반려율·사상 최대 표현은 제출 직전 재확인",
            "4. 예전 자기소개서는 바로 제출본으로 쓰기보다 소재 저장고와 표현 위험 점검 자료로 활용",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    sources = collect_experience_sources()
    experiences = build_curated_experiences(sources)
    coverage = old_intro_coverage()
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": [
            {
                "file": item["file"],
                "relpath": item["relpath"],
                "paragraph_count": item["paragraph_count"],
            }
            for item in sources
        ],
        "old_self_intro_coverage": coverage,
        "experiences": experiences,
    }
    (OUT_DIR / "experience_rebuild_20260705.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "experience_rebuild_20260705.md").write_text(
        render_markdown(experiences, coverage),
        encoding="utf-8",
    )
    (OUT_DIR / "experience_ledger_curated_20260705.proposed.json").write_text(
        json.dumps(curated_ledger(experiences), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(OUT_DIR / "experience_rebuild_20260705.md")


if __name__ == "__main__":
    main()
