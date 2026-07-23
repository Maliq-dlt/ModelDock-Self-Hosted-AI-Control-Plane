"""Add routing, provider resilience, evaluation queue, and session fields."""

from alembic import op
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, inspect

revision = "0003_upgrade_v02"
down_revision = "0002_governance"
branch_labels = None
depends_on = None

def _add_column_if_missing(bind, table: str, column: Column) -> None:
    if column.name not in {item["name"] for item in inspect(bind).get_columns(table)}:
        op.add_column(table, column)

def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "providers" in tables:
        _add_column_if_missing(bind, "providers", Column("concurrency_limit", Integer(), nullable=True, server_default="8"))
        _add_column_if_missing(bind, "providers", Column("consecutive_failures", Integer(), nullable=True, server_default="0"))
        _add_column_if_missing(bind, "providers", Column("circuit_open_until", DateTime(timezone=True), nullable=True))
        _add_column_if_missing(bind, "providers", Column("reliability_score", Float(), nullable=True, server_default="1.0"))
    if "models" in tables:
        _add_column_if_missing(bind, "models", Column("quality_score", Float(), nullable=True, server_default="0.5"))
    if "admin_users" in tables:
        _add_column_if_missing(bind, "admin_users", Column("session_version", Integer(), nullable=True, server_default="0"))
    if "evaluations" in tables:
        _add_column_if_missing(bind, "evaluations", Column("status", String(20), nullable=True, server_default="completed"))
        _add_column_if_missing(bind, "evaluations", Column("payload_json", JSON(), nullable=True))
        _add_column_if_missing(bind, "evaluations", Column("started_at", DateTime(timezone=True), nullable=True))
        _add_column_if_missing(bind, "evaluations", Column("completed_at", DateTime(timezone=True), nullable=True))
        _add_column_if_missing(bind, "evaluations", Column("error_message", Text(), nullable=True))

def downgrade() -> None:
    bind = op.get_bind()
    columns_by_table = {
        "providers": ("reliability_score", "circuit_open_until", "consecutive_failures", "concurrency_limit"),
        "models": ("quality_score",),
        "admin_users": ("session_version",),
        "evaluations": ("error_message", "completed_at", "started_at", "payload_json", "status"),
    }
    for table, columns in columns_by_table.items():
        if table not in inspect(bind).get_table_names():
            continue
        existing = {item["name"] for item in inspect(bind).get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)