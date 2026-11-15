"""Deterministic medical-bill checks using the shared contract models."""
from __future__ import annotations

from collections import defaultdict
from math import isclose

from .contract import AuditResult, Bill, Eob, Flag, LineItem


def _provider_key(provider: str) -> str:
    """Normalize provider names for matching without changing displayed data."""
    return " ".join(provider.casefold().split())


def _same_amount(left: float, right: float) -> bool:
    """Compare demo-dollar amounts to the nearest cent."""
    return isclose(round(left, 2), round(right, 2), abs_tol=0.005)


def _line_ids(items: list[LineItem]) -> list[str]:
    return [item.line_id for item in items]


def audit(bill: Bill, eob: Eob | None = None) -> AuditResult:
    """Return deterministic flags for duplicate and EOB/bill discrepancies.

    Matching is based on provider, service date, and procedure code. No finding
    makes an accusation; each is described as something worth asking about.
    """
    flags: list[Flag] = []

    # Group lines with the same provider/date/code.
    service_groups: dict[tuple[str, str, str], list[LineItem]] = defaultdict(list)
    for item in bill.items:
        key = (_provider_key(item.provider), item.date_of_service, item.code)
        service_groups[key].append(item)

    # Exact and near duplicates. Exact groups are kept together so three or
    # more identical entries produce one flag containing every line ID.
    for group in service_groups.values():
        amount_groups: dict[float, list[LineItem]] = defaultdict(list)
        for item in group:
            amount_groups[round(item.amount, 2)].append(item)

        for amount, identical_items in amount_groups.items():
            if len(identical_items) >= 2:
                ids = _line_ids(identical_items)
                flags.append(
                    Flag(
                        kind="exact_duplicate",
                        line_ids=ids,
                        detail=(
                            f"Lines {', '.join(ids)} have the same provider, service "
                            f"date, code, and amount (${amount:.2f}); this duplicate "
                            "is worth asking about."
                        ),
                    )
                )

        distinct_amounts = {round(item.amount, 2) for item in group}
        if len(group) >= 2 and len(distinct_amounts) > 1:
            ids = _line_ids(group)
            flags.append(
                Flag(
                    kind="near_duplicate",
                    line_ids=ids,
                    detail=(
                        f"Lines {', '.join(ids)} share a provider, service date, "
                        "and code but have different amounts; this is worth asking about."
                    ),
                )
            )

    # Same procedure/date billed by different providers.
    cross_provider_groups: dict[tuple[str, str], list[LineItem]] = defaultdict(list)
    for item in bill.items:
        cross_provider_groups[(item.date_of_service, item.code)].append(item)

    for group in cross_provider_groups.values():
        providers = {_provider_key(item.provider) for item in group}
        if len(providers) > 1 and len(group) > 1:
            ids = _line_ids(group)
            flags.append(
                Flag(
                    kind="same_service_twice",
                    line_ids=ids,
                    detail=(
                        f"Lines {', '.join(ids)} show the same service code on the "
                        "same date from different providers; this is worth asking about."
                    ),
                )
            )

    # Compare each bill line with its matching EOB line, when supplied.
    if eob is not None:
        eob_index: dict[tuple[str, str, str], list] = defaultdict(list)
        for eob_line in eob.lines:
            key = (
                _provider_key(eob_line.provider),
                eob_line.date_of_service,
                eob_line.code,
            )
            eob_index[key].append(eob_line)

        for item in bill.items:
            key = (_provider_key(item.provider), item.date_of_service, item.code)
            matches = eob_index.get(key, [])
            if not matches:
                continue

            # The contract has no EOB-line identifier. If multiple matching
            # EOB lines exist, compare against each; normally there is one.
            for eob_line in matches:
                if item.amount > eob_line.allowed and not _same_amount(
                    item.amount, eob_line.allowed
                ):
                    flags.append(
                        Flag(
                            kind="balance_billing",
                            line_ids=[item.line_id],
                            detail=(
                                f"Line {item.line_id} is billed at "
                                f"${item.amount:.2f}, above the EOB allowed amount "
                                f"of ${eob_line.allowed:.2f}; this is worth asking about."
                            ),
                        )
                    )
                elif not _same_amount(item.amount, eob_line.member_owes):
                    flags.append(
                        Flag(
                            kind="eob_mismatch",
                            line_ids=[item.line_id],
                            detail=(
                                f"Line {item.line_id} is billed at "
                                f"${item.amount:.2f}, but the EOB lists "
                                f"${eob_line.member_owes:.2f} as member responsibility; "
                                "this difference is worth asking about."
                            ),
                        )
                    )

    return AuditResult(flags=flags)
