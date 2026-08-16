from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalized_count(text: str) -> int:
    return len(text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", ""))


def validate_candidate(candidate: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for question in ("q1", "q2", "q3", "q4"):
        count = normalized_count(candidate["answers"][question])
        minimum, maximum = (400, 600) if question != "q4" else (0, 1500)
        if not minimum <= count <= maximum:
            raise ValueError(f"{candidate['candidate_id']} {question}: {count}")
        counts[question] = count
    if candidate.get("counts") != counts:
        raise ValueError(
            f"{candidate['candidate_id']} declared counts {candidate.get('counts')} "
            f"!= actual {counts}"
        )
    return counts


def build_blind() -> None:
    assignments = [
        ("R8", "candidate_fact_first.json"),
        ("C3", "candidate_question_first.json"),
        ("M7", "candidate_natural_voice.json"),
        ("P2", "candidate_job_relevance.json"),
    ]
    blind = {"data_package_id": "SOL-DATA-608228643DF2-REFINAL", "candidates": []}
    private = {"data_package_id": blind["data_package_id"], "mapping": {}}
    for blind_id, filename in assignments:
        candidate = load_json(ROOT / "work" / filename)
        validate_candidate(candidate)
        blind["candidates"].append(
            {
                "candidate_id": blind_id,
                "answers": candidate["answers"],
                "counts": candidate["counts"],
                "fact_ids": candidate["fact_ids"],
                "risks": candidate.get("risks", []),
            }
        )
        private["mapping"][blind_id] = {
            "source_file": f"work/{filename}",
            "source_candidate_id": candidate["candidate_id"],
            "strategy": candidate["strategy"],
        }
    dump_json(ROOT / "work" / "blind_candidates.json", blind)
    dump_json(ROOT / "work" / "private_mapping.json", private)


def aggregate() -> None:
    judge_paths = [
        ROOT / "work" / "judge_1_recruiter.json",
        ROOT / "work" / "judge_2_job_fact.json",
        ROOT / "work" / "judge_3_korean_editor.json",
    ]
    judges = [load_json(path) for path in judge_paths]
    candidate_map: dict[str, list[dict]] = {}
    for judge in judges:
        for evaluation in judge["evaluations"]:
            candidate_map.setdefault(evaluation["candidate_id"], []).append(evaluation)

    results = []
    for candidate_id, evaluations in candidate_map.items():
        if len(evaluations) != 3:
            raise ValueError(f"{candidate_id}: expected 3 evaluations")
        totals = [int(item["total"]) for item in evaluations]
        core = [
            int(item["scores"]["question_fidelity"])
            + int(item["scores"]["fact_accuracy"])
            + int(item["scores"]["job_relevance"])
            for item in evaluations
        ]
        results.append(
            {
                "candidate_id": candidate_id,
                "hard_fail": any(item["hard_fail"] for item in evaluations),
                "median_total": median(totals),
                "median_core": median(core),
                "minimum_total": min(totals),
                "maximum_total": max(totals),
                "judge_spread": max(totals) - min(totals),
            }
        )
    valid = [result for result in results if not result["hard_fail"]]
    valid.sort(
        key=lambda item: (
            item["median_total"],
            item["median_core"],
            item["minimum_total"],
        ),
        reverse=True,
    )
    output = {
        "aggregation_rule": "median_total, median_core, minimum_total descending; any hard fail excludes",
        "ranking": valid,
        "excluded": [result for result in results if result["hard_fail"]],
    }
    dump_json(ROOT / "work" / "aggregate.json", output)


def manifest(paths: list[str]) -> None:
    entries = []
    for relative in paths:
        path = ROOT / relative
        data = path.read_bytes()
        entries.append(
            {
                "path": relative.replace("\\", "/"),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    dump_json(ROOT / "output" / "11_manifest.json", {"artifacts": entries})


def publish() -> None:
    comparison = load_json(ROOT / "work" / "final_comparison_final.json")
    if not comparison.get("comparison_ready"):
        raise ValueError("X/Y comparison is not ready")
    choice = comparison.get("overall_choice")
    if choice not in {"X", "Y"}:
        raise ValueError(f"invalid overall choice: {choice}")
    selected_path = ROOT / "work" / ("version_s.json" if choice == "X" else "version_y.json")
    selected = load_json(selected_path)
    postprocess_edits = []
    if choice == "X":
        original = (
            "최근 중소기업에 큰 영향을 미치는 이슈로 높은 환율 변동성과 중동지역 리스크를 "
            "선택하겠습니다. 한국은행이 이 위험을 점검하며"
        )
        replacement = (
            "최근 중소기업에 큰 영향을 미치는 이슈로 높은 환율 변동성을 선택하겠습니다. "
            "한국은행이 높은 환율 변동성과 중동지역 리스크를 점검하며"
        )
        if original not in selected["answers"]["q4"]:
            raise ValueError("expected X Q4 opening was not found")
        selected["answers"]["q4"] = selected["answers"]["q4"].replace(
            original, replacement, 1
        )
        selected["counts"]["q4"] = normalized_count(selected["answers"]["q4"])
        postprocess_edits.append(
            {
                "question": "q4",
                "reason": "단일 이슈 요구를 분명히 하고 중동지역 리스크는 공식 근거의 점검 맥락으로 분리",
                "fact_change": False,
            }
        )
    posting = load_json(ROOT / "input" / "career_run" / "00_채용공고분석.json")
    questions = {f"q{item['index']}": item["prompt"] for item in posting["questions"]}
    counts = {key: normalized_count(value) for key, value in selected["answers"].items()}
    if counts != selected["counts"]:
        raise ValueError(f"selected counts mismatch: {selected['counts']} != {counts}")

    final = {
        "target": posting["target"],
        "organization": posting["organization"],
        "role": posting["role"],
        "selected_version": choice,
        "selected_source": selected_path.relative_to(ROOT).as_posix(),
        "data_package_id": "SOL-DATA-608228643DF2-REFINAL",
        "questions": questions,
        "answers": selected["answers"],
        "counts": counts,
        "fact_ids": selected["fact_ids"],
        "postprocess_edits": postprocess_edits,
        "submission_readiness": "CONDITIONAL_PASS",
        "remaining_user_checks": [
            "청년인턴 연령 요건 충족 여부",
            "과거 신용보증기금 인턴 근무 여부",
            "2026년 9월 17일부터 선택 근무부점으로 출퇴근 가능한지",
            "채용 결격사유 해당 여부",
        ],
    }
    dump_json(ROOT / "output" / "08_final_selfintro.json", final)

    markdown = [
        "# 신용보증기금 체험형 청년인턴1(보증) 자기소개서",
        "",
    ]
    for number in range(1, 5):
        key = f"q{number}"
        markdown.extend(
            [
                f"## 문항 {number}",
                "",
                f"> {questions[key]}",
                "",
                selected["answers"][key],
                "",
                f"- 글자 수: {counts[key]:,}자(공백 포함, 줄바꿈 제외)",
                "",
            ]
        )
    (ROOT / "output" / "08_final_selfintro.md").write_text(
        "\n".join(markdown).rstrip() + "\n", encoding="utf-8"
    )

    evidence_catalog = {
        "PF-01": {"status": "CONFIRMED", "source": "input/career_run/02_확정경험원장.json", "claim_id": "clm_88cfeab230789e5b0d5f"},
        "PF-02": {"status": "CONFIRMED", "source": "input/career_run/02_확정경험원장.json", "claim_id": "clm_3e69991c9b56d728b429"},
        "PF-03": {"status": "CONFIRMED", "source": "input/career_run/02_확정경험원장.json", "claim_id": "clm_bdbd0d8bf79f5b7efce0"},
        "RF-01": {"status": "VERIFIED", "source": "input/career_run/04_공식근거.json", "claim_id": "kodit-role-20260711"},
        "RF-02": {"status": "VERIFIED", "source": "input/career_run/04_공식근거.json", "claim_id": "kodit-intern-duty-20260711"},
        "RF-03": {"status": "VERIFIED", "source": "input/career_run/04_공식근거.json", "claim_id": "bok-fx-risk-20260711"},
        "RF-04": {"status": "VERIFIED", "source": "input/career_run/04_공식근거.json", "claim_id": "kodit-liquidity-support-20260711"},
    }
    evidence_map = {
        "selected_version": choice,
        "questions": {},
        "catalog": evidence_catalog,
    }
    for key, ids in selected["fact_ids"].items():
        canonical = [item for item in ids if item in evidence_catalog]
        evidence_map["questions"][key] = {
            "fact_ids": canonical,
            "all_source_ids": ids,
            "count": counts[key],
        }
    dump_json(ROOT / "output" / "10_evidence_map.json", evidence_map)

    copies = {
        "work/blind_candidates.json": "output/01_blind_candidates.json",
        "work/private_mapping.json": "output/01_private_mapping.json",
        "work/judge_1_recruiter.json": "output/02_judge_1_recruiter.json",
        "work/judge_2_job_fact.json": "output/03_judge_2_job_fact.json",
        "work/judge_3_korean_editor.json": "output/04_judge_3_korean_editor.json",
        "work/aggregate.json": "output/05_aggregate.json",
        "work/version_s.json": "output/06_version_s.json",
        "work/version_s_judge_recruiter.json": "output/06_version_s_judge_recruiter.json",
        "work/version_s_judge_fact.json": "output/06_version_s_judge_fact.json",
        "work/version_s_judge_editor.json": "output/06_version_s_judge_editor.json",
        "work/version_s_reassessment.json": "output/06_version_s_reassessment.json",
        "work/version_y.json": "output/07_version_y.json",
        "work/final_comparison.json": "output/07_final_comparison_first.json",
        "work/final_comparison_retry.json": "output/07_final_comparison_second.json",
        "work/final_comparison_final.json": "output/07_final_comparison.json",
    }
    for source, destination in copies.items():
        target = ROOT / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("blind")
    sub.add_parser("aggregate")
    sub.add_parser("publish")
    manifest_parser = sub.add_parser("manifest")
    manifest_parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.command == "blind":
        build_blind()
    elif args.command == "aggregate":
        aggregate()
    elif args.command == "publish":
        publish()
    elif args.command == "manifest":
        manifest(args.paths)


if __name__ == "__main__":
    main()
