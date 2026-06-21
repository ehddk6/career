from .models import Conflict, FactClaim


GENERIC_TOKENS = {
    "예산",
    "검증",
    "업무",
    "경험",
    "결과",
    "데이터",
    "지원",
    "처리",
    "절감",
    "방지",
}
CONFLICT_FIELDS = {
    "budget_savings",
    "case_count",
    "processed_case_count",
    "employment_period",
}


def _similar(left: FactClaim, right: FactClaim) -> bool:
    if left.field != right.field or left.field not in CONFLICT_FIELDS:
        return False
    if left.source_path == right.source_path:
        return False
    left_tokens = left.tokens - GENERIC_TOKENS
    right_tokens = right.tokens - GENERIC_TOKENS
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    overlap = len(shared) / min(len(left_tokens), len(right_tokens))
    return len(shared) >= 2 and overlap >= 0.35


def _cluster(claims: list[FactClaim]) -> list[list[int]]:
    groups: list[list[int]] = []
    for index, claim in enumerate(claims):
        for group in groups:
            if all(_similar(claim, claims[member]) for member in group):
                group.append(index)
                break
        else:
            groups.append([index])
    return groups


def detect_conflicts(claims: list[FactClaim]) -> list[Conflict]:
    conflicts = []
    for group in _cluster(claims):
        values = sorted({claims[index].normalized_value for index in group})
        if len(values) > 1:
            conflicts.append(
                Conflict(
                    claims[group[0]].field,
                    tuple(group),
                    tuple(values),
                    "same field and overlapping experience context have different values",
                )
            )
    return conflicts


def _override_key(field: str, tokens: frozenset[str] | set[str]) -> str:
    anchors = sorted(tokens - GENERIC_TOKENS)[:2]
    if not anchors:
        anchors = ["fact"]
    return f"{field}:{'|'.join(anchors)}"


def override_key(claim: FactClaim) -> str:
    return _override_key(claim.field, claim.tokens)


def conflict_override_key(conflict: Conflict, claims: list[FactClaim]) -> str:
    shared = set(claims[conflict.claim_indexes[0]].tokens)
    for index in conflict.claim_indexes[1:]:
        shared &= claims[index].tokens
    if len(shared - GENERIC_TOKENS) < 2:
        shared = set(claims[conflict.claim_indexes[0]].tokens)
    return _override_key(conflict.field, shared)


def apply_overrides(
    claims: list[FactClaim], overrides: dict[str, str]
) -> list[FactClaim]:
    accepted = []
    for claim in claims:
        expected = overrides.get(override_key(claim))
        if expected is None or claim.normalized_value == expected:
            accepted.append(claim)

    while True:
        rejected: set[int] = set()
        for conflict in detect_conflicts(accepted):
            expected = overrides.get(conflict_override_key(conflict, accepted))
            if expected is None:
                continue
            rejected.update(
                index
                for index in conflict.claim_indexes
                if accepted[index].normalized_value != expected
            )
        if not rejected:
            break
        accepted = [
            claim for index, claim in enumerate(accepted) if index not in rejected
        ]
    return accepted
