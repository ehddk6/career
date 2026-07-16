"""Writing strategy guidance from local YouTube frame analysis."""

from __future__ import annotations

import csv
from datetime import datetime
import os
from pathlib import Path
import re


GUIDANCE_KIND = "youtube_frame_strategy"
GUIDANCE_POLICY = "strategy_only_not_factual_evidence"
GUIDANCE_ARTIFACT = "05_작성가이드_유튜브프레임.md"
FRAME_DIR_GLOB = "자소서_유튜브_프레임분석_*"

SOURCE_FILE_ROLES = {
    "00_읽어주세요_활용법.md": "활용법",
    "01_자소서_작성원칙_요약.md": "전체 작성 원칙",
    "02_문항유형별_전략.md": "문항 유형별 전략",
    "03_기관별_적용노트.md": "기관별 적용 노트",
    "04_프레임_근거색인.csv": "캡처 프레임 원문 색인",
    "05_문장_근거색인.csv": "문장 단위 원문 색인",
    "06_영상별_요약.md": "영상별 요약",
    "07_전체프레임_OCR.jsonl": "전체 OCR 원문",
    "run_summary.json": "분석 실행 요약",
}

TARGET_ALIASES = {
    "신용보증기금": ("신용보증기금", "KODIT", "신보"),
    "한국주택금융공사": ("한국주택금융공사", "주택금융공사", "HF"),
    "주택도시보증공사": ("주택도시보증공사", "HUG"),
}

TARGET_GROUP_ALIASES = {
    "신용보증기금": ("보증/기금/HUG",),
    "한국주택금융공사": ("보증/기금/HUG",),
    "주택도시보증공사": ("보증/기금/HUG",),
}


def _latest_frame_dir(root: Path) -> Path | None:
    base = root / "자료조사"
    if not base.exists():
        return None
    candidates = [path for path in base.glob(FRAME_DIR_GLOB) if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (path.name, path.stat().st_mtime), reverse=True)[0]


def _existing_source_files(source_dir: Path, root: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for name, role in SOURCE_FILE_ROLES.items():
        path = source_dir / name
        if path.exists():
            files.append(
                {
                    "name": name,
                    "path": path.relative_to(root).as_posix(),
                    "role": role,
                }
            )
    return files


def _read_summary_lines(path: Path, limit: int = 18) -> list[str]:
    if not path.exists():
        return []
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= limit:
            break
    return lines


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _target_terms(target: str | None) -> tuple[str, ...]:
    if not target or not target.strip():
        return ()
    normalized_target = _normalized(target)
    terms = {_normalized(target)}
    matched_alias_group = False
    for anchor, aliases in TARGET_ALIASES.items():
        if _normalized(anchor) in normalized_target or any(
            _normalized(alias) in normalized_target for alias in aliases
        ):
            matched_alias_group = True
            terms.update(_normalized(alias) for alias in aliases)
    if not matched_alias_group:
        terms.update(
            _normalized(item)
            for item in re.findall(r"[가-힣A-Za-z]{3,}", target)
        )
    return tuple(sorted((term for term in terms if len(term) >= 2), key=lambda item: (-len(item), item)))


def _target_group_terms(target: str | None) -> tuple[str, ...]:
    if not target or not target.strip():
        return ()
    normalized_target = _normalized(target)
    terms: set[str] = set()
    for anchor, aliases in TARGET_GROUP_ALIASES.items():
        if _normalized(anchor) in normalized_target:
            terms.update(_normalized(alias) for alias in aliases)
    return tuple(sorted(terms, key=lambda item: (-len(item), item)))


def _compact_strategy_excerpt(value: str, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _target_specific_youtube_strategy(
    source_dir: Path,
    target: str | None,
    *,
    max_videos: int = 8,
    max_frames_per_video: int = 3,
) -> dict[str, object]:
    """Extract institution-matched writing patterns without promoting facts."""

    terms = _target_terms(target)
    result: dict[str, object] = {
        "status": "not_requested" if not terms else "source_unavailable",
        "target": target,
        "match_terms": list(terms),
        "group_match_terms": list(_target_group_terms(target)),
        "source_file": "04_프레임_근거색인.csv",
        "use_policy": GUIDANCE_POLICY,
        "videos": [],
        "video_count": 0,
        "frame_count": 0,
    }
    if not terms:
        return result

    index_path = source_dir / "04_프레임_근거색인.csv"
    if not index_path.is_file():
        return result

    group_terms = _target_group_terms(target)
    grouped: dict[str, dict[str, object]] = {}
    try:
        with index_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            for row in csv.DictReader(stream):
                title_haystack = _normalized(row.get("title", ""))
                company_values = {
                    _normalized(value)
                    for value in (row.get("companies", "") or "").split(";")
                    if value.strip()
                }
                group_haystack = _normalized(row.get("company_groups", ""))
                title_match = any(term in title_haystack for term in terms)
                company_match = any(term in company_values for term in terms)
                direct_match = title_match or company_match
                group_match = any(term in group_haystack for term in group_terms)
                if not direct_match and not group_match:
                    continue
                video_id = (row.get("video_id") or "unknown").strip()
                item = grouped.setdefault(
                    video_id,
                    {
                        "video_id": video_id,
                        "title": (row.get("title") or "").strip(),
                        "youtube_url": (row.get("youtube_url") or "").strip(),
                        "question_types": set(),
                        "company_groups": set(),
                        "frames": [],
                        "match_type": (
                            "title_direct"
                            if title_match
                            else "company_tag"
                            if company_match
                            else "institution_group"
                        ),
                    },
                )
                if title_match:
                    item["match_type"] = "title_direct"
                elif company_match and item["match_type"] == "institution_group":
                    item["match_type"] = "company_tag"
                item["question_types"].update(
                    value.strip() for value in (row.get("question_types") or "").split(";") if value.strip()
                )
                item["company_groups"].update(
                    value.strip() for value in (row.get("company_groups") or "").split(";") if value.strip()
                )
                frames = item["frames"]
                if len(frames) < max_frames_per_video:
                    try:
                        score = int(float(row.get("score") or 0))
                    except ValueError:
                        score = 0
                    frames.append(
                        {
                            "timestamp": (row.get("timestamp") or "").strip(),
                            "score": score,
                            "question_types": (row.get("question_types") or "").strip(),
                            "strategy_excerpt": _compact_strategy_excerpt(row.get("key_lines", "")),
                            "youtube_url": (row.get("youtube_url") or "").strip(),
                        }
                    )
    except (OSError, csv.Error, UnicodeError):
        return result

    videos = sorted(
        grouped.values(),
        key=lambda item: (
            {"title_direct": 0, "company_tag": 1, "institution_group": 2}[item["match_type"]],
            -max((frame.get("score", 0) for frame in item["frames"]), default=0),
            str(item["video_id"]),
        ),
    )[:max_videos]
    normalized_videos: list[dict[str, object]] = []
    for item in videos:
        normalized_videos.append(
            {
                **item,
                "question_types": sorted(item["question_types"]),
                "company_groups": sorted(item["company_groups"]),
            }
        )
    result.update(
        {
            "status": "matched" if normalized_videos else "no_match",
            "videos": normalized_videos,
            "video_count": len(normalized_videos),
            "direct_video_count": sum(item["match_type"] == "title_direct" for item in normalized_videos),
            "company_tag_video_count": sum(item["match_type"] == "company_tag" for item in normalized_videos),
            "institution_group_video_count": sum(item["match_type"] == "institution_group" for item in normalized_videos),
            "frame_count": sum(len(item["frames"]) for item in normalized_videos),
        }
    )
    return result


def _render_guidance(
    source_dir: Path,
    source_files: list[dict[str, str]],
    target_specific: dict[str, object] | None = None,
) -> str:
    summary_lines = _read_summary_lines(source_dir / "01_자소서_작성원칙_요약.md")
    source_lines = [
        f"- `{item['name']}`: {item['role']}"
        for item in source_files
    ]
    if not source_lines:
        source_lines = ["- 사용 가능한 원문 파일을 찾지 못했습니다."]

    lines = [
        "# 유튜브 프레임 작성가이드",
        "",
        "이 문서는 자기소개서 작성 전략 참고자료입니다.",
        "공식 근거 또는 경험 사실 근거로 사용하지 않습니다.",
        "",
        "## 사용 원칙",
        "",
        "- 지원기관의 사실, 수치, 사업명, 채용조건은 공식 공고와 공식 조사 자료에서만 가져옵니다.",
        "- 본인 경험의 사실, 역할, 성과, 기간은 확정 경험원장 또는 사용자 원자료에서만 가져옵니다.",
        "- 유튜브 프레임 자료는 문항 해석, 소재 배치, 첫 문장 방향, 강조 순서, 금지 표현 점검에만 씁니다.",
        "- 예시 문장을 그대로 복사하지 않고, 필요한 경우 캡처 원문을 확인해 구조와 판단 기준만 반영합니다.",
        "",
        "## 작성 단계에서 확인할 것",
        "",
        "1. 문항을 유형별로 나눕니다: 지원동기, 직무역량, 고객/서비스, 문제해결, 협업, 윤리/책임, 성장.",
        "2. 같은 경험이 여러 문항에 반복되지 않도록 문항별 역할을 나눕니다.",
        "3. 첫 문장은 결론, 부족했던 점, 개선 방향, 기여 방향 중 하나로 분명하게 시작합니다.",
        "4. 상황 설명보다 행동과 결과를 길게 씁니다.",
        "5. 면접에서 다시 물어봐도 설명할 수 있는 사실만 남깁니다.",
        "",
        "## 원문 확인 위치",
        "",
        f"- 프레임 분석 폴더: `{source_dir}`",
        *source_lines,
        "",
        "## 빠른 요약",
        "",
    ]
    if summary_lines:
        lines.extend(f"- {line}" for line in summary_lines)
    else:
        lines.append("- 요약 파일을 찾지 못했습니다. 색인 CSV와 OCR 원문을 직접 확인하세요.")
    if target_specific and target_specific.get("status") == "matched":
        lines.extend(
            [
                "",
                "## 지원기관 맞춤 유튜브 전략 (사실 근거 아님)",
                "",
                f"- 대상: `{target_specific.get('target')}`",
                f"- 일치 영상: {target_specific.get('video_count', 0)}개 · 대표 프레임: {target_specific.get('frame_count', 0)}개",
                "- 아래 내용은 신용보증기금 등 기관별 자기소개서 사례의 구조·문항 대응 패턴을 참고하는 용도입니다.",
                "- 기관의 사업·업무·수치·채용조건은 반드시 공식 조사 패킷으로 다시 확인합니다.",
            ]
        )
        for video in target_specific.get("videos", []):
            lines.extend(
                [
                    "",
                    f"### {video.get('title') or video.get('video_id')}",
                    f"- video_id: `{video.get('video_id')}`",
                    f"- 일치 방식: `{video.get('match_type')}`",
                    f"- 문항 유형: {', '.join(video.get('question_types', [])) or '미분류'}",
                    f"- 기관군: {', '.join(video.get('company_groups', [])) or '미분류'}",
                ]
            )
            for frame in video.get("frames", []):
                lines.append(
                    f"- {frame.get('timestamp') or '?'} · 전략 발췌: {frame.get('strategy_excerpt') or '(원문 발췌 없음)'}"
                )
    elif target_specific and target_specific.get("status") == "no_match":
        lines.extend(
            [
                "",
                "## 지원기관 맞춤 유튜브 전략",
                "",
                f"- `{target_specific.get('target')}`와 직접 일치하는 영상 색인 항목을 찾지 못했습니다.",
                "- 일반 작성전략만 사용하며 기관별 사례를 추정하지 않습니다.",
            ]
        )
    lines.extend(
        [
            "",
            "## 다음 산출물에 반영",
            "",
            "- `05_문항전략.md`를 만들기 전에 이 가이드를 먼저 확인합니다.",
            "- `draft.json`과 최종 자기소개서에는 공식 근거와 사용자 경험 근거만 evidence로 연결합니다.",
            "- 이 자료에서 온 내용은 `writing_guidance`로만 추적하고, `research_refs`나 `experience_refs`에 넣지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def _latest_mtime(paths: list[Path]) -> float | None:
    values: list[float] = []
    for path in paths:
        try:
            if path.is_dir():
                values.extend(
                    item.stat().st_mtime
                    for item in path.iterdir()
                    if item.is_file()
                )
            elif path.is_file():
                values.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(values) if values else None


def guidance_freshness(source_dir: Path) -> dict[str, str | None]:
    """Compare an imported strategy snapshot with its local source project."""

    configured = os.environ.get("CAREER_YOUTUBE_GUIDANCE_ROOT", "").strip()
    external_root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / "OneDrive" / "\ubb38\uc11c" / "\uc790\uc18c\uc11c \uc720\ud29c\ube0c \uc815\ubcf4"
    )
    imported_latest = _latest_mtime([source_dir])
    external_latest = _latest_mtime(
        [
            external_root / "captures_manifest.csv",
            external_root / "playlist.json",
            external_root / "progress.json",
            external_root / "analyses",
        ]
    )
    if external_latest is None:
        status = "external_source_unavailable"
    elif imported_latest is None:
        status = "imported_snapshot_unavailable"
    elif external_latest > imported_latest:
        status = "stale"
    else:
        status = "fresh"
    return {
        "status": status,
        "external_source_latest_at": (
            datetime.fromtimestamp(external_latest).astimezone().isoformat()
            if external_latest is not None
            else None
        ),
        "imported_snapshot_latest_at": (
            datetime.fromtimestamp(imported_latest).astimezone().isoformat()
            if imported_latest is not None
            else None
        ),
    }


def workspace_guidance_status(root: Path, target: str | None = None) -> dict[str, object]:
    """Return strategy snapshot availability and freshness without copying content."""

    source_dir = _latest_frame_dir(root)
    if source_dir is None:
        return {
            "status": "missing",
            "kind": GUIDANCE_KIND,
            "use_policy": GUIDANCE_POLICY,
            "freshness": {"status": "imported_snapshot_unavailable"},
        }
    return {
        "status": "available",
        "kind": GUIDANCE_KIND,
        "use_policy": GUIDANCE_POLICY,
        "source_dir": source_dir.relative_to(root).as_posix(),
        "target_specific": _target_specific_youtube_strategy(source_dir, target),
        "freshness": guidance_freshness(source_dir),
    }


def attach_writing_guidance(
    root: Path,
    run_dir: Path,
    state: dict,
    target: str | None = None,
) -> dict:
    """Attach strategy-only YouTube frame guidance metadata to a run state."""

    source_dir = _latest_frame_dir(root)
    metadata = {
        "status": "missing",
        "kind": GUIDANCE_KIND,
        "use_policy": GUIDANCE_POLICY,
    }
    if source_dir is None:
        state["writing_guidance"] = metadata
        return metadata

    source_files = _existing_source_files(source_dir, root)
    target_specific = _target_specific_youtube_strategy(source_dir, target)
    missing_files = [
        name for name in SOURCE_FILE_ROLES if not (source_dir / name).exists()
    ]
    artifact = run_dir / GUIDANCE_ARTIFACT
    artifact.parent.mkdir(parents=True, exist_ok=True)
    source_label = source_dir.relative_to(root).as_posix()
    rendered = _render_guidance(source_dir, source_files, target_specific).replace(
        str(source_dir), source_label
    )
    artifact.write_text(rendered, encoding="utf-8")

    metadata.update(
        {
            "status": "available",
            "source_dir": source_dir.relative_to(root).as_posix(),
            "artifact": artifact.relative_to(root).as_posix(),
            "source_files": source_files,
            "missing_files": missing_files,
            "target": target,
            "target_specific": target_specific,
            "generated_at": datetime.now().isoformat(),
            "freshness": guidance_freshness(source_dir),
        }
    )
    state["writing_guidance"] = metadata
    return metadata
