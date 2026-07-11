"""Writing strategy guidance from local YouTube frame analysis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


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


def _latest_frame_dir(root: Path) -> Path | None:
    base = root / "자료조사"
    if not base.exists():
        return None
    candidates = [path for path in base.glob(FRAME_DIR_GLOB) if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (path.name, path.stat().st_mtime), reverse=True)[0]


def _existing_source_files(source_dir: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for name, role in SOURCE_FILE_ROLES.items():
        path = source_dir / name
        if path.exists():
            files.append({"name": name, "path": str(path), "role": role})
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


def _render_guidance(source_dir: Path, source_files: list[dict[str, str]]) -> str:
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


def attach_writing_guidance(root: Path, run_dir: Path, state: dict) -> dict:
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

    source_files = _existing_source_files(source_dir)
    missing_files = [
        name for name in SOURCE_FILE_ROLES if not (source_dir / name).exists()
    ]
    artifact = run_dir / GUIDANCE_ARTIFACT
    artifact.write_text(_render_guidance(source_dir, source_files), encoding="utf-8")

    metadata.update(
        {
            "status": "available",
            "source_dir": str(source_dir),
            "artifact": str(artifact),
            "source_files": source_files,
            "missing_files": missing_files,
            "generated_at": datetime.now().isoformat(),
        }
    )
    state["writing_guidance"] = metadata
    return metadata
