from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.mikrotik.client import (
    MikroTikClient,
    MikroTikConfig,
    _parse_routeros_duration,
)
from app.models.router import Router
from app.models.router_hourly_metric import RouterHourlyMetric
from app.services.admin_dashboard import AdminDashboardService
from app.services.router_metrics import RouterMetricSample, store_sample


class MemorySession:
    def __init__(self, metric=None, rows=None):
        self.metric = metric
        self.rows = rows or []

    def get(self, _model, _key):
        return self.metric

    def scalar(self, _query):
        return None

    def scalars(self, _query):
        return self.rows

    def add(self, metric):
        self.metric = metric


def sample(**overrides) -> RouterMetricSample:
    values = {
        "active_devices": 10,
        "cpu_usage": 20,
        "memory_usage": 40,
        "memory_free_bytes": 600,
        "memory_total_bytes": 1000,
        "download_bps": 8_000_000,
        "upload_bps": 2_000_000,
        "download_counter": 10_000,
        "upload_counter": 2_000,
        "uptime_seconds": 100,
        "interface_running": True,
        "interface_name": "ether1",
        "temperature": 42.0,
        "voltage": 24.0,
    }
    values.update(overrides)
    return RouterMetricSample(**values)


def router() -> Router:
    return Router(
        id="hall", name="Hall", vpn_host="hall.example", api_port=8728,
        hotspot_network="192.168.88.0/24", is_active=True,
    )


def hourly_metric(router_id: str, devices: float, download_bps: float) -> RouterHourlyMetric:
    hour = datetime(2026, 9, 26, 23, tzinfo=UTC)
    return RouterHourlyMetric(
        router_id=router_id, hour=hour, sample_count=12, failed_samples=0,
        interface_running_samples=12, active_devices_avg=devices,
        active_devices_peak=int(devices + 2), cpu_usage_avg=20, cpu_usage_peak=30,
        memory_usage_avg=40, memory_usage_peak=45, memory_free_bytes_avg=600,
        memory_total_bytes=1000, download_bps_avg=download_bps,
        download_bps_peak=int(download_bps * 1.5), upload_bps_avg=500_000,
        upload_bps_peak=800_000, download_bytes=1_000_000, upload_bytes=100_000,
        uptime_seconds=1000, restart_count=0, temperature_avg=None, voltage_avg=None,
        interface_name="ether1", last_sample_at=hour + timedelta(minutes=55),
    )


def test_routeros_resource_normalization(monkeypatch) -> None:
    class Resource:
        def __init__(self, rows):
            self.rows = rows

        def get(self):
            return self.rows

    class Api:
        def get_resource(self, path):
            if path == "/system/resource":
                return Resource([{
                    "cpu-load": "37", "total-memory": "1000",
                    "free-memory": "250", "uptime": "1d02:03:04",
                }])
            assert path == "/system/health"
            return Resource([
                {"name": "temperature", "value": "46 C"},
                {"name": "voltage", "value": "24.2V"},
            ])

    client = MikroTikClient(MikroTikConfig(host="router", username="admin", password="secret"))
    monkeypatch.setattr(client, "connect", lambda: Api())

    result = client.get_system_resource()

    assert result["cpu_usage"] == 37
    assert result["memory_usage_percent"] == 75
    assert result["uptime_seconds"] == 93_784
    assert result["temperature"] == 46
    assert result["voltage"] == 24.2
    assert _parse_routeros_duration("2w3d4h5m6s") == 1_483_506


def test_store_sample_builds_hourly_averages_peaks_and_counter_deltas() -> None:
    session = MemorySession()
    sampled_at = datetime(2026, 9, 26, 10, 5, tzinfo=UTC)
    metric = store_sample(session, router(), sample(), sampled_at)
    assert metric.download_bytes == 0

    store_sample(
        session,
        router(),
        sample(
            active_devices=20,
            cpu_usage=60,
            memory_usage=50,
            download_bps=12_000_000,
            download_counter=14_000,
            upload_counter=3_000,
            uptime_seconds=50,
        ),
        sampled_at + timedelta(minutes=5),
    )

    assert metric.sample_count == 2
    assert metric.active_devices_avg == 15
    assert metric.active_devices_peak == 20
    assert metric.cpu_usage_avg == 40
    assert metric.cpu_usage_peak == 60
    assert metric.download_bps_avg == 10_000_000
    assert metric.download_bytes == 4_000
    assert metric.upload_bytes == 1_000
    assert metric.restart_count == 1


def test_failed_sample_is_counted_without_distorting_successful_average() -> None:
    session = MemorySession()
    sampled_at = datetime(2026, 9, 26, 10, 5, tzinfo=UTC)
    metric = store_sample(session, router(), None, sampled_at)
    store_sample(session, router(), sample(cpu_usage=35), sampled_at + timedelta(minutes=5))

    assert metric.sample_count == 2
    assert metric.failed_samples == 1
    assert metric.cpu_usage_avg == 35


def test_router_analytics_finds_peak_hours_and_health_summary() -> None:
    first = RouterHourlyMetric(
        router_id="hall", hour=datetime(2026, 9, 25, 18, tzinfo=UTC),
        sample_count=12, failed_samples=0, interface_running_samples=12,
        active_devices_avg=30, active_devices_peak=40, cpu_usage_avg=35,
        cpu_usage_peak=70, memory_usage_avg=50, memory_usage_peak=60,
        memory_free_bytes_avg=500, memory_total_bytes=1000,
        download_bps_avg=8_000_000, download_bps_peak=12_000_000,
        upload_bps_avg=2_000_000, upload_bps_peak=4_000_000,
        download_bytes=1_000_000, upload_bytes=250_000,
        uptime_seconds=1000, temperature_avg=44, voltage_avg=24,
        restart_count=0,
        interface_name="ether1", last_sample_at=datetime(2026, 9, 25, 18, 55, tzinfo=UTC),
    )
    second = RouterHourlyMetric(
        router_id="hall", hour=datetime(2026, 9, 26, 2, tzinfo=UTC),
        sample_count=10, failed_samples=2, interface_running_samples=7,
        active_devices_avg=5, active_devices_peak=8, cpu_usage_avg=10,
        cpu_usage_peak=20, memory_usage_avg=40, memory_usage_peak=45,
        memory_free_bytes_avg=600, memory_total_bytes=1000,
        download_bps_avg=1_000_000, download_bps_peak=2_000_000,
        upload_bps_avg=500_000, upload_bps_peak=1_000_000,
        download_bytes=100_000, upload_bytes=50_000,
        uptime_seconds=2000, temperature_avg=None, voltage_avg=None,
        restart_count=0,
        interface_name="ether1", last_sample_at=datetime(2026, 9, 26, 2, 55, tzinfo=UTC),
    )
    service = AdminDashboardService(MemorySession(rows=[first, second]))

    result = service._router_analytics(
        [router()],
        current_start=datetime(2026, 9, 25, tzinfo=UTC),
        current_end=datetime(2026, 9, 27, tzinfo=UTC),
    )

    assert result.available is True
    assert result.prediction_ready is False
    assert result.predicted_peak_hours == []
    assert result.hourly_profile[18].predicted_peak is False
    assert result.summary is not None
    assert result.summary.peak_devices == 40
    assert result.summary.successful_samples == 20
    assert result.summary.failed_samples == 2
    assert result.summary.collection_success_percent == pytest.approx(90.9)


def test_combined_router_analytics_sums_concurrent_devices_and_bandwidth() -> None:
    first_router = router()
    second_router = Router(
        id="annex", name="Annex", vpn_host="annex.example", api_port=8728,
        hotspot_network="192.168.89.0/24", is_active=True,
    )
    service = AdminDashboardService(MemorySession(rows=[
        hourly_metric("hall", 10, 2_000_000),
        hourly_metric("annex", 5, 1_000_000),
    ]))

    result = service._router_analytics(
        [first_router, second_router],
        current_start=datetime(2026, 9, 26, 22, tzinfo=UTC),
        current_end=datetime(2026, 9, 27, tzinfo=UTC),
    )

    assert result.summary is not None
    assert result.summary.average_devices == 15
    assert result.summary.peak_devices == 19
    assert result.summary.average_download_bps == 3_000_000
    assert result.hourly_profile[23].average_devices == 15
