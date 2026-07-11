import json
from pathlib import Path

from career_pipeline.__main__ import main
from career_pipeline.eligibility import (
    applicant_profile_from_ledger,
    applicant_profile_from_dict,
    compare_postings,
    decision_from_dict,
    evaluate_eligibility,
    is_profile_stale,
    posting_record_to_dict,
    normalized_posting_content_sha256,
)
from career_pipeline.models import (
    ApplicantExperience,
    ApplicantLocation,
    ApplicantProfile,
    CertificationRecord,
    EducationRecord,
    EligibilityRule,
    PostingRecord,
)
from career_pipeline.profile_schema import Experience, ExperienceLedger


HASH = "a" * 64


def profile(**overrides) -> ApplicantProfile:
    values = {
        "schema_version": 1,
        "profile_id": "applicant-1",
        "generated_at": "2026-07-11T12:00:00+09:00",
        "experience_ledger_path": None,
        "experiences": (
            ApplicantExperience(
                "exp-1", "자료 검증", months=24, skills=("자료 검증", "고객 응대"), status="confirmed"
            ),
        ),
        "education": (EducationRecord("bachelor", "경영학", True),),
        "certifications": (
            CertificationRecord("정보처리기사", expires_at="2027-01-01", status="valid", verified=True),
        ),
        "locations": ("서울",),
    }
    values.update(overrides)
    return ApplicantProfile(**values)


def posting(*, required=(), preferred=(), source_status="verified_domain") -> PostingRecord:
    return PostingRecord(
        schema_version=1,
        posting_id="posting-1",
        url="https://example.or.kr/jobs/1",
        official_domain="example.or.kr",
        published_at="2026-07-01",
        deadline_at="2026-07-31",
        title="자료 검증 담당",
        organization="기관",
        role="자료 검증 담당",
        body_sha256=HASH,
        retrieved_at="2026-07-11T12:00:00+09:00",
        source_status=source_status,
        locations=("서울",),
        required_rules=tuple(required),
        preferred_rules=tuple(preferred),
    )


def rule(rule_id, kind, *, required=True, **criteria):
    return EligibilityRule(rule_id, kind, f"{rule_id} 조건", required, criteria)


def test_all_structured_required_rules_are_eligible():
    decision = evaluate_eligibility(
        profile(),
        posting(
            required=(
                rule("edu", "education", minimum_level="bachelor"),
                rule("exp", "experience", minimum_months=12, skills=["자료 검증"]),
                rule("cert", "certification", names=["정보처리기사"]),
                rule("location", "location", allowed=["서울"]),
            )
        ),
        evaluated_at="2026-07-11T12:00:00+09:00",
    )

    assert decision.status == "eligible"
    assert not decision.human_review_required
    assert all(item.status == "met" for item in decision.rule_evaluations)


def test_missing_preferred_condition_is_eligible_with_gaps():
    decision = evaluate_eligibility(
        profile(),
        posting(
            required=(rule("edu", "education", minimum_level="bachelor"),),
            preferred=(rule("pref", "certification", required=False, names=["변호사"]),),
        ),
    )

    assert decision.status == "eligible_with_gaps"
    assert decision.human_review_required


def test_required_unknown_is_manual_review_not_eligible():
    pending = profile(education=(EducationRecord("bachelor", "경영학", None),))
    decision = evaluate_eligibility(
        pending,
        posting(required=(rule("edu", "education", minimum_level="bachelor", field="경제학"),)),
    )

    assert decision.status == "manual_review"
    assert decision.rule_evaluations[0].status == "unknown"


def test_required_failure_is_ineligible_even_when_another_rule_is_unknown():
    decision = evaluate_eligibility(
        profile(education=(EducationRecord("high_school", "", True),)),
        posting(
            required=(
                rule("edu", "education", minimum_level="bachelor"),
                rule("custom", "custom"),
            )
        ),
    )

    assert decision.status == "ineligible"


def test_unverified_source_requires_manual_review():
    decision = evaluate_eligibility(profile(), posting(source_status="unverified"))

    assert decision.status == "manual_review"
    assert decision.human_review_required


def test_profile_projection_uses_confirmed_experiences_only():
    from career_pipeline.profile_schema import EvidenceRef, ProfileClaim

    confirmed = Experience(
        "confirmed", "검증", "기관", None, "역할", "상황", (), (), (),
        (ProfileClaim("role", "검증", "confirmed", (EvidenceRef("career.txt", 0, HASH, HASH),)),),
        "confirmed", "2026-07-11"
    )
    proposed = Experience(
        "proposed", "추정", "기관", None, "역할", "상황", (), (), (), (), "proposed", None
    )
    ledger = ExperienceLedger(1, "2026-07-11", "C:/career", (confirmed, proposed))

    result = applicant_profile_from_ledger(ledger, profile_id="p1")

    assert [item.experience_id for item in result.experiences] == ["confirmed"]


def test_posting_change_and_duplicate_events_are_distinct():
    current = posting()
    assert compare_postings(None, current).event == "new"
    assert compare_postings(current, current).event == "exact_duplicate"
    changed = PostingRecord(**{**current.__dict__, "body_sha256": "b" * 64})
    assert compare_postings(current, changed).event == "changed"
    duplicate = PostingRecord(
        **{**current.__dict__, "posting_id": "other", "url": "https://mirror.example.or.kr/jobs/1"}
    )
    assert compare_postings(current, duplicate).event == "content_duplicate"


def test_json_round_trip_and_cli_evaluation(tmp_path: Path):
    profile_path = tmp_path / "profile.json"
    posting_path = tmp_path / "posting.json"
    output_path = tmp_path / "decision.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "p1",
                "generated_at": "2026-07-11",
                "experience_ledger_path": None,
                "experiences": [],
                "education": [],
                "certifications": [],
                "locations": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    posting_path.write_text(json.dumps(posting_record_to_dict(posting())), encoding="utf-8")

    result = main(
        [
            "eligibility",
            "evaluate",
            "--profile",
            str(profile_path),
            "--posting",
            str(posting_path),
            "--output",
            str(output_path),
        ]
    )

    assert result == 2
    decision = decision_from_dict(json.loads(output_path.read_text(encoding="utf-8")))
    assert decision.status == "manual_review"
    assert decision.human_review_required is True


def test_unknown_natural_language_requirement_stops_at_manual_review():
    decision = evaluate_eligibility(
        profile(), posting(required=(rule("custom", "custom"),))
    )

    assert decision.status == "manual_review"


def test_decision_reasons_are_machine_readable_and_status_specific():
    decision = evaluate_eligibility(
        profile(education=()),
        posting(required=(rule("edu", "education", minimum_level="bachelor"),)),
        evaluated_at="2026-07-11",
    )

    assert decision.status == "manual_review"
    assert decision.reasons[0].code == "education_info_missing"
    assert decision.reasons[0].field == "education"
    assert decision.reasons[0].message


def test_education_level_order_and_expected_date_boundary():
    assert evaluate_eligibility(
        profile(education=(EducationRecord("master", "경영학", True),)),
        posting(required=(rule("edu", "education", minimum_level="bachelor"),)),
        evaluated_at="2026-07-11",
    ).status == "eligible"
    expected = EducationRecord(
        "bachelor", "경영학", None, "2026-12-31", status="expected"
    )
    decision = evaluate_eligibility(
        profile(education=(expected,)),
        posting(required=(rule("edu", "education", minimum_level="bachelor", allow_expected=True),)),
        evaluated_at="2026-07-11",
    )
    assert decision.status == "manual_review"
    assert decision.reasons[0].code == "graduation_expected_after_cutoff"


def test_overlapping_dated_experience_is_not_double_counted():
    experiences = (
        ApplicantExperience("a", "검증", months=None, status="confirmed", start_date="2024-01-01", end_date="2024-12-31"),
        ApplicantExperience("b", "검증", months=None, status="confirmed", start_date="2024-06-01", end_date="2025-05-31"),
    )
    decision = evaluate_eligibility(
        profile(experiences=experiences),
        posting(required=(rule("exp", "experience", minimum_months=18),)),
        evaluated_at="2026-07-11",
    )
    assert decision.status == "ineligible"
    assert decision.reasons[0].code == "experience_minimum_not_met"


def test_certification_or_and_and_expiry_cutoff():
    certifications = (
        CertificationRecord("정보처리기사", expires_at="2026-07-11", status="valid", verified=True),
        CertificationRecord("공인중개사", status="valid", verified=True),
    )
    any_decision = evaluate_eligibility(
        profile(certifications=certifications),
        posting(required=(rule("cert", "certification", names=["정보처리기사", "공인중개사"], operator="any"),)),
        evaluated_at="2026-07-11",
    )
    all_decision = evaluate_eligibility(
        profile(certifications=certifications),
        posting(required=(rule("cert", "certification", names=["정보처리기사", "공인중개사"], operator="all"),)),
        evaluated_at="2026-07-12",
    )
    assert any_decision.status == "eligible"
    assert all_decision.status == "ineligible"


def test_location_type_and_alias_are_not_conflated():
    decision = evaluate_eligibility(
        profile(
            locations=("강원특별자치도",),
            location_records=(ApplicantLocation("강원특별자치도", "regional_talent"),),
        ),
        posting(required=(rule("region", "location", allowed=["강원도"], location_type="regional_talent"),)),
        evaluated_at="2026-07-11",
    )
    assert decision.status == "eligible"


def test_same_input_without_explicit_cutoff_is_deterministic():
    required = (rule("edu", "education", minimum_level="bachelor"),)
    first = evaluate_eligibility(profile(), posting(required=required))
    second = evaluate_eligibility(profile(), posting(required=required))
    assert first == second


def test_profile_projection_records_ledger_hash_and_staleness(tmp_path: Path):
    from career_pipeline.profile_schema import EvidenceRef, ProfileClaim

    confirmed = Experience(
        "confirmed", "검증", "기관", None, "역할", "상황", (), (), (),
        (ProfileClaim("role", "검증", "confirmed", (EvidenceRef("career.txt", 0, HASH, HASH),)),),
        "confirmed", "2026-07-11"
    )
    ledger = ExperienceLedger(1, "2026-07-11", "C:/career", (confirmed,))
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    result = applicant_profile_from_ledger(ledger, profile_id="p1", ledger_path=str(ledger_path))
    assert result.experience_ledger_sha256
    assert is_profile_stale(result, ledger_path) is False
    ledger_path.write_text("changed", encoding="utf-8")
    assert is_profile_stale(result, ledger_path) is True


def test_html_normalization_ignores_markup_and_whitespace_but_not_text():
    first = normalized_posting_content_sha256("<p>지원 자격</p> <div>학사</div>".encode())
    second = normalized_posting_content_sha256("<div>지원 자격</div>\n<p>학사</p>".encode())
    changed = normalized_posting_content_sha256("<p>지원 자격</p> <div>석사</div>".encode())
    assert first == second
    assert first != changed


def test_phase2_output_does_not_overwrite_without_force(tmp_path: Path):
    profile_path = tmp_path / "profile.json"
    posting_path = tmp_path / "posting.json"
    output_path = tmp_path / "decision.json"
    profile_path.write_text(
        json.dumps({
            "schema_version": 1,
            "profile_id": "p1",
            "generated_at": "2026-07-11",
            "experience_ledger_path": None,
            "experiences": [],
            "education": [],
            "certifications": [],
            "locations": [],
        }),
        encoding="utf-8",
    )
    posting_path.write_text(json.dumps(posting_record_to_dict(posting())), encoding="utf-8")
    args = [
        "eligibility", "evaluate", "--profile", str(profile_path),
        "--posting", str(posting_path), "--output", str(output_path),
        "--run-dir", str(tmp_path),
    ]
    assert main(args) == 2
    assert main(args) == 4
    assert main(args + ["--force"]) == 2
    outside = tmp_path.parent / "phase2-outside.json"
    assert main(
        [
            "eligibility", "evaluate", "--profile", str(profile_path),
            "--posting", str(posting_path), "--output", str(outside),
            "--run-dir", str(tmp_path),
        ]
    ) == 4
