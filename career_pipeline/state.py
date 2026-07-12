"""실행 상태 관리. 원자적 JSON 저장과 실행 상태 이력을 담당합니다."""
from datetime import datetime
import json
from pathlib import Path
import re

from .path_policy import atomic_write_text


def resolve_run_dir(
    root: Path,
    target: str,
    run_name: str | None,
    resume: Path | None,
) -> Path:
    if resume:
        path = resume.resolve()
        if not (path / "run.json").exists():
            raise FileNotFoundError(f"resume run.json not found: {path}")
        return path

    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", run_name or target).strip("-")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = root / "career_runs" / f"{slug}-{stamp}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, payload) -> None:
    path = Path(path)
    data = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    atomic_write_text(path, data)


def write_state(run_dir: Path, state: dict) -> None:
    if "started_at" not in state:
        state["started_at"] = datetime.now().isoformat()
    history = state.setdefault("state_history", [])
    if not isinstance(history, list):
        history = []
        state["state_history"] = history
    status = state.get("status")
    blocked_stage = state.get("blocked_stage")
    previous = history[-1] if history else None
    if not previous or (
        not isinstance(previous, dict)
        or previous.get("status") != status
        or previous.get("blocked_stage") != blocked_stage
    ):
        history.append(
            {
                "recorded_at": datetime.now().isoformat(),
                "status": status,
                "blocked_stage": blocked_stage,
            }
        )
    write_json(run_dir / "run.json", state)
