from career_pipeline.models import ApplicantProfile, CertificationRecord
from career_pipeline.submission_preflight import assess_submission_preflight


def _profile(*credentials: CertificationRecord) -> ApplicantProfile:
    return ApplicantProfile(
        1,
        "profile-1",
        "2026-08-30T09:00:00+09:00",
        None,
        (),
        (),
        tuple(credentials),
        (),
    )


def test_expired_language_or_credential_is_excluded_and_requires_review():
    report = assess_submission_preflight(
        _profile(
            CertificationRecord(
                "TOEIC", expires_at="2026-08-29", status="valid", verified=True
            )
        ),
        as_of="2026-08-30T18:00:00+09:00",
        included_credential_names=("TOEIC",),
    )

    assert report.status == "blocked"
    assert report.excluded_credentials == ("TOEIC",)
    assert "credential_expired:TOEIC" in report.reason_codes
    assert report.metric == "application_completeness_not_writing_score_or_hire_probability"


def test_valid_verified_credential_is_usable():
    report = assess_submission_preflight(
        _profile(
            CertificationRecord(
                "컴퓨터활용능력", expires_at=None, status="valid", verified=True
            )
        ),
        as_of="2026-08-30",
        included_credential_names=("컴퓨터활용능력",),
    )

    assert report.status == "ready"
    assert report.usable_credentials == ("컴퓨터활용능력",)


def test_expired_language_can_be_explicitly_excluded_without_blocking():
    report = assess_submission_preflight(
        _profile(
            CertificationRecord(
                "TOEIC", expires_at="2026-08-29", status="valid", verified=True
            )
        ),
        as_of="2026-08-30",
        included_credential_names=(),
    )

    assert report.status == "ready"
    assert report.excluded_credentials == ("TOEIC",)
    assert report.reason_codes == ()


def test_missing_required_attachment_blocks_preflight():
    report = assess_submission_preflight(
        _profile(),
        as_of="2026-08-30",
        supplied_attachment_keys=("resume",),
        required_attachment_keys=("resume", "transcript"),
    )

    assert report.status == "blocked"
    assert report.missing_required_attachments == ("transcript",)


def test_selected_credential_binding_automatically_requires_its_attachment():
    report = assess_submission_preflight(
        _profile(
            CertificationRecord(
                "컴퓨터활용능력", status="valid", verified=True
            )
        ),
        as_of="2026-08-30",
        selected_credential_attachments={"컴퓨터활용능력": "certificate"},
        supplied_attachment_keys=(),
    )

    assert report.status == "blocked"
    assert report.missing_required_attachments == ("certificate",)


def test_selected_language_without_expiry_requires_manual_review():
    report = assess_submission_preflight(
        _profile(CertificationRecord("TOEIC", status="valid", verified=True)),
        as_of="2026-08-30",
        selected_credential_attachments={"TOEIC": "language_score"},
        supplied_attachment_keys=("language_score",),
    )

    assert report.status == "manual_review"
    assert "language_credential_expiry_missing:TOEIC" in report.reason_codes


def test_ambiguous_selected_credential_requires_manual_review():
    duplicate = CertificationRecord(
        "컴퓨터활용능력", status="valid", verified=True
    )
    report = assess_submission_preflight(
        _profile(duplicate, duplicate),
        as_of="2026-08-30",
        selected_credential_attachments={"컴퓨터활용능력": "certificate"},
        supplied_attachment_keys=("certificate",),
    )

    assert report.status == "manual_review"
    assert "credential_ambiguous:컴퓨터활용능력" in report.reason_codes
