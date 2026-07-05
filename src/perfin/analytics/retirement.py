"""Deterministic retirement projection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from perfin.core.models import RiskTolerance, UserProfile

DEFAULT_RETURNS = {
    RiskTolerance.CONSERVATIVE: 0.04,
    RiskTolerance.MODERATE: 0.06,
    RiskTolerance.AGGRESSIVE: 0.08,
}


@dataclass(frozen=True, slots=True)
class RetirementProjection:
    current_age: int | None
    retirement_age: int
    years: int
    starting_balance: Decimal
    annual_contribution: Decimal
    expected_return: float
    projected_balance: Decimal
    safe_annual_spend: Decimal
    target_annual_spend: Decimal | None
    surplus: Decimal | None


def project_retirement(
    *,
    profile: UserProfile,
    starting_balance: Decimal,
    annual_contribution: Decimal,
    retirement_age: int | None = None,
) -> RetirementProjection:
    current_age = profile.current_age()
    target_age = retirement_age or profile.retirement_age_target or 65
    years = max(0, target_age - current_age) if current_age is not None else 30
    expected_return = profile.expected_return_override
    if expected_return is None:
        expected_return = DEFAULT_RETURNS[profile.risk_tolerance]
    balance = starting_balance
    for _ in range(years):
        balance = balance * Decimal(str(1 + expected_return)) + annual_contribution
    safe_spend = balance * Decimal("0.04")
    target_spend = profile.retirement_annual_spend
    surplus = None if target_spend is None else safe_spend - target_spend
    return RetirementProjection(
        current_age=current_age,
        retirement_age=target_age,
        years=years,
        starting_balance=starting_balance,
        annual_contribution=annual_contribution,
        expected_return=expected_return,
        projected_balance=balance,
        safe_annual_spend=safe_spend,
        target_annual_spend=target_spend,
        surplus=surplus,
    )
