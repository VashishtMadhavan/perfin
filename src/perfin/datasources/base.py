"""Data source contracts.

The service layer syncs against this protocol, whether the backing source is
Plaid, CSV import, or the deterministic fake source used by local development.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from perfin.core.models import Account, PlaidItem, SyncBatch


@dataclass(frozen=True, slots=True)
class LinkResult:
    item: PlaidItem
    accounts: list[Account]


class DataSource(Protocol):
    def link(self) -> LinkResult: ...
    def fetch_accounts(self, item: PlaidItem) -> list[Account]: ...
    def sync_transactions(
        self, item: PlaidItem, cursor: str | None
    ) -> SyncBatch: ...
