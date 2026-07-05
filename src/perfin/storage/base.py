"""Repository protocols — the persistence contract the service layer depends on.

Services depend on these Protocols, not on the SQLAlchemy implementations, so a
future backend can supply Postgres-backed (or API-backed) repositories without
touching business logic. All methods speak in :mod:`perfin.core.models` domain
objects, never ORM rows.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from perfin.core.models import (
    Account,
    BalanceSnapshot,
    PlaidItem,
    SyncState,
    Transaction,
    UserProfile,
)


@dataclass(frozen=True, slots=True)
class TransactionQuery:
    """Filter for :meth:`TransactionRepo.query`. All fields optional/AND-ed."""

    start_date: dt.date | None = None
    end_date: dt.date | None = None
    category: str | None = None
    account_id: str | None = None
    merchant_contains: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    include_pending: bool = True
    limit: int | None = None


class ItemRepo(Protocol):
    def upsert(self, item: PlaidItem) -> None: ...
    def get(self, item_id: str) -> PlaidItem | None: ...
    def list_all(self) -> list[PlaidItem]: ...
    def set_cursor(self, item_id: str, cursor: str) -> None: ...
    def set_status(self, item_id: str, status: str) -> None: ...
    def mark_synced(self, item_id: str, when: dt.datetime) -> None: ...


class AccountRepo(Protocol):
    def upsert(self, account: Account) -> None: ...
    def get(self, account_id: str) -> Account | None: ...
    def list_all(self, *, active_only: bool = True) -> list[Account]: ...


class TransactionRepo(Protocol):
    def upsert_many(self, txns: list[Transaction]) -> None: ...
    def delete_many(self, transaction_ids: list[str]) -> None: ...
    def query(self, q: TransactionQuery) -> list[Transaction]: ...
    def set_category_override(self, transaction_id: str, category: str) -> None: ...


class SnapshotRepo(Protocol):
    def upsert(self, snapshot: BalanceSnapshot) -> None: ...
    def list_between(
        self, start: dt.date, end: dt.date
    ) -> list[BalanceSnapshot]: ...
    def list_all(self) -> list[BalanceSnapshot]: ...


class ProfileRepo(Protocol):
    def get(self) -> UserProfile | None: ...
    def save(self, profile: UserProfile) -> None: ...


class SyncStateRepo(Protocol):
    def get(self, scope: str) -> SyncState | None: ...
    def mark_synced(self, scope: str, when: dt.datetime) -> None: ...
    def mark_error(self, scope: str, message: str, when: dt.datetime) -> None: ...
