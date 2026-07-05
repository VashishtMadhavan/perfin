"""User profile service."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from perfin.core.models import RiskTolerance, UserProfile
from perfin.storage.db import session_scope
from perfin.storage.repositories import SqlProfileRepo


class ProfileService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def get(self) -> UserProfile:
        with session_scope(self._sessions) as session:
            return SqlProfileRepo(session).get() or UserProfile()

    def update(
        self,
        *,
        birth_year: int | None = None,
        annual_net_income: Decimal | None = None,
        annual_gross_income: Decimal | None = None,
        monthly_savings_target: Decimal | None = None,
        emergency_fund_months: int | None = None,
        risk_tolerance: RiskTolerance | None = None,
        retirement_age_target: int | None = None,
        retirement_annual_spend: Decimal | None = None,
        expected_return_override: float | None = None,
    ) -> UserProfile:
        current = self.get()
        updated = UserProfile(
            birth_year=birth_year if birth_year is not None else current.birth_year,
            annual_gross_income=(
                annual_gross_income
                if annual_gross_income is not None
                else current.annual_gross_income
            ),
            annual_net_income=(
                annual_net_income
                if annual_net_income is not None
                else current.annual_net_income
            ),
            monthly_savings_target=(
                monthly_savings_target
                if monthly_savings_target is not None
                else current.monthly_savings_target
            ),
            emergency_fund_months=(
                emergency_fund_months
                if emergency_fund_months is not None
                else current.emergency_fund_months
            ),
            risk_tolerance=risk_tolerance or current.risk_tolerance,
            retirement_age_target=(
                retirement_age_target
                if retirement_age_target is not None
                else current.retirement_age_target
            ),
            retirement_annual_spend=(
                retirement_annual_spend
                if retirement_annual_spend is not None
                else current.retirement_annual_spend
            ),
            expected_return_override=(
                expected_return_override
                if expected_return_override is not None
                else current.expected_return_override
            ),
            extras=current.extras,
        )
        with session_scope(self._sessions) as session:
            SqlProfileRepo(session).save(updated)
        return updated
