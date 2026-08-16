from __future__ import annotations

import json
from pathlib import Path

from career_pipeline.orchestrator import finalize_run
from career_pipeline.rigorous_selection import subprocess_model_runner


class CachedRunner:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.rigorous = run_dir / "rigorous"
        self.package = json.loads(
            (self.rigorous / "data_package.json").read_text(encoding="utf-8")
        )

    def __call__(self, stage: str, prompt: str, model_id: str, timeout_ms: int):
        if stage.startswith("candidate_"):
            index = stage.rsplit("_", 1)[1]
            if stage == "candidate_repair_1":
                path = self.rigorous / "candidates" / "generated_1.json"
                responses = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "data_package_id": self.package["data_package_id"],
                    "data_package_version": self.package["data_package_version"],
                    "responses": responses,
                }
            raw_path = self.rigorous / "candidates" / f"generated_{index}_raw.json"
            return json.loads(raw_path.read_text(encoding="utf-8"))
        if stage.startswith("judge_"):
            name = stage[len("judge_") :]
            path = self.rigorous / "judges" / f"{name}.json"
            return json.loads(path.read_text(encoding="utf-8"))
        if stage == "synthesis":
            responses = json.loads(
                (self.rigorous / "synthesis.json").read_text(encoding="utf-8")
            )
            return {
                "data_package_id": self.package["data_package_id"],
                "data_package_version": self.package["data_package_version"],
                "responses": responses,
            }
        if stage == "final_comparison":
            return subprocess_model_runner(stage, prompt, model_id, timeout_ms)
        raise RuntimeError(f"unexpected cached stage: {stage}")


def main() -> None:
    run_dir = Path(__file__).resolve().parent / "career_pipeline_max_quality_retry"
    result = finalize_run(
        run_dir,
        max_model_calls=13,
        rigorous_runner=CachedRunner(run_dir),
        rigorous_timeout_ms=600_000,
        quality_profile="max_quality",
    )
    print(json.dumps({
        "status": result.get("status"),
        "rigorous_selection": result.get("rigorous_selection"),
        "final_artifact": result.get("final_artifact"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
