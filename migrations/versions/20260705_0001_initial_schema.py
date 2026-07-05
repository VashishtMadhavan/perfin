"""Initial schema.

Revision ID: 20260705_0001
Revises:
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260705_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plaid_items",
        sa.Column("item_id", sa.String(length=128), primary_key=True),
        sa.Column("institution_id", sa.String(length=128), nullable=True),
        sa.Column("institution_name", sa.String(length=256), nullable=True),
        sa.Column("access_token_ref", sa.String(length=256), nullable=False),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sync_state",
        sa.Column("scope", sa.String(length=128), primary_key=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("annual_gross_income", sa.String(length=32), nullable=True),
        sa.Column("annual_net_income", sa.String(length=32), nullable=True),
        sa.Column("monthly_savings_target", sa.String(length=32), nullable=True),
        sa.Column("emergency_fund_months", sa.Integer(), nullable=False),
        sa.Column("risk_tolerance", sa.String(length=16), nullable=False),
        sa.Column("retirement_age_target", sa.Integer(), nullable=True),
        sa.Column("retirement_annual_spend", sa.String(length=32), nullable=True),
        sa.Column("expected_return_override", sa.Float(), nullable=True),
        sa.Column("extras", sa.JSON(), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(length=128), primary_key=True),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("official_name", sa.String(length=256), nullable=True),
        sa.Column("mask", sa.String(length=16), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("subtype", sa.String(length=32), nullable=True),
        sa.Column("current_balance", sa.String(length=32), nullable=True),
        sa.Column("available_balance", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["plaid_items.item_id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_accounts_item_id"), "accounts", ["item_id"])
    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("current_balance", sa.String(length=32), nullable=True),
        sa.Column("available_balance", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", "as_of", name="uq_snapshot_account_day"),
    )
    op.create_index(
        op.f("ix_balance_snapshots_account_id"),
        "balance_snapshots",
        ["account_id"],
    )
    op.create_index(
        op.f("ix_balance_snapshots_as_of"),
        "balance_snapshots",
        ["as_of"],
    )
    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.String(length=128), primary_key=True),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("authorized_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("merchant_name", sa.String(length=256), nullable=True),
        sa.Column("category_primary", sa.String(length=64), nullable=True),
        sa.Column("category_detailed", sa.String(length=128), nullable=True),
        sa.Column("user_category_override", sa.String(length=64), nullable=True),
        sa.Column("payment_channel", sa.String(length=32), nullable=True),
        sa.Column("pending", sa.Boolean(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_txn_account_date", "transactions", ["account_id", "date"])
    op.create_index("ix_txn_category_date", "transactions", ["category_primary", "date"])
    op.create_index("ix_txn_date", "transactions", ["date"])


def downgrade() -> None:
    op.drop_index("ix_txn_date", table_name="transactions")
    op.drop_index("ix_txn_category_date", table_name="transactions")
    op.drop_index("ix_txn_account_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_balance_snapshots_as_of"), table_name="balance_snapshots")
    op.drop_index(op.f("ix_balance_snapshots_account_id"), table_name="balance_snapshots")
    op.drop_table("balance_snapshots")
    op.drop_index(op.f("ix_accounts_item_id"), table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("user_profile")
    op.drop_table("sync_state")
    op.drop_table("plaid_items")
