from datetime import datetime
import json
from pathlib import Path
import re


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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def write_state(run_dir: Path, state: dict) -> None:
    write_json(run_dir / "run.json", state)
