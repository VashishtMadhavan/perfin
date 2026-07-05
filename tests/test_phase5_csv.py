from __future__ import annotations

from decimal import Decimal

from perfin.core.finance_service import FinanceService
from perfin.core.sync_service import SyncService
from perfin.datasources.csv_source import CsvSource
from perfin.storage.db import create_db_engine, create_session_factory, init_schema


def _session_factory():
    engine = create_db_engine("sqlite:///:memory:")
    init_schema(engine)
    return create_session_factory(engine)


def test_csv_import_syncs_transactions_and_is_idempotent(tmp_path) -> None:
    path = tmp_path / "transactions.csv"
    path.write_text(
        "date,amount,name,merchant,category\n"
        "2026-07-01,12.50,Coffee,Cafe,FOOD_AND_DRINK\n"
        "2026-07-02,-100.00,Payroll,Employer,INCOME\n",
        encoding="utf-8",
    )
    sessions = _session_factory()
    source = CsvSource(
        path,
        account_name="Checking",
        current_balance=Decimal("500"),
    )

    first = SyncService(sessions).sync(source)
    second = SyncService(sessions).sync(source)
    spending = FinanceService(sessions).spending_summary(months=1)
    networth = FinanceService(sessions).networth_summary()

    assert first.added == 2
    assert second.added == 0
    assert spending.total == Decimal("12.50")
    assert networth.total == Decimal("500")


def test_csv_import_can_invert_bank_sign_convention(tmp_path) -> None:
    path = tmp_path / "bank.csv"
    path.write_text(
        "date,amount,name,category\n"
        "2026-07-01,-20.00,Lunch,FOOD_AND_DRINK\n",
        encoding="utf-8",
    )
    sessions = _session_factory()

    SyncService(sessions).sync(CsvSource(path, invert_amounts=True))

    assert FinanceService(sessions).spending_summary(months=1).total == Decimal("20.00")
