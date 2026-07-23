"""Add governance, prompt, evaluation, audit, and admin tables."""

from alembic import op
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, inspect

revision = "0002_governance"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _add_column_if_missing(bind, table: str, column: Column) -> None:
    if column.name not in {item["name"] for item in inspect(bind).get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "api_keys" in tables:
        _add_column_if_missing(bind, "api_keys", Column("rate_limit_rpm", Integer(), nullable=True, server_default="60"))
        _add_column_if_missing(bind, "api_keys", Column("token_limit_monthly", Integer(), nullable=True))
        _add_column_if_missing(bind, "api_keys", Column("concurrent_limit", Integer(), nullable=True, server_default="4"))
        _add_column_if_missing(bind, "api_keys", Column("allowed_models_json", JSON(), nullable=True))
        _add_column_if_missing(bind, "api_keys", Column("allowed_ips_json", JSON(), nullable=True))
    if "providers" in tables:
        _add_column_if_missing(bind, "providers", Column("health_status", String(20), nullable=True, server_default="unknown"))
        _add_column_if_missing(bind, "providers", Column("last_health_checked_at", DateTime(timezone=True), nullable=True))
        _add_column_if_missing(bind, "providers", Column("last_health_latency_ms", Float(), nullable=True))
    if "requests" in tables:
        _add_column_if_missing(bind, "requests", Column("idempotency_key", String(255), nullable=True))
    if "routing_rules" not in tables:
        op.create_table("routing_rules", Column("id", String(36), primary_key=True), Column("project_id", String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), Column("name", String(120), nullable=False), Column("priority", Integer(), nullable=False, server_default="100"), Column("condition_json", JSON(), nullable=False), Column("action_json", JSON(), nullable=False), Column("enabled", Boolean(), nullable=False, server_default="true"), Column("created_at", DateTime(timezone=True), nullable=False), Column("updated_at", DateTime(timezone=True), nullable=False))
    if "prompt_templates" not in tables:
        op.create_table("prompt_templates", Column("id", String(36), primary_key=True), Column("project_id", String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), Column("name", String(120), nullable=False), Column("description", Text()), Column("active_version", Integer()), Column("created_at", DateTime(timezone=True), nullable=False), Column("updated_at", DateTime(timezone=True), nullable=False))
    if "prompt_versions" not in tables:
        op.create_table("prompt_versions", Column("id", String(36), primary_key=True), Column("prompt_template_id", String(36), ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False), Column("version", Integer(), nullable=False), Column("content", Text(), nullable=False), Column("variables_json", JSON(), nullable=False), Column("model_configuration_json", JSON(), nullable=False), Column("created_by", String(120)), Column("created_at", DateTime(timezone=True), nullable=False))
    if "evaluations" not in tables:
        op.create_table("evaluations", Column("id", String(36), primary_key=True), Column("request_id", String(36), ForeignKey("requests.id", ondelete="SET NULL")), Column("evaluation_type", String(50), nullable=False), Column("score", Float()), Column("result_json", JSON(), nullable=False), Column("created_at", DateTime(timezone=True), nullable=False))
    if "audit_logs" not in tables:
        op.create_table("audit_logs", Column("id", String(36), primary_key=True), Column("actor", String(160), nullable=False), Column("action", String(80), nullable=False), Column("resource_type", String(80), nullable=False), Column("resource_id", String(36)), Column("metadata_json", JSON(), nullable=False), Column("created_at", DateTime(timezone=True), nullable=False))
    if "admin_users" not in tables:
        op.create_table("admin_users", Column("id", String(36), primary_key=True), Column("email", String(255), nullable=False, unique=True), Column("password_hash", String(255), nullable=False), Column("role", String(30), nullable=False, server_default="viewer"), Column("active", Boolean(), nullable=False, server_default="true"), Column("created_at", DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("admin_users", "audit_logs", "evaluations", "prompt_versions", "prompt_templates", "routing_rules"):
        if table in inspect(bind).get_table_names():
            op.drop_table(table)
    if "providers" in inspect(bind).get_table_names():
        for column in ("last_health_latency_ms", "last_health_checked_at", "health_status"):
            if column in {item["name"] for item in inspect(bind).get_columns("providers")}:
                op.drop_column("providers", column)
    if "requests" in inspect(bind).get_table_names() and "idempotency_key" in {item["name"] for item in inspect(bind).get_columns("requests")}:
        op.drop_column("requests", "idempotency_key")
    if "api_keys" in inspect(bind).get_table_names():
        for column in ("allowed_ips_json", "allowed_models_json", "concurrent_limit", "token_limit_monthly", "rate_limit_rpm"):
            if column in {item["name"] for item in inspect(bind).get_columns("api_keys")}:
                op.drop_column("api_keys", column)
