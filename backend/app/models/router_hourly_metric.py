from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.router import Router


class RouterHourlyMetric(Base):
    """Incremental summary of the router samples collected during one UTC hour."""

    __tablename__ = "router_hourly_metrics"
    __table_args__ = (
        CheckConstraint("sample_count > 0", name="router_metric_sample_count_positive"),
        CheckConstraint("failed_samples >= 0", name="router_metric_failed_samples_non_negative"),
        CheckConstraint("restart_count >= 0", name="router_metric_restart_count_non_negative"),
    )

    router_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("routers.id", ondelete="CASCADE"), primary_key=True
    )
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=1)
    failed_samples: Mapped[int] = mapped_column(Integer, default=0)
    interface_running_samples: Mapped[int] = mapped_column(Integer, default=0)

    active_devices_avg: Mapped[float] = mapped_column(Float, default=0)
    active_devices_peak: Mapped[int] = mapped_column(Integer, default=0)
    cpu_usage_avg: Mapped[float] = mapped_column(Float, default=0)
    cpu_usage_peak: Mapped[float] = mapped_column(Float, default=0)
    memory_usage_avg: Mapped[float] = mapped_column(Float, default=0)
    memory_usage_peak: Mapped[float] = mapped_column(Float, default=0)
    memory_free_bytes_avg: Mapped[float] = mapped_column(Float, default=0)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    download_bps_avg: Mapped[float] = mapped_column(Float, default=0)
    download_bps_peak: Mapped[int] = mapped_column(BigInteger, default=0)
    upload_bps_avg: Mapped[float] = mapped_column(Float, default=0)
    upload_bps_peak: Mapped[int] = mapped_column(BigInteger, default=0)
    download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_download_counter: Mapped[int | None] = mapped_column(BigInteger)
    last_upload_counter: Mapped[int | None] = mapped_column(BigInteger)
    uptime_seconds: Mapped[int] = mapped_column(BigInteger, default=0)
    restart_count: Mapped[int] = mapped_column(Integer, default=0)
    temperature_avg: Mapped[float | None] = mapped_column(Float)
    voltage_avg: Mapped[float | None] = mapped_column(Float)
    interface_name: Mapped[str] = mapped_column(String(120), default="ether1")
    last_sample_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    router: Mapped[Router] = relationship(back_populates="hourly_metrics")
