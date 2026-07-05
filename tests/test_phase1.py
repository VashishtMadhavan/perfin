from __future__ import annotations

from decimal import Decimal

from perfin.core.finance_service import FinanceService
from perfin.core.sync_service import SyncService
from perfin.datasources.fake_source import FakeDataSource
from perfin.storage.db import create_db_engine, create_session_factory, init_schema


def _session_factory():
    engine = create_db_engine("sqlite:///:memory:")
    init_schema(engine)
    return create_session_factory(engine)


def test_fake_sync_is_cursor_idempotent() -> None:
    sessions = _session_factory()
    service = SyncService(sessions)

    first = service.sync(FakeDataSource())
    second = service.sync(FakeDataSource())

    assert first.accounts == 4
    assert first.added == 64
    assert first.batches == 2
    assert second.added == 0
    assert second.batches == 1


def test_spending_excludes_transfers() -> None:
    sessions = _session_factory()
    SyncService(sessions).sync(FakeDataSource())

    summary = FinanceService(sessions).spending_summary(months=3)

    totals = {row.key: row.total for row in summary.rows}
    assert "TRANSFER_OUT" not in totals
    assert totals["RENT_AND_UTILITIES"] == Decimal("8356.80")
    assert summary.total == Decimal("10591.29")


def test_networth_treats_credit_as_liability() -> None:
    sessions = _session_factory()
    SyncService(sessions).sync(FakeDataSource())

    summary = FinanceService(sessions).networth_summary()

    assert summary.total == Decimal("100250.87")
    assert any(
        row.account_name == "Rewards Card" and row.amount == Decimal("-1240.18")
        for row in summary.contributions
    )
