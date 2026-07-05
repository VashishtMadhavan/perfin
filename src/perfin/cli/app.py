"""Typer root application.

The root ``@app.callback`` is the single hook that runs before every subcommand:
it builds the dependency container and (once Phase 3 lands) runs the auto-sync
staleness gate. Command modules register their own sub-apps / commands here.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import typer

from perfin.agent.client import AnthropicAgentClient
from perfin.agent.loop import run_agent_loop
from perfin.agent.tools import ToolDispatcher
from perfin import __version__
from perfin.cli.render import console, money, pct, simple_table
from perfin.config import ASK_CONSENT_PATH, get_settings
from perfin.core.finance_service import FinanceService
from perfin.core.models import RiskTolerance
from perfin.core.profile_service import ProfileService
from perfin.core.sync_service import SyncService
from perfin.datasources.fake_source import FakeDataSource
from perfin.datasources.csv_source import CsvSource
from perfin.datasources.plaid_source import PlaidSource
from perfin.secrets import DefaultSecretStore
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


def _source(source_name: str):
    settings = get_settings()
    name = settings.sync.default_source if source_name == "auto" else source_name
    if name == "fake":
        return FakeDataSource()
    if name == "plaid":
        return PlaidSource(settings, DefaultSecretStore())
    raise typer.BadParameter("source must be 'auto', 'fake', or 'plaid'.")


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
    ctx.ensure_object(dict)
    ctx.obj["no_sync"] = no_sync
    read_commands = {"spend", "networth", "savings-rate", "afford", "retire", "ask"}
    if no_sync or ctx.invoked_subcommand not in read_commands:
        return
    settings = get_settings()
    try:
        SyncService(_session_factory()).ensure_fresh(
            _source("auto"),
            staleness=dt.timedelta(hours=settings.sync.staleness_hours),
        )
    except Exception as exc:
        console.print(f"[yellow]Auto-sync skipped:[/yellow] {exc}")


@app.command("link")
def link_command(
    source: str = typer.Option(
        "plaid", "--source", help="Data source to link. Use 'plaid' or 'fake'."
    ),
    public_token: str | None = typer.Option(
        None,
        "--public-token",
        help="Exchange a public token from Hosted Link.",
    ),
    sync_after: bool = typer.Option(True, "--sync/--no-sync", help="Run initial sync."),
) -> None:
    """Link an institution or demo data source."""
    data_source = _source(source)
    service = SyncService(_session_factory())
    if public_token is not None:
        if not isinstance(data_source, PlaidSource):
            raise typer.BadParameter("--public-token is only valid for Plaid.")
        result = data_source.exchange_public_token(public_token)
        service.save_link_result(result)
        if sync_after:
            report = service.sync_item(data_source, result.item.item_id)
            console.print(
                f"Linked and synced {report.item_id}: {report.accounts} accounts, "
                f"{report.added} added."
            )
        else:
            console.print(f"Linked {result.item.item_id}.")
        return
    if isinstance(data_source, PlaidSource) and get_settings().plaid.env != "sandbox":
        url = data_source.create_hosted_link_url()
        console.print("Open this Hosted Link URL, then rerun with --public-token:")
        console.print(url)
        return
    if sync_after:
        report = service.sync(data_source)
        console.print(
            f"Linked and synced {report.item_id}: {report.accounts} accounts, "
            f"{report.added} added."
        )
    else:
        item_id = service.link(data_source)
        console.print(f"Linked {item_id}.")


@app.command("sync")
def sync_command(
    source: str = typer.Option(
        "auto", "--source", help="Data source to sync: auto, fake, or plaid."
    ),
    full: bool = typer.Option(False, "--full", help="Reset the source cursor first."),
) -> None:
    """Sync accounts and transactions."""
    report = SyncService(_session_factory()).sync(_source(source), full=full)
    console.print(
        f"Synced {report.item_id}: {report.accounts} accounts, "
        f"{report.added} added, {report.modified} modified, "
        f"{report.removed} removed across {report.batches} batch(es)."
    )


@app.command("import-csv")
def import_csv_command(
    path: Path = typer.Argument(..., help="CSV with date, amount, and name columns."),
    account_name: str = typer.Option("CSV Import", "--account-name"),
    current_balance: str | None = typer.Option(None, "--current-balance"),
    invert_amounts: bool = typer.Option(
        False,
        "--invert-amounts",
        help="Flip signs for CSVs where spending is negative.",
    ),
    full: bool = typer.Option(False, "--full", help="Re-import even if cursor is done."),
) -> None:
    """Import transactions from a local CSV file."""
    source = CsvSource(
        path,
        account_name=account_name,
        current_balance=_decimal_option(current_balance, "current balance"),
        invert_amounts=invert_amounts,
    )
    report = SyncService(_session_factory()).sync(source, full=full)
    console.print(
        f"Imported {report.added} transaction(s) from {path} "
        f"into {report.item_id}."
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


@app.command("afford")
def afford_command(
    amount: str = typer.Argument(..., help="Purchase amount, e.g. 3000."),
    by_date: str | None = typer.Option(None, "--by-date", help="YYYY-MM-DD."),
    months: int = typer.Option(3, "--months", min=1, help="Cash-flow lookback."),
) -> None:
    """Check whether a purchase fits current liquidity and cash flow."""
    result = FinanceService(_session_factory()).affordability(
        amount=_decimal_option(amount, "amount") or Decimal("0"),
        months=months,
        by_date=_date_option(by_date, "by date"),
    )
    verdict = "Yes" if result.affordable_now else "Not from cash over buffer"
    if result.affordable_by_date is not None:
        verdict = "Yes" if result.affordable_by_date else "Not by that date"
    console.print(f"[bold]{verdict}[/bold]")
    table = simple_table("Affordability", ["Metric", "Value"])
    table.add_row("Amount", money(result.amount))
    table.add_row("Liquid balance", money(result.liquid_balance))
    table.add_row("Emergency buffer", money(result.emergency_buffer))
    table.add_row("Available after buffer", money(result.available_after_buffer))
    table.add_row("Monthly slack", money(result.monthly_slack))
    if result.monthly_required is not None:
        table.add_row("Monthly required", money(result.monthly_required))
        table.add_row("Months until date", str(result.months_until_date))
    console.print(table)


@app.command("retire")
def retire_command(
    retirement_age: int | None = typer.Option(None, "--age", help="Target age."),
    annual_contribution: str | None = typer.Option(
        None, "--annual-contribution", help="Override annual savings contribution."
    ),
    months: int = typer.Option(12, "--months", min=1, help="Savings lookback."),
) -> None:
    """Run a deterministic compound-growth retirement projection."""
    projection = FinanceService(_session_factory()).retirement_projection(
        months=months,
        annual_contribution=_decimal_option(
            annual_contribution, "annual contribution"
        ),
        retirement_age=retirement_age,
    )
    console.print(
        f"Projected balance at {projection.retirement_age}: "
        f"[bold]{money(projection.projected_balance)}[/bold]"
    )
    table = simple_table("Retirement projection", ["Metric", "Value"])
    table.add_row("Current age", str(projection.current_age or "-"))
    table.add_row("Years", str(projection.years))
    table.add_row("Starting balance", money(projection.starting_balance))
    table.add_row("Annual contribution", money(projection.annual_contribution))
    table.add_row("Expected return", f"{projection.expected_return * 100:.1f}%")
    table.add_row("4% rule spend", money(projection.safe_annual_spend))
    if projection.target_annual_spend is not None:
        table.add_row("Target spend", money(projection.target_annual_spend))
        table.add_row("Surplus", money(projection.surplus))
    console.print(table)


@app.command("ask")
def ask_command(
    question: str = typer.Argument(..., help="Question to answer from local data."),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Accept the one-time Anthropic tool-result privacy notice.",
    ),
) -> None:
    """Ask an LLM-backed personal-finance question."""
    settings = get_settings()
    _ensure_ask_consent(yes=yes)
    finance = FinanceService(_session_factory())
    answer = run_agent_loop(
        question,
        client=AnthropicAgentClient(settings.llm),
        dispatcher=ToolDispatcher(finance),
        max_iterations=settings.llm.max_iterations,
    )
    if answer.refused:
        console.print("[yellow]The model refused to answer.[/yellow]")
    console.print(answer.text)


@app.command("profile")
def profile_command(
    birth_year: int | None = typer.Option(None, "--birth-year"),
    annual_net_income: str | None = typer.Option(None, "--annual-net-income"),
    annual_gross_income: str | None = typer.Option(None, "--annual-gross-income"),
    monthly_savings_target: str | None = typer.Option(None, "--monthly-savings-target"),
    emergency_fund_months: int | None = typer.Option(None, "--emergency-fund-months"),
    risk_tolerance: RiskTolerance | None = typer.Option(None, "--risk-tolerance"),
    retirement_age_target: int | None = typer.Option(None, "--retirement-age-target"),
    retirement_annual_spend: str | None = typer.Option(None, "--retirement-annual-spend"),
    expected_return_override: float | None = typer.Option(None, "--expected-return"),
) -> None:
    """Show or update local planning profile values."""
    service = ProfileService(_session_factory())
    if any(
        value is not None
        for value in (
            birth_year,
            annual_net_income,
            annual_gross_income,
            monthly_savings_target,
            emergency_fund_months,
            risk_tolerance,
            retirement_age_target,
            retirement_annual_spend,
            expected_return_override,
        )
    ):
        profile = service.update(
            birth_year=birth_year,
            annual_net_income=_decimal_option(annual_net_income, "annual net income"),
            annual_gross_income=_decimal_option(
                annual_gross_income, "annual gross income"
            ),
            monthly_savings_target=_decimal_option(
                monthly_savings_target, "monthly savings target"
            ),
            emergency_fund_months=emergency_fund_months,
            risk_tolerance=risk_tolerance,
            retirement_age_target=retirement_age_target,
            retirement_annual_spend=_decimal_option(
                retirement_annual_spend, "retirement annual spend"
            ),
            expected_return_override=expected_return_override,
        )
    else:
        profile = service.get()
    table = simple_table("Profile", ["Field", "Value"])
    table.add_row("Birth year", str(profile.birth_year or "-"))
    table.add_row("Annual gross income", money(profile.annual_gross_income))
    table.add_row("Annual net income", money(profile.annual_net_income))
    table.add_row("Monthly savings target", money(profile.monthly_savings_target))
    table.add_row("Emergency fund months", str(profile.emergency_fund_months))
    table.add_row("Risk tolerance", str(profile.risk_tolerance))
    table.add_row("Retirement age target", str(profile.retirement_age_target or "-"))
    table.add_row("Retirement annual spend", money(profile.retirement_annual_spend))
    expected = (
        "-"
        if profile.expected_return_override is None
        else f"{profile.expected_return_override * 100:.1f}%"
    )
    table.add_row("Expected return override", expected)
    console.print(table)


def _decimal_option(value: str | None, label: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except Exception as exc:
        raise typer.BadParameter(f"{label} must be a decimal number") from exc


def _date_option(value: str | None, label: str) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{label} must use YYYY-MM-DD") from exc


def _ensure_ask_consent(*, yes: bool) -> None:
    if ASK_CONSENT_PATH.is_file():
        return
    notice = (
        "perfin ask sends selected local finance tool results to the Anthropic API "
        "so the model can answer your question."
    )
    if not yes and not typer.confirm(notice + " Continue?"):
        raise typer.Abort()
    ASK_CONSENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ASK_CONSENT_PATH.open("w", encoding="utf-8") as fh:
        json.dump({"accepted": True, "accepted_at": dt.datetime.now(dt.UTC).isoformat()}, fh)


if __name__ == "__main__":
    app()
