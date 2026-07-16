import json
from pathlib import Path

from career_pipeline.__main__ import build_parser, main
from career_pipeline.inventory import digest_path
from career_pipeline.profile_builder import excerpt_sha256


def confirmed_payload(root: Path, source: Path) -> dict:
    text = source.read_text(encoding="utf-8")
    return {
        "schema_version": 1,
        "generated_at": "2026-06-21T12:00:00+09:00",
        "workspace_root": root.as_posix(),
        "experiences": [
            {
                "experience_id": "exp_1",
                "title": "절감 경험",
                "organization_alias": "",
                "period": None,
                "role": "",
                "situation": text,
                "actions": [],
                "outcomes": [],
                "competencies": [],
                "claims": [
                    {
                        "field": "budget_savings",
                        "normalized_value": "10000000원",
                        "status": "confirmed",
                        "evidence": [
                            {
                                "source_path": source.relative_to(root).as_posix(),
                                "paragraph_index": 0,
                                "source_sha256": digest_path(source),
                                "excerpt_sha256": excerpt_sha256(text),
                            }
                        ],
                    }
                ],
                "status": "confirmed",
                "confirmed_at": "2026-06-21T12:00:00+09:00",
            }
        ],
    }


def test_parser_exposes_profile_build_refresh_and_validate():
    parser = build_parser()

    build = parser.parse_args(
        ["profile", "build", "--root", ".", "--output", "profile.json"]
    )
    refresh = parser.parse_args(
        ["profile", "refresh", "--root", ".", "--profile", "profile.json"]
    )
    validate = parser.parse_args(
        ["profile", "validate", "--profile", "profile.json"]
    )

    assert build.profile_command == "build"
    assert refresh.profile_command == "refresh"
    assert validate.profile_command == "validate"


def test_profile_build_and_validate_commands(tmp_path: Path, capsys):
    (tmp_path / "career.txt").write_text(
        "자료를 확인해 예산 1,000만원을 절감했습니다.", encoding="utf-8"
    )
    output = tmp_path / ".career_profile" / "experience_ledger.proposed.json"

    assert main(["profile", "build", "--root", str(tmp_path), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["experiences"][0]["status"] == "proposed"
    assert "모두 proposed" in output.with_suffix(".md").read_text(encoding="utf-8")
    assert (output.parent / "experience_review_queue.json").exists()
    assert "확정 우선 검토표" in (
        output.parent / "experience_review_queue.md"
    ).read_text(encoding="utf-8")

    assert main(["profile", "validate", "--profile", str(output)]) == 0
    assert "valid" in capsys.readouterr().out


def test_profile_build_prefers_dedicated_experience_folder(tmp_path: Path):
    (tmp_path / "template.txt").write_text(
        "자료를 확인하고 결과를 정리했습니다.", encoding="utf-8"
    )
    experience_dir = tmp_path / "경험정리"
    experience_dir.mkdir()
    (experience_dir / "career.txt").write_text(
        "민원 안내 담당으로 문의 유형을 분석해 안내 순서를 개선했습니다.",
        encoding="utf-8",
    )
    output = tmp_path / ".career_profile" / "experience_ledger.proposed.json"

    assert main(["profile", "build", "--root", str(tmp_path), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["experiences"]) == 1
    assert payload["experiences"][0]["title"] == "career 문단 1"


def test_profile_validate_returns_4_for_invalid_profile(tmp_path: Path):
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")

    assert main(["profile", "validate", "--profile", str(path)]) == 4


def test_profile_validate_blocks_missing_source_evidence(tmp_path: Path, capsys):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원을 절감했습니다.", encoding="utf-8")
    profile = tmp_path / ".career_profile" / "experience_ledger.json"
    profile.parent.mkdir()
    profile.write_text(
        json.dumps(confirmed_payload(tmp_path, source), ensure_ascii=False),
        encoding="utf-8",
    )
    source.unlink()

    assert main(["profile", "validate", "--profile", str(profile)]) == 4
    output = capsys.readouterr().out
    assert "invalid source evidence" in output
    assert "source_missing" in output


def test_profile_refresh_returns_2_and_writes_review_when_stale(tmp_path: Path):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원을 절감했습니다.", encoding="utf-8")
    profile_dir = tmp_path / ".career_profile"
    profile_dir.mkdir()
    profile = profile_dir / "experience_ledger.json"
    profile.write_text(
        json.dumps(confirmed_payload(tmp_path, source), ensure_ascii=False),
        encoding="utf-8",
    )
    source.write_text("예산 2,000만원을 절감했습니다.", encoding="utf-8")

    result = main(
        [
            "profile",
            "refresh",
            "--root",
            str(tmp_path),
            "--profile",
            str(profile),
        ]
    )

    assert result == 2
    assert "source_sha256_changed" in (profile_dir / "profile_review.md").read_text(
        encoding="utf-8"
    )
