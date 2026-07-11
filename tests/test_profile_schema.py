import json
from pathlib import Path

import pytest

from career_pipeline.profile_schema import (
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
    ProfileValidationError,
    ledger_to_dict,
    load_ledger,
    validate_ledger,
)


HASH = "a" * 64


def evidence() -> EvidenceRef:
    return EvidenceRef(
        source_path="경험정리/source.docx",
        paragraph_index=3,
        source_sha256=HASH,
        excerpt_sha256="b" * 64,
    )


def experience(*, claim_status: str = "confirmed", claim_evidence=None) -> Experience:
    refs = (evidence(),) if claim_evidence is None else claim_evidence
    return Experience(
        experience_id="exp_123",
        title="숙박비 검증",
        organization_alias="지자체",
        period=None,
        role="증빙 검토",
        situation="금액 불일치",
        actions=("교차 확인",),
        outcomes=("예산 누수 방지",),
        competencies=("정확성",),
        claims=(
            ProfileClaim(
                field="budget_savings",
                normalized_value="10000000원",
                status=claim_status,
                evidence=refs,
            ),
        ),
        status="confirmed",
        confirmed_at="2026-06-21T12:00:00+09:00",
    )


def ledger(*experiences: Experience) -> ExperienceLedger:
    return ExperienceLedger(
        schema_version=1,
        generated_at="2026-06-21T12:00:00+09:00",
        workspace_root="C:/career",
        experiences=experiences or (experience(),),
    )


def test_confirmed_claim_requires_hashed_evidence():
    candidate = ledger(experience(claim_evidence=()))

    with pytest.raises(ProfileValidationError) as error:
        validate_ledger(candidate)

    assert "experiences[0].claims[0].evidence" in str(error.value)


def test_confirmed_experience_cannot_use_only_proposed_claims():
    candidate = ledger(experience(claim_status="proposed"))

    with pytest.raises(ProfileValidationError) as error:
        validate_ledger(candidate)

    assert "experiences[0].claims" in str(error.value)
    assert "confirmed claim" in str(error.value)


def test_load_ledger_reports_nested_json_error_path(tmp_path: Path):
    payload = ledger_to_dict(ledger())
    payload["experiences"][0]["claims"][0]["evidence"][0]["source_sha256"] = "bad"
    path = tmp_path / "experience_ledger.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ProfileValidationError) as error:
        load_ledger(path)

    assert "experiences[0].claims[0].evidence[0].source_sha256" in str(error.value)


def test_validate_ledger_collects_duplicate_id_and_status_errors():
    first = experience()
    second = Experience(**{**first.__dict__, "status": "invented"})

    with pytest.raises(ProfileValidationError) as error:
        validate_ledger(ledger(first, second))

    message = str(error.value)
    assert "experiences[1].experience_id" in message
    assert "experiences[1].status" in message


def test_ledger_json_round_trip(tmp_path: Path):
    path = tmp_path / "experience_ledger.json"
    path.write_text(
        json.dumps(ledger_to_dict(ledger()), ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_ledger(path) == ledger()
