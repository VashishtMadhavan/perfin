"""Domain models — plain dataclasses decoupled from the ORM and from Plaid.

These are the objects the service layer, analytics, and (future) API speak in.
Repositories translate between these and SQLAlchemy rows, so nothing above the
storage layer imports SQLAlchemy.

Money convention
----------------
All monetary amounts are :class:`decimal.Decimal`. For **transactions** we keep
Plaid's sign convention: **positive = money leaving the account (an outflow /
spend), negative = money coming in (income, refund, inflow)**. This is the single
most important invariant in the codebase — analytics depend on it.

For **balances** the number is a plain magnitude; whether it counts as an asset
or a liability is determined by the owning account's type (see
:meth:`Account.is_asset`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

# Plaid account types that represent things you own vs. things you owe.
_ASSET_TYPES = {"depository", "investment", "brokerage"}
_LIABILITY_TYPES = {"credit", "loan"}


class ItemStatus(StrEnum):
    ACTIVE = "active"
    ERROR = "error"
    LOGIN_REQUIRED = "login_required"


class RiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True, slots=True)
class PlaidItem:
    """A linked institution (a Plaid "Item")."""

    item_id: str
    institution_id: str | None
    institution_name: str | None
    access_token_ref: str  # keyring lookup key — never the token itself
    sync_cursor: str | None = None
    last_synced_at: dt.datetime | None = None
    status: ItemStatus = ItemStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    item_id: str
    name: str
    type: str
    subtype: str | None = None
    official_name: str | None = None
    mask: str | None = None
    current_balance: Decimal | None = None
    available_balance: Decimal | None = None
    currency: str = "USD"
    is_active: bool = True
    updated_at: dt.datetime | None = None

    @property
    def is_asset(self) -> bool:
        return self.type in _ASSET_TYPES

    @property
    def is_liability(self) -> bool:
        return self.type in _LIABILITY_TYPES

    @property
    def is_depository(self) -> bool:
        """Liquid cash accounts (checking/savings) — the affordability buffer."""
        return self.type == "depository"

    def networth_contribution(self) -> Decimal:
        """Signed contribution to net worth: assets add, liabilities subtract."""
        bal = self.current_balance or Decimal(0)
        if self.is_liability:
            return -bal
        return bal


@dataclass(frozen=True, slots=True)
class Transaction:
    transaction_id: str
    account_id: str
    date: dt.date
    amount: Decimal  # positive = outflow/spend, negative = inflow/income
    name: str
    merchant_name: str | None = None
    authorized_date: dt.date | None = None
    category_primary: str | None = None
    category_detailed: str | None = None
    user_category_override: str | None = None
    payment_channel: str | None = None
    pending: bool = False
    currency: str = "USD"

    @property
    def category(self) -> str:
        """Effective category: user override wins over the Plaid categorization."""
        return self.user_category_override or self.category_primary or "UNCATEGORIZED"

    @property
    def is_outflow(self) -> bool:
        return self.amount > 0

    @property
    def is_inflow(self) -> bool:
        return self.amount < 0


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    account_id: str
    as_of: dt.date
    current_balance: Decimal | None
    available_balance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class UserProfile:
    birth_year: int | None = None
    annual_gross_income: Decimal | None = None
    annual_net_income: Decimal | None = None
    monthly_savings_target: Decimal | None = None
    emergency_fund_months: int = 6
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    retirement_age_target: int | None = None
    retirement_annual_spend: Decimal | None = None
    expected_return_override: float | None = None
    extras: dict = field(default_factory=dict)

    def current_age(self, today: dt.date | None = None) -> int | None:
        if self.birth_year is None:
            return None
        today = today or dt.date.today()
        return today.year - self.birth_year


@dataclass(frozen=True, slots=True)
class SyncState:
    scope: str  # "global" or an item_id
    last_sync_at: dt.datetime | None = None
    last_error: str | None = None
    last_error_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class SyncBatch:
    """One page of changes from a :class:`~perfin.datasources.base.DataSource`."""

    added: list[Transaction]
    modified: list[Transaction]
    removed: list[str]  # transaction_ids
    next_cursor: str | None
    has_more: bool
