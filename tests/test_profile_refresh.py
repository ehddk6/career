import json
from pathlib import Path

from career_pipeline.inventory import digest_path
from career_pipeline.profile_builder import excerpt_sha256
from career_pipeline.profile_refresh import (
    refresh_profile,
    render_profile_review,
    write_refresh_outputs,
)
from career_pipeline.profile_schema import (
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
)


def confirmed_ledger_for(
    root: Path,
    source: Path,
    *,
    paragraph_index: int = 0,
    excerpt_hash: str | None = None,
) -> ExperienceLedger:
    paragraph = source.read_text(encoding="utf-8").splitlines()[paragraph_index]
    reference = EvidenceRef(
        source_path=source.relative_to(root).as_posix(),
        paragraph_index=paragraph_index,
        source_sha256=digest_path(source),
        excerpt_sha256=excerpt_hash or excerpt_sha256(paragraph),
    )
    claim = ProfileClaim("budget_savings", "10000000원", "confirmed", (reference,))
    experience = Experience(
        "exp_1",
        "절감 경험",
        "",
        None,
        "",
        paragraph,
        (),
        (),
        (),
        (claim,),
        "confirmed",
        "2026-06-21T12:00:00+09:00",
    )
    return ExperienceLedger(1, "2026-06-21T12:00:00+09:00", root.as_posix(), (experience,))


def test_refresh_marks_changed_evidence_stale_without_mutating_confirmed_ledger(
    tmp_path: Path,
):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원을 절감했습니다.", encoding="utf-8")
    ledger = confirmed_ledger_for(tmp_path, source)
    source.write_text("예산 2,000만원을 절감했습니다.", encoding="utf-8")

    review = refresh_profile(tmp_path, ledger)

    assert ledger.experiences[0].status == "confirmed"
    assert review.items[0].status == "stale"
    assert review.items[0].reason == "source_sha256_changed"


def test_refresh_reports_missing_and_out_of_range_evidence(tmp_path: Path):
    source = tmp_path / "career.txt"
    source.write_text("근거 10건", encoding="utf-8")
    missing_ledger = confirmed_ledger_for(tmp_path, source)
    source.unlink()

    missing = refresh_profile(tmp_path, missing_ledger)
    assert missing.items[0].status == "missing"
    assert missing.items[0].reason == "source_missing"

    source.write_text("근거 10건", encoding="utf-8")
    out_of_range = confirmed_ledger_for(tmp_path, source)
    reference = out_of_range.experiences[0].claims[0].evidence[0]
    bad_reference = EvidenceRef(**{**reference.__dict__, "paragraph_index": 5})
    claim = ProfileClaim("case_count", "10건", "confirmed", (bad_reference,))
    experience = Experience(
        **{**out_of_range.experiences[0].__dict__, "claims": (claim,)}
    )

    review = refresh_profile(
        tmp_path,
        ExperienceLedger(**{**out_of_range.__dict__, "experiences": (experience,)}),
    )
    assert review.items[0].reason == "paragraph_index_out_of_range"


def test_refresh_distinguishes_excerpt_change_and_unchanged(tmp_path: Path):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원을 절감했습니다.", encoding="utf-8")

    unchanged = refresh_profile(tmp_path, confirmed_ledger_for(tmp_path, source))
    assert unchanged.items[0].status == "unchanged"

    changed = refresh_profile(
        tmp_path,
        confirmed_ledger_for(tmp_path, source, excerpt_hash="c" * 64),
    )
    assert changed.items[0].status == "stale"
    assert changed.items[0].reason == "excerpt_sha256_changed"


def test_refresh_rejects_path_traversal(tmp_path: Path):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원", encoding="utf-8")
    ledger = confirmed_ledger_for(tmp_path, source)
    reference = ledger.experiences[0].claims[0].evidence[0]
    escaped = EvidenceRef(**{**reference.__dict__, "source_path": "../outside.txt"})
    claim = ProfileClaim("budget_savings", "10000000원", "confirmed", (escaped,))
    experience = Experience(**{**ledger.experiences[0].__dict__, "claims": (claim,)})

    review = refresh_profile(
        tmp_path,
        ExperienceLedger(**{**ledger.__dict__, "experiences": (experience,)}),
    )

    assert review.items[0].status == "missing"
    assert review.items[0].reason == "path_outside_workspace"


def test_render_and_write_refresh_outputs(tmp_path: Path):
    source = tmp_path / "career.txt"
    source.write_text("예산 1,000만원을 절감했습니다.", encoding="utf-8")
    ledger = confirmed_ledger_for(tmp_path, source)
    review = refresh_profile(tmp_path, ledger)

    rendered = render_profile_review(review)
    assert "## 변경 없음" in rendered
    assert "## 재확인 필요" in rendered
    assert "## 근거 없음" in rendered

    profile_dir = tmp_path / ".career_profile"
    write_refresh_outputs(profile_dir, review, ledger)

    assert (profile_dir / "profile_review.md").read_text(encoding="utf-8") == rendered
    payload = json.loads(
        (profile_dir / "experience_ledger.proposed.json").read_text(encoding="utf-8")
    )
    assert payload["experiences"][0]["experience_id"] == "exp_1"
