"""Add project token policy for inherited request optimization."""

from alembic import op
from sqlalchemy import Column, JSON, inspect

revision = "0005_quality_loop"
down_revision = "0004_competitive_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "projects" not in inspect(bind).get_table_names():
        return
    columns = {item["name"] for item in inspect(bind).get_columns("projects")}
    if "token_policy_json" not in columns:
        op.add_column("projects", Column("token_policy_json", JSON(), nullable=True, server_default="{}"))


def downgrade() -> None:
    bind = op.get_bind()
    if "projects" not in inspect(bind).get_table_names():
        return
    columns = {item["name"] for item in inspect(bind).get_columns("projects")}
    if "token_policy_json" in columns:
        op.drop_column("projects", "token_policy_json")
