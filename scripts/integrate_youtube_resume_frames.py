from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


JOB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path.home() / "OneDrive" / "문서" / "자소서 유튜브 정보"
DEFAULT_OUTPUT_ROOT = JOB_ROOT / "자료조사" / f"자소서_유튜브_프레임분석_{datetime.now():%Y-%m-%d}"


QUESTION_PATTERNS = {
    "지원동기": ["지원동기", "왜 지원", "입사 이유", "입행", "입사 동기", "동기"],
    "직무역량": ["직무", "역량", "강점", "전문성", "업무", "수행", "교육"],
    "경험/성과": ["경험", "성과", "실적", "결과", "활동", "사례", "숫자", "수치"],
    "문제해결": ["문제", "해결", "개선", "어려움", "위기", "불편"],
    "협업/갈등": ["협업", "협력", "갈등", "소통", "팀", "조율"],
    "고객/서비스": ["고객", "민원", "서비스", "응대", "상담", "이용자"],
    "윤리/책임": ["윤리", "책임", "정직", "공정", "규정", "원칙"],
    "입사 후 포부": ["입사 후", "포부", "기여", "계획", "목표", "비전"],
    "성장과정": ["성장", "가치관", "배움", "태도"],
    "성격/장단점": ["성격", "장점", "단점", "강점", "약점"],
    "실패/도전": ["실패", "도전", "극복", "좌절", "시도"],
    "디지털/변화": ["디지털", "AI", "데이터", "변화", "혁신", "전환"],
}

COMPANY_GROUPS = {
    "농협/NH": ["농협", "농협은행", "NH", "지역농협", "축협", "지농"],
    "은행권": ["은행", "기업은행", "IBK", "우리은행", "하나은행", "신한은행", "국민은행", "KB"],
    "건강보험/심평원": ["건강보험", "건보", "국민건강보험공단", "심평원", "h•well", "HIRA"],
    "연금/복지": ["국민연금", "NPS", "사회보장", "복지"],
    "보증/기금/HUG": ["신용보증기금", "기술보증기금", "주택도시보증공사", "HUG", "주택금융공사", "HF", "기금"],
    "공기업/일반행정": ["LH", "한전", "코레일", "마사회", "공사", "공단", "행정"],
}

IMPORTANT_WORDS = [
    "자기소개서",
    "자소서",
    "두괄식",
    "소재",
    "소제목",
    "직무",
    "역량",
    "경험",
    "성과",
    "결과",
    "지원동기",
    "입사 후",
    "기여",
    "고객",
    "민원",
    "서비스",
    "문제",
    "해결",
    "개선",
    "갈등",
    "협업",
    "윤리",
    "책임",
    "성장",
    "노력",
    "구체",
    "수치",
    "숫자",
    "면접",
    "농협",
    "은행",
    "기업은행",
    "IBK",
    "건보",
    "건강보험",
    "심평원",
    "국민연금",
    "HUG",
    "주택",
]

NOISE_NEEDLES = [
    "KAKAO",
    "mgedu",
    "카카오",
    "각종 문의",
    "댓글 링크",
    "교재 구매",
    "한달 자기소개서",
    "면접 완성 PLAN",
    "완성 PLAN",
    "월과정",
    "일과정",
    "과정",
]

REPORT_NOISE_NEEDLES = NOISE_NEEDLES + [
    "글자수",
    "컨설팅",
    "첨삭",
    "구독",
    "좋아요",
    "KAKAO",
    "mgedu",
    "카카오",
    "피드백하기",
    "자소서 분석 특강",
    "자기소개서/면접",
    "자소서/면접",
]

REPORT_SIGNAL_WORDS = [
    "두괄식",
    "소재",
    "직무",
    "역량",
    "경험",
    "성과",
    "지원동기",
    "입사 후",
    "기여",
    "고객",
    "민원",
    "서비스",
    "문제",
    "해결",
    "개선",
    "협업",
    "갈등",
    "윤리",
    "책임",
    "노력",
    "구체",
    "수치",
    "숫자",
    "면접",
    "목표",
    "정리",
    "작성",
]

OCR_FIXES = {
    "불여넣기": "붙여넣기",
    "복불": "복붙",
    "복블": "복붙",
    "연접": "면접",
    "자기소,": "자기소개서",
    "자기소.": "자기소개서",
    "자기소 ": "자기소개서 ",
    "자소세": "자소서",
    "지원동기1": "지원동기",
    "입사후": "입사 후",
    "직무노대": "직무노력",
    "직무노뎨": "직무노력",
    "문항도비쇼": "문항도 비슷",
    "문항도비슷": "문항도 비슷",
    "구체적": "구체적",
}


@dataclass
class FrameRecord:
    video_id: str
    playlist_index: int
    title: str
    timestamp: str
    timestamp_seconds: int
    image_file: str
    youtube_url: str
    question_types: list[str]
    company_groups: list[str]
    companies: list[str]
    score: int
    key_lines: list[str]
    red_lines: list[str]
    highlighted_lines: list[str]
    text_lines: list[str]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(text: str) -> str:
    text = str(text or "").replace("\u00a0", " ")
    for old, new in OCR_FIXES.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def hangul_count(text: str) -> int:
    return len(re.findall(r"[가-힣]", text))


def useful_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    useful = re.findall(r"[가-힣A-Za-z0-9\s.,:;!?()\[\]<>/%+-]", text)
    return len(useful) / max(len(text), 1)


def is_noise_line(text: str) -> bool:
    if len(text) < 4:
        return True
    upper = text.upper()
    if any(needle.upper() in upper for needle in NOISE_NEEDLES):
        return True
    if hangul_count(text) < 2 and not any(word in text for word in ["IBK", "KB", "NH", "HUG", "AI", "FIT", "OK"]):
        return True
    if useful_char_ratio(text) < 0.45:
        return True
    return False


def normalize_key(text: str) -> str:
    text = clean_text(text).lower()
    text = re.sub(r"[^가-힣a-z0-9]+", "", text)
    return text[:120]


def unique_clean(lines: Iterable[str], limit: int | None = None, drop_noise: bool = False) -> list[str]:
    seen = set()
    out: list[str] = []
    for line in lines:
        cleaned = clean_text(line)
        if not cleaned:
            continue
        if drop_noise and is_noise_line(cleaned):
            continue
        key = normalize_key(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if limit and len(out) >= limit:
            break
    return out


def infer_question_types(text: str, existing: Iterable[str]) -> list[str]:
    found = list(existing or [])
    for label, needles in QUESTION_PATTERNS.items():
        if any(needle.lower() in text.lower() for needle in needles):
            found.append(label)
    return sorted(set(found), key=lambda value: list(QUESTION_PATTERNS).index(value) if value in QUESTION_PATTERNS else 99)


def infer_company_groups(text: str, existing_companies: Iterable[str]) -> list[str]:
    haystack = f"{text} {' '.join(existing_companies or [])}"
    found = []
    for group, needles in COMPANY_GROUPS.items():
        if any(needle.lower() in haystack.lower() for needle in needles):
            found.append(group)
    return found


def source_url(video_id: str, url: str, seconds: int) -> str:
    base = url or f"https://www.youtube.com/watch?v={video_id}"
    if "youtube.com/watch" in base:
        return f"{base.split('&t=')[0]}&t={seconds}s" if "&" in base else f"{base}&t={seconds}s"
    return base


def frame_score(text: str, key_lines: list[str], red_lines: list[str], highlighted_lines: list[str], question_types: list[str]) -> int:
    score = 0
    for word in IMPORTANT_WORDS:
        if word.lower() in text.lower():
            score += 2
    score += min(len(key_lines), 8)
    score += min(len(red_lines), 6) * 2
    score += min(len(highlighted_lines), 6) * 2
    score += len(question_types)
    if "두괄식" in text:
        score += 4
    if "소재" in text:
        score += 4
    return score


def load_records(source_root: Path) -> tuple[list[FrameRecord], dict[str, dict], Counter, Counter]:
    analyses_dir = source_root / "analyses"
    if not analyses_dir.exists():
        raise FileNotFoundError(f"분석 폴더를 찾지 못했습니다: {analyses_dir}")

    records: list[FrameRecord] = []
    video_meta: dict[str, dict] = {}
    question_counts: Counter = Counter()
    company_counts: Counter = Counter()

    for path in sorted(analyses_dir.glob("*.json")):
        data = read_json(path)
        video_id = data.get("video_id") or path.stem
        title = clean_text(data.get("title", ""))
        playlist_index = int(float(data.get("playlist_index") or 0))
        summary = data.get("summary", {})
        question_counts.update(summary.get("question_types", {}))
        company_counts.update(summary.get("companies_or_roles", {}))
        video_meta[video_id] = {
            "video_id": video_id,
            "playlist_index": playlist_index,
            "title": title,
            "url": data.get("url", f"https://www.youtube.com/watch?v={video_id}"),
            "frame_count": data.get("frame_count", 0),
            "question_types": summary.get("question_types", {}),
            "companies": summary.get("companies_or_roles", {}),
        }
        for frame in data.get("frames", []):
            text_lines = unique_clean(frame.get("ocr_text_lines", []), limit=120)
            red_lines = unique_clean(frame.get("red_or_emphasis_text", []), limit=40)
            highlighted_lines = unique_clean(frame.get("highlighted_text", []), limit=40)
            principle_lines = unique_clean(frame.get("recommended_principles", []), limit=40, drop_noise=True)
            source_lines = red_lines + highlighted_lines + principle_lines + text_lines
            key_lines = unique_clean(source_lines, limit=12, drop_noise=True)
            text = "\n".join(source_lines + [title])
            qtypes = infer_question_types(text, frame.get("question_types", []))
            companies = unique_clean(frame.get("company_or_role_conditions", []), limit=20)
            groups = infer_company_groups(text, companies)
            seconds = int(round(float(frame.get("timestamp_seconds") or 0)))
            rec = FrameRecord(
                video_id=video_id,
                playlist_index=playlist_index,
                title=title,
                timestamp=frame.get("timestamp", ""),
                timestamp_seconds=seconds,
                image_file=str(frame.get("file", "")),
                youtube_url=source_url(video_id, data.get("url", ""), seconds),
                question_types=qtypes,
                company_groups=groups,
                companies=companies,
                score=frame_score(text, key_lines, red_lines, highlighted_lines, qtypes),
                key_lines=key_lines,
                red_lines=red_lines,
                highlighted_lines=highlighted_lines,
                text_lines=text_lines,
            )
            records.append(rec)

    records.sort(key=lambda rec: (rec.playlist_index, rec.video_id, rec.timestamp_seconds))
    return records, video_meta, question_counts, company_counts


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_line_index(records: list[FrameRecord]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for rec in records:
        line_sources = [
            ("red", rec.red_lines),
            ("highlight", rec.highlighted_lines),
            ("key", rec.key_lines),
            ("text", rec.text_lines),
        ]
        for source_type, lines in line_sources:
            for line in lines:
                line = clean_text(line)
                if is_noise_line(line):
                    continue
                key = normalize_key(line)
                if len(key) < 4:
                    continue
                bucket = buckets.setdefault(
                    key,
                    {
                        "line": line,
                        "count": 0,
                        "source_types": Counter(),
                        "question_types": Counter(),
                        "company_groups": Counter(),
                        "examples": [],
                    },
                )
                if len(line) > len(bucket["line"]) and useful_char_ratio(line) >= useful_char_ratio(bucket["line"]):
                    bucket["line"] = line
                bucket["count"] += 1
                bucket["source_types"].update([source_type])
                bucket["question_types"].update(rec.question_types)
                bucket["company_groups"].update(rec.company_groups)
                if len(bucket["examples"]) < 5:
                    bucket["examples"].append(f"{rec.video_id} {rec.timestamp} {rec.image_file}")

    rows = []
    for bucket in buckets.values():
        source_weight = bucket["source_types"]["red"] * 3 + bucket["source_types"]["highlight"] * 3 + bucket["source_types"]["key"] * 2
        score = bucket["count"] + source_weight + sum(2 for word in IMPORTANT_WORDS if word in bucket["line"])
        rows.append(
            {
                "score": score,
                "count": bucket["count"],
                "line": bucket["line"],
                "source_types": "; ".join(f"{k}:{v}" for k, v in bucket["source_types"].most_common()),
                "question_types": "; ".join(k for k, _ in bucket["question_types"].most_common(5)),
                "company_groups": "; ".join(k for k, _ in bucket["company_groups"].most_common(5)),
                "examples": " | ".join(bucket["examples"]),
            }
        )
    rows.sort(key=lambda row: (-int(row["score"]), -int(row["count"]), row["line"]))
    return rows


def top_records(records: list[FrameRecord], limit: int = 400) -> list[FrameRecord]:
    useful = [rec for rec in records if rec.score >= 8 and rec.key_lines]
    useful.sort(key=lambda rec: (-rec.score, rec.playlist_index, rec.timestamp_seconds))
    return useful[:limit]


def lines_table(rows: list[dict], limit: int = 30) -> str:
    out = ["| 순위 | 근거 문구 | 빈도 | 유형 |", "|---:|---|---:|---|"]
    for idx, row in enumerate(rows[:limit], start=1):
        line = row["line"].replace("|", "/")
        out.append(f"| {idx} | {line} | {row['count']} | {row['question_types']} |")
    return "\n".join(out)


def report_ready_rows(rows: list[dict]) -> list[dict]:
    filtered = []
    for row in rows:
        line = row["line"]
        upper = line.upper()
        if any(needle.upper() in upper for needle in REPORT_NOISE_NEEDLES):
            continue
        if not any(word.lower() in line.lower() for word in REPORT_SIGNAL_WORDS):
            continue
        if not row.get("question_types"):
            continue
        filtered.append(row)
    return filtered


def counter_table(counter: Counter, limit: int = 20) -> str:
    out = ["| 항목 | 화면 근거 수 |", "|---|---:|"]
    for key, value in counter.most_common(limit):
        out.append(f"| {key} | {value} |")
    return "\n".join(out)


def write_reports(
    out_dir: Path,
    source_root: Path,
    records: list[FrameRecord],
    video_meta: dict[str, dict],
    question_counts: Counter,
    company_counts: Counter,
    line_rows: list[dict],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    useful_records = [rec for rec in records if rec.score >= 8 and rec.key_lines]
    nonempty = [rec for rec in records if rec.text_lines]
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_rows = report_ready_rows(line_rows)

    readme = f"""# 자소서 유튜브 프레임 분석 활용법

- 생성 시각: {generated_at}
- 원본 프로젝트: `{source_root}`
- 분석 영상: {len(video_meta)}개
- 전체 프레임: {len(records)}개
- OCR 텍스트가 있는 프레임: {len(nonempty)}개
- 자소서 작성에 쓸 만한 프레임: {len(useful_records)}개

## 파일 안내

- `01_자소서_작성원칙_요약.md`: 바로 적용할 핵심 원칙
- `02_문항유형별_전략.md`: 지원동기, 직무역량, 경험, 문제해결 등 문항별 작성법
- `03_기관별_적용노트.md`: 농협, 은행권, 건보/심평원, 보증/기금 등 기관별 강조점
- `04_프레임_근거색인.csv`: 프레임별 OCR 핵심 문구와 이미지 경로
- `05_문장_근거색인.csv`: 반복되거나 강조된 문구 색인
- `06_영상별_요약.md`: 영상별로 어떤 자료가 있는지 훑어보기
- `07_전체프레임_OCR.jsonl`: 모든 프레임의 OCR 원문 색인
- `run_summary.json`: 처리 건수와 검증용 요약

## 취업 프로젝트에서 쓰는 법

자소서를 새로 만들 때는 `01`, `02`, `03`을 먼저 보고, 실제 근거 화면이 필요하면 `04_프레임_근거색인.csv`의 `image_file`을 열어 확인하면 됩니다.
OCR은 화면 글자 자동 인식이라 일부 오탈자가 있습니다. 최종 자소서 문장은 이 자료를 그대로 베끼기보다 구조와 판단 기준을 참고하는 방식으로 쓰는 것이 안전합니다.
"""
    (out_dir / "00_읽어주세요_활용법.md").write_text(readme, encoding="utf-8")

    principles = f"""# 자소서 작성 원칙 요약

## 전체 처리 결과

- 분석 영상: {len(video_meta)}개
- 전체 프레임: {len(records)}개
- OCR 텍스트 프레임: {len(nonempty)}개
- 활용 후보 프레임: {len(useful_records)}개

## 문항 유형 빈도

{counter_table(question_counts, 20)}

## 기관/직무 빈도

{counter_table(company_counts, 25)}

## 바로 적용할 핵심 원칙

1. 문항을 먼저 유형화하고 소재를 배치한다. 같은 경험을 여러 문항에 반복하지 않는다.
2. 첫 문장은 두괄식으로 쓴다. 결론, 부족했던 역량, 목표, 기여 방향을 먼저 말한다.
3. 경험은 상황보다 행동과 결과를 길게 쓴다. 무엇을 했고 무엇이 달라졌는지가 중심이다.
4. 가능한 한 숫자, 범위, 기간, 처리량, 개선 결과를 넣는다.
5. 지원동기는 기관 이름을 바꿔 끼우는 방식이 아니라 고객, 현장, 직무, 사업 이해로 쓴다.
6. 직무역량 문항은 공부했다는 말에서 끝내지 말고 실제 적용 경험으로 연결한다.
7. 입사 후 포부는 새 꿈을 말하기보다 이미 증명한 행동 방식을 입사 후 업무에 연결한다.
8. 고객/민원/서비스 문항은 친절함보다 문제 파악, 설명, 조율, 재발 방지까지 보여준다.
9. 윤리/책임 문항은 착한 태도보다 규정, 기록, 확인, 공정성을 지킨 행동을 보여준다.
10. 성장/노력 문항은 부족한 역량을 인정하고 보완 과정과 활용 결과를 함께 쓴다.
11. 자소서는 면접 재료다. 면접에서 물어봐도 답할 수 있는 사실만 남긴다.
12. 불필요한 감정 표현, 추상어, 기관 홍보문구, 문항 간 중복은 줄인다.

## 반복 강조 문구 근거 상위

{lines_table(report_rows, 35)}
"""
    (out_dir / "01_자소서_작성원칙_요약.md").write_text(principles, encoding="utf-8")

    q_sections = []
    for qtype in QUESTION_PATTERNS:
        examples = [row for row in report_rows if qtype in row["question_types"]][:12]
        q_sections.append(f"## {qtype}\n")
        q_sections.append(question_strategy(qtype))
        if examples:
            q_sections.append("\n### 화면 근거 문구\n")
            q_sections.append(lines_table(examples, 8))
        q_sections.append("")
    (out_dir / "02_문항유형별_전략.md").write_text("# 문항유형별 전략\n\n" + "\n".join(q_sections), encoding="utf-8")

    company_sections = []
    for group, needles in COMPANY_GROUPS.items():
        examples = [row for row in report_rows if group in row["company_groups"]][:14]
        frame_hits = [rec for rec in useful_records if group in rec.company_groups][:8]
        company_sections.append(f"## {group}\n")
        company_sections.append(company_strategy(group))
        if examples:
            company_sections.append("\n### 반복 근거 문구\n")
            company_sections.append(lines_table(examples, 8))
        if frame_hits:
            company_sections.append("\n### 확인할 프레임\n")
            for rec in frame_hits:
                company_sections.append(f"- {rec.video_id} {rec.timestamp}: {rec.key_lines[0]}  ")
                company_sections.append(f"  `{rec.image_file}`")
        company_sections.append("")
    (out_dir / "03_기관별_적용노트.md").write_text("# 기관별 적용 노트\n\n" + "\n".join(company_sections), encoding="utf-8")

    video_lines = ["# 영상별 요약", ""]
    for video_id, meta in sorted(video_meta.items(), key=lambda item: (item[1]["playlist_index"], item[0])):
        recs = [rec for rec in useful_records if rec.video_id == video_id]
        qtypes = "; ".join(f"{k}({v})" for k, v in Counter(meta.get("question_types", {})).most_common(5))
        companies = "; ".join(f"{k}({v})" for k, v in Counter(meta.get("companies", {})).most_common(5))
        video_lines.append(f"## {meta['playlist_index']}. {meta['title']}")
        video_lines.append(f"- 영상 ID: `{video_id}`")
        video_lines.append(f"- 문항 유형: {qtypes or '미분류'}")
        video_lines.append(f"- 기관/직무: {companies or '미분류'}")
        if recs:
            video_lines.append("- 주요 프레임:")
            for rec in recs[:6]:
                video_lines.append(f"  - {rec.timestamp}: {rec.key_lines[0]} (`{rec.image_file}`)")
        else:
            video_lines.append("- 주요 프레임: 자동 추출된 활용 후보가 적음")
        video_lines.append("")
    (out_dir / "06_영상별_요약.md").write_text("\n".join(video_lines), encoding="utf-8")

    frame_rows = [
        {
            "playlist_index": rec.playlist_index,
            "video_id": rec.video_id,
            "timestamp": rec.timestamp,
            "score": rec.score,
            "title": rec.title,
            "question_types": "; ".join(rec.question_types),
            "company_groups": "; ".join(rec.company_groups),
            "companies": "; ".join(rec.companies),
            "key_lines": " | ".join(rec.key_lines),
            "red_lines": " | ".join(rec.red_lines),
            "highlighted_lines": " | ".join(rec.highlighted_lines),
            "youtube_url": rec.youtube_url,
            "image_file": rec.image_file,
        }
        for rec in records
    ]
    write_csv(
        out_dir / "04_프레임_근거색인.csv",
        frame_rows,
        [
            "playlist_index",
            "video_id",
            "timestamp",
            "score",
            "title",
            "question_types",
            "company_groups",
            "companies",
            "key_lines",
            "red_lines",
            "highlighted_lines",
            "youtube_url",
            "image_file",
        ],
    )
    write_csv(
        out_dir / "05_문장_근거색인.csv",
        line_rows,
        ["score", "count", "line", "source_types", "question_types", "company_groups", "examples"],
    )

    with (out_dir / "07_전체프레임_OCR.jsonl").open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(
                json.dumps(
                    {
                        "video_id": rec.video_id,
                        "playlist_index": rec.playlist_index,
                        "title": rec.title,
                        "timestamp": rec.timestamp,
                        "timestamp_seconds": rec.timestamp_seconds,
                        "score": rec.score,
                        "question_types": rec.question_types,
                        "company_groups": rec.company_groups,
                        "key_lines": rec.key_lines,
                        "text_lines": rec.text_lines,
                        "youtube_url": rec.youtube_url,
                        "image_file": rec.image_file,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    summary = {
        "generated_at": generated_at,
        "source_root": str(source_root),
        "output_root": str(out_dir),
        "video_count": len(video_meta),
        "frame_count": len(records),
        "nonempty_ocr_frame_count": len(nonempty),
        "usable_frame_count": len(useful_records),
        "line_index_count": len(line_rows),
        "question_type_counts": dict(question_counts.most_common()),
        "company_counts": dict(company_counts.most_common()),
        "notes": [
            "원본 이미지와 기존 자기소개서 파일은 수정하지 않았습니다.",
            "OCR 기반 분석이라 일부 글자 오인식이 있습니다.",
            "최종 자소서에는 문구 복사가 아니라 구조와 판단 기준을 적용하는 용도입니다.",
        ],
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def question_strategy(qtype: str) -> str:
    strategies = {
        "지원동기": """- 구조: 기관/직무 이해 -> 내 경험에서 확인한 접점 -> 입사 후 기여.
- 주의: 기관명만 바꿔도 통하는 문장은 약하다.
- 우리 자료 적용: `자료조사`의 기관 사업, `경험정리`의 고객/행정/정산 경험을 먼저 연결한다.""",
        "직무역량": """- 구조: 필요한 역량 정의 -> 실제 사용 경험 -> 결과 -> 같은 역량을 지원 직무에 쓰는 방식.
- 주의: 공부했다는 말만 쓰지 않는다. 업무 상황에 적용한 장면이 있어야 한다.
- 우리 자료 적용: 민원 응대, 서류 확인, 정산, 안내, 자료 정리 경험을 직무 언어로 바꾼다.""",
        "경험/성과": """- 구조: 목표 -> 행동 -> 수치나 변화 -> 배운 점.
- 주의: 상황 설명이 길어지면 성과가 흐려진다.
- 우리 자료 적용: 처리 건수, 일정 단축, 오류 감소, 민원 예방처럼 확인 가능한 결과를 찾는다.""",
        "문제해결": """- 구조: 문제 발견 -> 원인 파악 -> 조치 -> 재발 방지.
- 주의: 힘들었다는 감정보다 판단 과정과 해결 방식을 쓴다.
- 우리 자료 적용: 코로나 숙박비 정산, 서류 안내, 고객 불편 해결 경험을 우선 검토한다.""",
        "협업/갈등": """- 구조: 이해관계자 차이 -> 조율 행동 -> 합의 또는 실행 결과.
- 주의: 상대를 탓하지 않고 역할 분담과 소통 방식을 보여준다.
- 우리 자료 적용: 부서 협업, 민원인/담당자 사이 조율 경험을 찾는다.""",
        "고객/서비스": """- 구조: 고객 상황 파악 -> 쉽게 설명 -> 확인 -> 후속 조치.
- 주의: 친절했다는 표현만으로는 부족하다.
- 우리 자료 적용: 민원 응대, 제도 안내, 서류 보완 요청 경험을 고객 관점으로 재작성한다.""",
        "윤리/책임": """- 구조: 규정 또는 원칙 -> 선택 상황 -> 지킨 행동 -> 신뢰 결과.
- 주의: 정직하다는 선언보다 기록, 확인, 절차 준수가 강하다.
- 우리 자료 적용: 개인정보, 서류, 예산, 정산 관련 경험에서 책임 행동을 찾는다.""",
        "입사 후 포부": """- 구조: 내가 이미 증명한 역량 -> 입사 후 적용 업무 -> 고객/조직에 생기는 변화.
- 주의: 거창한 포부보다 실무에서 바로 할 행동이 좋다.
- 우리 자료 적용: 안내 정확도, 현장 판단, 반복 민원 예방, 지역 고객 지원으로 연결한다.""",
        "성장과정": """- 구조: 가치관 형성 계기 -> 행동 습관 -> 직무와 연결.
- 주의: 가족사나 감상문처럼 흐르지 않게 한다.
- 우리 자료 적용: 일관된 성실성, 책임감, 행정 정확성의 흐름으로 정리한다.""",
        "성격/장단점": """- 구조: 강점은 증거와 함께, 약점은 보완 행동과 함께.
- 주의: 장점과 단점이 직무와 무관하면 힘이 약하다.
- 우리 자료 적용: 꼼꼼함, 설명력, 책임감은 사례로 증명하고 단점은 업무 방식 개선으로 처리한다.""",
        "실패/도전": """- 구조: 실패 또는 한계 -> 원인 인정 -> 바꾼 행동 -> 이후 결과.
- 주의: 실패를 포장하지 말고 배운 점을 실제 변화로 보여준다.
- 우리 자료 적용: 처음 부족했던 업무 이해를 보완해 성과로 만든 경험을 찾는다.""",
        "디지털/변화": """- 구조: 변화 필요성 -> 도구/데이터 활용 -> 업무 개선 -> 확장 가능성.
- 주의: 최신 기술명 나열보다 실제 업무 개선이 중요하다.
- 우리 자료 적용: 자료 정리, 엑셀, 문서화, 반복 업무 개선 경험을 연결한다.""",
    }
    return strategies.get(qtype, "- 핵심 요구를 먼저 확인하고 경험, 행동, 결과, 직무 연결 순서로 쓴다.")


def company_strategy(group: str) -> str:
    strategies = {
        "농협/NH": """- 지역성, 조합원/고객 접점, 농업/금융/생활 서비스 이해를 먼저 세운다.
- 창구, 서류, 상담, 민원 상황에서 신뢰를 만든 경험이 잘 맞는다.
- 지원동기는 금융권 일반론보다 지역 고객의 생활 문제를 돕는 방향이 강하다.""",
        "은행권": """- 고객 신뢰, 정확한 업무 처리, 상품/제도 설명, 영업 이전의 관계 형성이 중요하다.
- 숫자 성과가 없다면 고객 불편 감소, 설명 개선, 확인 절차 강화로 성과를 만든다.
- 지원동기는 은행 브랜드 칭찬보다 고객 접점과 직무 수행 방식으로 쓴다.""",
        "건강보험/심평원": """- 제도 이해, 민원 응대, 공정성, 설명력, 기록 정확성이 핵심이다.
- 공공 서비스 이용자가 이해하기 쉽게 안내한 경험을 우선 배치한다.
- 규정과 고객 사이에서 균형 있게 설명한 장면이 좋다.""",
        "연금/복지": """- 장기적 신뢰, 제도 안내, 취약 고객 배려, 정확한 행정 처리가 중요하다.
- 개인 경험은 공공성, 지속성, 책임감으로 연결한다.""",
        "보증/기금/HUG": """- 보증, 심사, 서류, 리스크, 정책금융의 공공성을 이해해야 한다.
- 고객 안내와 서류 정확성, 제도 목적을 함께 보여주는 경험이 잘 맞는다.""",
        "공기업/일반행정": """- 규정 준수, 문서화, 민원 대응, 협업, 일정 관리가 기본 축이다.
- 기관 사업을 과하게 칭찬하기보다 행정 실무에서 어떻게 기여할지 쓴다.""",
    }
    return strategies.get(group, "- 기관 사업과 고객 접점을 확인한 뒤 경험을 직무 언어로 연결한다.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    records, video_meta, question_counts, company_counts = load_records(args.source_root)
    line_rows = build_line_index(records)
    write_reports(args.output_root, args.source_root, records, video_meta, question_counts, company_counts, line_rows)
    print(json.dumps({
        "output_root": str(args.output_root),
        "videos": len(video_meta),
        "frames": len(records),
        "nonempty_ocr_frames": sum(1 for rec in records if rec.text_lines),
        "usable_frames": sum(1 for rec in records if rec.score >= 8 and rec.key_lines),
        "line_index": len(line_rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
