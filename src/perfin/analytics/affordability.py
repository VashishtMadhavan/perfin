"""Affordability checks."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from perfin.analytics.savings import SavingsRate
from perfin.analytics.spending import is_spend_transaction
from perfin.core.models import Account, Transaction, UserProfile


@dataclass(frozen=True, slots=True)
class AffordabilityResult:
    amount: Decimal
    liquid_balance: Decimal
    emergency_buffer: Decimal
    available_after_buffer: Decimal
    monthly_slack: Decimal
    affordable_now: bool
    affordable_by_date: bool | None
    months_until_date: int | None
    monthly_required: Decimal | None


def check_affordability(
    amount: Decimal,
    *,
    accounts: list[Account],
    transactions: list[Transaction],
    savings_rate: SavingsRate,
    profile: UserProfile,
    by_date: dt.date | None = None,
) -> AffordabilityResult:
    liquid = sum(
        (a.current_balance or Decimal("0") for a in accounts if a.is_depository),
        Decimal("0"),
    )
    spend = sum((t.amount for t in transactions if is_spend_transaction(t)), Decimal("0"))
    months = max(1, _covered_months(transactions))
    monthly_spend = spend / Decimal(months)
    emergency_buffer = monthly_spend * Decimal(profile.emergency_fund_months)
    monthly_slack = savings_rate.savings / Decimal(months)
    available = liquid - emergency_buffer
    affordable_now = available >= amount

    months_until_date = None
    monthly_required = None
    affordable_by_date = None
    if by_date is not None:
        today = dt.date.today()
        days = max(0, (by_date - today).days)
        months_until_date = max(1, (days + 29) // 30)
        monthly_required = amount / Decimal(months_until_date)
        affordable_by_date = affordable_now or monthly_slack >= monthly_required

    return AffordabilityResult(
        amount=amount,
        liquid_balance=liquid,
        emergency_buffer=emergency_buffer,
        available_after_buffer=available,
        monthly_slack=monthly_slack,
        affordable_now=affordable_now,
        affordable_by_date=affordable_by_date,
        months_until_date=months_until_date,
        monthly_required=monthly_required,
    )


def _covered_months(transactions: list[Transaction]) -> int:
    if not transactions:
        return 1
    days = max(1, (max(t.date for t in transactions) - min(t.date for t in transactions)).days)
    return max(1, (days + 29) // 30)
