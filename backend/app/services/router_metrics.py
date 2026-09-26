from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import get_engine
from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.registry import RouterDefinition
from app.models.router import Router
from app.models.router_hourly_metric import RouterHourlyMetric

logger = logging.getLogger(__name__)
_COLLECTOR_LOCK_ID = 847_221_609


@dataclass(slots=True)
class RouterMetricSample:
    active_devices: int
    cpu_usage: float
    memory_usage: float
    memory_free_bytes: int
    memory_total_bytes: int
    download_bps: int
    upload_bps: int
    download_counter: int
    upload_counter: int
    uptime_seconds: int
    interface_running: bool
    interface_name: str
    temperature: float | None
    voltage: float | None


def _hour_start(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _definition(router: Router) -> RouterDefinition:
    return RouterDefinition(
        router_id=router.id,
        name=router.name,
        host=router.vpn_host,
        port=router.api_port,
        hotspot_network=router.hotspot_network or "",
    )


def read_router_sample(router: Router, settings: Settings) -> RouterMetricSample:
    with mikrotik_client_context(_definition(router)) as client:
        resource = client.get_system_resource()
        traffic = client.get_interface_traffic(settings.router_metrics_interface)
        sessions = client.get_hotspot_active_sessions()
    return RouterMetricSample(
        active_devices=len(sessions),
        cpu_usage=float(resource["cpu_usage"] or 0),
        memory_usage=float(resource["memory_usage_percent"] or 0),
        memory_free_bytes=int(resource["memory_free_bytes"] or 0),
        memory_total_bytes=int(resource["memory_total_bytes"] or 0),
        download_bps=int(traffic["download_bps"]),
        upload_bps=int(traffic["upload_bps"]),
        download_counter=int(traffic["download_bytes"]),
        upload_counter=int(traffic["upload_bytes"]),
        uptime_seconds=int(resource["uptime_seconds"] or 0),
        interface_running=bool(traffic["running"]) and not bool(traffic["disabled"]),
        interface_name=str(traffic["name"]),
        temperature=(float(resource["temperature"]) if resource["temperature"] is not None else None),
        voltage=(float(resource["voltage"]) if resource["voltage"] is not None else None),
    )


def _average(previous: float, count: int, value: float) -> float:
    return (previous * count + value) / (count + 1)


def _optional_average(previous: float | None, count: int, value: float | None) -> float | None:
    if value is None:
        return previous
    return value if previous is None else _average(previous, count, value)


def _counter_delta(current: int, previous: int | None) -> int:
    return current - previous if previous is not None and current >= previous else 0


def _latest_metric(session: Session, router_id: str) -> RouterHourlyMetric | None:
    return session.scalar(
        select(RouterHourlyMetric)
        .where(RouterHourlyMetric.router_id == router_id)
        .order_by(RouterHourlyMetric.hour.desc())
        .limit(1)
    )


def store_sample(
    session: Session,
    router: Router,
    sample: RouterMetricSample | None,
    sampled_at: datetime,
) -> RouterHourlyMetric:
    """Incrementally fold one reading into its router/hour summary."""
    hour = _hour_start(sampled_at)
    metric = session.get(RouterHourlyMetric, (router.id, hour))
    previous = metric or _latest_metric(session, router.id)
    previous_download = previous.last_download_counter if previous else None
    previous_upload = previous.last_upload_counter if previous else None

    if metric is None:
        metric = RouterHourlyMetric(
            router_id=router.id,
            hour=hour,
            sample_count=1,
            failed_samples=1 if sample is None else 0,
            interface_running_samples=int(bool(sample and sample.interface_running)),
            active_devices_avg=float(sample.active_devices if sample else 0),
            active_devices_peak=sample.active_devices if sample else 0,
            cpu_usage_avg=sample.cpu_usage if sample else 0,
            cpu_usage_peak=sample.cpu_usage if sample else 0,
            memory_usage_avg=sample.memory_usage if sample else 0,
            memory_usage_peak=sample.memory_usage if sample else 0,
            memory_free_bytes_avg=float(sample.memory_free_bytes if sample else 0),
            memory_total_bytes=sample.memory_total_bytes if sample else 0,
            download_bps_avg=float(sample.download_bps if sample else 0),
            download_bps_peak=sample.download_bps if sample else 0,
            upload_bps_avg=float(sample.upload_bps if sample else 0),
            upload_bps_peak=sample.upload_bps if sample else 0,
            download_bytes=_counter_delta(sample.download_counter, previous_download) if sample else 0,
            upload_bytes=_counter_delta(sample.upload_counter, previous_upload) if sample else 0,
            last_download_counter=sample.download_counter if sample else previous_download,
            last_upload_counter=sample.upload_counter if sample else previous_upload,
            uptime_seconds=sample.uptime_seconds if sample else 0,
            restart_count=int(
                bool(sample and previous and sample.uptime_seconds < previous.uptime_seconds)
            ),
            temperature_avg=sample.temperature if sample else None,
            voltage_avg=sample.voltage if sample else None,
            interface_name=sample.interface_name if sample else "ether1",
            last_sample_at=sampled_at,
        )
        session.add(metric)
        return metric

    metric.sample_count += 1
    metric.last_sample_at = sampled_at
    if sample is None:
        metric.failed_samples += 1
        return metric

    successful_count = metric.sample_count - metric.failed_samples - 1
    metric.interface_running_samples += int(sample.interface_running)
    metric.active_devices_avg = _average(metric.active_devices_avg, successful_count, sample.active_devices)
    metric.active_devices_peak = max(metric.active_devices_peak, sample.active_devices)
    metric.cpu_usage_avg = _average(metric.cpu_usage_avg, successful_count, sample.cpu_usage)
    metric.cpu_usage_peak = max(metric.cpu_usage_peak, sample.cpu_usage)
    metric.memory_usage_avg = _average(metric.memory_usage_avg, successful_count, sample.memory_usage)
    metric.memory_usage_peak = max(metric.memory_usage_peak, sample.memory_usage)
    metric.memory_free_bytes_avg = _average(metric.memory_free_bytes_avg, successful_count, sample.memory_free_bytes)
    metric.memory_total_bytes = sample.memory_total_bytes
    metric.download_bps_avg = _average(metric.download_bps_avg, successful_count, sample.download_bps)
    metric.download_bps_peak = max(metric.download_bps_peak, sample.download_bps)
    metric.upload_bps_avg = _average(metric.upload_bps_avg, successful_count, sample.upload_bps)
    metric.upload_bps_peak = max(metric.upload_bps_peak, sample.upload_bps)
    metric.download_bytes += _counter_delta(sample.download_counter, metric.last_download_counter)
    metric.upload_bytes += _counter_delta(sample.upload_counter, metric.last_upload_counter)
    metric.last_download_counter = sample.download_counter
    metric.last_upload_counter = sample.upload_counter
    if sample.uptime_seconds < metric.uptime_seconds:
        metric.restart_count += 1
    metric.uptime_seconds = sample.uptime_seconds
    metric.temperature_avg = _optional_average(metric.temperature_avg, successful_count, sample.temperature)
    metric.voltage_avg = _optional_average(metric.voltage_avg, successful_count, sample.voltage)
    metric.interface_name = sample.interface_name
    return metric


def collect_router_metrics(settings: Settings) -> int:
    """Sample due routers once; a transaction lock prevents duplicate web workers."""
    factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as session:
        if session.bind and session.bind.dialect.name == "postgresql":
            acquired = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _COLLECTOR_LOCK_ID}
            )
            if not acquired:
                return 0
        routers = list(
            session.scalars(
                select(Router).where(Router.is_active.is_(True)).order_by(Router.display_order)
            )
        )
        collected = 0
        due_before = now - timedelta(seconds=settings.router_metrics_sample_interval_seconds - 5)
        for router in routers:
            latest = _latest_metric(session, router.id)
            if latest is not None and latest.last_sample_at > due_before:
                continue
            try:
                sample = read_router_sample(router, settings)
            except Exception:  # noqa: BLE001 - one router must not stop the collector
                # RouterOS exceptions may contain command details; keep logs credential-safe.
                logger.warning("Router metric sample failed; router_id=%s", router.id)
                sample = None
            store_sample(session, router, sample, datetime.now(UTC))
            collected += 1
        session.commit()
        return collected
