from dataclasses import asdict, replace
import json
from pathlib import Path

import yaml

from .conflicts import (
    apply_overrides,
    conflict_override_key,
    detect_conflicts,
)
from .extractors import extract_path
from .facts import extract_fact_claims
from .inventory import build_inventory
from .questions import extract_questions
from .models import DraftResponse, Question, ValidationIssue
from .rendering import render_draft_docx, render_draft_markdown
from .state import resolve_run_dir, write_json, write_state
from .validation import validate_draft


def _inventory_markdown(records) -> str:
    lines = ["# 자료 목록", "", "| 상태 | 파일 | 사유 |", "|---|---|---|"]
    lines.extend(
        f"| {item.status} | {item.relative_path} | {item.reason} |"
        for item in records
    )
    return "\n".join(lines) + "\n"


def _conflict_markdown(conflicts, claims) -> str:
    lines = ["# 충돌 검사", ""]
    if not conflicts:
        lines.append("- 충돌 없음")
    for number, conflict in enumerate(conflicts, 1):
        lines.extend(
            [
                f"## 충돌 {number}: {conflict.field}",
                f"값: {', '.join(conflict.values)}",
            ]
        )
        for index in conflict.claim_indexes:
            claim = claims[index]
            lines.append(f"- `{claim.source_path}`: {claim.context}")
        lines.append(
            f"- override key: `{conflict_override_key(conflict, claims)}`"
        )
        lines.append(
            "- 확인 질문: 실제 제출에 사용할 값과 근거 파일을 지정해 주세요."
        )
    return "\n".join(lines) + "\n"


def _load_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload.items()
    ):
        raise ValueError("fact_overrides.yaml must be a string-to-string mapping")
    return payload


def prepare_run(
    root: Path,
    target: str,
    draft: Path,
    posting: str | None,
    run_name: str | None,
    resume: Path | None = None,
) -> dict:
    root = root.resolve()
    draft = draft.resolve()
    run_dir = resolve_run_dir(root, target, run_name, resume)
    inventory = build_inventory(root)
    draft_record = next(
        item for item in inventory if item.path.resolve() == draft
    )
    if draft_record.status == "failed":
        raise PermissionError(
            "대상 초안을 읽을 수 없습니다. 초안 파일을 닫고 다시 실행해 주세요. "
            f"원인: {draft_record.reason}"
        )
    documents = []
    for index, source in enumerate(inventory):
        if source.status != "use":
            continue
        try:
            documents.append(extract_path(source))
        except Exception as error:
            inventory[index] = replace(
                source, status="failed", reason=f"{type(error).__name__}: {error}"
            )

    fact_documents = [
        document
        for document in documents
        if "자료조사" not in Path(document.source.relative_path).parts
        and "직무기술서" not in Path(document.source.relative_path).name
        and "채용공고" not in Path(document.source.relative_path).name
    ]
    claims = extract_fact_claims(fact_documents)
    overrides = _load_overrides(run_dir / "fact_overrides.yaml")
    accepted = apply_overrides(claims, overrides)
    conflicts = detect_conflicts(accepted)

    questions = extract_questions(extract_path(draft_record).paragraphs)

    (run_dir / "01_자료목록.md").write_text(
        _inventory_markdown(inventory), encoding="utf-8"
    )
    fact_payload = []
    for claim in claims:
        item = asdict(claim)
        item["tokens"] = sorted(claim.tokens)
        fact_payload.append(item)
    write_json(run_dir / "02_사실원장.json", fact_payload)
    (run_dir / "03_충돌검사.md").write_text(
        _conflict_markdown(conflicts, accepted), encoding="utf-8"
    )

    state = {
        "status": "blocked" if conflicts else "ready_for_research",
        "run_dir": str(run_dir),
        "root": str(root),
        "target": target,
        "draft": str(draft),
        "posting": posting,
        "questions": [asdict(question) for question in questions],
        "conflict_count": len(conflicts),
    }
    write_state(run_dir, state)
    return state


def finalize_run(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if state.get("status") == "blocked":
        raise ValueError("사실 충돌을 먼저 해결해야 합니다.")

    required = [
        "02_사실원장.json",
        "04_기업직무조사.md",
        "05_문항전략.md",
        "08_면접대비팩.md",
        "draft.json",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"missing synthesis artifacts: {', '.join(missing)}"
        )

    questions = [Question(**item) for item in state["questions"]]
    draft_data = json.loads((run_dir / "draft.json").read_text(encoding="utf-8"))
    responses = [
        DraftResponse(
            item["question_index"],
            item["answer"],
            tuple(item.get("evidence_paths", [])),
        )
        for item in draft_data
    ]
    fact_data = json.loads(
        (run_dir / "02_사실원장.json").read_text(encoding="utf-8")
    )
    known_sources = {item["source_path"] for item in fact_data}
    issues = validate_draft(
        questions, responses, state["target"], known_sources
    )

    research = (run_dir / "04_기업직무조사.md").read_text(encoding="utf-8")
    if "http://" not in research and "https://" not in research:
        issues.append(
            ValidationIssue(
                "missing_research_link", 0, "공식 조사 링크가 없습니다."
            )
        )

    interview = (run_dir / "08_면접대비팩.md").read_text(encoding="utf-8")
    for section in ("1분 자기소개", "꼬리질문", "압박질문", "근거"):
        if section not in interview:
            issues.append(
                ValidationIssue(
                    "missing_interview_section",
                    0,
                    f"면접팩 누락: {section}",
                )
            )

    if issues:
        state.update(
            status="blocked_validation",
            validation_issues=[asdict(item) for item in issues],
        )
        write_state(run_dir, state)
        return state

    markdown = render_draft_markdown(questions, responses)
    (run_dir / "06_자기소개서.md").write_text(markdown, encoding="utf-8")
    render_draft_docx(
        questions, responses, run_dir / "06_자기소개서.docx"
    )

    response_by_index = {item.question_index: item for item in responses}
    review_lines = ["# 자기소개서 검토보고서", ""]
    for question in questions:
        response = response_by_index[question.index]
        review_lines.append(
            f"- 문항 {question.index}: {len(response.answer)}/"
            f"{question.character_limit or '미지정'}자, "
            f"근거 {len(response.evidence_paths)}개"
        )
    review_lines.extend(
        ["- 블라인드: 통과", "- 타기관명: 통과", "- 빈 답변: 없음"]
    )
    (run_dir / "07_자기소개서_검토보고서.md").write_text(
        "\n".join(review_lines) + "\n", encoding="utf-8"
    )
    state["status"] = "complete"
    state.pop("validation_issues", None)
    write_state(run_dir, state)
    return state
