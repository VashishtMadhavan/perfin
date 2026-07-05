"""Plaid-backed data source."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from perfin.config import Settings
from perfin.core.models import Account, PlaidItem, SyncBatch, Transaction
from perfin.datasources.base import LinkResult
from perfin.secrets import SecretStore, plaid_access_token_ref

DEFAULT_SANDBOX_INSTITUTION = "ins_109508"


class PlaidSource:
    def __init__(
        self,
        settings: Settings,
        secrets: SecretStore,
        *,
        client: Any | None = None,
        sandbox_institution_id: str = DEFAULT_SANDBOX_INSTITUTION,
    ) -> None:
        self._settings = settings
        self._secrets = secrets
        self._client = client or _plaid_client(settings)
        self._sandbox_institution_id = sandbox_institution_id

    def link(self) -> LinkResult:
        if self._settings.plaid.env != "sandbox":
            raise NotImplementedError("Hosted Link is planned for Phase 5.")
        public_token_response = self._client.sandbox_public_token_create(
            SandboxPublicTokenCreateRequest(
                institution_id=self._sandbox_institution_id,
                initial_products=[Products("transactions")],
            )
        )
        public_token = _get(public_token_response, "public_token")
        exchange_response = self._client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
        item_id = str(_get(exchange_response, "item_id"))
        access_token = str(_get(exchange_response, "access_token"))
        access_token_ref = plaid_access_token_ref(item_id)
        self._secrets.set(access_token_ref, access_token)
        item = PlaidItem(
            item_id=item_id,
            institution_id=self._sandbox_institution_id,
            institution_name="Plaid Sandbox",
            access_token_ref=access_token_ref,
        )
        return LinkResult(item=item, accounts=self.fetch_accounts(item))

    def matches_item(self, item: PlaidItem) -> bool:
        return item.access_token_ref.startswith("plaid/")

    def fetch_accounts(self, item: PlaidItem) -> list[Account]:
        access_token = self._access_token(item)
        response = self._client.accounts_balance_get(
            AccountsBalanceGetRequest(access_token=access_token)
        )
        accounts = _get(response, "accounts", default=[])
        return [_account_from_plaid(item.item_id, account) for account in accounts]

    def sync_transactions(
        self, item: PlaidItem, cursor: str | None
    ) -> SyncBatch:
        kwargs: dict[str, Any] = {"access_token": self._access_token(item), "count": 500}
        if cursor is not None:
            kwargs["cursor"] = cursor
        response = self._client.transactions_sync(TransactionsSyncRequest(**kwargs))
        return SyncBatch(
            added=[
                _transaction_from_plaid(txn)
                for txn in _get(response, "added", default=[])
            ],
            modified=[
                _transaction_from_plaid(txn)
                for txn in _get(response, "modified", default=[])
            ],
            removed=[
                str(_get(txn, "transaction_id"))
                for txn in _get(response, "removed", default=[])
            ],
            next_cursor=_get(response, "next_cursor"),
            has_more=bool(_get(response, "has_more", default=False)),
        )

    def _access_token(self, item: PlaidItem) -> str:
        token = self._secrets.get(item.access_token_ref)
        if token is None:
            raise RuntimeError(f"Missing Plaid access token for {item.item_id}")
        return token


def _plaid_client(settings: Settings):
    if not settings.plaid.client_id or not settings.plaid.secret:
        raise RuntimeError("PLAID_CLIENT_ID and PLAID_SECRET are required.")
    host = plaid.Environment.Sandbox
    if settings.plaid.env == "production":
        host = plaid.Environment.Production
    configuration = plaid.Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid.client_id,
            "secret": settings.plaid.secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _account_from_plaid(item_id: str, raw: Any) -> Account:
    balances = _get(raw, "balances", default={})
    now = dt.datetime.now(dt.UTC)
    return Account(
        account_id=str(_get(raw, "account_id")),
        item_id=item_id,
        name=str(_get(raw, "name")),
        official_name=_get(raw, "official_name"),
        mask=_get(raw, "mask"),
        type=_scalar(_get(raw, "type")),
        subtype=_scalar(_get(raw, "subtype")),
        current_balance=_decimal(_get(balances, "current")),
        available_balance=_decimal(_get(balances, "available")),
        currency=_get(balances, "iso_currency_code", default="USD") or "USD",
        updated_at=now,
    )


def _transaction_from_plaid(raw: Any) -> Transaction:
    pfc = _get(raw, "personal_finance_category", default=None)
    legacy_category = _get(raw, "category", default=None)
    legacy_primary = legacy_category[0] if legacy_category else None
    legacy_detailed = legacy_category[-1] if legacy_category else None
    return Transaction(
        transaction_id=str(_get(raw, "transaction_id")),
        account_id=str(_get(raw, "account_id")),
        date=_get(raw, "date"),
        authorized_date=_get(raw, "authorized_date", default=None),
        amount=_decimal(_get(raw, "amount")) or Decimal("0"),
        name=str(_get(raw, "name")),
        merchant_name=_get(raw, "merchant_name", default=None),
        category_primary=_get(pfc, "primary", default=legacy_primary),
        category_detailed=_get(pfc, "detailed", default=legacy_detailed),
        payment_channel=_get(raw, "payment_channel", default=None),
        pending=bool(_get(raw, "pending", default=False)),
        currency=_get(raw, "iso_currency_code", default="USD") or "USD",
    )


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
