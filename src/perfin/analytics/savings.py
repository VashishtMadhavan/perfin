"""Savings-rate calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from perfin.analytics.spending import is_spend_transaction
from perfin.core.models import Transaction, UserProfile


@dataclass(frozen=True, slots=True)
class SavingsRate:
    income: Decimal
    spend: Decimal
    savings: Decimal
    rate: Decimal | None
    income_source: str


def calculate_savings_rate(
    transactions: list[Transaction],
    *,
    months: int,
    profile: UserProfile | None = None,
) -> SavingsRate:
    income = sum((-t.amount for t in transactions if t.is_inflow), Decimal("0"))
    income_source = "transactions"
    if income <= 0 and profile and profile.annual_net_income:
        income = profile.annual_net_income / Decimal(12) * Decimal(months)
        income_source = "profile annual net income"
    spend = sum((t.amount for t in transactions if is_spend_transaction(t)), Decimal("0"))
    savings = income - spend
    rate = None if income <= 0 else savings / income
    return SavingsRate(income, spend, savings, rate, income_source)
