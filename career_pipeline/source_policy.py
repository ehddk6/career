"""소스 경로 정책. 근거로 사용할 수 있는 경로와 사용할 수 없는 경로를 분류합니다."""
from pathlib import Path


NON_EVIDENCE_PARTS = {"자료조사", "입사지원서(양식)", "docs", ".agents"}
NON_EVIDENCE_NAMES = ("직무기술서", "채용공고")


def is_evidence_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return not any(part in NON_EVIDENCE_PARTS for part in path.parts) and not any(
        marker in path.name for marker in NON_EVIDENCE_NAMES
    )
