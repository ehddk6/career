"""동일 입력의 익명 품질 비교를 검증하고 과장 없는 판정을 만든다."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Literal

from .copyeditor_adapter import _resolved_codex_command


BENCHMARK_SECTIONS: dict[str, tuple[str, ...]] = {
    "company_research": (
        "business_model_depth",
        "strategy_execution_evidence",
        "recency",
        "source_traceability",
        "role_connection",
        "motivation_reusability",
        "prohibited_claim_control",
        "specificity_without_generalities",
    ),
    "self_intro": (
        "question_fidelity",
        "fact_accuracy",
        "contribution_boundary",
        "action_and_judgment_specificity",
        "experience_allocation",
        "job_relevance",
        "company_specificity",
        "applicant_distinctiveness",
        "natural_korean",
        "length_and_format",
        "interview_defensibility",
    ),
    "interview": (
        "question_relevance",
        "probe_depth",
        "submitted_claim_traceability",
        "spoken_answer_quality",
        "unknown_question_response",
        "fact_boundary_under_pressure",
        "retry_goal_specificity",
    ),
}


BenchmarkVerdict = Literal[
    "ALL_DIMENSIONS_AHEAD",
    "IMPROVED",
    "MIXED",
    "HARD_FAIL",
]


@dataclass(frozen=True)
class BenchmarkResult:
    verdict: BenchmarkVerdict
    baseline_wins: int
    challenger_wins: int
    ties: int
    section_results: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "baseline_wins": self.baseline_wins,
            "challenger_wins": self.challenger_wins,
            "ties": self.ties,
            "section_results": self.section_results,
        }


def benchmark_template(
    *, data_package_id: str, baseline_label: str, challenger_label: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "data_package_id": data_package_id,
        "systems": {"A": baseline_label, "B": challenger_label},
        "blind_protocol": {
            "system_labels_hidden": True,
            "strategy_metadata_removed": True,
            "file_order_randomized": True,
        },
        "hard_fail": {"A": [], "B": []},
        "sections": {
            section: {
                dimension: {
                    "choice": "TIE",
                    "reason": "PENDING",
                    "decisive_difference": "PENDING",
                    "evidence_refs": [],
                }
                for dimension in dimensions
            }
            for section, dimensions in BENCHMARK_SECTIONS.items()
        },
    }


def write_benchmark_template(
    output: Path,
    *,
    data_package_id: str,
    baseline_label: str,
    challenger_label: str,
) -> Path:
    if output.exists():
        raise FileExistsError(f"benchmark file already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            benchmark_template(
                data_package_id=data_package_id,
                baseline_label=baseline_label,
                challenger_label=challenger_label,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def evaluate_benchmark(payload: dict[str, Any]) -> BenchmarkResult:
    if payload.get("schema_version") != 1:
        raise ValueError("benchmark schema_version must be 1")
    if not str(payload.get("data_package_id", "")).strip():
        raise ValueError("benchmark data_package_id is required")
    systems = payload.get("systems")
    if not isinstance(systems, dict) or set(systems) != {"A", "B"}:
        raise ValueError("benchmark systems must contain anonymous A and B labels")
    blind = payload.get("blind_protocol")
    if not isinstance(blind, dict) or any(
        blind.get(key) is not True
        for key in (
            "system_labels_hidden",
            "strategy_metadata_removed",
            "file_order_randomized",
        )
    ):
        raise ValueError("benchmark blind protocol is incomplete")
    hard_fail = payload.get("hard_fail")
    if not isinstance(hard_fail, dict) or set(hard_fail) != {"A", "B"} or any(
        not isinstance(hard_fail[side], list) for side in ("A", "B")
    ):
        raise ValueError("benchmark hard_fail audit is invalid")

    if hard_fail["B"]:
        return BenchmarkResult("HARD_FAIL", 0, 0, 0, {})

    sections = payload.get("sections")
    if not isinstance(sections, dict) or set(sections) != set(BENCHMARK_SECTIONS):
        raise ValueError("benchmark section set mismatch")
    counts = {"A": 0, "B": 0, "TIE": 0}
    section_results: dict[str, str] = {}
    all_challenger = True
    for section, dimensions in BENCHMARK_SECTIONS.items():
        rows = sections.get(section)
        if not isinstance(rows, dict) or set(rows) != set(dimensions):
            raise ValueError(f"benchmark dimension set mismatch: {section}")
        local = {"A": 0, "B": 0, "TIE": 0}
        for dimension in dimensions:
            item = rows[dimension]
            if not isinstance(item, dict):
                raise ValueError(f"invalid benchmark result: {section}.{dimension}")
            choice = item.get("choice")
            if choice not in {"A", "B", "TIE"}:
                raise ValueError(f"invalid benchmark choice: {section}.{dimension}")
            reason = str(item.get("reason", "")).strip()
            decisive = str(item.get("decisive_difference", "")).strip()
            refs = item.get("evidence_refs")
            if not reason or not decisive or not isinstance(refs, list):
                raise ValueError(f"incomplete benchmark rationale: {section}.{dimension}")
            if reason == "PENDING" or decisive == "PENDING":
                raise ValueError(f"pending benchmark result: {section}.{dimension}")
            counts[choice] += 1
            local[choice] += 1
            all_challenger = all_challenger and choice == "B"
        if local["B"] > local["A"]:
            section_results[section] = "B"
        elif local["A"] > local["B"]:
            section_results[section] = "A"
        else:
            section_results[section] = "TIE"

    if all_challenger:
        verdict: BenchmarkVerdict = "ALL_DIMENSIONS_AHEAD"
    elif counts["B"] > counts["A"] and all(
        result != "A" for result in section_results.values()
    ):
        verdict = "IMPROVED"
    else:
        verdict = "MIXED"
    return BenchmarkResult(
        verdict,
        baseline_wins=counts["A"],
        challenger_wins=counts["B"],
        ties=counts["TIE"],
        section_results=section_results,
    )


def load_and_evaluate_benchmark(path: Path) -> BenchmarkResult:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark input must be a JSON object")
    return evaluate_benchmark(value)


_REDACT_KEYS = {
    "model_id",
    "quality_profile",
    "private_mapping",
    "run_dir",
    "strategy",
    "stage_models",
    "system",
    "systems",
}


def _sanitize_artifact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_artifact(item)
            for key, item in value.items()
            if str(key).casefold() not in _REDACT_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_artifact(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"(?i)career[ _-]?pipeline|external[ _-]?prompt(?:s)?",
            "[SYSTEM]",
            value,
        )
    return value


def _artifact_rows(paths: list[Path], label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, path in enumerate(paths, 1):
        raw = path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            content: Any = _sanitize_artifact(raw)
            content_type = "text"
        else:
            content = _sanitize_artifact(parsed)
            content_type = "json"
        rows.append(
            {
                "artifact_id": f"{label}{index}",
                "content_type": content_type,
                "content_sha256": sha256(raw.encode("utf-8")).hexdigest(),
                "content": content,
            }
        )
    return rows


def _benchmark_judge_schema() -> dict[str, Any]:
    detail = {
        "type": "object",
        "additionalProperties": False,
        "required": ["choice", "reason", "decisive_difference", "evidence_refs"],
        "properties": {
            "choice": {"type": "string", "enum": ["X", "Y", "TIE"]},
            "reason": {"type": "string"},
            "decisive_difference": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["hard_fail", "sections"],
        "properties": {
            "hard_fail": {
                "type": "object",
                "additionalProperties": False,
                "required": ["X", "Y"],
                "properties": {
                    "X": {"type": "array", "items": {"type": "string"}},
                    "Y": {"type": "array", "items": {"type": "string"}},
                },
            },
            "sections": {
                "type": "object",
                "additionalProperties": False,
                "required": list(BENCHMARK_SECTIONS),
                "properties": {
                    section: {
                        "type": "object",
                        "additionalProperties": False,
                        "required": list(dimensions),
                        "properties": {dimension: detail for dimension in dimensions},
                    }
                    for section, dimensions in BENCHMARK_SECTIONS.items()
                },
            },
        },
    }


def subprocess_benchmark_judge(
    prompt: str, *, model_id: str, timeout_ms: int
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="career-benchmark-") as temp:
        temp_path = Path(temp)
        schema = temp_path / "schema.json"
        schema.write_text(
            json.dumps(_benchmark_judge_schema(), ensure_ascii=False), encoding="utf-8"
        )
        command = _resolved_codex_command(
            temp_path, schema, resolve=True, model_id=model_id
        )
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            timeout=max(1, timeout_ms // 1000 + 30),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
            raise ValueError(f"benchmark model call failed: {detail}")
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("benchmark model returned invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("benchmark model returned a non-object")
        return value


def run_blind_benchmark(
    output: Path,
    *,
    data_package_id: str,
    baseline_label: str,
    challenger_label: str,
    baseline_files: list[Path],
    challenger_files: list[Path],
    model_id: str,
    timeout_ms: int = 600_000,
) -> BenchmarkResult:
    if output.exists():
        raise FileExistsError(f"benchmark file already exists: {output}")
    if not baseline_files or not challenger_files:
        raise ValueError("both benchmark systems require at least one artifact")
    for path in baseline_files + challenger_files:
        if not path.is_file():
            raise FileNotFoundError(path)

    baseline_rows = _artifact_rows(baseline_files, "B")
    challenger_rows = _artifact_rows(challenger_files, "C")
    assignment_digest = sha256(
        (data_package_id + "\0" + json.dumps([baseline_rows, challenger_rows], ensure_ascii=False, sort_keys=True)).encode("utf-8")
    ).hexdigest()
    baseline_side = "X" if int(assignment_digest[0], 16) % 2 == 0 else "Y"
    challenger_side = "Y" if baseline_side == "X" else "X"
    anonymous = {
        baseline_side: baseline_rows,
        challenger_side: challenger_rows,
    }
    prompt = (
        "Blindly compare two Korean career-output systems built from the same frozen input. "
        "Do not infer identities from formatting. HARD FAIL includes unsupported personal facts, contribution "
        "overstatement, unverified metrics, prohibited claims, missing required question content, or claim-defense "
        "mismatch. If one side has a HARD FAIL, record it before quality comparison. Evidence that caused or depends "
        "on a HARD FAIL must not earn an advantage in any quality dimension; compare only defensible evidence and "
        "safe alternative artifacts from that side. In particular, unsupported numbers cannot win applicant "
        "distinctiveness or spoken-answer quality. A numeric personal experience used in a submitted answer requires "
        "D4 defense; D3 or lower is a HARD FAIL even when the source text itself is confirmed. For every fixed dimension choose "
        "X, Y, or TIE and cite artifact_id plus a precise field, question or heading. A longer output is not inherently "
        "better. Prefer traceable evidence, concrete applicant action, natural Korean and interview usability. "
        "Return JSON only.\n"
        + json.dumps(
            {
                "data_package_id": data_package_id,
                "dimensions": BENCHMARK_SECTIONS,
                "artifacts": anonymous,
            },
            ensure_ascii=False,
        )
    )
    judged = subprocess_benchmark_judge(
        prompt, model_id=model_id, timeout_ms=timeout_ms
    )
    side_to_canonical = {baseline_side: "A", challenger_side: "B", "TIE": "TIE"}
    payload = benchmark_template(
        data_package_id=data_package_id,
        baseline_label=baseline_label,
        challenger_label=challenger_label,
    )
    hard_fail = judged.get("hard_fail")
    sections = judged.get("sections")
    if not isinstance(hard_fail, dict) or not isinstance(sections, dict):
        raise ValueError("benchmark judge schema mismatch")
    payload["hard_fail"] = {
        "A": list(hard_fail.get(baseline_side, [])),
        "B": list(hard_fail.get(challenger_side, [])),
    }
    for section, dimensions in BENCHMARK_SECTIONS.items():
        for dimension in dimensions:
            item = sections[section][dimension]
            payload["sections"][section][dimension] = {
                **item,
                "choice": side_to_canonical[item["choice"]],
            }
    payload["blind_protocol"]["assignment_sha256"] = assignment_digest
    payload["judge_model_id"] = model_id
    payload["artifact_manifest"] = {
        "A": [
            {key: row[key] for key in ("artifact_id", "content_sha256", "content_type")}
            for row in baseline_rows
        ],
        "B": [
            {key: row[key] for key in ("artifact_id", "content_sha256", "content_type")}
            for row in challenger_rows
        ],
    }
    result = evaluate_benchmark(payload)
    payload["result"] = result.to_dict()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result
