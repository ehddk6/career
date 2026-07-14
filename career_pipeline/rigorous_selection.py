"""Fail-closed independent candidate generation and blind selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import tempfile
from typing import Any, Callable

from .copyeditor_adapter import _resolved_codex_command
from .models import DraftResponse, ExperienceClaimRef, Question
from .state import write_json


WEIGHTS = {
    "question_fidelity": 20,
    "fact_accuracy": 20,
    "job_relevance": 15,
    "action_specificity": 15,
    "experience_allocation": 10,
    "interview_defensibility": 10,
    "korean_readability": 5,
    "applicant_distinctiveness": 3,
    "length_and_format": 2,
}
STRATEGIES = ("FACT_FIRST", "QUESTION_FIRST", "EXPERIENCE_DIVERSITY", "JOB_RELEVANCE")
STRATEGY_INSTRUCTIONS = {
    "FACT_FIRST": (
        "검증된 claim과 직접 행동을 최우선으로 하며, 결과와 기여 범위가 불명확하면 표현을 낮춘다."
    ),
    "QUESTION_FIRST": (
        "각 문항의 하위 요구를 먼저 분해하고 핵심 답을 첫 문단에 둔다. 기관 설명보다 질문에 직접 답한다."
    ),
    "EXPERIENCE_DIVERSITY": (
        "문항 1~3에는 가능한 한 서로 다른 confirmed experience_id를 배치한다. "
        "대체 경험이 있으면 재사용하지 말고, 재사용이 꼭 필요할 때만 더 높은 적합성 근거를 남긴다."
    ),
    "JOB_RELEVANCE": (
        "경험을 실제 업무의 확인·대조·기록·보고·안내·인계 행동으로 번역하고, "
        "인턴의 판단 권한을 넘는 결정을 주장하지 않는다."
    ),
}
JUDGES = ("RECRUITER", "JOB_FACT_AUDITOR", "KOREAN_EDITOR")
WEAKNESS_CODES = {
    "question_gap", "fact_risk", "job_gap", "action_gap", "experience_overlap",
    "interview_risk", "korean_style", "generic_voice", "format_risk",
}
WEAKNESS_ALIASES = {
    "LOW_APPLICANT_DISTINCTIVENESS": "generic_voice",
    "MINOR_SCOPE_DRIFT": "job_gap",
    "EXPERIENCE_REUSE": "experience_overlap",
    "EXPERIENCE_OVERALLOCATION": "experience_overlap",
    "ANSWER_REDUNDANCY": "korean_style",
}


class RigorousSelectionError(ValueError):
    pass


ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]


@dataclass(frozen=True)
class RigorousResult:
    responses: tuple[DraftResponse, ...]
    metadata: dict[str, Any]


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _json_schema(stage: str) -> dict[str, Any]:
    if stage.startswith("candidate") or stage == "synthesis":
        return {
            "type": "object", "additionalProperties": False,
            "required": ["data_package_id", "data_package_version", "responses"],
            "properties": {
                "data_package_id": {"type": "string"},
                "data_package_version": {"type": "string"},
                "responses": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["question_index", "answer", "evidence_paths", "experience_refs", "research_refs"],
                "properties": {
                    "question_index": {"type": "integer"}, "answer": {"type": "string"},
                    "evidence_paths": {"type": "array", "items": {"type": "string"}},
                    "experience_refs": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["experience_id", "claim_ids"],
                        "properties": {"experience_id": {"type": "string"}, "claim_ids": {"type": "array", "items": {"type": "string"}}},
                    }},
                    "research_refs": {"type": "array", "items": {"type": "string"}},
                },
            }}},
        }
    if stage.startswith("judge"):
        score_properties = {key: {"type": "integer", "minimum": 0, "maximum": weight} for key, weight in WEIGHTS.items()}
        return {
            "type": "object", "additionalProperties": False,
            "required": ["data_package_id", "data_package_version", "judge_mode", "evaluations"],
            "properties": {
                "data_package_id": {"type": "string"},
                "data_package_version": {"type": "string"},
                "judge_mode": {"type": "string"},
                "evaluations": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["candidate_id", "hard_fail", "hard_fail_reasons", "hard_fail_status", "hard_fail_type", "review_required", "scores", "total", "weakness_codes", "transferable_elements"],
                    "properties": {
                        "candidate_id": {"type": "string"}, "hard_fail": {"type": "boolean"},
                        "hard_fail_reasons": {"type": "array", "items": {"type": "string"}},
                        "hard_fail_status": {"type": "string", "enum": ["NONE", "REVIEW_REQUIRED", "CONFIRMED"]},
                        "hard_fail_type": {"type": ["string", "null"]},
                        "review_required": {"type": "array", "items": {"type": "string"}},
                        "scores": {"type": "object", "additionalProperties": False, "required": list(WEIGHTS), "properties": score_properties},
                        "total": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weakness_codes": {"type": "array", "items": {"type": "string"}},
                        "transferable_elements": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["question", "element_type", "exact_element", "reason", "fact_ids"],
                            "properties": {
                                "question": {"type": "string"},
                                "element_type": {"type": "string"},
                                "exact_element": {"type": "string"},
                                "reason": {"type": "string"},
                                "fact_ids": {"type": "array", "items": {"type": "string"}},
                            },
                        }},
                    },
                }},
            },
        }
    return {
        "type": "object", "additionalProperties": False,
        "required": ["data_package_id", "data_package_version", "choice", "hard_fail", "reason", "comparison_ready", "question_choices", "risk_audit", "remaining_risks"],
        "properties": {
            "data_package_id": {"type": "string"},
            "data_package_version": {"type": "string"},
            "choice": {"type": "string", "enum": ["X", "Y"]},
            "hard_fail": {"type": "object", "additionalProperties": False, "required": ["X", "Y"], "properties": {
                "X": {"type": "array", "items": {"type": "string"}}, "Y": {"type": "array", "items": {"type": "string"}},
            }},
            "reason": {"type": "string"},
            "comparison_ready": {"type": "boolean"},
            "question_choices": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    f"q{index}": {"type": "string", "enum": ["X", "Y"]}
                    for index in range(1, 5)
                },
                "required": [f"q{index}" for index in range(1, 5)],
            },
            "risk_audit": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "X": {"type": "array", "items": {"type": "string"}},
                    "Y": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["X", "Y"],
            },
            "remaining_risks": {"type": "array", "items": {"type": "string"}},
        },
    }


def subprocess_model_runner(stage: str, prompt: str, model_id: str, timeout_ms: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="career-rigorous-") as temp:
        temp_path = Path(temp)
        schema = temp_path / "schema.json"
        schema.write_text(json.dumps(_json_schema(stage), ensure_ascii=False), encoding="utf-8")
        command = _resolved_codex_command(temp_path, schema, resolve=True, model_id=model_id)
        completed = subprocess.run(
            command, input=prompt, text=True, encoding="utf-8", errors="strict",
            capture_output=True, timeout=max(1, timeout_ms // 1000 + 30),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if len(detail) > 2000:
                detail = detail[-2000:]
            suffix = f": {detail}" if detail else ""
            raise RigorousSelectionError(f"model call failed at {stage}{suffix}")
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RigorousSelectionError(f"invalid JSON at {stage}") from error
        if not isinstance(value, dict):
            raise RigorousSelectionError(f"non-object model output at {stage}")
        return value


def _coerce_payload(value: dict[str, Any] | str, stage: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise RigorousSelectionError(f"invalid JSON at {stage}") from error
    if not isinstance(value, dict):
        raise RigorousSelectionError(f"invalid object at {stage}")
    return value


def _validate_data_package_payload(
    payload: dict[str, Any], package_meta: dict[str, Any], stage: str
) -> None:
    if (
        payload.get("data_package_id") != package_meta["data_package_id"]
        or payload.get("data_package_version") != package_meta["data_package_version"]
    ):
        raise RigorousSelectionError(f"data package mismatch at {stage}")


def _responses(value: dict[str, Any], questions: list[Question], stage: str) -> tuple[DraftResponse, ...]:
    rows = value.get("responses")
    if not isinstance(rows, list):
        raise RigorousSelectionError(f"responses missing at {stage}")
    result: list[DraftResponse] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RigorousSelectionError(f"invalid response row at {stage}")
        refs = tuple(
            ExperienceClaimRef(
                str(item["experience_id"]), (), tuple(str(value) for value in item.get("claim_ids", []))
            )
            for item in row.get("experience_refs", [])
            if isinstance(item, dict) and item.get("experience_id")
        )
        result.append(DraftResponse(
            question_index=int(row["question_index"]), answer=str(row["answer"]),
            evidence_paths=tuple(str(item) for item in row.get("evidence_paths", [])),
            experience_refs=refs,
            research_refs=tuple(str(item) for item in row.get("research_refs", [])),
        ))
    expected = {item.index for item in questions}
    actual = [item.question_index for item in result]
    if set(actual) != expected or len(actual) != len(expected):
        raise RigorousSelectionError(f"question set mismatch at {stage}")
    return tuple(sorted(result, key=lambda item: item.question_index))


def _candidate_payload(responses: tuple[DraftResponse, ...]) -> list[dict[str, Any]]:
    return [asdict(item) for item in responses]


def _validate_judge(
    payload: dict[str, Any],
    judge: str,
    candidate_ids: set[str],
    package_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    _validate_data_package_payload(payload, package_meta, f"judge_{judge.lower()}")
    if payload.get("judge_mode") != judge:
        raise RigorousSelectionError(f"judge mode mismatch: {judge}")
    rows = payload.get("evaluations")
    if not isinstance(rows, list):
        raise RigorousSelectionError(f"judge evaluations missing: {judge}")
    ids = [row.get("candidate_id") for row in rows if isinstance(row, dict)]
    if set(ids) != candidate_ids or len(ids) != len(candidate_ids):
        raise RigorousSelectionError(f"candidate set mismatch: {judge}")
    for row in rows:
        required_fields = {
            "candidate_id", "hard_fail", "hard_fail_reasons", "hard_fail_status",
            "hard_fail_type", "review_required", "scores", "total",
            "weakness_codes", "transferable_elements",
        }
        if not required_fields.issubset(row):
            raise RigorousSelectionError(f"judge field schema mismatch: {judge}")
        scores = row.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(WEIGHTS):
            raise RigorousSelectionError(f"score schema mismatch: {judge}")
        if any(not isinstance(scores[key], int) or not 0 <= scores[key] <= WEIGHTS[key] for key in WEIGHTS):
            raise RigorousSelectionError(f"score range mismatch: {judge}")
        if row.get("total") != sum(scores.values()):
            raise RigorousSelectionError(f"score total mismatch: {judge}")
        codes = row.get("weakness_codes")
        if not isinstance(codes, list) or any(
            not isinstance(code, str)
            or (code not in WEAKNESS_CODES and code not in WEAKNESS_ALIASES)
            for code in codes
        ):
            raise RigorousSelectionError(f"weakness schema mismatch: {judge}")
        row["weakness_codes"] = [WEAKNESS_ALIASES.get(code, code) for code in codes]
        if not isinstance(row.get("hard_fail"), bool) or not isinstance(row.get("hard_fail_reasons"), list):
            raise RigorousSelectionError(f"hard fail schema mismatch: {judge}")
        status = row.get("hard_fail_status")
        if status not in {"NONE", "REVIEW_REQUIRED", "CONFIRMED"}:
            raise RigorousSelectionError(f"hard fail status mismatch: {judge}")
        fail_type = row.get("hard_fail_type")
        if fail_type is not None and fail_type not in {"DETERMINISTIC", "SEMANTIC"}:
            raise RigorousSelectionError(f"hard fail type mismatch: {judge}")
        if not isinstance(row["review_required"], list):
            raise RigorousSelectionError(f"review-required schema mismatch: {judge}")
        elements = row.get("transferable_elements")
        if not isinstance(elements, list):
            raise RigorousSelectionError(f"transferable-elements schema mismatch: {judge}")
        for element in elements:
            if not isinstance(element, dict) or not all(
                isinstance(element.get(key), str)
                for key in ("question", "element_type", "exact_element", "reason")
            ) or not isinstance(element.get("fact_ids", []), list):
                raise RigorousSelectionError(f"transferable-elements schema mismatch: {judge}")
    return rows


def _data_package_metadata(
    questions: list[Question], frozen_packet: dict[str, Any]
) -> dict[str, Any]:
    canonical = json.dumps(
        {"questions": [asdict(item) for item in questions], "frozen_packet": frozen_packet},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    modes = sorted({question.count_mode for question in questions})
    return {
        "data_package_id": f"SOL-DATA-{digest[:12].upper()}",
        "data_package_version": "1.1",
        "frozen_data_sha256": digest,
        "count_mode": modes[0] if len(modes) == 1 else "mixed",
        "candidate_count": len(STRATEGIES) + 1,
        "judge_count": len(JUDGES),
    }


def _row_hard_fail_status(row: dict[str, Any]) -> tuple[bool, bool]:
    """Return (deterministic_or_confirmed_fail, review_required)."""
    if "hard_fail_status" not in row and row.get("hard_fail") is True:
        # Backward-compatible judge payloads predate the semantic review state.
        return True, False
    status = row.get("hard_fail_status", "NONE")
    fail_type = row.get("hard_fail_type")
    if status == "CONFIRMED":
        return True, False
    return False, bool(status == "REVIEW_REQUIRED" or row.get("review_required"))


def _candidate_hard_fail(rows: list[dict[str, Any]]) -> tuple[bool, bool]:
    deterministic = False
    confirmed_semantic = 0
    review_required = False
    for row in rows:
        hard_fail, review = _row_hard_fail_status(row)
        review_required = review_required or review
        if hard_fail:
            if row.get("hard_fail_type") == "SEMANTIC":
                confirmed_semantic += 1
            else:
                deterministic = True
        elif row.get("hard_fail_status") == "REVIEW_REQUIRED":
            review_required = True
    # A semantic concern is only disqualifying after independent confirmation
    # by two judges. A JOB_FACT_AUDITOR confirmation is also sufficient.
    semantic_confirmed = confirmed_semantic >= 2 or any(
        row.get("judge_mode") == "JOB_FACT_AUDITOR"
        and row.get("hard_fail_status") == "CONFIRMED"
        and row.get("hard_fail_type") == "SEMANTIC"
        for row in rows
    )
    return deterministic or semantic_confirmed, review_required


def _agreed_transferable_elements(
    judge_rows: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Keep only elements independently named by at least two judges."""
    support: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rows in judge_rows:
        for row in rows:
            judge_mode = str(row.get("judge_mode", ""))
            for element in row.get("transferable_elements", []) or []:
                key = (
                    str(element.get("question", "")),
                    str(element.get("element_type", "")),
                    str(element.get("exact_element", "")),
                )
                if not all(key):
                    continue
                record = support.setdefault(
                    key,
                    {
                        "question": key[0],
                        "element_type": key[1],
                        "exact_element": key[2],
                        "reason": str(element.get("reason", "")),
                        "fact_ids": sorted(set(str(item) for item in element.get("fact_ids", []))),
                        "judges": set(),
                    },
                )
                record["judges"].add(judge_mode)
                record["fact_ids"] = sorted(
                    set(record["fact_ids"]) | set(str(item) for item in element.get("fact_ids", []))
                )
    result = []
    for record in support.values():
        if len(record["judges"]) >= 2:
            result.append({
                key: value
                for key, value in record.items()
                if key != "judges"
            } | {"judge_count": len(record["judges"])})
    return sorted(result, key=lambda item: (item["question"], item["element_type"], item["exact_element"]))


def _candidate_job_fit_score(
    responses: tuple[DraftResponse, ...], frozen_packet: dict[str, Any]
) -> int:
    """Small deterministic guard against a synthesis dropping job linkage."""
    posting = frozen_packet.get("posting", {})
    terms = [
        str(term).strip().casefold()
        for key in ("duties", "competencies")
        for term in posting.get(key, []) or []
        if str(term).strip()
    ]
    score = 0
    for response in responses:
        if response.question_index not in {1, 2, 3}:
            continue
        answer = response.answer.casefold()
        score += sum(1 for term in terms if term in answer)
        score += sum(
            1 for marker in ("확인", "대조", "보고", "인계") if marker in answer
        )
    return score


def _prompt_data(questions: list[Question], frozen_packet: dict[str, Any]) -> str:
    return json.dumps({"questions": [asdict(item) for item in questions], "frozen_packet": frozen_packet}, ensure_ascii=False)


def run_rigorous_selection(
    run_dir: Path,
    *,
    questions: list[Question],
    incumbent: tuple[DraftResponse, ...],
    frozen_packet: dict[str, Any],
    model_id: str | None,
    validate_candidate: Callable[[list[DraftResponse]], list[Any]],
    runner: ModelRunner = subprocess_model_runner,
    max_calls: int = 9,
    timeout_ms: int = 300_000,
) -> RigorousResult:
    if not model_id or "sol" not in model_id.casefold():
        raise RigorousSelectionError("rigorous selection requires a configured Sol model ID")
    if max_calls < 9:
        raise RigorousSelectionError("rigorous selection requires a 9-call budget")
    rigorous_dir = run_dir / "rigorous"
    (rigorous_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (rigorous_dir / "judges").mkdir(parents=True, exist_ok=True)
    calls: list[dict[str, str]] = []
    candidates: dict[str, tuple[DraftResponse, ...]] = {"incumbent": incumbent}
    package_meta = _data_package_metadata(questions, frozen_packet)
    write_json(rigorous_dir / "data_package.json", package_meta)
    data = _prompt_data(questions, frozen_packet)
    private_mapping: dict[str, str] = {}
    candidate_failures: list[dict[str, Any]] = []
    for index, strategy in enumerate(STRATEGIES, 1):
        stage = f"candidate_{index}"
        prompt = (
            "Create one complete Korean self-introduction set from the frozen data only. "
            "Do not invent facts. Return JSON only. Keep the data package ID and version fixed. "
            "Every experience-based question MUST include at least one exact experience_id and "
            "claim_id in experience_refs; every research-only question MUST include research_refs. "
            "Evidence paths for experience claims are hydrated from claim IDs. "
            "A claim with contribution=observed cannot be described as a personally caused improvement. "
            "Use a numeric expression from an experience only when that exact numeric token appears "
            "in the referenced claim's normalized_value and the claim is submission-safe; numbers "
            "visible only in situation, actions or outcomes are context, not authorization. "
            "Research numbers may be used only when the referenced research claim contains them. "
            "For every research_ref, repeat the referenced claim's core wording or numeric fact in the "
            "answer; never attach a research_ref that is not visibly used. "
            "Avoid repeating the same experience across questions 1-3 when a confirmed alternative exists. "
            "Respect safe length targets: questions 1-3 should be 500-550 characters including spaces, "
            "and question 4 should be 1150-1350 characters including spaces while staying under its maximum. "
            "For question 1 state a personal reason for choosing this institution and role. "
            "For question 2 connect the stated attitude to at least one named duty from the job packet, "
            "such as credit-guarantee extension or ongoing corporate-credit management. "
            "For question 3 name 신용보증기금 and its actual duty, then describe an explicit initial-learning, "
            "execution, checking and handoff sequence rather than only listing general work habits. "
            "Private strategy: " + strategy + " — " + STRATEGY_INSTRUCTIONS[strategy] + "\n"
            + json.dumps(package_meta, ensure_ascii=False)
            + "\n"
            + data
        )
        payload = _coerce_payload(runner(stage, prompt, model_id, timeout_ms), stage)
        raw_path = rigorous_dir / "candidates" / f"generated_{index}_raw.json"
        write_json(raw_path, payload)
        _validate_data_package_payload(payload, package_meta, stage)
        responses = _responses(payload, questions, stage)
        candidate_responses = list(responses)
        issues = validate_candidate(candidate_responses)
        if issues:
            candidate_failures.append({
                "stage": stage,
                "codes": [issue.code for issue in issues],
                "question_indexes": sorted({issue.question_index for issue in issues}),
            })
            write_json(rigorous_dir / "candidate_failures.json", candidate_failures)
            raise RigorousSelectionError(f"deterministic candidate validation failed at {stage}: {issues[0].code}")
        responses = tuple(candidate_responses)
        internal_id = f"generated_{index}"
        candidates[internal_id] = responses
        private_mapping[internal_id] = strategy
        path = rigorous_dir / "candidates" / f"{internal_id}.json"
        write_json(path, _candidate_payload(responses))
        calls.append({"stage": stage, "model_id": model_id})
    if candidate_failures:
        write_json(rigorous_dir / "candidate_failures.json", candidate_failures)
    write_json(rigorous_dir / "private_mapping.json", private_mapping)

    blinded: dict[str, tuple[DraftResponse, ...]] = {}
    for internal_id, responses in candidates.items():
        digest = sha256(json.dumps(_candidate_payload(responses), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8].upper()
        blinded[f"C{digest}"] = responses
    blind_payload = {candidate_id: _candidate_payload(responses) for candidate_id, responses in sorted(blinded.items())}
    write_json(rigorous_dir / "blind_candidates.json", blind_payload)
    if any(strategy in json.dumps(blind_payload, ensure_ascii=False) for strategy in STRATEGIES):
        raise RigorousSelectionError("private strategy leaked into blind payload")

    judge_rows: list[list[dict[str, Any]]] = []
    for judge in JUDGES:
        stage = f"judge_{judge.lower()}"
        prompt = (
            "Independently score every anonymous candidate. Use the fixed weights, identify HARD FAILs, "
            "classify deterministic failures separately from semantic REVIEW_REQUIRED findings, "
            "record transferable elements only when they are grounded in fact IDs, and return JSON only. "
            "Use only these weakness_codes: question_gap, fact_risk, job_gap, action_gap, "
            "experience_overlap, interview_risk, korean_style, generic_voice, format_risk. "
            "Do not invent or translate code names. "
            "Do not rewrite.\n"
            + json.dumps({"judge_mode": judge, "weights": WEIGHTS, "data_package": package_meta, "data": frozen_packet, "questions": [asdict(q) for q in questions], "candidates": blind_payload}, ensure_ascii=False)
        )
        payload = _coerce_payload(runner(stage, prompt, model_id, timeout_ms), stage)
        raw_judge_path = rigorous_dir / "judges" / f"{judge.lower()}_raw.json"
        write_json(raw_judge_path, payload)
        try:
            rows = _validate_judge(payload, judge, set(blinded), package_meta)
        except RigorousSelectionError as error:
            write_json(
                rigorous_dir / "judge_failures.json",
                [{"stage": stage, "error": str(error)}],
            )
            raise
        for row in rows:
            row["judge_mode"] = judge
        judge_rows.append(rows)
        write_json(rigorous_dir / "judges" / f"{judge.lower()}.json", payload)
        calls.append({"stage": stage, "model_id": model_id})

    aggregate = []
    for candidate_id in blinded:
        rows = [next(row for row in judge if row["candidate_id"] == candidate_id) for judge in judge_rows]
        totals = [row["total"] for row in rows]
        candidate_fail, review_required = _candidate_hard_fail(rows)
        aggregate.append({
            "candidate_id": candidate_id,
            "hard_fail": candidate_fail,
            "review_required": review_required,
            "median_total": median(totals), "minimum_total": min(totals),
            "median_core": median(row["scores"]["question_fidelity"] + row["scores"]["fact_accuracy"] + row["scores"]["job_relevance"] for row in rows),
            "judge_spread": max(totals) - min(totals),
        })
    eligible = [row for row in aggregate if not row["hard_fail"]]
    if not eligible:
        raise RigorousSelectionError("every candidate received HARD FAIL")
    eligible.sort(key=lambda row: (row["median_total"], row["median_core"], row["minimum_total"]), reverse=True)
    winner_id = eligible[0]["candidate_id"]
    weakness_counts = {code: 0 for code in WEAKNESS_CODES}
    for rows in judge_rows:
        winner_row = next(row for row in rows if row["candidate_id"] == winner_id)
        for code in set(winner_row["weakness_codes"]):
            weakness_counts[code] += 1
    agreed = sorted(code for code, count in weakness_counts.items() if count >= 2)
    agreed_transferable = _agreed_transferable_elements(judge_rows)
    write_json(
        rigorous_dir / "aggregate.json",
        {
            "ranking": eligible,
            "agreed_weaknesses": agreed,
            "agreed_transferable_elements": agreed_transferable,
        },
    )

    baseline = blinded[winner_id]
    synthesis = baseline
    if agreed or agreed_transferable:
        stage = "synthesis"
        prompt = (
            "Minimally revise the winning set only for the agreed weaknesses. Preserve facts, claim IDs, "
            "experience allocation and limits. Do not add an experience merely to increase length. "
            "Return JSON only.\n"
            + json.dumps({"data_package": package_meta, "weaknesses": agreed, "transferable_elements": agreed_transferable, "winner": _candidate_payload(baseline), "frozen_packet": frozen_packet, "questions": [asdict(q) for q in questions]}, ensure_ascii=False)
        )
        synthesis_payload = _coerce_payload(runner(stage, prompt, model_id, timeout_ms), stage)
        _validate_data_package_payload(synthesis_payload, package_meta, stage)
        synthesis = _responses(synthesis_payload, questions, stage)
        synthesis_responses = list(synthesis)
        issues = validate_candidate(synthesis_responses)
        if issues:
            synthesis = baseline
        else:
            synthesis = tuple(synthesis_responses)
        calls.append({"stage": stage, "model_id": model_id})
        write_json(rigorous_dir / "synthesis.json", _candidate_payload(synthesis))

    stage = "final_comparison"
    comparison_prompt = (
        "Blindly choose X or Y. Reject any new fact, weaker causality, question gap or length violation. "
        "Choose one complete version; do not create a mixed version. Record question-level choices and "
        "remaining fact, interview, duplication and style risks. Return JSON only.\n"
        + json.dumps({"data_package": package_meta, "frozen_packet": frozen_packet, "questions": [asdict(q) for q in questions], "X": _candidate_payload(baseline), "Y": _candidate_payload(synthesis)}, ensure_ascii=False)
    )
    comparison = _coerce_payload(runner(stage, comparison_prompt, model_id, timeout_ms), stage)
    _validate_data_package_payload(comparison, package_meta, stage)
    comparison_fields = {
        "choice", "hard_fail", "reason", "comparison_ready", "question_choices",
        "risk_audit", "remaining_risks",
    }
    if not comparison_fields.issubset(comparison):
        raise RigorousSelectionError("final comparison schema mismatch")
    if comparison.get("choice") not in {"X", "Y"} or not isinstance(comparison.get("hard_fail"), dict):
        raise RigorousSelectionError("invalid final comparison")
    if not isinstance(comparison.get("comparison_ready"), bool):
        raise RigorousSelectionError("invalid final comparison readiness")
    if not isinstance(comparison.get("question_choices"), dict) or not isinstance(comparison.get("risk_audit"), dict):
        raise RigorousSelectionError("invalid final comparison audit")
    if not isinstance(comparison.get("remaining_risks"), list):
        raise RigorousSelectionError("invalid final comparison risks")
    if comparison.get("comparison_ready") is False:
        raise RigorousSelectionError("final comparison is not ready")
    selected = baseline if comparison["choice"] == "X" else synthesis
    if comparison["choice"] == "Y":
        baseline_fit = _candidate_job_fit_score(baseline, frozen_packet)
        synthesis_fit = _candidate_job_fit_score(synthesis, frozen_packet)
        if synthesis_fit < baseline_fit:
            comparison["choice"] = "X"
            comparison["reason"] = (
                str(comparison.get("reason", ""))
                + f" Deterministic safety guard retained X because job-linkage score "
                f"{synthesis_fit} was below X's {baseline_fit}."
            ).strip()
            selected = baseline
    issues = validate_candidate(list(selected))
    if issues:
        raise RigorousSelectionError(f"final deterministic validation failed: {issues[0].code}")
    calls.append({"stage": stage, "model_id": model_id})
    write_json(rigorous_dir / "final_comparison.json", comparison)
    selected_path = rigorous_dir / "selected.json"
    write_json(selected_path, _candidate_payload(selected))

    artifact_paths = [
        path for path in rigorous_dir.rglob("*.json")
        if path.name != "private_mapping.json"
    ]
    metadata = {
        "status": "passed", "selection_mode": "rigorous", "model_id": model_id,
        "call_count": len(calls), "calls": calls, "winner_candidate_id": winner_id,
        "final_choice": comparison["choice"], "final_reason": comparison.get("reason", ""),
        "hard_fail": False,
        "data_package": package_meta,
        "candidate_count": len(blinded),
        "judge_count": len(JUDGES),
        "review_required_candidates": [row["candidate_id"] for row in aggregate if row.get("review_required")],
        "artifact_sha256": {str(path.relative_to(run_dir)): _sha(path) for path in sorted(artifact_paths)},
    }
    write_json(rigorous_dir / "manifest.json", metadata)
    return RigorousResult(selected, metadata)
