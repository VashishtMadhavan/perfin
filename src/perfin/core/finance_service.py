"""Read-only finance facade over repositories and analytics."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from perfin.analytics.affordability import AffordabilityResult, check_affordability
from perfin.analytics.networth import (
    AccountContribution,
    NetWorthPoint,
    current_networth,
    snapshot_series,
)
from perfin.analytics.retirement import RetirementProjection, project_retirement
from perfin.analytics.savings import SavingsRate, calculate_savings_rate
from perfin.analytics.spending import SpendingRow, rollup_spending
from perfin.core.models import Account, Transaction
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

    def query_transactions(self, query: TransactionQuery) -> list[Transaction]:
        with session_scope(self._sessions) as session:
            return SqlTransactionRepo(session).query(query)

    def get_profile(self):
        with session_scope(self._sessions) as session:
            return SqlProfileRepo(session).get() or _empty_profile()

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

    def affordability(
        self, *, amount: Decimal, months: int = 3, by_date: dt.date | None = None
    ) -> AffordabilityResult:
        end = dt.date.today()
        start = _add_months(end, -months)
        with session_scope(self._sessions) as session:
            accounts = SqlAccountRepo(session).list_all()
            txns = SqlTransactionRepo(session).query(
                TransactionQuery(start_date=start, end_date=end, include_pending=False)
            )
            profile = SqlProfileRepo(session).get()
        profile = profile or _empty_profile()
        savings_rate = calculate_savings_rate(txns, months=months, profile=profile)
        return check_affordability(
            amount,
            accounts=accounts,
            transactions=txns,
            savings_rate=savings_rate,
            profile=profile,
            by_date=by_date,
        )

    def retirement_projection(
        self,
        *,
        months: int = 12,
        annual_contribution: Decimal | None = None,
        retirement_age: int | None = None,
    ) -> RetirementProjection:
        with session_scope(self._sessions) as session:
            accounts = SqlAccountRepo(session).list_all()
            profile = SqlProfileRepo(session).get()
            end = dt.date.today()
            start = _add_months(end, -months)
            txns = SqlTransactionRepo(session).query(
                TransactionQuery(start_date=start, end_date=end, include_pending=False)
            )
        profile = profile or _empty_profile()
        starting_balance, _ = current_networth(accounts)
        if annual_contribution is None:
            if profile.monthly_savings_target is not None:
                annual_contribution = profile.monthly_savings_target * Decimal(12)
            else:
                savings_rate = calculate_savings_rate(
                    txns, months=months, profile=profile
                )
                annual_contribution = savings_rate.savings / Decimal(months) * Decimal(12)
        return project_retirement(
            profile=profile,
            starting_balance=starting_balance,
            annual_contribution=annual_contribution,
            retirement_age=retirement_age,
        )


def _empty_profile():
    from perfin.core.models import UserProfile

    return UserProfile()


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
