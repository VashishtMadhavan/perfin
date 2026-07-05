"""Spending rollups over transaction domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from operator import attrgetter

from perfin.core.models import Transaction

_EXCLUDED_PRIMARY_PREFIXES = ("TRANSFER_",)
_EXCLUDED_PRIMARY = {"LOAN_PAYMENTS", "BANK_FEES"}


@dataclass(frozen=True, slots=True)
class SpendingRow:
    key: str
    total: Decimal
    count: int


def is_spend_transaction(txn: Transaction) -> bool:
    if not txn.is_outflow:
        return False
    category = txn.category_primary or ""
    if category in _EXCLUDED_PRIMARY:
        return False
    return not category.startswith(_EXCLUDED_PRIMARY_PREFIXES)


def rollup_spending(
    transactions: list[Transaction], *, group_by: str = "category"
) -> list[SpendingRow]:
    """Return spend totals grouped by ``category`` or ``merchant``."""
    buckets: dict[str, tuple[Decimal, int]] = {}
    for txn in transactions:
        if not is_spend_transaction(txn):
            continue
        if group_by == "merchant":
            key = txn.merchant_name or txn.name
        else:
            key = txn.category
        total, count = buckets.get(key, (Decimal("0"), 0))
        buckets[key] = (total + txn.amount, count + 1)
    return sorted(
        (SpendingRow(key, total, count) for key, (total, count) in buckets.items()),
        key=attrgetter("total"),
        reverse=True,
    )
