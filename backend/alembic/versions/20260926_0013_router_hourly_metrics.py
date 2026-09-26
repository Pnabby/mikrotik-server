"""add hourly router performance metrics

Revision ID: 20260926_0013
Revises: 20260913_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0013"
down_revision: str | Sequence[str] | None = "20260913_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "router_hourly_metrics",
        sa.Column("router_id", sa.String(length=64), nullable=False),
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("failed_samples", sa.Integer(), nullable=False),
        sa.Column("interface_running_samples", sa.Integer(), nullable=False),
        sa.Column("active_devices_avg", sa.Float(), nullable=False),
        sa.Column("active_devices_peak", sa.Integer(), nullable=False),
        sa.Column("cpu_usage_avg", sa.Float(), nullable=False),
        sa.Column("cpu_usage_peak", sa.Float(), nullable=False),
        sa.Column("memory_usage_avg", sa.Float(), nullable=False),
        sa.Column("memory_usage_peak", sa.Float(), nullable=False),
        sa.Column("memory_free_bytes_avg", sa.Float(), nullable=False),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("download_bps_avg", sa.Float(), nullable=False),
        sa.Column("download_bps_peak", sa.BigInteger(), nullable=False),
        sa.Column("upload_bps_avg", sa.Float(), nullable=False),
        sa.Column("upload_bps_peak", sa.BigInteger(), nullable=False),
        sa.Column("download_bytes", sa.BigInteger(), nullable=False),
        sa.Column("upload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("last_download_counter", sa.BigInteger(), nullable=True),
        sa.Column("last_upload_counter", sa.BigInteger(), nullable=True),
        sa.Column("uptime_seconds", sa.BigInteger(), nullable=False),
        sa.Column("restart_count", sa.Integer(), nullable=False),
        sa.Column("temperature_avg", sa.Float(), nullable=True),
        sa.Column("voltage_avg", sa.Float(), nullable=True),
        sa.Column("interface_name", sa.String(length=120), nullable=False),
        sa.Column("last_sample_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sample_count > 0", name=op.f("ck_router_hourly_metrics_router_metric_sample_count_positive")),
        sa.CheckConstraint("failed_samples >= 0", name=op.f("ck_router_hourly_metrics_router_metric_failed_samples_non_negative")),
        sa.CheckConstraint("restart_count >= 0", name=op.f("ck_router_hourly_metrics_router_metric_restart_count_non_negative")),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], name=op.f("fk_router_hourly_metrics_router_id_routers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("router_id", "hour", name=op.f("pk_router_hourly_metrics")),
    )
    op.create_index(
        op.f("ix_router_hourly_metrics_hour"),
        "router_hourly_metrics",
        ["hour"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_router_hourly_metrics_hour"), table_name="router_hourly_metrics")
    op.drop_table("router_hourly_metrics")
