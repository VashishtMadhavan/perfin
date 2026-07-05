"""Account and transaction sync orchestration."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from perfin.core.models import BalanceSnapshot
from perfin.datasources.base import DataSource
from perfin.storage.db import session_scope
from perfin.storage.repositories import (
    SqlAccountRepo,
    SqlItemRepo,
    SqlSnapshotRepo,
    SqlSyncStateRepo,
    SqlTransactionRepo,
)


@dataclass(frozen=True, slots=True)
class SyncReport:
    item_id: str
    accounts: int
    added: int = 0
    modified: int = 0
    removed: int = 0
    batches: int = 0


class SyncService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def sync(self, source: DataSource, *, full: bool = False) -> SyncReport:
        item = self._ensure_linked(source)
        return self.sync_item(source, item.item_id, full=full)

    def link(self, source: DataSource) -> str:
        result = source.link()
        with session_scope(self._sessions) as session:
            items = SqlItemRepo(session)
            accounts = SqlAccountRepo(session)
            items.upsert(result.item)
            for account in result.accounts:
                accounts.upsert(account)
        return result.item.item_id

    def ensure_fresh(
        self, source: DataSource, *, staleness: dt.timedelta
    ) -> SyncReport | None:
        now = dt.datetime.now(dt.UTC)
        with session_scope(self._sessions) as session:
            items = SqlItemRepo(session)
            matching = [item for item in items.list_all() if source.matches_item(item)]
        if not matching:
            return self.sync(source)
        item = min(
            matching,
            key=lambda candidate: candidate.last_synced_at or dt.datetime.min.replace(tzinfo=dt.UTC),
        )
        if item.last_synced_at is None or now - _aware(item.last_synced_at) >= staleness:
            return self.sync_item(source, item.item_id)
        return None

    def sync_item(
        self, source: DataSource, item_id: str, *, full: bool = False
    ) -> SyncReport:
        now = dt.datetime.now(dt.UTC)
        today = now.date()
        added = modified = removed = batches = 0

        with session_scope(self._sessions) as session:
            items = SqlItemRepo(session)
            accounts = SqlAccountRepo(session)
            snapshots = SqlSnapshotRepo(session)
            item = items.get(item_id)
            if item is None:
                raise ValueError(f"No linked item found for {item_id!r}")
            current_accounts = source.fetch_accounts(item)
            for account in current_accounts:
                accounts.upsert(account)
                snapshots.upsert(
                    BalanceSnapshot(
                        account_id=account.account_id,
                        as_of=today,
                        current_balance=account.current_balance,
                        available_balance=account.available_balance,
                    )
                )
            cursor = None if full else item.sync_cursor

        while True:
            batch = source.sync_transactions(item, cursor)
            with session_scope(self._sessions) as session:
                items = SqlItemRepo(session)
                txns = SqlTransactionRepo(session)
                txns.upsert_many(batch.added)
                txns.upsert_many(batch.modified)
                txns.delete_many(batch.removed)
                if batch.next_cursor is not None:
                    items.set_cursor(item_id, batch.next_cursor)
                added += len(batch.added)
                modified += len(batch.modified)
                removed += len(batch.removed)
                batches += 1
            cursor = batch.next_cursor
            if not batch.has_more:
                break

        with session_scope(self._sessions) as session:
            SqlItemRepo(session).mark_synced(item_id, now)
            SqlSyncStateRepo(session).mark_synced("global", now)

        return SyncReport(
            item_id=item_id,
            accounts=len(current_accounts),
            added=added,
            modified=modified,
            removed=removed,
            batches=batches,
        )

    def _ensure_linked(self, source: DataSource):
        with session_scope(self._sessions) as session:
            items = SqlItemRepo(session)
            existing = [item for item in items.list_all() if source.matches_item(item)]
            if existing:
                return existing[0]
            result = source.link()
            items.upsert(result.item)
            accounts = SqlAccountRepo(session)
            for account in result.accounts:
                accounts.upsert(account)
            return result.item


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value
