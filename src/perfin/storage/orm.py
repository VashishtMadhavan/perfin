"""SQLAlchemy ORM models — the persistence schema.

Design notes
------------
* **Money is stored as text** via :class:`Money`, not float. SQLite has no exact
  decimal type; storing ``Decimal`` through SQLAlchemy's ``Numeric`` silently
  round-trips through a C double and loses cents. A ``TypeDecorator`` that
  serialises ``Decimal`` to a string keeps values exact on SQLite *and*
  Postgres, so the cloud migration doesn't change numbers.
* The schema mirrors :mod:`perfin.core.models`; repositories map between them.
* Keep this the single source of truth for the DB — Alembic autogenerates
  migrations from ``Base.metadata``.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Money(TypeDecorator):
    """Store a ``Decimal`` exactly, as a string, regardless of backend."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: str | None, dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


class Base(DeclarativeBase):
    pass


class PlaidItemRow(Base):
    __tablename__ = "plaid_items"

    item_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    institution_id: Mapped[str | None] = mapped_column(String(128))
    institution_name: Mapped[str | None] = mapped_column(String(256))
    # Keyring lookup key (e.g. "perfin/plaid/{item_id}") — never the raw token.
    access_token_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    sync_cursor: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC)
    )

    accounts: Mapped[list[AccountRow]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class AccountRow(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("plaid_items.item_id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))
    official_name: Mapped[str | None] = mapped_column(String(256))
    mask: Mapped[str | None] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))
    subtype: Mapped[str | None] = mapped_column(String(32))
    current_balance: Mapped[Decimal | None] = mapped_column(Money)
    available_balance: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    item: Mapped[PlaidItemRow] = relationship(back_populates="accounts")


class TransactionRow(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_txn_account_date", "account_id", "date"),
        Index("ix_txn_date", "date"),
        Index("ix_txn_category_date", "category_primary", "date"),
    )

    transaction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="CASCADE")
    )
    date: Mapped[dt.date] = mapped_column(Date)
    authorized_date: Mapped[dt.date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    name: Mapped[str] = mapped_column(String(512))
    merchant_name: Mapped[str | None] = mapped_column(String(256))
    category_primary: Mapped[str | None] = mapped_column(String(64))
    category_detailed: Mapped[str | None] = mapped_column(String(128))
    user_category_override: Mapped[str | None] = mapped_column(String(64))
    payment_channel: Mapped[str | None] = mapped_column(String(32))
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")


class BalanceSnapshotRow(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "as_of", name="uq_snapshot_account_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="CASCADE"), index=True
    )
    as_of: Mapped[dt.date] = mapped_column(Date, index=True)
    current_balance: Mapped[Decimal | None] = mapped_column(Money)
    available_balance: Mapped[Decimal | None] = mapped_column(Money)


class UserProfileRow(Base):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    annual_gross_income: Mapped[Decimal | None] = mapped_column(Money)
    annual_net_income: Mapped[Decimal | None] = mapped_column(Money)
    monthly_savings_target: Mapped[Decimal | None] = mapped_column(Money)
    emergency_fund_months: Mapped[int] = mapped_column(Integer, default=6)
    risk_tolerance: Mapped[str] = mapped_column(String(16), default="moderate")
    retirement_age_target: Mapped[int | None] = mapped_column(Integer)
    retirement_annual_spend: Mapped[Decimal | None] = mapped_column(Money)
    expected_return_override: Mapped[float | None] = mapped_column(Float)
    extras: Mapped[dict] = mapped_column(JSON, default=dict)


class SyncStateRow(Base):
    __tablename__ = "sync_state"

    scope: Mapped[str] = mapped_column(String(128), primary_key=True)  # "global"|item_id
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
