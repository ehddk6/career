from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
FINAL_MD_DIR = ROOT / "final_gate_20260705" / "final_gate_drafts"
OUT_DIR = ROOT / "final_gate_20260705" / "patina_batch_all"
STATE = ROOT / "final_gate_20260705" / "patina_batch_all_state.json"


USER_NPM_BIN = Path.home() / "AppData" / "Roaming" / "npm"
if USER_NPM_BIN.exists():
    os.environ["PATH"] = str(USER_NPM_BIN) + os.pathsep + os.environ.get("PATH", "")


def chunks(items: list[Path], size: int) -> list[list[Path]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    patina = shutil.which("patina.cmd") or shutil.which("patina") or "patina"
    files = sorted(FINAL_MD_DIR.glob("*.md"))
    completed = {path.name for path in OUT_DIR.glob("*.md")}
    pending = [path for path in files if path.name not in completed]
    state = {
        "total_files": len(files),
        "completed_files": len(completed),
        "pending_files": len(pending),
        "chunk_size": 10,
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    if not pending:
        print(json.dumps(state, ensure_ascii=False), flush=True)
        return 0
    for index, batch in enumerate(chunks(pending, 10), 1):
        print(f"[patina batch {index}] {len(batch)} files", flush=True)
        command = [
            patina,
            "--score",
            "--exit-on",
            "30",
            "--format",
            "json",
            "--backend",
            "codex-cli",
            "--timeout-ms",
            "180000",
            "--max-retries",
            "0",
            "--batch",
            "--outdir",
            str(OUT_DIR),
            "--max-failures",
            "999",
            *[str(path) for path in batch],
        ]
        completed_run = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=1800,
        )
        log_base = OUT_DIR / f"batch_{index:03d}"
        (log_base.with_suffix(".stdout.log")).write_text(
            completed_run.stdout,
            encoding="utf-8",
        )
        (log_base.with_suffix(".stderr.log")).write_text(
            completed_run.stderr,
            encoding="utf-8",
        )
        completed = {path.name for path in OUT_DIR.glob("*.md")}
        state = {
            "total_files": len(files),
            "completed_files": len(completed),
            "pending_files": len(files) - len(completed),
            "last_batch": index,
            "last_returncode": completed_run.returncode,
        }
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if completed_run.returncode not in (0, 3):
            print(json.dumps(state, ensure_ascii=False), flush=True)
            return completed_run.returncode or 1
    print(json.dumps(state, ensure_ascii=False), flush=True)
    return 0 if state["pending_files"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
