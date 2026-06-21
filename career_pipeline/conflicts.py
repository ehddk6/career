from .models import Conflict, FactClaim


def _similar(left: FactClaim, right: FactClaim) -> bool:
    return left.field == right.field and len(left.tokens & right.tokens) >= 3


def _cluster(claims: list[FactClaim]) -> list[list[int]]:
    groups: list[list[int]] = []
    for index, claim in enumerate(claims):
        for group in groups:
            if any(_similar(claim, claims[member]) for member in group):
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


def override_key(claim: FactClaim) -> str:
    anchors = sorted(claim.tokens)[:2]
    return f"{claim.field}:{'|'.join(anchors)}"


def apply_overrides(
    claims: list[FactClaim], overrides: dict[str, str]
) -> list[FactClaim]:
    accepted = []
    for claim in claims:
        expected = overrides.get(override_key(claim))
        if expected is None or claim.normalized_value == expected:
            accepted.append(claim)
    return accepted
