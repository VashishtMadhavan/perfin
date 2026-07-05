"""Rich rendering helpers for CLI commands."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.table import Table

console = Console()


def money(value: Decimal | None) -> str:
    if value is None:
        return "-"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def pct(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value * Decimal(100):.1f}%"


def simple_table(title: str, columns: list[str]) -> Table:
    table = Table(title=title, show_lines=False)
    for column in columns:
        table.add_column(column)
    return table
