"""Net-worth calculations."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from perfin.core.models import Account, BalanceSnapshot


@dataclass(frozen=True, slots=True)
class NetWorthPoint:
    as_of: dt.date
    total: Decimal


@dataclass(frozen=True, slots=True)
class AccountContribution:
    account_name: str
    account_type: str
    amount: Decimal


def current_networth(accounts: list[Account]) -> tuple[Decimal, list[AccountContribution]]:
    rows = [
        AccountContribution(a.name, a.type, a.networth_contribution())
        for a in accounts
        if a.current_balance is not None
    ]
    total = sum((r.amount for r in rows), Decimal("0"))
    return total, sorted(rows, key=lambda r: abs(r.amount), reverse=True)


def snapshot_series(
    snapshots: list[BalanceSnapshot], accounts: list[Account]
) -> list[NetWorthPoint]:
    accounts_by_id = {a.account_id: a for a in accounts}
    totals: dict[dt.date, Decimal] = {}
    for snapshot in snapshots:
        account = accounts_by_id.get(snapshot.account_id)
        if account is None or snapshot.current_balance is None:
            continue
        amount = -snapshot.current_balance if account.is_liability else snapshot.current_balance
        totals[snapshot.as_of] = totals.get(snapshot.as_of, Decimal("0")) + amount
    return [NetWorthPoint(day, total) for day, total in sorted(totals.items())]
