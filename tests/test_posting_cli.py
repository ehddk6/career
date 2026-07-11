from hashlib import sha256
from pathlib import Path

from career_pipeline.__main__ import build_parser, main
from career_pipeline.posting_schema import LoadedPosting, PostingSourceMetadata


FIXTURE = Path(__file__).parent / "fixtures" / "hug_posting_excerpt.html"


def loaded_fixture() -> LoadedPosting:
    content = FIXTURE.read_bytes()
    return LoadedPosting(
        PostingSourceMetadata(
            "url",
            "https://khug.or.kr/posting",
            "2026-06-21T12:00:00+09:00",
            sha256(content).hexdigest(),
            "verified_domain",
            "text/html; charset=utf-8",
        ),
        ".html",
        content,
    )


def test_parser_exposes_posting_analyze():
    args = build_parser().parse_args(
        [
            "posting",
            "analyze",
            "--target",
            "HUG 금융·기금(강원)",
            "--source",
            "posting.html",
            "--official-source",
            "--output",
            "career_runs/test",
        ]
    )

    assert args.posting_command == "analyze"


def test_posting_analyze_writes_snapshot_json_and_markdown(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.setattr(
        "career_pipeline.__main__.load_posting_source",
        lambda *args, **kwargs: loaded_fixture(),
    )
    output = tmp_path / "analysis"

    result = main(
        [
            "posting",
            "analyze",
            "--target",
            "HUG 금융·기금(강원)",
            "--source",
            "https://khug.or.kr/posting",
            "--official-domain",
            "khug.or.kr",
            "--output",
            str(output),
        ]
    )

    assert result == 2  # fixture deliberately omits an explicit organization field
    assert (output / "00_채용공고원문" / "source.html").exists()
    assert (output / "00_채용공고분석.json").exists()
    markdown = (output / "00_채용공고분석.md").read_text(encoding="utf-8")
    assert "verified_domain" in markdown
    assert "도시재생 금융지원 관련 안내 등 업무 보조" in markdown
    assert "지원동기와 인턴 근무 목표" in markdown
    assert "organization" in markdown
    assert str(output) in capsys.readouterr().out


def test_posting_analyze_rejects_url_attestation_flag(tmp_path: Path):
    result = main(
        [
            "posting",
            "analyze",
            "--target",
            "기관 직무",
            "--source",
            "https://example.or.kr/posting",
            "--official-source",
            "--output",
            str(tmp_path / "analysis"),
        ]
    )

    assert result == 4
