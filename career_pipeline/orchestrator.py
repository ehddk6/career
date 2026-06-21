from dataclasses import asdict, replace
from pathlib import Path

import yaml

from .conflicts import apply_overrides, detect_conflicts, override_key
from .extractors import extract_path
from .facts import extract_fact_claims
from .inventory import build_inventory
from .questions import extract_questions
from .state import resolve_run_dir, write_json, write_state


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
            f"- override key: `{override_key(claims[conflict.claim_indexes[0]])}`"
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

    claims = extract_fact_claims(documents)
    overrides = _load_overrides(run_dir / "fact_overrides.yaml")
    accepted = apply_overrides(claims, overrides)
    conflicts = detect_conflicts(accepted)

    draft_record = next(
        item for item in inventory if item.path.resolve() == draft
    )
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
