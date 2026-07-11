"""Patina CLI 어댑터. 인간화와 점수 게이팅을 제공하며 의미 보존을 보장합니다."""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from subprocess import CompletedProcess

from .character_count import CharacterCountMode, count_characters
from .facts import METRIC, _normalize
from .models import DraftResponse, Question
from .rewrite_validation import meaning_preservation_issue as _shared_meaning_preservation_issue


Runner = Callable[..., CompletedProcess[str]]


@dataclass(frozen=True)
class HumanizationResult:
    text: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class PatinaScoreResult:
    score: int | None
    status: str
    message: str = ""


def _safe_backend_error(stderr: str) -> str:
    lowered = stderr.lower()
    if "usage limit" in lowered or "rate limit" in lowered or "429" in lowered:
        return "패티나 백엔드 사용 한계 도다"
    if "auth required" in lowered or "not authenticated" in lowered:
        return "패티나 백엔드 인증 필요"
    if "timeout" in lowered or "timed out" in lowered:
        return "패티나 백엔드 시간 초조"
    return "패티나 백엔드 실패; patina doctor 확인"


def _metric_values(text: str) -> Counter[str]:
    return Counter(
        _normalize(match.group("number"), match.group("unit"))[0]
        for match in METRIC.finditer(text)
    )


def _strip_footer(text: str) -> str:
    for marker in ("\n\n---\ntone:", "\n---\ntone:"):
        if marker in text:
            return text.split(marker, 1)[0].strip()
    return text.strip()


def _resolved_command(arguments: list[str], *, resolve: bool) -> list[str]:
    if os.name != "nt" or not resolve:
        return ["patina", *arguments]
    executable = shutil.which("patina.cmd")
    if executable is None:
        return ["patina", *arguments]
    node = shutil.which("node.exe") or shutil.which("node")
    script = (
        Path(executable).parent
        / "node_modules"
        / "patina-cli"
        / "bin"
        / "patina.js"
    )
    if node and script.is_file():
        return [node, str(script), *arguments]
    return [
        os.environ.get("COMSPEC", "cmd.exe"),
        "/d",
        "/s",
        "/c",
        executable,
        *arguments,
    ]


def _command(
    backend: str,
    timeout_ms: int,
    *,
    profile: str,
    tone: str,
    voice_sample: Path | None,
    max_retries: int,
    resolve: bool,
) -> list[str]:
    arguments = [
        "--lang",
        "ko",
        "--profile",
        profile,
        "--tone",
        tone,
        "--restyle",
        "sentence",
        "--backend",
        backend,
        "--format",
        "json",
        "--quiet",
        "--timeout-ms",
        str(timeout_ms),
        "--max-retries",
        str(max_retries),
    ]
    if voice_sample is not None:
        arguments.extend(("--voice-sample", str(voice_sample)))
    return _resolved_command(arguments, resolve=resolve)


def _score_command(
    backend: str,
    timeout_ms: int,
    *,
    profile: str,
    threshold: int,
    max_retries: int,
    resolve: bool,
) -> list[str]:
    return _resolved_command(
        [
            "--lang",
            "ko",
            "--profile",
            profile,
            "--score",
            "--exit-on",
            str(threshold),
            "--backend",
            backend,
            "--format",
            "json",
            "--quiet",
            "--timeout-ms",
            str(timeout_ms),
            "--max-retries",
            str(max_retries),
        ],
        resolve=resolve,
    )


_QUOTED_PATTERNS = (
    re.compile(r'"([^"\n]+)"'),
    re.compile(r"“([^”\n]+)”"),
    re.compile(r"‘([^’\n]+)’"),
    re.compile(r"「([^」\n]+)」"),
    re.compile(r"『([^』\n]+)』"),
)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9._-]{1,}\b")
_SEMANTIC_MARKERS = (
    re.compile(r"않|못|없|아니|불가|제외|미달"),
    re.compile(r"때문|결과|따라|덕분|(?:으로|로)\s*인(?:해|하여)"),
)


def _quoted_values(text: str) -> Counter[str]:
    return Counter(
        match
        for pattern in _QUOTED_PATTERNS
        for match in pattern.findall(text)
    )


def _semantic_change(
    original: str,
    rewritten: str,
    protected_terms: tuple[str, ...],
) -> bool:
    if _quoted_values(original) != _quoted_values(rewritten):
        return True
    if Counter(_ACRONYM.findall(original)) != Counter(_ACRONYM.findall(rewritten)):
        return True
    for pattern in _SEMANTIC_MARKERS:
        if bool(pattern.search(original)) != bool(pattern.search(rewritten)):
            return True
    compact_original = re.sub(r"\s+", "", original)
    compact_rewritten = re.sub(r"\s+", "", rewritten)
    return any(
        re.sub(r"\s+", "", term) in compact_original
        and re.sub(r"\s+", "", term) not in compact_rewritten
        for term in protected_terms
        if term.strip()
    )


def meaning_preservation_issue(
    original: str,
    rewritten: str,
    protected_terms: tuple[str, ...] = (),
) -> str | None:
    return _shared_meaning_preservation_issue(original, rewritten, protected_terms)


_SAFE_COMPACTIONS = (
    ("진행할 수 있었습니다", "진행했습니다"),
    ("할 수 있었습니다", "했습니다"),
    ("검토를 진행했습니다", "검토했습니다"),
    ("하게 되었습니다", "했습니다"),
    ("하고자 하였습니다", "했습니다"),
    ("하기 위해", "하고자"),
    ("과정을 통해", "과정에서"),
    ("할 예정입니다", "하겠습니다"),
)


def _compact_to_limit(
    text: str,
    character_limit: int,
    count_mode: CharacterCountMode,
) -> str | None:
    compacted = text
    for before, after in _SAFE_COMPACTIONS:
        compacted = compacted.replace(before, after)
        if count_characters(compacted, count_mode) <= character_limit:
            return compacted
    compacted = re.sub(r"[ \t]+", " ", compacted).strip()
    return compacted if count_characters(compacted, count_mode) <= character_limit else None


def humanize_text(
    text: str,
    *,
    character_limit: int | None,
    count_mode: CharacterCountMode = "spaces_included",
    backend: str = "codex-cli",
    timeout_ms: int = 180_000,
    profile: str = "formal",
    tone: str = "professional",
    voice_sample: Path | None = None,
    protected_terms: tuple[str, ...] = (),
    max_retries: int = 1,
    runner: Runner = subprocess.run,
) -> HumanizationResult:
    try:
        completed = runner(
            _command(
                backend,
                timeout_ms,
                profile=profile,
                tone=tone,
                voice_sample=voice_sample,
                max_retries=max_retries,
                resolve=runner is subprocess.run,
            ),
            input=text,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            timeout=max(1, timeout_ms // 1000 + 30),
        )
    except (OSError, subprocess.SubprocessError) as error:
        message = "패티나 백엔드 시간 초조" if isinstance(
            error, subprocess.TimeoutExpired
        ) else "패티나 백엔드 용도 없음"
        return HumanizationResult(text, "fallback_backend_error", message)
    if completed.returncode != 0:
        return HumanizationResult(
            text,
            "fallback_backend_error",
            _safe_backend_error(completed.stderr or ""),
        )
    try:
        payload = json.loads(completed.stdout)
        rewritten = _strip_footer(str(payload["output"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return HumanizationResult(text, "fallback_invalid_output", str(error))
    if not rewritten:
        return HumanizationResult(text, "fallback_invalid_output", "빈 출력")

    rewritten_length = count_characters(rewritten, count_mode)
    compacted = False
    if character_limit is not None and rewritten_length > character_limit:
        shortened = _compact_to_limit(rewritten, character_limit, count_mode)
        if shortened is None:
            return HumanizationResult(
                text,
                "fallback_over_limit",
                f"{rewritten_length}/{character_limit}자",
            )
        rewritten = shortened
        compacted = True
    meaning_issue = meaning_preservation_issue(text, rewritten, protected_terms)
    if meaning_issue in {"숫자 증명 변경", "숫자·단위 변경"}:
        return HumanizationResult(
            text,
            "fallback_fact_change",
            meaning_issue,
        )
    if meaning_issue:
        return HumanizationResult(
            text,
            "fallback_semantic_change",
            meaning_issue,
        )
    status = (
        "unchanged"
        if rewritten == text.strip()
        else "humanized_compacted" if compacted else "humanized"
    )
    return HumanizationResult(rewritten, status)


def score_text(
    text: str,
    *,
    threshold: int = 30,
    backend: str = "codex-cli",
    timeout_ms: int = 180_000,
    profile: str = "formal",
    max_retries: int = 1,
    runner: Runner = subprocess.run,
) -> PatinaScoreResult:
    try:
        completed = runner(
            _score_command(
                backend,
                timeout_ms,
                profile=profile,
                threshold=threshold,
                max_retries=max_retries,
                resolve=runner is subprocess.run,
            ),
            input=text,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            timeout=max(1, timeout_ms // 1000 + 30),
        )
    except (OSError, subprocess.SubprocessError) as error:
        message = "패티나 점수 시간 초조" if isinstance(
            error, subprocess.TimeoutExpired
        ) else "패티나 점수 용도 없음"
        return PatinaScoreResult(None, "score_unavailable", message)
    if completed.returncode not in (0, 3):
        return PatinaScoreResult(
            None,
            "score_unavailable",
            _safe_backend_error(completed.stderr or ""),
        )
    try:
        payload = json.loads(completed.stdout)
        score = int(round(float(payload["overall"])))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return PatinaScoreResult(None, "score_unavailable", "유효하지 알수 점수 출력")
    message = f"above threshold {threshold}" if score > threshold else ""
    return PatinaScoreResult(score, "scored", message)


def humanize_responses(
    responses: list[DraftResponse],
    questions: list[Question],
    *,
    backend: str = "codex-cli",
    timeout_ms: int = 180_000,
    voice_sample: Path | None = None,
    max_retries: int = 1,
    runner: Runner = subprocess.run,
) -> tuple[list[DraftResponse], list[dict[str, object]]]:
    question_by_index = {question.index: question for question in questions}
    rewritten: list[DraftResponse] = []
    reports: list[dict[str, object]] = []
    for response in responses:
        question = question_by_index[response.question_index]
        result = humanize_text(
            response.answer,
            character_limit=question.character_limit,
            count_mode=question.count_mode,
            backend=backend,
            timeout_ms=timeout_ms,
            voice_sample=voice_sample,
            max_retries=max_retries,
            runner=runner,
        )
        rewritten.append(
            DraftResponse(
                response.question_index,
                result.text,
                response.evidence_paths,
                response.experience_refs,
                response.research_refs,
            )
        )
        reports.append(
            {
                "question_index": response.question_index,
                "status": result.status,
                "message": result.message,
                "input_length": count_characters(response.answer, question.count_mode),
                "output_length": count_characters(result.text, question.count_mode),
                "count_mode": question.count_mode,
                "backend": backend,
            }
        )
    return rewritten, reports
