"""Read-only finance facade over repositories and analytics."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from perfin.analytics.networth import (
    AccountContribution,
    NetWorthPoint,
    current_networth,
    snapshot_series,
)
from perfin.analytics.savings import SavingsRate, calculate_savings_rate
from perfin.analytics.spending import SpendingRow, rollup_spending
from perfin.core.models import Account
from perfin.storage.base import TransactionQuery
from perfin.storage.db import session_scope
from perfin.storage.repositories import (
    SqlAccountRepo,
    SqlProfileRepo,
    SqlSnapshotRepo,
    SqlTransactionRepo,
)


@dataclass(frozen=True, slots=True)
class SpendingSummary:
    start: dt.date
    end: dt.date
    group_by: str
    total: Decimal
    rows: list[SpendingRow]


@dataclass(frozen=True, slots=True)
class NetWorthSummary:
    total: Decimal
    accounts: list[Account]
    contributions: list[AccountContribution]
    history: list[NetWorthPoint]


class FinanceService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def list_accounts(self) -> list[Account]:
        with session_scope(self._sessions) as session:
            return SqlAccountRepo(session).list_all()

    def spending_summary(
        self, *, months: int = 1, group_by: str = "category"
    ) -> SpendingSummary:
        end = dt.date.today()
        start = _add_months(end, -months)
        with session_scope(self._sessions) as session:
            txns = SqlTransactionRepo(session).query(
                TransactionQuery(start_date=start, end_date=end, include_pending=False)
            )
        rows = rollup_spending(txns, group_by=group_by)
        total = sum((r.total for r in rows), Decimal("0"))
        return SpendingSummary(start, end, group_by, total, rows)

    def networth_summary(self, *, months: int = 12) -> NetWorthSummary:
        end = dt.date.today()
        start = _add_months(end, -months)
        with session_scope(self._sessions) as session:
            accounts = SqlAccountRepo(session).list_all()
            snapshots = SqlSnapshotRepo(session).list_between(start, end)
        total, contributions = current_networth(accounts)
        return NetWorthSummary(
            total=total,
            accounts=accounts,
            contributions=contributions,
            history=snapshot_series(snapshots, accounts),
        )

    def savings_rate(self, *, months: int = 3) -> SavingsRate:
        end = dt.date.today()
        start = _add_months(end, -months)
        with session_scope(self._sessions) as session:
            txns = SqlTransactionRepo(session).query(
                TransactionQuery(start_date=start, end_date=end, include_pending=False)
            )
            profile = SqlProfileRepo(session).get()
        return calculate_savings_rate(txns, months=months, profile=profile)


def _add_months(date: dt.date, months: int) -> dt.date:
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(date.day, _days_in_month(year, month))
    return dt.date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day
