from __future__ import annotations

import datetime as dt
from decimal import Decimal

from perfin.config import PlaidSettings, Settings
from perfin.core.finance_service import FinanceService
from perfin.core.profile_service import ProfileService
from perfin.core.sync_service import SyncService
from perfin.datasources.fake_source import FakeDataSource
from perfin.datasources.plaid_source import PlaidSource
from perfin.secrets import FileFallbackStore
from perfin.storage.db import create_db_engine, create_session_factory, init_schema


def _session_factory():
    engine = create_db_engine("sqlite:///:memory:")
    init_schema(engine)
    return create_session_factory(engine)


def test_plaid_source_maps_sandbox_link_accounts_and_sync(tmp_path) -> None:
    secrets = FileFallbackStore(tmp_path / "secrets.json")
    client = _FakePlaidClient()
    source = PlaidSource(Settings(), secrets, client=client)

    result = source.link()
    batch = source.sync_transactions(result.item, None)

    assert result.item.item_id == "item-123"
    assert secrets.get("plaid/item-123/access-token") == "access-123"
    assert result.accounts[0].account_id == "acc-checking"
    assert result.accounts[0].current_balance == Decimal("1200.5")
    assert batch.added[0].category_primary == "FOOD_AND_DRINK"
    assert batch.removed == ["removed-1"]
    assert batch.next_cursor == "cursor-1"


def test_plaid_source_creates_hosted_link_url(tmp_path) -> None:
    source = PlaidSource(
        Settings(plaid=PlaidSettings(env="development")),
        FileFallbackStore(tmp_path / "secrets.json"),
        client=_FakePlaidClient(),
    )

    assert source.create_hosted_link_url() == "https://hosted-link.example/session"


def test_affordability_and_retirement_facades() -> None:
    sessions = _session_factory()
    SyncService(sessions).sync(FakeDataSource())
    ProfileService(sessions).update(
        birth_year=1990,
        monthly_savings_target=Decimal("1500"),
        retirement_age_target=65,
        retirement_annual_spend=Decimal("80000"),
    )

    finance = FinanceService(sessions)
    afford = finance.affordability(amount=Decimal("3000"), months=3)
    retire = finance.retirement_projection(months=3)

    assert afford.affordable_now is True
    assert afford.available_after_buffer > Decimal("0")
    assert retire.current_age == dt.date.today().year - 1990
    assert retire.annual_contribution == Decimal("18000")
    assert retire.target_annual_spend == Decimal("80000")


class _FakePlaidClient:
    def sandbox_public_token_create(self, request):
        assert request.institution_id == "ins_109508"
        return {"public_token": "public-123"}

    def item_public_token_exchange(self, request):
        assert request.public_token == "public-123"
        return {"item_id": "item-123", "access_token": "access-123"}

    def accounts_balance_get(self, request):
        assert request.access_token == "access-123"
        return {
            "accounts": [
                {
                    "account_id": "acc-checking",
                    "name": "Checking",
                    "official_name": "Plaid Checking",
                    "mask": "0000",
                    "type": "depository",
                    "subtype": "checking",
                    "balances": {
                        "current": 1200.50,
                        "available": 1100.25,
                        "iso_currency_code": "USD",
                    },
                }
            ]
        }

    def transactions_sync(self, request):
        assert request.access_token == "access-123"
        return {
            "added": [
                {
                    "transaction_id": "txn-1",
                    "account_id": "acc-checking",
                    "date": dt.date(2026, 7, 1),
                    "amount": 12.34,
                    "name": "Cafe",
                    "merchant_name": "Cafe",
                    "personal_finance_category": {
                        "primary": "FOOD_AND_DRINK",
                        "detailed": "FOOD_AND_DRINK_COFFEE",
                    },
                    "payment_channel": "in store",
                    "pending": False,
                    "iso_currency_code": "USD",
                }
            ],
            "modified": [],
            "removed": [{"transaction_id": "removed-1", "account_id": "acc-checking"}],
            "next_cursor": "cursor-1",
            "has_more": False,
        }

    def link_token_create(self, request):
        assert request.client_name == "Perfin"
        assert request.hosted_link is not None
        return {"hosted_link_url": "https://hosted-link.example/session"}
