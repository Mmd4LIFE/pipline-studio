"""initial studio schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "connection_refs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("airflow_conn_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("allowed_schemas", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("slug", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dag_id", sa.String(length=200), nullable=False, unique=True),
        sa.Column("owner_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("desired_enabled", sa.Boolean(), nullable=False),
        sa.Column("current_revision_id", sa.String(length=32), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_revisions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "revision_no", name="uq_job_revision_no"),
    )
    op.create_foreign_key(
        "fk_jobs_current_revision",
        "jobs",
        "job_revisions",
        ["current_revision_id"],
        ["id"],
    )
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("revision_id", sa.String(length=32), sa.ForeignKey("job_revisions.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("airflow_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_immediately", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("trigger_run_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("airflow_run_id", sa.String(length=200), nullable=False),
        sa.Column("revision_id", sa.String(length=32), sa.ForeignKey("job_revisions.id"), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_read", sa.BigInteger(), nullable=True),
        sa.Column("rows_written", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("source_query_duration_ms", sa.Integer(), nullable=True),
        sa.Column("load_duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "airflow_run_id", name="uq_job_airflow_run"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("actor_id", sa.String(length=32), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before_json", postgresql.JSONB(), nullable=True),
        sa.Column("after_json", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("audit_events")
    op.drop_table("job_runs")
    op.drop_table("deployments")
    op.drop_constraint("fk_jobs_current_revision", "jobs", type_="foreignkey")
    op.drop_table("job_revisions")
    op.drop_table("jobs")
    op.drop_table("connection_refs")
    op.drop_table("users")
