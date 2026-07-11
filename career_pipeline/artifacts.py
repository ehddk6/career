"""최종 산출물 manifest 생성과 파일 무결성 검증."""

from datetime import datetime
import hashlib
import json
from pathlib import Path

from .state import write_json


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, run_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def write_final_artifact_manifest(
    run_dir: Path,
    *,
    selected_source: str,
    postprocess_attempted: bool,
    postprocess_applied: bool,
    model_tier: str | None,
    model_id: str | None,
    validation: dict,
) -> dict:
    files = {
        "answer_json": run_dir / "draft_final.json",
        "markdown": run_dir / "06_자기소개서.md",
        "docx": run_dir / "06_자기소개서.docx",
    }
    missing = [str(path.name) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"final artifact files missing: {', '.join(missing)}")
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "selected_source": selected_source,
        "answer_json_path": _relative(files["answer_json"], run_dir),
        "markdown_path": _relative(files["markdown"], run_dir),
        "docx_path": _relative(files["docx"], run_dir),
        "sha256": {
            name: sha256_file(path)
            for name, path in files.items()
        },
        "postprocess_attempted": postprocess_attempted,
        "postprocess_applied": postprocess_applied,
        "model_tier": model_tier,
        "model_id": model_id,
        "validation": validation,
    }
    write_json(run_dir / "12_최종산출물.json", payload)
    return payload


def load_and_verify_final_artifact(run_dir: Path, state: dict) -> tuple[dict | None, list[str]]:
    if "final_artifact" in state and state.get("final_artifact") is None:
        return None, ["최종 산출물 manifest가 아직 확정되지 않았습니다."]
    artifact = state.get("final_artifact")
    if not isinstance(artifact, dict):
        manifest = run_dir / "12_최종산출물.json"
        if manifest.exists():
            try:
                artifact = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                artifact = None
    if not isinstance(artifact, dict):
        return None, ["최종 산출물 manifest가 없습니다."]
    issues: list[str] = []
    for name, path_key in (
        ("answer_json", "answer_json_path"),
        ("markdown", "markdown_path"),
        ("docx", "docx_path"),
    ):
        raw_path = artifact.get(path_key)
        if not isinstance(raw_path, str) or not raw_path:
            issues.append(f"{name} 경로가 manifest에 없습니다.")
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = run_dir / path
        try:
            resolved_path = path.resolve()
            resolved_path.relative_to(run_dir.resolve())
        except (OSError, ValueError):
            issues.append(f"{name} 경로가 run 디렉터리 밖입니다: {raw_path}")
            continue
        if path.is_symlink():
            issues.append(f"{name} 심볼릭 링크는 허용되지 않습니다: {raw_path}")
            continue
        if not path.exists():
            issues.append(f"{name} 파일이 없습니다: {raw_path}")
            continue
        if not path.is_file():
            issues.append(f"{name} 경로가 일반 파일이 아닙니다: {raw_path}")
            continue
        expected = artifact.get("sha256", {}).get(name)
        actual = sha256_file(resolved_path)
        if expected != actual:
            issues.append(f"{name} SHA-256 불일치")
    return artifact, issues
