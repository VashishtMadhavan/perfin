"""Deterministic local data source for Phase 1 development and demos."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from perfin.core.models import Account, PlaidItem, SyncBatch, Transaction
from perfin.datasources.base import LinkResult


class FakeDataSource:
    """A tiny Plaid-like source with cursor pages and stable account ids."""

    item_id = "fake-item"
    _DONE = "fake-v1"
    _PAGE_1 = "fake-page-1"

    def link(self) -> LinkResult:
        return LinkResult(item=self._item(cursor=None), accounts=self._accounts())

    def matches_item(self, item: PlaidItem) -> bool:
        return item.item_id == self.item_id

    def fetch_accounts(self, item: PlaidItem) -> list[Account]:
        return self._accounts()

    def sync_transactions(
        self, item: PlaidItem, cursor: str | None
    ) -> SyncBatch:
        txns = self._transactions()
        if cursor == self._DONE:
            return SyncBatch([], [], [], self._DONE, False)
        if cursor == self._PAGE_1:
            return SyncBatch(txns[len(txns) // 2 :], [], [], self._DONE, False)
        return SyncBatch(txns[: len(txns) // 2], [], [], self._PAGE_1, True)

    def _item(self, cursor: str | None) -> PlaidItem:
        return PlaidItem(
            item_id=self.item_id,
            institution_id="ins_fake",
            institution_name="Perfin Demo Bank",
            access_token_ref="fake://plaid/access-token",
            sync_cursor=cursor,
        )

    def _accounts(self) -> list[Account]:
        now = dt.datetime.now(dt.UTC)
        return [
            Account(
                account_id="fake-checking",
                item_id=self.item_id,
                name="Everyday Checking",
                type="depository",
                subtype="checking",
                current_balance=Decimal("8420.35"),
                available_balance=Decimal("8120.35"),
                updated_at=now,
            ),
            Account(
                account_id="fake-savings",
                item_id=self.item_id,
                name="High-Yield Savings",
                type="depository",
                subtype="savings",
                current_balance=Decimal("28750.00"),
                available_balance=Decimal("28750.00"),
                updated_at=now,
            ),
            Account(
                account_id="fake-credit",
                item_id=self.item_id,
                name="Rewards Card",
                type="credit",
                subtype="credit card",
                current_balance=Decimal("1240.18"),
                updated_at=now,
            ),
            Account(
                account_id="fake-brokerage",
                item_id=self.item_id,
                name="Long-Term Brokerage",
                type="investment",
                subtype="brokerage",
                current_balance=Decimal("64320.70"),
                updated_at=now,
            ),
        ]

    def _transactions(self) -> list[Transaction]:
        today = dt.date.today()
        first_of_month = today.replace(day=1)
        rows: list[Transaction] = []

        for month_offset in range(4):
            month = _add_months(first_of_month, -month_offset)
            rows.extend(
                [
                    _txn(
                        f"salary-{month:%Y-%m}",
                        "fake-checking",
                        month,
                        "-7200.00",
                        "Payroll Deposit",
                        "Employer Inc",
                        "INCOME",
                    ),
                    _txn(
                        f"rent-{month:%Y-%m}",
                        "fake-checking",
                        month + dt.timedelta(days=2),
                        "2550.00",
                        "Apartment Rent",
                        "Cedar House Apartments",
                        "RENT_AND_UTILITIES",
                    ),
                    _txn(
                        f"utilities-{month:%Y-%m}",
                        "fake-checking",
                        month + dt.timedelta(days=6),
                        "235.60",
                        "Electric and Internet",
                        "City Utilities",
                        "RENT_AND_UTILITIES",
                    ),
                    _txn(
                        f"transfer-savings-{month:%Y-%m}",
                        "fake-checking",
                        month + dt.timedelta(days=8),
                        "1500.00",
                        "Transfer to Savings",
                        "High-Yield Savings",
                        "TRANSFER_OUT",
                    ),
                    _txn(
                        f"card-payment-{month:%Y-%m}",
                        "fake-checking",
                        month + dt.timedelta(days=18),
                        "980.00",
                        "Credit Card Payment",
                        "Rewards Card",
                        "TRANSFER_OUT",
                    ),
                ]
            )

            for week in range(4):
                day = month + dt.timedelta(days=4 + week * 6)
                rows.extend(
                    [
                        _txn(
                            f"grocery-{month:%Y-%m}-{week}",
                            "fake-credit",
                            day,
                            str(Decimal("92.40") + Decimal(week * 7)),
                            "Neighborhood Market",
                            "Neighborhood Market",
                            "FOOD_AND_DRINK",
                        ),
                        _txn(
                            f"coffee-{month:%Y-%m}-{week}",
                            "fake-credit",
                            day + dt.timedelta(days=1),
                            "8.75",
                            "Coffee Shop",
                            "Coffee Shop",
                            "FOOD_AND_DRINK",
                        ),
                    ]
                )

            rows.extend(
                [
                    _txn(
                        f"rideshare-{month:%Y-%m}",
                        "fake-credit",
                        month + dt.timedelta(days=12),
                        "42.18",
                        "Rideshare",
                        "Lyft",
                        "TRANSPORTATION",
                    ),
                    _txn(
                        f"gym-{month:%Y-%m}",
                        "fake-credit",
                        month + dt.timedelta(days=14),
                        "79.00",
                        "Gym Membership",
                        "City Gym",
                        "GENERAL_MERCHANDISE",
                    ),
                    _txn(
                        f"dinner-{month:%Y-%m}",
                        "fake-credit",
                        month + dt.timedelta(days=21),
                        "146.25",
                        "Dinner",
                        "Northstar Bistro",
                        "FOOD_AND_DRINK",
                    ),
                ]
            )

        return sorted(rows, key=lambda t: t.date, reverse=True)


def _txn(
    transaction_id: str,
    account_id: str,
    date: dt.date,
    amount: str,
    name: str,
    merchant: str,
    category: str,
) -> Transaction:
    return Transaction(
        transaction_id=f"fake-{transaction_id}",
        account_id=account_id,
        date=date,
        amount=Decimal(amount),
        name=name,
        merchant_name=merchant,
        category_primary=category,
        category_detailed=category,
    )


def _add_months(date: dt.date, months: int) -> dt.date:
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    return dt.date(year, month, 1)
