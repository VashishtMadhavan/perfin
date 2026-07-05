"""Typer root application.

The root ``@app.callback`` is the single hook that runs before every subcommand:
it builds the dependency container and (once Phase 3 lands) runs the auto-sync
staleness gate. Command modules register their own sub-apps / commands here.
"""

from __future__ import annotations

from decimal import Decimal

import typer

from perfin import __version__
from perfin.cli.render import console, money, pct, simple_table
from perfin.config import get_settings
from perfin.core.finance_service import FinanceService
from perfin.core.models import RiskTolerance
from perfin.core.profile_service import ProfileService
from perfin.core.sync_service import SyncService
from perfin.datasources.fake_source import FakeDataSource
from perfin.storage.db import create_db_engine, create_session_factory, init_schema

app = typer.Typer(
    name="perfin",
    help="A one-stop personal finance CLI.",
    no_args_is_help=True,
    add_completion=False,
)


def _session_factory():
    settings = get_settings()
    engine = create_db_engine(settings.db_url)
    init_schema(engine)
    return create_session_factory(engine)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"perfin {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
    no_sync: bool = typer.Option(
        False, "--no-sync", help="Skip the automatic freshness sync for this command."
    ),
) -> None:
    """Root callback: wire dependencies and gate on data freshness."""
    # Dependency container + auto-sync gate are wired in later phases. Stash the
    # flag now so command implementations and the future gate can read it.
    ctx.ensure_object(dict)
    ctx.obj["no_sync"] = no_sync


@app.command("sync")
def sync_command(
    source: str = typer.Option(
        "fake", "--source", help="Data source to sync. Phase 1 supports 'fake'."
    ),
    full: bool = typer.Option(False, "--full", help="Reset the source cursor first."),
) -> None:
    """Sync accounts and transactions."""
    if source != "fake":
        raise typer.BadParameter("Only --source fake is implemented in Phase 1.")
    report = SyncService(_session_factory()).sync(FakeDataSource(), full=full)
    console.print(
        f"Synced {report.item_id}: {report.accounts} accounts, "
        f"{report.added} added, {report.modified} modified, "
        f"{report.removed} removed across {report.batches} batch(es)."
    )


@app.command("spend")
def spend_command(
    months: int = typer.Option(1, "--months", min=1, help="Lookback window."),
    group_by: str = typer.Option(
        "category", "--group-by", help="category or merchant."
    ),
) -> None:
    """Show spending over a recent period."""
    if group_by not in {"category", "merchant"}:
        raise typer.BadParameter("--group-by must be 'category' or 'merchant'.")
    summary = FinanceService(_session_factory()).spending_summary(
        months=months, group_by=group_by
    )
    table = simple_table(
        f"Spending {summary.start} to {summary.end}", [group_by.title(), "Count", "Total"]
    )
    for row in summary.rows:
        table.add_row(row.key, str(row.count), money(row.total))
    table.add_section()
    table.add_row("Total", "", money(summary.total))
    console.print(table)


@app.command("networth")
def networth_command(
    months: int = typer.Option(12, "--months", min=1, help="History lookback window."),
) -> None:
    """Show current net worth and account contributions."""
    summary = FinanceService(_session_factory()).networth_summary(months=months)
    console.print(f"Current net worth: [bold]{money(summary.total)}[/bold]")
    table = simple_table("Account contributions", ["Account", "Type", "Amount"])
    for row in summary.contributions:
        table.add_row(row.account_name, row.account_type, money(row.amount))
    console.print(table)
    if summary.history:
        latest = summary.history[-1]
        console.print(f"Latest snapshot: {latest.as_of} at {money(latest.total)}")


@app.command("savings-rate")
def savings_rate_command(
    months: int = typer.Option(3, "--months", min=1, help="Lookback window."),
) -> None:
    """Show income, spending, and savings rate."""
    result = FinanceService(_session_factory()).savings_rate(months=months)
    table = simple_table(f"Savings rate over {months} month(s)", ["Metric", "Value"])
    table.add_row(f"Income ({result.income_source})", money(result.income))
    table.add_row("Spend", money(result.spend))
    table.add_row("Savings", money(result.savings))
    table.add_row("Rate", pct(result.rate))
    console.print(table)


@app.command("profile")
def profile_command(
    birth_year: int | None = typer.Option(None, "--birth-year"),
    annual_net_income: str | None = typer.Option(None, "--annual-net-income"),
    annual_gross_income: str | None = typer.Option(None, "--annual-gross-income"),
    emergency_fund_months: int | None = typer.Option(None, "--emergency-fund-months"),
    risk_tolerance: RiskTolerance | None = typer.Option(None, "--risk-tolerance"),
) -> None:
    """Show or update local planning profile values."""
    service = ProfileService(_session_factory())
    if any(
        value is not None
        for value in (
            birth_year,
            annual_net_income,
            annual_gross_income,
            emergency_fund_months,
            risk_tolerance,
        )
    ):
        profile = service.update(
            birth_year=birth_year,
            annual_net_income=_decimal_option(annual_net_income, "annual net income"),
            annual_gross_income=_decimal_option(
                annual_gross_income, "annual gross income"
            ),
            emergency_fund_months=emergency_fund_months,
            risk_tolerance=risk_tolerance,
        )
    else:
        profile = service.get()
    table = simple_table("Profile", ["Field", "Value"])
    table.add_row("Birth year", str(profile.birth_year or "-"))
    table.add_row("Annual gross income", money(profile.annual_gross_income))
    table.add_row("Annual net income", money(profile.annual_net_income))
    table.add_row("Emergency fund months", str(profile.emergency_fund_months))
    table.add_row("Risk tolerance", str(profile.risk_tolerance))
    console.print(table)


def _decimal_option(value: str | None, label: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except Exception as exc:
        raise typer.BadParameter(f"{label} must be a decimal number") from exc


if __name__ == "__main__":
    app()
