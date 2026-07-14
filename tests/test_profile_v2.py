import csv
import json
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.models import DraftResponse, ExperienceClaimRef
from career_pipeline.orchestrator import (
    _hydrate_claim_evidence_paths,
    _link_final_claims_to_interview_pack,
)
from career_pipeline.profile_confirmation import confirm_ledger
from career_pipeline.profile_schema import (
    ClaimVerification,
    EvidenceRef,
    Experience,
    ExperienceLedger,
    ProfileClaim,
    stable_claim_id,
)
from career_pipeline.validation import _claim_overstates_contribution


HASH = "a" * 64


def _v2_proposal() -> ExperienceLedger:
    evidence = (EvidenceRef("career.txt", 0, HASH, "b" * 64),)
    provisional = ProfileClaim(
        "experience_summary", "자료를 대조했습니다", "proposed", evidence,
        verification=ClaimVerification(
            method="direct_source", scope="source excerpt", contribution="observed"
        ),
    )
    claim = ProfileClaim(
        provisional.field, provisional.normalized_value, provisional.status,
        provisional.evidence, stable_claim_id("exp_1", provisional), provisional.verification,
    )
    return ExperienceLedger(
        2, "2026-07-14T00:00:00+09:00", "C:/career",
        (Experience(
            "exp_1", "경험", "", None, "역할", "상황", ("대조",), (), (),
            (claim,), "proposed", None,
        ),),
    )


def test_v2_confirmation_is_claim_scoped(tmp_path: Path):
    ledger = _v2_proposal()
    claim = ledger.experiences[0].claims[0]
    decisions = tmp_path / "decisions.csv"
    with decisions.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "claim_id", "decision", "method", "baseline", "result", "formula",
            "measurement_period", "scope", "contribution",
        ))
        writer.writeheader()
        writer.writerow({
            "claim_id": claim.claim_id, "decision": "confirmed",
            "method": "direct_source", "scope": "source excerpt",
            "contribution": "observed",
        })

    confirmed, counts = confirm_ledger(ledger, decisions)

    assert confirmed.experiences[0].claims[0].status == "confirmed"
    assert confirmed.experiences[0].status == "confirmed"
    assert counts["confirmed"] == 1


def test_profile_migrate_writes_separate_v2_file(tmp_path: Path):
    source = tmp_path / "v1.json"
    payload = {
        "schema_version": 1, "generated_at": "2026-07-14", "workspace_root": "C:/career",
        "experiences": [{
            "experience_id": "exp_1", "title": "경험", "organization_alias": "",
            "period": None, "role": "역할", "situation": "상황", "actions": ["확인"],
            "outcomes": [], "competencies": [], "status": "confirmed",
            "confirmed_at": "2026-07-14", "claims": [{
                "field": "metric:percentage", "normalized_value": "30%", "status": "confirmed",
                "evidence": [{"source_path": "career.txt", "paragraph_index": 0,
                    "source_sha256": HASH, "excerpt_sha256": "b" * 64}],
            }],
        }],
    }
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "v2.proposed.json"

    assert main(["profile", "migrate", "--source", str(source), "--output", str(output)]) == 0
    assert json.loads(source.read_text(encoding="utf-8"))["schema_version"] == 1
    migrated = json.loads(output.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2
    assert migrated["experiences"][0]["claims"][0]["status"] == "needs_verification"


def test_contribution_scope_only_applies_to_sentence_describing_claim():
    claim = ProfileClaim(
        field="experience_summary",
        normalized_value="기초연금 관련 자료를 체계적으로 분류했습니다.",
        status="confirmed",
        evidence=(),
        claim_id="clm_test",
        verification=ClaimVerification(
            method="direct_source",
            scope="source excerpt",
            contribution="observed",
        ),
    )

    assert not _claim_overstates_contribution(
        claim,
        "기초연금 관련 자료를 체계적으로 분류했습니다. 입사 후 업무에 기여하겠습니다.",
    )
    assert _claim_overstates_contribution(
        claim,
        "기초연금 관련 자료를 체계적으로 분류해 처리 속도 개선에 기여했습니다.",
    )
    assert _claim_overstates_contribution(
        claim,
        "기초연금 관련 자료를 체계적으로 분류해 지급 절차가 원활히 진행되도록 기여한 경험이 있습니다.",
    )


def test_rigorous_candidate_evidence_paths_are_hydrated_from_exact_claim_ids():
    ledger = _v2_proposal()
    claim = ledger.experiences[0].claims[0]
    responses = [DraftResponse(
        1,
        "자료를 정리했습니다.",
        (),
        (ExperienceClaimRef(ledger.experiences[0].experience_id, (), (claim.claim_id,)),),
    )]

    _hydrate_claim_evidence_paths(responses, ledger)

    assert responses[0].evidence_paths == ("career.txt",)


def test_final_claim_ids_are_linked_to_matching_interview_blocks(tmp_path: Path):
    pack = tmp_path / "08_면접대비팩.md"
    pack.write_text("## 문항 1\n기존 답변\n\n## 문항 2\n다른 답변\n", encoding="utf-8")
    responses = [
        DraftResponse(
            1,
            "답변",
            (),
            (ExperienceClaimRef("exp_1", (), ("clm_1",)),),
            ("research_1",),
        ),
    ]

    _link_final_claims_to_interview_pack(tmp_path, responses)

    text = pack.read_text(encoding="utf-8")
    assert "최종 제출본 근거 ID: exp_1, clm_1, research_1" in text
    assert text.index("최종 제출본 근거 ID") < text.index("## 문항 2")
