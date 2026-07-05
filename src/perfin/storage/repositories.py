"""SQLAlchemy implementations of the repository protocols.

Each repo wraps a live :class:`~sqlalchemy.orm.Session` and maps between ORM rows
and domain dataclasses. Repos do not commit — the caller controls the
transaction boundary via :func:`perfin.storage.db.session_scope`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from perfin.core.models import (
    Account,
    BalanceSnapshot,
    ItemStatus,
    PlaidItem,
    RiskTolerance,
    SyncState,
    Transaction,
    UserProfile,
)
from perfin.storage.base import TransactionQuery
from perfin.storage.orm import (
    AccountRow,
    BalanceSnapshotRow,
    PlaidItemRow,
    SyncStateRow,
    TransactionRow,
    UserProfileRow,
)

# --------------------------------------------------------------------------- #
# ORM <-> domain mapping helpers
# --------------------------------------------------------------------------- #


def _item_to_domain(row: PlaidItemRow) -> PlaidItem:
    return PlaidItem(
        item_id=row.item_id,
        institution_id=row.institution_id,
        institution_name=row.institution_name,
        access_token_ref=row.access_token_ref,
        sync_cursor=row.sync_cursor,
        last_synced_at=row.last_synced_at,
        status=ItemStatus(row.status),
    )


def _account_to_domain(row: AccountRow) -> Account:
    return Account(
        account_id=row.account_id,
        item_id=row.item_id,
        name=row.name,
        type=row.type,
        subtype=row.subtype,
        official_name=row.official_name,
        mask=row.mask,
        current_balance=row.current_balance,
        available_balance=row.available_balance,
        currency=row.currency,
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


def _txn_to_domain(row: TransactionRow) -> Transaction:
    return Transaction(
        transaction_id=row.transaction_id,
        account_id=row.account_id,
        date=row.date,
        amount=row.amount,
        name=row.name,
        merchant_name=row.merchant_name,
        authorized_date=row.authorized_date,
        category_primary=row.category_primary,
        category_detailed=row.category_detailed,
        user_category_override=row.user_category_override,
        payment_channel=row.payment_channel,
        pending=row.pending,
        currency=row.currency,
    )


def _snapshot_to_domain(row: BalanceSnapshotRow) -> BalanceSnapshot:
    return BalanceSnapshot(
        account_id=row.account_id,
        as_of=row.as_of,
        current_balance=row.current_balance,
        available_balance=row.available_balance,
    )


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #


class SqlItemRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, item: PlaidItem) -> None:
        row = self._s.get(PlaidItemRow, item.item_id)
        if row is None:
            row = PlaidItemRow(item_id=item.item_id)
            self._s.add(row)
        row.institution_id = item.institution_id
        row.institution_name = item.institution_name
        row.access_token_ref = item.access_token_ref
        row.sync_cursor = item.sync_cursor
        row.last_synced_at = item.last_synced_at
        row.status = str(item.status)

    def get(self, item_id: str) -> PlaidItem | None:
        row = self._s.get(PlaidItemRow, item_id)
        return _item_to_domain(row) if row else None

    def list_all(self) -> list[PlaidItem]:
        rows = self._s.scalars(select(PlaidItemRow)).all()
        return [_item_to_domain(r) for r in rows]

    def set_cursor(self, item_id: str, cursor: str) -> None:
        row = self._s.get(PlaidItemRow, item_id)
        if row:
            row.sync_cursor = cursor

    def set_status(self, item_id: str, status: str) -> None:
        row = self._s.get(PlaidItemRow, item_id)
        if row:
            row.status = status

    def mark_synced(self, item_id: str, when: dt.datetime) -> None:
        row = self._s.get(PlaidItemRow, item_id)
        if row:
            row.last_synced_at = when


class SqlAccountRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, account: Account) -> None:
        row = self._s.get(AccountRow, account.account_id)
        if row is None:
            row = AccountRow(account_id=account.account_id)
            self._s.add(row)
        row.item_id = account.item_id
        row.name = account.name
        row.official_name = account.official_name
        row.mask = account.mask
        row.type = account.type
        row.subtype = account.subtype
        row.current_balance = account.current_balance
        row.available_balance = account.available_balance
        row.currency = account.currency
        row.is_active = account.is_active
        row.updated_at = account.updated_at

    def get(self, account_id: str) -> Account | None:
        row = self._s.get(AccountRow, account_id)
        return _account_to_domain(row) if row else None

    def list_all(self, *, active_only: bool = True) -> list[Account]:
        stmt = select(AccountRow)
        if active_only:
            stmt = stmt.where(AccountRow.is_active.is_(True))
        rows = self._s.scalars(stmt).all()
        return [_account_to_domain(r) for r in rows]


class SqlTransactionRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert_many(self, txns: list[Transaction]) -> None:
        for txn in txns:
            row = self._s.get(TransactionRow, txn.transaction_id)
            if row is None:
                row = TransactionRow(transaction_id=txn.transaction_id)
                self._s.add(row)
            row.account_id = txn.account_id
            row.date = txn.date
            row.authorized_date = txn.authorized_date
            row.amount = txn.amount
            row.name = txn.name
            row.merchant_name = txn.merchant_name
            row.category_primary = txn.category_primary
            row.category_detailed = txn.category_detailed
            # Preserve an existing user override unless the incoming txn sets one.
            if txn.user_category_override is not None:
                row.user_category_override = txn.user_category_override
            row.payment_channel = txn.payment_channel
            row.pending = txn.pending
            row.currency = txn.currency

    def delete_many(self, transaction_ids: list[str]) -> None:
        if not transaction_ids:
            return
        self._s.execute(
            delete(TransactionRow).where(
                TransactionRow.transaction_id.in_(transaction_ids)
            )
        )

    def query(self, q: TransactionQuery) -> list[Transaction]:
        stmt = select(TransactionRow)
        if q.start_date is not None:
            stmt = stmt.where(TransactionRow.date >= q.start_date)
        if q.end_date is not None:
            stmt = stmt.where(TransactionRow.date <= q.end_date)
        if q.account_id is not None:
            stmt = stmt.where(TransactionRow.account_id == q.account_id)
        if q.category is not None:
            # Match against the effective category (override first, else Plaid).
            stmt = stmt.where(
                (TransactionRow.user_category_override == q.category)
                | (
                    TransactionRow.user_category_override.is_(None)
                    & (TransactionRow.category_primary == q.category)
                )
            )
        if q.merchant_contains is not None:
            like = f"%{q.merchant_contains}%"
            stmt = stmt.where(
                TransactionRow.merchant_name.ilike(like)
                | TransactionRow.name.ilike(like)
            )
        if not q.include_pending:
            stmt = stmt.where(TransactionRow.pending.is_(False))
        stmt = stmt.order_by(TransactionRow.date.desc())
        if q.limit is not None:
            stmt = stmt.limit(q.limit)
        rows = self._s.scalars(stmt).all()
        txns = [_txn_to_domain(r) for r in rows]
        # Amount bounds filtered in Python: amounts are stored as text, so SQL
        # comparisons would be lexical, not numeric.
        if q.min_amount is not None:
            txns = [t for t in txns if float(t.amount) >= q.min_amount]
        if q.max_amount is not None:
            txns = [t for t in txns if float(t.amount) <= q.max_amount]
        return txns

    def set_category_override(self, transaction_id: str, category: str) -> None:
        row = self._s.get(TransactionRow, transaction_id)
        if row:
            row.user_category_override = category


class SqlSnapshotRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, snapshot: BalanceSnapshot) -> None:
        row = self._s.scalars(
            select(BalanceSnapshotRow).where(
                BalanceSnapshotRow.account_id == snapshot.account_id,
                BalanceSnapshotRow.as_of == snapshot.as_of,
            )
        ).one_or_none()
        if row is None:
            row = BalanceSnapshotRow(
                account_id=snapshot.account_id, as_of=snapshot.as_of
            )
            self._s.add(row)
        row.current_balance = snapshot.current_balance
        row.available_balance = snapshot.available_balance

    def list_between(self, start: dt.date, end: dt.date) -> list[BalanceSnapshot]:
        rows = self._s.scalars(
            select(BalanceSnapshotRow)
            .where(BalanceSnapshotRow.as_of >= start, BalanceSnapshotRow.as_of <= end)
            .order_by(BalanceSnapshotRow.as_of)
        ).all()
        return [_snapshot_to_domain(r) for r in rows]

    def list_all(self) -> list[BalanceSnapshot]:
        rows = self._s.scalars(
            select(BalanceSnapshotRow).order_by(BalanceSnapshotRow.as_of)
        ).all()
        return [_snapshot_to_domain(r) for r in rows]


class SqlProfileRepo:
    _ID = 1

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self) -> UserProfile | None:
        row = self._s.get(UserProfileRow, self._ID)
        if row is None:
            return None
        return UserProfile(
            birth_year=row.birth_year,
            annual_gross_income=row.annual_gross_income,
            annual_net_income=row.annual_net_income,
            monthly_savings_target=row.monthly_savings_target,
            emergency_fund_months=row.emergency_fund_months,
            risk_tolerance=RiskTolerance(row.risk_tolerance),
            retirement_age_target=row.retirement_age_target,
            retirement_annual_spend=row.retirement_annual_spend,
            expected_return_override=row.expected_return_override,
            extras=dict(row.extras or {}),
        )

    def save(self, profile: UserProfile) -> None:
        row = self._s.get(UserProfileRow, self._ID)
        if row is None:
            row = UserProfileRow(id=self._ID)
            self._s.add(row)
        row.birth_year = profile.birth_year
        row.annual_gross_income = profile.annual_gross_income
        row.annual_net_income = profile.annual_net_income
        row.monthly_savings_target = profile.monthly_savings_target
        row.emergency_fund_months = profile.emergency_fund_months
        row.risk_tolerance = str(profile.risk_tolerance)
        row.retirement_age_target = profile.retirement_age_target
        row.retirement_annual_spend = profile.retirement_annual_spend
        row.expected_return_override = profile.expected_return_override
        row.extras = dict(profile.extras)


class SqlSyncStateRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, scope: str) -> SyncState | None:
        row = self._s.get(SyncStateRow, scope)
        if row is None:
            return None
        return SyncState(
            scope=row.scope,
            last_sync_at=row.last_sync_at,
            last_error=row.last_error,
            last_error_at=row.last_error_at,
        )

    def _get_or_create(self, scope: str) -> SyncStateRow:
        row = self._s.get(SyncStateRow, scope)
        if row is None:
            row = SyncStateRow(scope=scope)
            self._s.add(row)
        return row

    def mark_synced(self, scope: str, when: dt.datetime) -> None:
        row = self._get_or_create(scope)
        row.last_sync_at = when
        row.last_error = None
        row.last_error_at = None

    def mark_error(self, scope: str, message: str, when: dt.datetime) -> None:
        row = self._get_or_create(scope)
        row.last_error = message
        row.last_error_at = when
