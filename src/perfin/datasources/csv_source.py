"""CSV transaction import source."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
from decimal import Decimal
from pathlib import Path

from perfin.core.models import Account, PlaidItem, SyncBatch, Transaction
from perfin.datasources.base import LinkResult


class CsvSource:
    """Import a simple transaction CSV using the DataSource contract.

    Required columns: ``date``, ``amount``, ``name``.
    Optional columns: ``transaction_id``, ``merchant_name``/``merchant``,
    ``category_primary``/``category``, ``category_detailed``, ``pending``.
    Amounts use the project convention by default: positive is outflow/spend.
    """

    _DONE = "csv-v1"

    def __init__(
        self,
        path: Path,
        *,
        account_name: str = "CSV Import",
        current_balance: Decimal | None = None,
        invert_amounts: bool = False,
    ) -> None:
        self._path = path
        self._account_name = account_name
        self._current_balance = current_balance
        self._invert_amounts = invert_amounts
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
        stem = "".join(ch for ch in path.stem.lower() if ch.isalnum())[:24] or "import"
        self.item_id = f"csv-{stem}-{digest}"
        self.account_id = f"{self.item_id}-account"

    def link(self) -> LinkResult:
        return LinkResult(item=self._item(cursor=None), accounts=self._accounts())

    def matches_item(self, item: PlaidItem) -> bool:
        return item.item_id == self.item_id

    def fetch_accounts(self, item: PlaidItem) -> list[Account]:
        return self._accounts()

    def sync_transactions(
        self, item: PlaidItem, cursor: str | None
    ) -> SyncBatch:
        if cursor == self._DONE:
            return SyncBatch([], [], [], self._DONE, False)
        return SyncBatch(self._transactions(), [], [], self._DONE, False)

    def _item(self, cursor: str | None) -> PlaidItem:
        return PlaidItem(
            item_id=self.item_id,
            institution_id="csv",
            institution_name=self._path.name,
            access_token_ref=f"csv://{self._path}",
            sync_cursor=cursor,
        )

    def _accounts(self) -> list[Account]:
        return [
            Account(
                account_id=self.account_id,
                item_id=self.item_id,
                name=self._account_name,
                type="depository",
                subtype="checking",
                current_balance=self._current_balance,
                available_balance=self._current_balance,
                updated_at=dt.datetime.now(dt.UTC),
            )
        ]

    def _transactions(self) -> list[Transaction]:
        if not self._path.is_file():
            raise FileNotFoundError(self._path)
        rows = []
        with self._path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                rows.append(self._transaction(idx, row))
        return rows

    def _transaction(self, idx: int, row: dict[str, str]) -> Transaction:
        date = _date(_required(row, "date"))
        amount = Decimal(_required(row, "amount"))
        if self._invert_amounts:
            amount = -amount
        name = _required(row, "name")
        transaction_id = row.get("transaction_id") or _row_id(self.account_id, idx, row)
        return Transaction(
            transaction_id=transaction_id,
            account_id=self.account_id,
            date=date,
            amount=amount,
            name=name,
            merchant_name=row.get("merchant_name") or row.get("merchant") or None,
            category_primary=row.get("category_primary") or row.get("category") or None,
            category_detailed=row.get("category_detailed") or None,
            pending=_bool(row.get("pending")),
            currency=row.get("currency") or "USD",
        )


def _required(row: dict[str, str], name: str) -> str:
    value = row.get(name)
    if value is None or value == "":
        raise ValueError(f"CSV row missing required column {name!r}")
    return value


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _row_id(account_id: str, idx: int, row: dict[str, str]) -> str:
    payload = "|".join(f"{key}={row.get(key, '')}" for key in sorted(row))
    digest = hashlib.sha1(f"{account_id}|{idx}|{payload}".encode("utf-8")).hexdigest()
    return f"csv-{digest}"
