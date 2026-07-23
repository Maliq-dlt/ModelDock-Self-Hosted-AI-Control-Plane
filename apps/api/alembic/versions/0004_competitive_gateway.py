"""Add provider account pools and request-attempt account tracing."""

from alembic import op
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, inspect

revision = "0004_competitive_gateway"
down_revision = "0003_upgrade_v02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "provider_accounts" not in tables:
        op.create_table(
            "provider_accounts",
            Column("id", String(36), primary_key=True),
            Column("provider_id", String(36), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
            Column("name", String(120), nullable=False),
            Column("encrypted_credentials", Text(), nullable=False),
            Column("priority", Integer(), nullable=False, server_default="100"),
            Column("enabled", Boolean(), nullable=False, server_default="true"),
            Column("quota_remaining", Integer()),
            Column("quota_reset_at", DateTime(timezone=True)),
            Column("last_used_at", DateTime(timezone=True)),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            UniqueConstraint("provider_id", "name", name="uq_provider_accounts_provider_name"),
        )
    attempt_columns = {item["name"] for item in inspect(bind).get_columns("request_attempts")}
    if "provider_account_id" not in attempt_columns:
        op.add_column(
            "request_attempts",
            Column("provider_account_id", String(36), ForeignKey("provider_accounts.id", ondelete="SET NULL")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "request_attempts" in tables:
        columns = {item["name"] for item in inspect(bind).get_columns("request_attempts")}
        if "provider_account_id" in columns:
            op.drop_column("request_attempts", "provider_account_id")
    if "provider_accounts" in tables:
        op.drop_table("provider_accounts")
