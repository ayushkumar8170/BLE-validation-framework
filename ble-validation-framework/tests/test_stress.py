"""
Stress/endurance validation: connection interval stability, pairing
latency, and MTU throughput over repeated connect/disconnect cycles.

Iteration count defaults to a small number suitable for CI
(BLE_STRESS_ITERATIONS, default 100 -> capped at 20 here for test speed);
use scripts/run_stress_test.py directly for multi-hour endurance runs.
"""
from __future__ import annotations

import pytest

from ble_framework.ble_client import build_client
from ble_framework.stress_test import StressTestRunner


@pytest.mark.asyncio
@pytest.mark.stress
async def test_connection_stability_stress(ble_config, report_data):
    iterations = min(ble_config.stress_iterations, 20)
    client = build_client(ble_config.use_mock)
    address = ble_config.target_address or "AA:BB:CC:DD:EE:FF"

    runner = StressTestRunner(
        client=client,
        address=address,
        connect_timeout_s=ble_config.connect_timeout_s,
        connect_retries=ble_config.connect_retries,
    )
    result = await runner.run(iterations=iterations)
    report_data.stress_result = result

    assert result.success_rate_pct >= 95.0, (
        f"Connection success rate {result.success_rate_pct:.1f}% below 95% threshold "
        f"({result.connect_failures} failures out of {result.iterations_requested})"
    )


@pytest.mark.asyncio
@pytest.mark.stress
async def test_pairing_latency_within_bound(ble_config, report_data):
    if report_data.stress_result is None:
        pytest.skip("Run test_connection_stability_stress first to populate latency data")
    stats = report_data.stress_result.pairing_latency_stats
    if stats["count"] == 0:
        pytest.skip("No pairing latency samples recorded")
    assert stats["max"] <= ble_config.max_pairing_latency_s, (
        f"Max observed pairing latency {stats['max']:.3f}s exceeds bound "
        f"{ble_config.max_pairing_latency_s}s"
    )


@pytest.mark.asyncio
@pytest.mark.stress
async def test_connection_interval_stability(ble_config, report_data):
    if report_data.stress_result is None:
        pytest.skip("Run test_connection_stability_stress first to populate interval data")
    stats = report_data.stress_result.connection_interval_stats
    if stats["count"] == 0:
        pytest.skip("Connection interval telemetry unavailable on this platform/client")
    mean = stats["mean"]
    tolerance = mean * (ble_config.connection_interval_tolerance_pct / 100.0)
    assert stats["max"] - stats["min"] <= 2 * tolerance, (
        f"Connection interval spread ({stats['min']:.2f}-{stats['max']:.2f}ms) exceeds "
        f"{ble_config.connection_interval_tolerance_pct}% tolerance around mean {mean:.2f}ms"
    )
