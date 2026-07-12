"""Build and validate privacy-safe, review-only application packages."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .artifacts import load_and_verify_final_artifact, sha256_file
from .eligibility import canonicalize_url
from .models import ApplicantProfile, ApplicationAnswer, ApplicationAttachment, ApplicationPackage, EligibilityDecision, PostingRecord
from .path_policy import LockAcquisitionError, PathConfinementError, PathLinkError, confine_path, exclusive_lock
from .state import write_json

SCHEMA_VERSION = 1
OUTPUT_CONTRACT_VERSION = "phase4-review-required-v1"
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
_FIELD_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_REF = re.compile(r"^(private|attachment)-[0-9a-f]{24}$")
_FORBIDDEN = {"password", "passwd", "token", "secret", "authorization", "cookie", "session", "mfa", "otp"}


class ApplicationPackageError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _resource_ref(kind: str, digest: str) -> str:
    return f"{kind}-{sha256(f'{kind}|{digest}'.encode()).hexdigest()[:24]}"


def _timezone_aware(value: str, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ApplicationPackageError(f"{label} must be timezone-aware ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApplicationPackageError(f"{label} must be timezone-aware ISO-8601")


def _inside(root: Path, path: Path, *, label: str, must_exist: bool = True) -> Path:
    try:
        return confine_path(root, path, must_exist=must_exist)
    except PathLinkError as error:
        raise ApplicationPackageError(f"{label} must not traverse a symlink") from error
    except PathConfinementError as error:
        raise ApplicationPackageError(f"{label} must remain inside the workspace") from error


def _safe_file(root: Path, path: Path, *, label: str) -> Path:
    try:
        resolved = confine_path(root, path, require_file=True)
    except PathLinkError as error:
        raise ApplicationPackageError(f"{label} must be a regular non-symlink file") from error
    except PathConfinementError as error:
        raise ApplicationPackageError(f"{label} must be a regular non-symlink file")
    return resolved


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _attachment_type(path: Path) -> tuple[str, str]:
    suffix = path.suffix.casefold()
    head = path.read_bytes()[:16]
    types = {
        ".pdf": (b"%PDF", "application/pdf"),
        ".docx": (b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    }
    if suffix in {".jpg", ".jpeg"} and head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", suffix
    expected = types.get(suffix)
    if expected and head.startswith(expected[0]):
        return expected[1], suffix
    raise ApplicationPackageError(f"unsupported or mismatched attachment type: {suffix or 'missing'}")


def load_private_fields(root: Path, path: Path) -> tuple[dict[str, str], Path, str]:
    resolved = _safe_file(root, path, label="private data")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApplicationPackageError("private data must be valid UTF-8 JSON") from error
    fields = payload.get("fields") if isinstance(payload, dict) and payload.get("schema_version") == 1 else None
    if not isinstance(fields, dict) or not fields:
        raise ApplicationPackageError("private data fields must be a non-empty schema version 1 object")
    normalized: dict[str, str] = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not _FIELD_KEY.fullmatch(key):
            raise ApplicationPackageError(f"invalid private field key: {key}")
        if any(marker in key.casefold() for marker in _FORBIDDEN):
            raise ApplicationPackageError(f"credential-like private field is not allowed: {key}")
        if not isinstance(value, str) or not value.strip():
            raise ApplicationPackageError(f"private field must be a non-empty string: {key}")
        normalized[key] = value
    return normalized, resolved, sha256_file(resolved)


def _load_final_answers(run_dir: Path, state: dict[str, Any]) -> tuple[tuple[ApplicationAnswer, ...], str, str, str]:
    artifact, issues = load_and_verify_final_artifact(run_dir, state)
    if issues or artifact is None:
        raise ApplicationPackageError("final artifact verification failed: " + "; ".join(issues))
    if not isinstance(artifact.get("validation"), dict) or artifact["validation"].get("status") != "passed":
        raise ApplicationPackageError("final artifact quality gate has not passed")
    raw_path = artifact.get("answer_json_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise ApplicationPackageError("final artifact answer JSON path is missing")
    answer_path = _safe_file(run_dir, Path(raw_path), label="final answer JSON")
    try:
        payload = json.loads(answer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ApplicationPackageError("final answer JSON is invalid") from error
    items = payload.get("responses") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise ApplicationPackageError("final answer JSON must contain responses")
    questions = {q.get("index"): q for q in state.get("questions", []) if isinstance(q, dict) and isinstance(q.get("index"), int)}
    answers: list[ApplicationAnswer] = []
    seen: set[int] = set()
    for item in items:
        index = item.get("question_index") if isinstance(item, dict) else None
        answer = item.get("answer") if isinstance(item, dict) else None
        if not isinstance(index, int) or index < 1 or index in seen or not isinstance(answer, str) or not answer.strip():
            raise ApplicationPackageError("final answers require unique positive question indexes and non-empty text")
        question = questions.get(index, {})
        limit = question.get("character_limit")
        if limit is not None and (not isinstance(limit, int) or limit < 1 or len(answer) > limit):
            raise ApplicationPackageError(f"invalid or exceeded character limit for question {index}")
        answers.append(ApplicationAnswer(f"answer_{index}", index, str(question.get("prompt", f"Question {index}")), answer, sha256(answer.encode()).hexdigest(), limit))
        seen.add(index)
    answer_sha = sha256_file(answer_path)
    if artifact.get("sha256", {}).get("answer_json") != answer_sha:
        raise ApplicationPackageError("final answer SHA-256 does not match the manifest")
    return tuple(answers), answer_sha, _digest(artifact), _digest(state.get("questions", []))


def build_application_package(*, root: Path, run_dir: Path, run_state: dict[str, Any], profile: ApplicantProfile,
                              posting: PostingRecord, decision: EligibilityDecision, private_data_path: Path,
                              profile_sha256: str, attachments: Mapping[str, Path] | None = None,
                              created_at: str | None = None) -> ApplicationPackage:
    root, run_dir = root.resolve(), run_dir.resolve()
    _inside(root, run_dir, label="run directory")
    if not _SHA256.fullmatch(profile_sha256):
        raise ApplicationPackageError("profile_sha256 must be lowercase SHA-256")
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    _timezone_aware(created_at, "created_at")
    private_fields, _private_path, private_sha = load_private_fields(root, private_data_path)
    answers, final_sha, manifest_sha, question_sha = _load_final_answers(run_dir, run_state)
    reasons: list[str] = []
    if run_state.get("status") != "complete": reasons.append("final_run_not_complete")
    if decision.posting_id != posting.posting_id: reasons.append("decision_posting_mismatch")
    if decision.profile_id != profile.profile_id: reasons.append("decision_profile_mismatch")
    if posting.status != "active": reasons.append(f"posting_status:{posting.status}")
    if decision.status not in {"eligible", "eligible_with_gaps"}: reasons.append(f"eligibility_status:{decision.status}")
    attachment_items: list[ApplicationAttachment] = []
    for key, raw_path in sorted((attachments or {}).items()):
        if not _FIELD_KEY.fullmatch(key): raise ApplicationPackageError(f"invalid attachment field key: {key}")
        path = _safe_file(root, Path(raw_path), label=f"attachment {key}")
        size, digest = path.stat().st_size, sha256_file(path)
        if size > MAX_ATTACHMENT_BYTES: raise ApplicationPackageError(f"attachment exceeds 20MB: {key}")
        media_type, suffix = _attachment_type(path)
        attachment_items.append(ApplicationAttachment(key, _resource_ref("attachment", digest), digest, size, media_type, suffix))
    identity = sha256(f"{profile.profile_id}|{profile_sha256}|{private_sha}".encode()).hexdigest()
    seed = (OUTPUT_CONTRACT_VERSION, posting.posting_id, posting.body_sha256, profile_sha256, question_sha, manifest_sha, final_sha, identity)
    blocked = any(r.startswith(("final_run", "decision_", "posting_status", "eligibility_status:manual", "eligibility_status:ineligible")) for r in reasons)
    status = "blocked" if blocked else "manual_review" if decision.status == "eligible_with_gaps" else "ready_for_review"
    package = ApplicationPackage(
        SCHEMA_VERSION, "application-" + sha256("|".join(seed).encode()).hexdigest()[:24], created_at, "review_required",
        posting.posting_id, posting.body_sha256, canonicalize_url(posting.canonical_url or posting.url), posting.organization,
        posting.role, posting.locations, profile.profile_id, decision.decision_id, decision.status, profile_sha256, question_sha,
        manifest_sha, final_sha, OUTPUT_CONTRACT_VERSION, _resource_ref("private", private_sha), private_sha,
        tuple(sorted(private_fields)), identity, answers, tuple(attachment_items), status, tuple(reasons),
    )
    return validate_application_package(package)


def validate_application_package(package: ApplicationPackage) -> ApplicationPackage:
    if package.schema_version != SCHEMA_VERSION or package.mode != "review_required" or package.output_contract_version != OUTPUT_CONTRACT_VERSION:
        raise ApplicationPackageError("unsupported application package schema, mode, or output contract")
    _timezone_aware(package.created_at, "created_at")
    if package.validation_status not in {"ready_for_review", "manual_review", "blocked"}:
        raise ApplicationPackageError("invalid application package status")
    if package.validation_status == "ready_for_review" and package.eligibility_status != "eligible":
        raise ApplicationPackageError("only eligible packages can be ready_for_review")
    for name in ("posting_sha256", "profile_sha256", "question_schema_sha256", "final_manifest_sha256", "final_artifact_sha256", "private_data_sha256", "applicant_identity_fingerprint"):
        if not _SHA256.fullmatch(getattr(package, name)): raise ApplicationPackageError(f"{name} must be lowercase SHA-256")
    if not _RESOURCE_REF.fullmatch(package.private_data_ref) or package.private_data_ref != _resource_ref("private", package.private_data_sha256):
        raise ApplicationPackageError("invalid private data reference")
    keys = list(package.private_field_keys)
    if not keys or len(keys) != len(set(keys)) or any(not _FIELD_KEY.fullmatch(k) or any(m in k for m in _FORBIDDEN) for k in keys):
        raise ApplicationPackageError("invalid private field keys")
    answer_keys, attachment_keys = [], []
    for answer in package.answers:
        if not _FIELD_KEY.fullmatch(answer.field_key) or sha256(answer.answer.encode()).hexdigest() != answer.answer_sha256:
            raise ApplicationPackageError("invalid application answer")
        if answer.character_limit is not None and len(answer.answer) > answer.character_limit:
            raise ApplicationPackageError("application answer exceeds character limit")
        answer_keys.append(answer.field_key)
    for attachment in package.attachments:
        if (not _FIELD_KEY.fullmatch(attachment.field_key) or not _SHA256.fullmatch(attachment.sha256)
                or attachment.resource_ref != _resource_ref("attachment", attachment.sha256)
                or attachment.size < 0 or attachment.suffix not in {".pdf", ".docx", ".jpg", ".jpeg", ".png"}):
            raise ApplicationPackageError("invalid application attachment metadata")
        attachment_keys.append(attachment.field_key)
    if len([*keys, *answer_keys, *attachment_keys]) != len(set([*keys, *answer_keys, *attachment_keys])):
        raise ApplicationPackageError("application package field keys must be unique")
    if not package.package_id or not package.posting_id or not package.profile_id or not package.answers:
        raise ApplicationPackageError("application package is missing required fields")
    return package


def application_package_to_dict(package: ApplicationPackage) -> dict[str, Any]:
    return asdict(validate_application_package(package))


def application_package_from_dict(value: Any) -> ApplicationPackage:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ApplicationPackageError("unsupported application package schema version")
    try:
        data = dict(value)
        data["locations"] = tuple(data.get("locations", [])); data["private_field_keys"] = tuple(data.get("private_field_keys", [])); data["validation_reasons"] = tuple(data.get("validation_reasons", []))
        data["answers"] = tuple(ApplicationAnswer(**item) for item in data.get("answers", []))
        data["attachments"] = tuple(ApplicationAttachment(**item) for item in data.get("attachments", []))
        return validate_application_package(ApplicationPackage(**data))
    except (KeyError, TypeError, ValueError) as error:
        raise ApplicationPackageError("invalid application package") from error


def load_application_package(path: Path) -> ApplicationPackage:
    try: return application_package_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except json.JSONDecodeError as error: raise ApplicationPackageError("invalid application package JSON") from error


def materialize_package_values(root: Path, package: ApplicationPackage, *, private_data_path: Path,
                               attachments: Mapping[str, Path] | None = None) -> dict[str, str]:
    validate_application_package(package)
    fields, _path, digest = load_private_fields(root, private_data_path)
    if digest != package.private_data_sha256 or _resource_ref("private", digest) != package.private_data_ref:
        raise ApplicationPackageError("private data SHA-256 changed after package creation")
    if tuple(sorted(fields)) != package.private_field_keys:
        raise ApplicationPackageError("private data field set changed after package creation")
    supplied = attachments or {}
    if set(supplied) != {a.field_key for a in package.attachments}:
        raise ApplicationPackageError("attachment bindings do not match the package")
    values = {**fields, **{a.field_key: a.answer for a in package.answers}}
    for item in package.attachments:
        path = _safe_file(root, Path(supplied[item.field_key]), label=f"attachment {item.field_key}")
        media_type, suffix = _attachment_type(path)
        if sha256_file(path) != item.sha256 or path.stat().st_size != item.size or media_type != item.media_type or suffix != item.suffix:
            raise ApplicationPackageError(f"attachment changed after package creation: {item.field_key}")
        values[item.field_key] = str(path)
    return values


def write_application_package(path: Path, package: ApplicationPackage, *, force: bool = False) -> None:
    payload = application_package_to_dict(package); path = Path(path)
    if path.exists() and not force:
        try: existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error: raise ApplicationPackageError(f"output already exists: {path}") from error
        if _canonical_json(existing) == _canonical_json(payload): return
        if isinstance(existing, dict) and existing.get("package_id") == package.package_id:
            # The identity is content-derived; a later created_at alone must not
            # turn an idempotent request into a conflicting package.
            application_package_from_dict(existing)
            return
        raise ApplicationPackageError(f"output already exists: {path}")
    write_json(path, payload)


def _load_registry(path: Path) -> dict[str, Any]:
    if path.is_symlink(): raise ApplicationPackageError("application registry must not be a symlink")
    if not path.exists(): return {"schema_version": 1, "entries": [], "events": []}
    try: registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error: raise ApplicationPackageError("invalid application registry JSON") from error
    if not isinstance(registry, dict) or registry.get("schema_version") != 1 or not isinstance(registry.get("entries"), list):
        raise ApplicationPackageError("unsupported application registry schema")
    registry.setdefault("events", [])
    if not isinstance(registry["events"], list): raise ApplicationPackageError("invalid application registry events")
    return registry


@contextmanager
def _application_lock(path: Path, timeout_seconds: float = 5.0):
    try:
        with exclusive_lock(path, timeout_seconds=timeout_seconds):
            yield
    except LockAcquisitionError as error:
        raise ApplicationPackageError("could not acquire application registry lock") from error


def ensure_application_not_duplicate(root: Path, package: ApplicationPackage) -> None:
    """Compatibility check: exact packages are idempotent; changed inputs create versions."""
    registry = _load_registry(root.resolve() / ".career_profile" / "application_registry.json")
    for entry in registry["entries"]:
        if not isinstance(entry, dict): raise ApplicationPackageError("invalid application registry entry")
        if entry.get("package_id") == package.package_id and entry.get("posting_id") != package.posting_id:
            raise ApplicationPackageError("package identity collision")


def _registry_update(root: Path, package_path: Path, package: ApplicationPackage, registry: dict[str, Any]) -> dict[str, Any]:
    package_sha = sha256_file(package_path); relative = _relative(root, package_path)
    for entry in registry["entries"]:
        if entry.get("package_id") == package.package_id:
            if entry.get("package_sha256") == package_sha and entry.get("package_path") == relative: return registry
            raise ApplicationPackageError("existing package registry entry does not match package content")
    key = (package.posting_id, package.applicant_identity_fingerprint)
    for entry in registry["entries"]:
        if (entry.get("posting_id"), entry.get("applicant_identity_fingerprint")) == key and entry.get("status") == "prepared":
            entry["status"] = "superseded"; entry["superseded_by"] = package.package_id
    registry["entries"].append({"package_id": package.package_id, "posting_id": package.posting_id, "organization": package.organization,
        "applicant_identity_fingerprint": package.applicant_identity_fingerprint, "package_path": relative, "package_sha256": package_sha,
        "status": "prepared", "mode": "review_required", "created_at": package.created_at})
    registry["events"].append({"event_id": "event-" + sha256(f"prepared|{package.package_id}|{package_sha}".encode()).hexdigest()[:24],
        "event_type": "package_prepared", "package_id": package.package_id, "occurred_at": package.created_at})
    return registry


def register_application_package(root: Path, package_path: Path, package: ApplicationPackage) -> None:
    root = root.resolve(); profile = root / ".career_profile"
    try: confine_path(root, profile, must_exist=False)
    except PathConfinementError as error: raise ApplicationPackageError(".career_profile must not be a symlink") from error
    with _application_lock(profile / ".application_registry.lock"):
        registry_path = _inside(root, profile / "application_registry.json", label="application registry", must_exist=False); registry = _load_registry(registry_path)
        write_json(registry_path, _registry_update(root, _safe_file(root, package_path, label="application package"), package, registry))


def persist_application_package(root: Path, package_path: Path, package: ApplicationPackage, *, private_data_path: Path,
                                attachments: Mapping[str, Path] | None = None) -> None:
    """Revalidate inputs immediately before atomically writing package and registry."""
    root = root.resolve(); profile = root / ".career_profile"
    try: confine_path(root, profile, must_exist=False)
    except PathConfinementError as error: raise ApplicationPackageError(".career_profile must not be a symlink") from error
    package_path = _inside(root, package_path, label="application package output", must_exist=False)
    with _application_lock(profile / ".application_registry.lock"):
        package_path = _inside(root, package_path, label="application package output", must_exist=False)
        materialize_package_values(root, package, private_data_path=private_data_path, attachments=attachments)
        registry_path = _inside(root, profile / "application_registry.json", label="application registry", must_exist=False); registry = _load_registry(registry_path)
        existed = package_path.exists()
        try:
            write_application_package(package_path, package)
            updated = _registry_update(root, package_path, package, registry)
            write_json(registry_path, updated)
        except Exception:
            if not existed and package_path.exists() and package_path.is_file() and not package_path.is_symlink(): package_path.unlink()
            raise
