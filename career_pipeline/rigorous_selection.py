"""Fail-closed independent candidate generation and blind selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import shutil
import tempfile
from typing import Any, Callable

from .copyeditor_adapter import _resolved_codex_command
from .models import DraftResponse, ExperienceClaimRef, Question
from .prompt_contracts import validate_blind_comparison_payload
from .quality_profiles import QualityProfile, legacy_rigorous_profile
from .state import write_json
from .style_diagnostics import diagnose_responses, style_repair_details


WEIGHTS = {
    "question_fidelity": 14,
    "fact_accuracy": 15,
    "job_relevance": 11,
    "company_specificity": 10,
    "action_specificity": 12,
    "experience_allocation": 8,
    "interview_defensibility": 8,
    "spoken_defensibility": 5,
    "korean_readability": 8,
    "applicant_distinctiveness": 8,
    "length_and_format": 1,
}
STRATEGIES = (
    "FACT_QUESTION_SAFE",
    "FACT_FIRST",
    "QUESTION_FIRST",
    "EXPERIENCE_DIVERSITY",
    "JOB_RELEVANCE",
    "JOB_COMPANY_FIT",
    "NATURAL_VOICE",
    "INTERVIEW_DEFENSE",
    "APPLICANT_DISTINCTIVENESS",
)
STRATEGY_INSTRUCTIONS = {
    "FACT_QUESTION_SAFE": (
        "검증된 사실 범위 안에서 문항의 모든 하위 요구를 빠짐없이 답한다. "
        "첫 두 문장에서 결론을 제시하고 근거 없는 수식은 쓰지 않는다."
    ),
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
    "JOB_COMPANY_FIT": (
        "안전한 회사 claim 한두 개를 직무의 현실적인 행동과 연결한다. 회사 홍보문구를 나열하지 말고 "
        "지원자의 선택 기준→검증된 회사 고유 사실→직무 행동→확정 경험→초기 기여의 흐름으로 쓴다."
    ),
    "NATURAL_VOICE": (
        "지원자가 실제로 말할 법한 담백한 한국어를 쓴다. 추상명사 나열, 같은 길이 문장, 상투적인 "
        "결론, 과도한 연결어를 피하고 구체적인 동사와 장단문 리듬을 사용한다. 화려한 표현보다 "
        "한 문항에 하나의 선명한 장면과 판단을 남긴다."
    ),
    "INTERVIEW_DEFENSE": (
        "각 핵심 문장을 추가질문으로 방어할 수 있게 직접 행동·판단 기준·기여 범위·한계를 함께 둔다. "
        "소리 내어 60초 안팎으로 설명하기 어려운 문장 구조와 암기식 장문을 피한다."
    ),
    "APPLICANT_DISTINCTIVENESS": (
        "문항마다 확정 원장에서 가장 기억에 남는 서로 다른 장면과 직접 행동을 고른다. "
        "수치 산식이 불완전하면 숫자는 빼되 행동·대상·도구·판단의 구체성은 보존한다. "
        "일정 관리처럼 누구에게나 가능한 습관보다 이용자 불편 개선, 자료 대조, 분류·보고처럼 "
        "지원자만의 확인된 행동을 우선한다."
    ),
}
JUDGES = ("RECRUITER", "JOB_FACT_AUDITOR", "KOREAN_EDITOR", "INTERVIEW_COACH")
JUDGE_INSTRUCTIONS = {
    "RECRUITER": (
        "문항 직접성, 기억에 남는 구체성, 지원자 고유성, 회사·직무 선택 논리와 실제 채용 활용성을 본다."
    ),
    "JOB_FACT_AUDITOR": (
        "원장·공고·회사 claim·수치·기여 범위·인과관계와 직무 권한을 대조한다. 의심을 사실처럼 확정하지 않는다."
    ),
    "KOREAN_EDITOR": (
        "소리 내어 읽었을 때의 자연스러움, 문장 호응, 장단문 리듬, 추상명사·상투어·기계적 병렬을 본다. "
        "단순히 화려하거나 긴 문장에 점수를 주지 않는다."
    ),
    "INTERVIEW_COACH": (
        "핵심 주장별 추가질문 방어, 말하기 용이성, 수치 산출·개인 기여·한계 설명, 모르는 범위 인정 가능성을 본다."
    ),
}
WEAKNESS_CODES = {
    "question_gap", "fact_risk", "job_gap", "action_gap", "experience_overlap",
    "interview_risk", "spoken_answer_risk", "korean_style", "generic_voice",
    "company_genericity", "format_risk",
}
WEAKNESS_ALIASES = {
    "LOW_APPLICANT_DISTINCTIVENESS": "generic_voice",
    "MINOR_SCOPE_DRIFT": "job_gap",
    "EXPERIENCE_REUSE": "experience_overlap",
    "EXPERIENCE_OVERALLOCATION": "experience_overlap",
    "ANSWER_REDUNDANCY": "korean_style",
}
HARD_FAIL_TYPE_ALIASES = {
    # Models sometimes make the deterministic failure category more
    # specific. Keep the fail-closed meaning while normalizing the value
    # before the rest of the selection logic evaluates it.
    "DETERMINISTIC_FORMAT": "DETERMINISTIC",
}


def _normalized_hard_fail_type(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = HARD_FAIL_TYPE_ALIASES.get(value, value)
    if normalized.startswith("DETERMINISTIC_"):
        return "DETERMINISTIC"
    if normalized.startswith("SEMANTIC_"):
        return "SEMANTIC"
    upper = normalized.upper()
    if any(token in upper for token in ("FORMAT", "LENGTH", "LIMIT_EXCEEDED")):
        return "DETERMINISTIC"
    return normalized


def _reset_rigorous_directory(run_dir: Path, rigorous_dir: Path) -> None:
    """Remove only the derived rigorous artifact directory before a rerun."""
    resolved_run = run_dir.resolve()
    resolved_rigorous = rigorous_dir.resolve()
    if resolved_rigorous.parent != resolved_run or resolved_rigorous.name != "rigorous":
        raise RigorousSelectionError("unsafe rigorous artifact directory")
    if resolved_rigorous.exists():
        shutil.rmtree(resolved_rigorous)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _resume_generated_candidates(
    rigorous_dir: Path,
    *,
    package_meta: dict[str, Any],
    strategies: tuple[str, ...],
    questions: list[Question],
    validate_candidate: Callable[[list[DraftResponse]], list[Any]],
) -> tuple[dict[str, tuple[DraftResponse, ...]], dict[str, str]] | None:
    """Load package-matched valid candidates from a partial or complete checkpoint."""
    stored_meta = _read_json_object(rigorous_dir / "data_package.json")
    mapping = _read_json_object(rigorous_dir / "private_mapping.json")
    if stored_meta != package_meta:
        return None
    expected_ids = {f"generated_{index}" for index in range(1, len(strategies) + 1)}
    expected_mapping = {
        f"generated_{index}": strategy
        for index, strategy in enumerate(strategies, 1)
    }
    if mapping is not None and any(
        str(mapping.get(internal_id, expected_mapping[internal_id])) != expected_mapping[internal_id]
        for internal_id in expected_ids
    ):
        return None
    candidates: dict[str, tuple[DraftResponse, ...]] = {}
    for internal_id in sorted(expected_ids):
        path = rigorous_dir / "candidates" / f"{internal_id}.json"
        if not path.is_file():
            continue
        responses = _read_valid_candidate_file(
            path,
            questions=questions,
            validate_candidate=validate_candidate,
            stage=f"resume_{internal_id}",
        )
        if responses is not None:
            candidates[internal_id] = responses
    return candidates, expected_mapping


def _read_valid_candidate_file(
    path: Path,
    *,
    questions: list[Question],
    validate_candidate: Callable[[list[DraftResponse]], list[Any]],
    stage: str,
) -> tuple[DraftResponse, ...] | None:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        responses = _responses({"responses": rows}, questions, stage)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RigorousSelectionError):
        return None
    return responses if not validate_candidate(list(responses)) else None


class RigorousSelectionError(ValueError):
    pass


def write_checkpoint_hybrid(run_dir: Path, output: Path) -> Path:
    """Write a non-destructive hybrid from completed blind-judge checkpoints."""
    run_dir = run_dir.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"hybrid output already exists: {output}")
    rigorous_dir = run_dir / "rigorous"
    aggregate = _read_json_object(rigorous_dir / "aggregate.json")
    if aggregate is None:
        raise RigorousSelectionError("aggregate checkpoint is missing")
    ranking = [row for row in aggregate.get("ranking", []) if isinstance(row, dict)]
    if not ranking:
        raise RigorousSelectionError("eligible ranking is missing")
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    questions = [
        Question(
            int(row["index"]),
            str(row["prompt"]),
            row.get("character_limit"),
            str(row.get("count_mode", "spaces_included")),
            row.get("minimum_character_limit"),
        )
        for row in state.get("questions", [])
        if isinstance(row, dict) and row.get("index")
    ]
    candidates: dict[str, tuple[DraftResponse, ...]] = {}
    for path in sorted((rigorous_dir / "candidates").glob("generated_[0-9].json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        responses = _responses({"responses": rows}, questions, path.stem)
        digest = sha256(json.dumps(_candidate_payload(responses), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8].upper()
        candidates[f"C{digest}"] = responses
    eligible = [row for row in ranking if str(row.get("candidate_id")) in candidates]
    if not eligible:
        raise RigorousSelectionError("ranked candidate checkpoints are missing")
    best_score = float(eligible[0]["median_total"])
    near = [row for row in eligible if float(row["median_total"]) >= best_score - 5]
    diverse = max(
        near,
        key=lambda row: (
            _experience_allocation_score(candidates[str(row["candidate_id"])]),
            float(row["median_total"]),
        ),
    )
    seed = candidates[str(diverse["candidate_id"])]
    hybrid = _transferable_synthesis_seed(
        seed,
        candidate_pool=[candidates[str(row["candidate_id"])] for row in eligible],
        elements=[row for row in aggregate.get("agreed_transferable_elements", []) if isinstance(row, dict)],
        validate_candidate=lambda _responses: [],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, _candidate_payload(hybrid))
    write_json(
        output.with_name(output.stem + "_provenance.json"),
        {
            "source_candidate_id": diverse["candidate_id"],
            "source_median_total": diverse["median_total"],
            "experience_allocation_score": _experience_allocation_score(hybrid),
            "agreed_transferable_elements": aggregate.get("agreed_transferable_elements", []),
        },
    )
    return output


ModelRunner = Callable[[str, str, str, int], dict[str, Any] | str]


@dataclass(frozen=True)
class RigorousResult:
    responses: tuple[DraftResponse, ...]
    metadata: dict[str, Any]


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _json_schema(stage: str) -> dict[str, Any]:
    if stage.startswith("candidate") or stage.startswith("synthesis"):
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
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["question_index", "choice", "reason", "decisive_difference"],
                    "properties": {
                        "question_index": {"type": "integer"},
                        "choice": {"type": "string", "enum": ["X", "Y"]},
                        "reason": {"type": "string"},
                        "decisive_difference": {"type": "string"},
                    },
                },
            },
            "risk_audit": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    category: {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["X", "Y"],
                        "properties": {
                            "X": {"type": "array", "items": {"type": "string"}},
                            "Y": {"type": "array", "items": {"type": "string"}},
                        },
                    }
                    for category in (
                        "remaining_fact_risks",
                        "interview_defense_risks",
                        "spoken_answer_risks",
                        "company_specificity_regression",
                        "applicant_voice_regression",
                        "experience_duplication",
                        "style_regression",
                    )
                },
                "required": [
                    "remaining_fact_risks",
                    "interview_defense_risks",
                    "spoken_answer_risks",
                    "company_specificity_regression",
                    "applicant_voice_regression",
                    "experience_duplication",
                    "style_regression",
                ],
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
    if stage == "final_comparison" and isinstance(value.get("question_choices"), list):
        normalized: dict[str, dict[str, Any]] = {}
        for item in value["question_choices"]:
            if not isinstance(item, dict) or "question_index" not in item:
                raise RigorousSelectionError("invalid final comparison question choice")
            item = dict(item)
            question_index = item.pop("question_index")
            normalized[f"q{int(question_index)}"] = item
        value["question_choices"] = normalized
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


def _style_report(responses: tuple[DraftResponse, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_index = {response.question_index: response for response in responses}
    for item in diagnose_responses(responses):
        row = item.to_dict()
        if item.should_rewrite:
            row["repair_details"] = style_repair_details(
                by_index[item.question_index].answer
            )
        result.append(row)
    return result


def _style_risk_total(responses: tuple[DraftResponse, ...]) -> int:
    return sum(item.style_risk_score for item in diagnose_responses(responses))


def _compact_judge_packet(
    frozen_packet: dict[str, Any],
    blind_payload: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Keep only evidence reachable from anonymous candidates for judging."""
    experience_ids: set[str] = set()
    profile_claim_ids: set[str] = set()
    research_ids: set[str] = set()
    for rows in blind_payload.values():
        for row in rows:
            research_ids.update(str(item) for item in row.get("research_refs", []) if item)
            for reference in row.get("experience_refs", []):
                if not isinstance(reference, dict):
                    continue
                experience_id = str(reference.get("experience_id", "")).strip()
                if experience_id:
                    experience_ids.add(experience_id)
                profile_claim_ids.update(
                    str(item) for item in reference.get("claim_ids", []) if item
                )

    compact: dict[str, Any] = {
        key: frozen_packet.get(key)
        for key in ("target", "posting", "question_requirement_map")
        if key in frozen_packet
    }
    research = frozen_packet.get("research_claims")
    if isinstance(research, list):
        compact["research_claims"] = [
            row
            for row in research
            if isinstance(row, dict) and str(row.get("claim_id", "")) in research_ids
        ]
    ledger = frozen_packet.get("experience_ledger")
    if isinstance(ledger, dict):
        compact_experiences: list[dict[str, Any]] = []
        for experience in ledger.get("experiences", []):
            if not isinstance(experience, dict) or str(
                experience.get("experience_id", "")
            ) not in experience_ids:
                continue
            compact_experiences.append(
                {
                    **experience,
                    "claims": [
                        claim
                        for claim in experience.get("claims", [])
                        if isinstance(claim, dict)
                        and str(claim.get("claim_id", "")) in profile_claim_ids
                    ],
                }
            )
        compact["experience_ledger"] = {
            "schema_version": ledger.get("schema_version"),
            "experiences": compact_experiences,
        }

    contracts = frozen_packet.get("prompt_contracts")
    if isinstance(contracts, dict):
        company = contracts.get("company_research")
        interview = contracts.get("interview_defense")
        compact_company: dict[str, Any] = {}
        if isinstance(company, dict):
            compact_company = {
                key: company.get(key)
                for key in (
                    "entity",
                    "business_model",
                    "role_value_map",
                    "applicant_bridge",
                    "red_team",
                    "decision",
                )
                if key in company
            }
            compact_company["safe_claims"] = [
                row
                for row in company.get("safe_claims", [])
                if isinstance(row, dict)
                and (
                    str(row.get("claim_id", "")) in research_ids
                    or str(row.get("claim_id", ""))
                    in {
                        str(item.get("claim_id", ""))
                        for item in frozen_packet.get("research_claims", [])
                        if isinstance(item, dict)
                    }
                )
            ]
            compact_company["prohibited_claim_ids"] = company.get(
                "prohibited_claim_ids", []
            )
        compact_interview: dict[str, Any] = {}
        if isinstance(interview, dict):
            compact_interview = {
                "defensible_experience_ids": sorted(
                    experience_ids.intersection(
                        str(item)
                        for item in interview.get("defensible_experience_ids", [])
                    )
                ),
                "experience_defense": [
                    row
                    for row in interview.get("experience_defense", [])
                    if isinstance(row, dict)
                    and str(row.get("experience_id", "")) in experience_ids
                ],
                "submitted_claims": interview.get("submitted_claims", []),
            }
        compact["prompt_contracts"] = {
            "contract_version": contracts.get("contract_version"),
            "data_package_id": contracts.get("data_package_id"),
            "data_package_version": contracts.get("data_package_version"),
            "company_research": compact_company,
            "interview_defense": compact_interview,
        }
    return compact


def _deduplicate_judge_evaluations(
    rows: list[Any], judge: str
) -> list[dict[str, Any]]:
    """Merge duplicate IDs only when their score and fail decisions agree."""
    merged: dict[str, dict[str, Any]] = {}
    decision_keys = (
        "hard_fail",
        "hard_fail_status",
        "hard_fail_type",
        "scores",
        "total",
    )
    for raw in rows:
        if not isinstance(raw, dict):
            raise RigorousSelectionError(f"judge evaluation row mismatch: {judge}")
        candidate_id = str(raw.get("candidate_id", ""))
        existing = merged.get(candidate_id)
        if existing is None:
            merged[candidate_id] = dict(raw)
            continue
        if any(existing.get(key) != raw.get(key) for key in decision_keys):
            raise RigorousSelectionError(f"conflicting duplicate candidate: {judge}")
        for key in ("hard_fail_reasons", "review_required", "weakness_codes"):
            existing[key] = list(
                dict.fromkeys(
                    [
                        str(item)
                        for item in list(existing.get(key, [])) + list(raw.get(key, []))
                    ]
                )
            )
        elements: dict[str, dict[str, Any]] = {}
        for item in list(existing.get("transferable_elements", [])) + list(
            raw.get("transferable_elements", [])
        ):
            if isinstance(item, dict):
                elements[
                    json.dumps(item, ensure_ascii=False, sort_keys=True)
                ] = item
        existing["transferable_elements"] = list(elements.values())
    return list(merged.values())


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
    rows = _deduplicate_judge_evaluations(rows, judge)
    payload["evaluations"] = rows
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
        if isinstance(fail_type, str):
            fail_type = _normalized_hard_fail_type(fail_type)
            row["hard_fail_type"] = fail_type
        if fail_type is not None and fail_type not in {"DETERMINISTIC", "SEMANTIC"}:
            raise RigorousSelectionError(f"hard fail type mismatch: {judge}")
        if not isinstance(row["review_required"], list):
            raise RigorousSelectionError(f"review-required schema mismatch: {judge}")
        if fail_type == "DETERMINISTIC" and status == "CONFIRMED":
            # Every anonymous candidate has already passed the authoritative
            # Python validator. A model-reported length/format issue is useful
            # review evidence, but cannot override the exact code result.
            row["hard_fail"] = False
            row["hard_fail_status"] = "REVIEW_REQUIRED"
            row["review_required"] = list(row["review_required"]) + [
                "모델이 결정론적 오류를 보고했으나 코드 사전검증과 불일치"
            ]
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
    questions: list[Question],
    frozen_packet: dict[str, Any],
    *,
    strategies: tuple[str, ...],
    judges: tuple[str, ...],
    quality_profile: str,
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
        "data_package_id": f"CAREER-DATA-{digest[:12].upper()}",
        "data_package_version": "2.0",
        "frozen_data_sha256": digest,
        "count_mode": modes[0] if len(modes) == 1 else "mixed",
        "candidate_count": len(strategies) + 1,
        "judge_count": len(judges),
        "quality_profile": quality_profile,
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


def _experience_allocation_score(responses: tuple[DraftResponse, ...]) -> tuple[int, int, int]:
    """Prefer distinct Q1-Q3 evidence without rewarding gratuitous extra refs."""
    ids = [
        reference.experience_id
        for response in responses
        if response.question_index in {1, 2, 3}
        for reference in response.experience_refs
        if reference.experience_id
    ]
    unique = len(set(ids))
    overlap = len(ids) - unique
    maximum_reuse = max((ids.count(value) for value in set(ids)), default=0)
    return unique, -overlap, -maximum_reuse


def _transferable_synthesis_seed(
    seed: tuple[DraftResponse, ...],
    *,
    candidate_pool: list[tuple[DraftResponse, ...]],
    elements: list[dict[str, Any]],
    validate_candidate: Callable[[list[DraftResponse]], list[Any]],
) -> tuple[DraftResponse, ...]:
    """Apply only judge-agreed exact elements from already valid candidates."""
    by_question = {response.question_index: response for response in seed}
    changed = False
    for element in elements:
        try:
            question_index = int(element.get("question", 0))
        except (TypeError, ValueError):
            continue
        exact = " ".join(str(element.get("exact_element", "")).split())
        current = by_question.get(question_index)
        if not exact or current is None or exact in " ".join(current.answer.split()):
            continue
        source = next(
            (
                response
                for candidate in candidate_pool
                for response in candidate
                if response.question_index == question_index
                and exact in " ".join(response.answer.split())
            ),
            None,
        )
        if source is not None:
            by_question[question_index] = source
            changed = True
    if not changed:
        return seed
    result = tuple(by_question[index] for index in sorted(by_question))
    return seed if validate_candidate(list(result)) else result


def _prompt_data(questions: list[Question], frozen_packet: dict[str, Any]) -> str:
    return json.dumps({"questions": [asdict(item) for item in questions], "frozen_packet": frozen_packet}, ensure_ascii=False)


def _stage_model(
    role: str,
    *,
    fallback_model_id: str | None,
    stage_models: dict[str, str | None] | None,
) -> str:
    model_id = (stage_models or {}).get(role) or fallback_model_id
    if not model_id:
        raise RigorousSelectionError(f"rigorous selection requires a configured {role} model ID")
    return model_id


def _question_quality_contract(questions: list[Question]) -> list[dict[str, Any]]:
    result = []
    for question in questions:
        if question.character_limit is None:
            minimum = question.minimum_character_limit
            preferred_maximum = None
        else:
            minimum = question.minimum_character_limit
            if minimum is None:
                minimum = round(question.character_limit * 0.80)
            preferred_maximum = max(minimum, round(question.character_limit * 0.93))
        result.append(
            {
                "question_index": question.index,
                "character_limit": question.character_limit,
                "count_mode": question.count_mode,
                "preferred_minimum": minimum,
                "preferred_maximum": preferred_maximum,
            }
        )
    return result


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
    quality_profile: QualityProfile | None = None,
    stage_models: dict[str, str | None] | None = None,
    resume_from_checkpoint: bool = False,
) -> RigorousResult:
    profile = quality_profile or legacy_rigorous_profile()
    if profile.selection_mode != "rigorous" or not profile.strategies or not profile.judges:
        raise RigorousSelectionError("rigorous selection requires a rigorous quality profile")
    if max_calls < profile.max_selection_calls:
        raise RigorousSelectionError(
            f"{profile.name} selection requires a {profile.max_selection_calls}-call budget"
        )
    strategies = profile.strategies
    judges = profile.judges
    rigorous_dir = run_dir / "rigorous"
    package_meta = _data_package_metadata(
        questions,
        frozen_packet,
        strategies=strategies,
        judges=judges,
        quality_profile=profile.name,
    )
    resumed = (
        _resume_generated_candidates(
            rigorous_dir,
            package_meta=package_meta,
            strategies=strategies,
            questions=questions,
            validate_candidate=validate_candidate,
        )
        if resume_from_checkpoint
        else None
    )
    if resumed is None:
        _reset_rigorous_directory(run_dir, rigorous_dir)
    (rigorous_dir / "candidates").mkdir(parents=True, exist_ok=True)
    (rigorous_dir / "judges").mkdir(parents=True, exist_ok=True)
    calls: list[dict[str, str]] = []
    resumed_stages: list[str] = []
    candidates: dict[str, tuple[DraftResponse, ...]] = (
        dict(resumed[0]) if resumed is not None else {}
    )
    write_json(rigorous_dir / "data_package.json", package_meta)
    data = _prompt_data(questions, frozen_packet)
    private_mapping: dict[str, str] = dict(resumed[1]) if resumed is not None else {}
    candidate_failures: list[dict[str, Any]] = []
    if resumed is not None:
        resumed_stages.extend(sorted(candidates))
        existing_failures = json.loads(
            (rigorous_dir / "candidate_failures.json").read_text(encoding="utf-8")
        ) if (rigorous_dir / "candidate_failures.json").is_file() else []
        if isinstance(existing_failures, list):
            candidate_failures.extend(
                item
                for item in existing_failures
                if isinstance(item, dict) and item.get("stage") != "incumbent"
            )
    incumbent_issues = validate_candidate(list(incumbent))
    if incumbent_issues:
        candidate_failures.append(
            {
                "stage": "incumbent",
                "repair_attempted": False,
                "repair_attempts": 0,
                "codes": [issue.code for issue in incumbent_issues],
                "question_indexes": sorted(
                    {issue.question_index for issue in incumbent_issues}
                ),
            }
        )
    else:
        candidates["incumbent"] = incumbent
    question_contract = frozen_packet.get("question_requirement_map")
    if not isinstance(question_contract, dict):
        question_contract = {"questions": _question_quality_contract(questions)}
    generation_model = _stage_model(
        "generation", fallback_model_id=model_id, stage_models=stage_models
    )
    for index, strategy in enumerate(strategies, 1):
        internal_id = f"generated_{index}"
        if internal_id in candidates:
            continue
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
            "When frozen_packet.prompt_contracts exists, use only company_research.safe_claims, never use "
            "company_research.prohibited_claim_ids, and select experience IDs only from "
            "interview_defense.defensible_experience_ids. Treat answer cards and probe defenses as claim "
            "boundaries rather than permission to invent a stronger story. A company claim with "
            "use_decision=QUALIFY must be explicitly framed as the source's statement or a bounded interpretation, "
            "never as an established objective result. "
            "Use the question_requirement_map as the authoritative per-question content contract. Answer every "
            "hard requirement and stay inside each question's actual character limit and preferred range. "
            "If a prompt asks for one issue, name exactly one issue in the selection sentence; other risks from a "
            "cited source may appear only as context and must not be framed as a second selected issue. "
            "Avoid repeating an experience when a confirmed alternative satisfies the question as well. "
            "Use one coherent narrative per answer: direct answer, concrete evidence, judgment, job/company bridge, "
            "and a realistic conclusion. Keep the applicant's natural voice; do not turn the answer into slogans, "
            "abstract noun lists or company brochure copy. Read every sentence as spoken Korean before returning it. "
            "For Korean style, do not use the same sentence ending three times in a row, do not repeat the same sentence "
            "opening, vary short and long sentences, use '할 수 있습니다' at most once per answer, and split a long "
            "sentence when three or more adnominal clauses stack together. "
            "Private strategy: " + strategy + " — " + STRATEGY_INSTRUCTIONS[strategy] + "\n"
            + json.dumps(package_meta, ensure_ascii=False)
            + "\nQUESTION_REQUIREMENT_MAP\n"
            + json.dumps(question_contract, ensure_ascii=False)
            + "\n"
            + data
        )
        payload = _coerce_payload(runner(stage, prompt, generation_model, timeout_ms), stage)
        calls.append({"stage": stage, "model_id": generation_model, "role": "generation"})
        raw_path = rigorous_dir / "candidates" / f"generated_{index}_raw.json"
        write_json(raw_path, payload)
        _validate_data_package_payload(payload, package_meta, stage)
        responses = _responses(payload, questions, stage)
        candidate_responses = list(responses)
        issues = validate_candidate(candidate_responses)
        repair_attempts = 0
        while issues and repair_attempts < profile.candidate_repair_attempts:
            repair_attempts += 1
            repair_stage = f"candidate_repair_{index}_{repair_attempts}"
            repair_prompt = (
                "Repair only the deterministic validation failures in this candidate. Preserve its strategy, "
                "facts, voice, experience allocation and safe claims. Do not add facts. Return the complete JSON set.\n"
                + json.dumps(
                    {
                        "data_package": package_meta,
                        "question_requirement_map": question_contract,
                        "issues": [
                            {
                                "code": issue.code,
                                "question_index": issue.question_index,
                                "message": issue.message,
                            }
                            for issue in issues
                        ],
                        "candidate": _candidate_payload(responses),
                    },
                    ensure_ascii=False,
                )
            )
            repaired_payload = _coerce_payload(
                runner(repair_stage, repair_prompt, generation_model, timeout_ms),
                repair_stage,
            )
            calls.append(
                {"stage": repair_stage, "model_id": generation_model, "role": "generation"}
            )
            _validate_data_package_payload(repaired_payload, package_meta, repair_stage)
            write_json(
                rigorous_dir / "candidates" / f"generated_{index}_repair_{repair_attempts}.json",
                repaired_payload,
            )
            responses = _responses(repaired_payload, questions, repair_stage)
            candidate_responses = list(responses)
            issues = validate_candidate(candidate_responses)
        if issues:
            candidate_failures.append({
                "stage": stage,
                "repair_attempted": repair_attempts > 0,
                "repair_attempts": repair_attempts,
                "codes": [issue.code for issue in issues],
                "question_indexes": sorted({issue.question_index for issue in issues}),
            })
            write_json(rigorous_dir / "candidate_failures.json", candidate_failures)
            if profile.candidate_repair_attempts:
                continue
            raise RigorousSelectionError(f"deterministic candidate validation failed at {stage}: {issues[0].code}")
        responses = tuple(candidate_responses)
        candidates[internal_id] = responses
        private_mapping[internal_id] = strategy
        path = rigorous_dir / "candidates" / f"{internal_id}.json"
        write_json(path, _candidate_payload(responses))
    if not candidates:
        raise RigorousSelectionError("every generated candidate failed deterministic validation")
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
    judge_packet = _compact_judge_packet(frozen_packet, blind_payload)
    write_json(rigorous_dir / "judge_data_package.json", judge_packet)

    judge_rows: list[list[dict[str, Any]]] = []
    judge_model = _stage_model("judge", fallback_model_id=model_id, stage_models=stage_models)
    for judge in judges:
        stage = f"judge_{judge.lower()}"
        prompt = (
            "Independently score every anonymous candidate. Use the fixed weights, identify HARD FAILs, "
            "classify deterministic failures separately from semantic REVIEW_REQUIRED findings, "
            "record transferable elements only when they are grounded in fact IDs, and return JSON only. "
            "Use only these weakness_codes: question_gap, fact_risk, job_gap, action_gap, "
            "experience_overlap, interview_risk, spoken_answer_risk, korean_style, generic_voice, "
            "company_genericity, format_risk. "
            "Do not invent or translate code names. "
            "When prompt contracts are present, mark company claims outside safe_claims or experiences outside "
            "defensible_experience_ids as fact_risk or interview_risk. "
            "Judge instruction: " + JUDGE_INSTRUCTIONS[judge] + " "
            "Do not reward verbosity, polish unsupported by evidence, or generic company praise. Do not rewrite.\n"
            + json.dumps({"judge_mode": judge, "weights": WEIGHTS, "data_package": package_meta, "data": judge_packet, "questions": [asdict(q) for q in questions], "candidates": blind_payload}, ensure_ascii=False)
        )
        checkpoint_paths = (
            rigorous_dir / "judges" / f"{judge.lower()}.json",
            rigorous_dir / "judges" / f"{judge.lower()}_raw.json",
        )
        checkpoint_payload = None
        if resume_from_checkpoint:
            checkpoint_payload = next(
                (
                    value
                    for path in checkpoint_paths
                    if (value := _read_json_object(path)) is not None
                ),
                None,
            )
        if checkpoint_payload is not None:
            try:
                rows = _validate_judge(
                    checkpoint_payload, judge, set(blinded), package_meta
                )
            except RigorousSelectionError:
                checkpoint_payload = None
            else:
                payload = checkpoint_payload
                resumed_stages.append(stage)
        if checkpoint_payload is None:
            payload = _coerce_payload(runner(stage, prompt, judge_model, timeout_ms), stage)
            calls.append({"stage": stage, "model_id": judge_model, "role": "judge"})
        raw_judge_path = rigorous_dir / "judges" / f"{judge.lower()}_raw.json"
        write_json(raw_judge_path, payload)
        judge_error: RigorousSelectionError | None = None
        for repair_attempt in range(0, 3):
            try:
                rows = _validate_judge(payload, judge, set(blinded), package_meta)
            except RigorousSelectionError as error:
                judge_error = error
                if repair_attempt >= 2:
                    break
                repair_stage = f"{stage}_repair_{repair_attempt + 1}"
                repair_prompt = (
                    "Repair only the evaluation-table structure. Return the same judge_mode and data package. "
                    "Output exactly one evaluation for each expected candidate ID, no duplicates and no omissions. "
                    "Preserve a candidate's existing scores and findings when one unambiguous row exists. "
                    "If duplicate rows conflict or an ID is missing, reassess only that candidate from the supplied "
                    "anonymous candidate packet. Return JSON only.\n"
                    + json.dumps(
                        {
                            "judge_mode": judge,
                            "data_package": package_meta,
                            "expected_candidate_ids": sorted(blinded),
                            "validation_error": str(error),
                            "invalid_evaluation": payload,
                            "candidates": blind_payload,
                        },
                        ensure_ascii=False,
                    )
                )
                try:
                    repaired_output = runner(repair_stage, repair_prompt, judge_model, timeout_ms)
                except Exception:
                    break
                payload = _coerce_payload(repaired_output, repair_stage)
                calls.append({"stage": repair_stage, "model_id": judge_model, "role": "judge"})
                write_json(
                    rigorous_dir / "judges" / f"{judge.lower()}_repair_{repair_attempt + 1}.json",
                    payload,
                )
            else:
                judge_error = None
                break
        if judge_error is not None:
            write_json(
                rigorous_dir / "judge_failures.json",
                [{"stage": stage, "error": str(judge_error)}],
            )
            raise judge_error
        for row in rows:
            row["judge_mode"] = judge
        judge_rows.append(rows)
        write_json(rigorous_dir / "judges" / f"{judge.lower()}.json", payload)

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
    synthesis_seed_id = winner_id
    synthesis = baseline
    if profile.name == "max_quality":
        near_winners = [
            row for row in eligible
            if float(row["median_total"]) >= float(eligible[0]["median_total"]) - 5
        ]
        diverse = max(
            near_winners,
            key=lambda row: (
                _experience_allocation_score(blinded[row["candidate_id"]]),
                row["median_total"],
            ),
        )
        if _experience_allocation_score(blinded[diverse["candidate_id"]]) > _experience_allocation_score(baseline):
            synthesis_seed_id = diverse["candidate_id"]
            synthesis = blinded[synthesis_seed_id]
        synthesis = _transferable_synthesis_seed(
            synthesis,
            candidate_pool=[blinded[row["candidate_id"]] for row in eligible],
            elements=agreed_transferable,
            validate_candidate=validate_candidate,
        )
        write_json(
            rigorous_dir / "synthesis_seed.json",
            {
                "source_candidate_id": synthesis_seed_id,
                "experience_allocation_score": _experience_allocation_score(synthesis),
                "responses": _candidate_payload(synthesis),
            },
        )
    baseline_style = _style_report(baseline)
    if agreed or agreed_transferable or profile.name == "max_quality":
        stage = "synthesis"
        synthesis_model = _stage_model(
            "synthesis", fallback_model_id=model_id, stage_models=stage_models
        )
        prompt = (
            "Minimally revise the winning set for the agreed weaknesses and the final quality floor. "
            "In MAX_QUALITY, even when judges found no shared weakness, inspect every answer for directness, "
            "concrete action and judgment, company/job specificity, natural spoken Korean, distinct experience "
            "allocation, and the preferred character range. Make a change only when it materially improves one "
            "of those dimensions. Treat the supplied deterministic style diagnostics as an exact repair checklist: "
            "When a question asks for one issue, preserve exactly one selected issue in the first sentence and "
            "treat any other source risk only as background context. "
            "remove every should_rewrite condition without changing facts or references. Vary consecutive endings and "
            "sentence lengths, remove repeated openings and ability phrases, and split stacked adnominal clauses. "
            "Preserve facts, claim IDs, "
            "experience allocation and limits. Preserve the strongest natural sentence rhythm and applicant voice. "
            "Do not add an experience merely to increase length or replace concrete language with polished abstractions. "
            "Return JSON only.\n"
            + json.dumps({"data_package": package_meta, "weaknesses": agreed, "transferable_elements": agreed_transferable, "style_diagnostics": _style_report(synthesis), "winner": _candidate_payload(synthesis), "frozen_packet": frozen_packet, "questions": [asdict(q) for q in questions]}, ensure_ascii=False)
        )
        repair_number = 0
        if resume_from_checkpoint:
            checkpoint_candidates = [
                (
                    number,
                    rigorous_dir / f"synthesis_repair_{number}.json",
                    f"synthesis_repair_{number}",
                )
                for number in range(profile.synthesis_repair_attempts, 0, -1)
            ] + [(0, rigorous_dir / "synthesis.json", "synthesis")]
            for number, path, checkpoint_stage in checkpoint_candidates:
                checkpoint = _read_valid_candidate_file(
                    path,
                    questions=questions,
                    validate_candidate=validate_candidate,
                    stage=f"resume_{checkpoint_stage}",
                )
                if checkpoint is not None:
                    synthesis = checkpoint
                    repair_number = number
                    resumed_stages.append(checkpoint_stage)
                    break
        if synthesis is baseline:
            synthesis_payload = _coerce_payload(
                runner(stage, prompt, synthesis_model, timeout_ms), stage
            )
            _validate_data_package_payload(synthesis_payload, package_meta, stage)
            synthesis = _responses(synthesis_payload, questions, stage)
            synthesis_responses = list(synthesis)
            issues = validate_candidate(synthesis_responses)
            if issues:
                synthesis = baseline
            else:
                synthesis = tuple(synthesis_responses)
            calls.append(
                {"stage": stage, "model_id": synthesis_model, "role": "synthesis"}
            )
            write_json(rigorous_dir / "synthesis.json", _candidate_payload(synthesis))

        synthesis_style = _style_report(synthesis)
        last_repair_issues: list[dict[str, Any]] = []
        while (
            profile.name == "max_quality"
            and any(bool(item.get("should_rewrite")) for item in synthesis_style)
            and repair_number < profile.synthesis_repair_attempts
        ):
            repair_number += 1
            repair_stage = f"synthesis_repair_{repair_number}"
            repair_prompt = (
                "Repair only the listed deterministic Korean style risks in the complete winning set. "
                "Preserve every fact, claim ID, research reference, experience allocation, question requirement and "
                "character range. Do not add polish for its own sake. You may split, merge, shorten or reorder sentences "
                "inside the same answer when meaning and causality stay identical. For repeated openings, give each "
                "sentence a different concrete subject or verb: the checker treats the first word or phrase as the "
                "opening, so the same first word must not begin two sentences. For low sentence-length variance, include both a short "
                "sentence and a materially longer evidence sentence. For repeated endings, vary declarative, past-action "
                "and future-plan endings without changing time; never leave three consecutive sentences in the same "
                "ending class. Remove repeated '할 수 있습니다' and formulaic conclusions. Change only questions whose "
                "diagnostic has should_rewrite=true; keep already-passing questions byte-for-byte unchanged. "
                "Return the complete JSON set.\n"
                + json.dumps(
                    {
                        "data_package": package_meta,
                        "style_diagnostics": synthesis_style,
                        "previous_validation_issues": last_repair_issues,
                        "candidate": _candidate_payload(synthesis),
                        "questions": [asdict(q) for q in questions],
                    },
                    ensure_ascii=False,
                )
            )
            repair_payload = _coerce_payload(
                runner(repair_stage, repair_prompt, synthesis_model, timeout_ms),
                repair_stage,
            )
            _validate_data_package_payload(repair_payload, package_meta, repair_stage)
            repaired = _responses(repair_payload, questions, repair_stage)
            write_json(
                rigorous_dir / f"synthesis_repair_{repair_number}_raw.json",
                repair_payload,
            )
            repair_issues = validate_candidate(list(repaired))
            if not repair_issues:
                synthesis = repaired
                synthesis_style = _style_report(synthesis)
                last_repair_issues = []
            else:
                last_repair_issues = [
                    {
                        "code": issue.code,
                        "question_index": issue.question_index,
                        "message": issue.message,
                    }
                    for issue in repair_issues
                ]
            calls.append(
                {"stage": repair_stage, "model_id": synthesis_model, "role": "synthesis"}
            )
            write_json(
                rigorous_dir / f"synthesis_repair_{repair_number}.json",
                _candidate_payload(synthesis),
            )

        if profile.name == "max_quality" and any(
            bool(item.get("should_rewrite")) for item in _style_report(synthesis)
        ):
            raise RigorousSelectionError("final Korean style quality floor failed")

    stage = "final_comparison"
    comparison_prompt = (
        "Blindly choose X or Y. Reject any new fact, weaker causality, question gap or length violation. "
        "Choose one complete version; do not create a mixed version. Record question-level choices and "
        "remaining fact, interview, spoken-answer, company-specificity, applicant-voice, duplication and style "
        "risks. Prefer the version that is both safer and more concrete; do not choose generic polish over a "
        "defensible applicant-specific answer. Return JSON only.\n"
        + json.dumps({"data_package": package_meta, "frozen_packet": frozen_packet, "questions": [asdict(q) for q in questions], "style_diagnostics": {"X": baseline_style, "Y": _style_report(synthesis)}, "X": _candidate_payload(baseline), "Y": _candidate_payload(synthesis)}, ensure_ascii=False)
    )
    comparison_model = _stage_model(
        "comparison", fallback_model_id=model_id, stage_models=stage_models
    )
    comparison = (
        _read_json_object(rigorous_dir / "final_comparison.json")
        if resume_from_checkpoint
        else None
    )
    if comparison is not None:
        try:
            _validate_data_package_payload(comparison, package_meta, stage)
            validate_blind_comparison_payload(
                comparison, (question.index for question in questions)
            )
        except (RigorousSelectionError, ValueError):
            comparison = None
        else:
            resumed_stages.append(stage)
    if comparison is None:
        comparison = _coerce_payload(
            runner(stage, comparison_prompt, comparison_model, timeout_ms), stage
        )
        _validate_data_package_payload(comparison, package_meta, stage)
        calls.append(
            {"stage": stage, "model_id": comparison_model, "role": "comparison"}
        )
    try:
        validate_blind_comparison_payload(
            comparison, (question.index for question in questions)
        )
    except ValueError as error:
        raise RigorousSelectionError(str(error)) from error
    if comparison.get("comparison_ready") is False:
        raise RigorousSelectionError("final comparison is not ready")
    selected = baseline if comparison["choice"] == "X" else synthesis
    if comparison["choice"] == "Y":
        baseline_fit = _candidate_job_fit_score(baseline, frozen_packet)
        synthesis_fit = _candidate_job_fit_score(synthesis, frozen_packet)
        style_improves = _style_risk_total(synthesis) < _style_risk_total(baseline)
        if synthesis_fit < baseline_fit and not (
            profile.name == "max_quality" and style_improves
        ):
            comparison["choice"] = "X"
            comparison["reason"] = (
                str(comparison.get("reason", ""))
                + f" Deterministic safety guard retained X because job-linkage score "
                f"{synthesis_fit} was below X's {baseline_fit}."
            ).strip()
            selected = baseline
    baseline_style_risk = _style_risk_total(baseline)
    synthesis_style_risk = _style_risk_total(synthesis)
    if (
        profile.name == "max_quality"
        and synthesis_style_risk < baseline_style_risk
    ):
        comparison["choice"] = "Y"
        comparison["reason"] = (
            str(comparison.get("reason", ""))
            + f" Deterministic style guard selected Y because its style risk "
            f"{synthesis_style_risk} was below X's {baseline_style_risk}; Y already passed the "
            "authoritative question, job-linkage, evidence and contract validators."
        ).strip()
        selected = synthesis
    issues = validate_candidate(list(selected))
    if issues:
        raise RigorousSelectionError(f"final deterministic validation failed: {issues[0].code}")
    write_json(rigorous_dir / "final_comparison.json", comparison)
    selected_path = rigorous_dir / "selected.json"
    write_json(selected_path, _candidate_payload(selected))

    artifact_paths = [
        path for path in rigorous_dir.rglob("*.json")
        if path.name != "private_mapping.json"
    ]
    metadata = {
        "status": "passed", "selection_mode": "rigorous", "model_id": model_id,
        "quality_profile": profile.name,
        "stage_models": {
            role: (stage_models or {}).get(role) or model_id
            for role in ("generation", "judge", "synthesis", "comparison")
        },
        "call_count": len(calls), "calls": calls, "winner_candidate_id": winner_id,
        "resumed_stages": resumed_stages,
        "final_choice": comparison["choice"], "final_reason": comparison.get("reason", ""),
        "hard_fail": False,
        "data_package": package_meta,
        "candidate_count": len(blinded),
        "judge_count": len(judges),
        "review_required_candidates": [row["candidate_id"] for row in aggregate if row.get("review_required")],
        "artifact_sha256": {str(path.relative_to(run_dir)): _sha(path) for path in sorted(artifact_paths)},
    }
    write_json(rigorous_dir / "manifest.json", metadata)
    return RigorousResult(selected, metadata)
