"""Read-only agent tools backed by FinanceService."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from perfin.core.finance_service import FinanceService
from perfin.storage.base import TransactionQuery


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_user_profile",
        "description": "Return the local planning profile.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_accounts",
        "description": "List linked accounts with balances and net-worth contribution.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "query_transactions",
        "description": "Query local transactions. Plaid amount convention: positive is outflow, negative is inflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "category": {"type": "string"},
                "account_id": {"type": "string"},
                "merchant_contains": {"type": "string"},
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
                "include_pending": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_spending_summary",
        "description": "Summarize spending over recent months, grouped by category or merchant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {"type": "integer", "minimum": 1, "maximum": 60},
                "group_by": {"type": "string", "enum": ["category", "merchant"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_networth_history",
        "description": "Return current net worth, account contributions, and snapshot history.",
        "input_schema": {
            "type": "object",
            "properties": {"months": {"type": "integer", "minimum": 1, "maximum": 240}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_savings_rate",
        "description": "Return income, spending, savings, and savings rate.",
        "input_schema": {
            "type": "object",
            "properties": {"months": {"type": "integer", "minimum": 1, "maximum": 60}},
            "additionalProperties": False,
        },
    },
    {
        "name": "check_affordability",
        "description": "Check whether a purchase fits liquidity and cash flow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "months": {"type": "integer", "minimum": 1, "maximum": 60},
                "by_date": {"type": "string", "description": "Optional YYYY-MM-DD"},
            },
            "required": ["amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_retirement_projection",
        "description": "Run deterministic compound-growth retirement projection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {"type": "integer", "minimum": 1, "maximum": 60},
                "annual_contribution": {"type": "number"},
                "retirement_age": {"type": "integer", "minimum": 18, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_current_date",
        "description": "Return today's local date.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


class ToolDispatcher:
    def __init__(self, finance: FinanceService) -> None:
        self._finance = finance

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_user_profile":
            return _jsonable(self._finance.get_profile())
        if name == "list_accounts":
            accounts = self._finance.list_accounts()
            return {"accounts": _jsonable(accounts)}
        if name == "query_transactions":
            query = TransactionQuery(
                start_date=_date(args.get("start_date")),
                end_date=_date(args.get("end_date")),
                category=args.get("category"),
                account_id=args.get("account_id"),
                merchant_contains=args.get("merchant_contains"),
                min_amount=args.get("min_amount"),
                max_amount=args.get("max_amount"),
                include_pending=args.get("include_pending", True),
                limit=args.get("limit"),
            )
            return {"transactions": _jsonable(self._finance.query_transactions(query))}
        if name == "get_spending_summary":
            summary = self._finance.spending_summary(
                months=args.get("months", 1),
                group_by=args.get("group_by", "category"),
            )
            return _jsonable(summary)
        if name == "get_networth_history":
            return _jsonable(self._finance.networth_summary(months=args.get("months", 12)))
        if name == "get_savings_rate":
            return _jsonable(self._finance.savings_rate(months=args.get("months", 3)))
        if name == "check_affordability":
            return _jsonable(
                self._finance.affordability(
                    amount=Decimal(str(args["amount"])),
                    months=args.get("months", 3),
                    by_date=_date(args.get("by_date")),
                )
            )
        if name == "run_retirement_projection":
            contribution = args.get("annual_contribution")
            return _jsonable(
                self._finance.retirement_projection(
                    months=args.get("months", 12),
                    annual_contribution=(
                        None if contribution is None else Decimal(str(contribution))
                    ),
                    retirement_age=args.get("retirement_age"),
                )
            )
        if name == "get_current_date":
            return {"date": dt.date.today().isoformat()}
        raise ValueError(f"Unknown tool: {name}")


def tool_result_json(result: dict[str, Any]) -> str:
    return json.dumps(result, sort_keys=True)


def _date(value: str | None) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {
            field: _jsonable(getattr(value, field))
            for field in value.__dataclass_fields__
        }
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value
