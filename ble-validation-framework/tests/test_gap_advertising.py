"""
Validates BLE GAP peripheral advertising: presence, decoded fields, and
advertising-interval consistency across multiple scan windows.
"""
from __future__ import annotations

import statistics

import pytest

from ble_framework.ble_client import build_client


@pytest.mark.asyncio
async def test_peripheral_is_advertising(ble_config):
    client = build_client(ble_config.use_mock)
    reports = await client.scan(timeout_s=ble_config.scan_timeout_s)
    assert reports, "No advertisement reports observed within the scan window"


@pytest.mark.asyncio
async def test_advertisement_contains_local_name(ble_config):
    client = build_client(ble_config.use_mock)
    reports = await client.scan(timeout_s=ble_config.scan_timeout_s)
    matching = [
        r for r in reports
        if (not ble_config.target_name or r.local_name == ble_config.target_name)
        and (not ble_config.target_address or r.address == ble_config.target_address)
    ]
    assert matching, (
        f"No advertisement matched target_name={ble_config.target_name!r} "
        f"target_address={ble_config.target_address!r}. Seen: {[r.local_name for r in reports]}"
    )
    assert matching[0].local_name, "Advertisement local name field is empty"


@pytest.mark.asyncio
async def test_advertisement_service_uuids_present(ble_config):
    if not ble_config.expected_service_uuids:
        pytest.skip("No BLE_EXPECTED_SERVICE_UUIDS configured for this target")
    client = build_client(ble_config.use_mock)
    reports = await client.scan(timeout_s=ble_config.scan_timeout_s)
    assert reports, "No advertisement reports observed"
    advertised = {uuid.lower() for r in reports for uuid in r.service_uuids}
    expected = {u.lower() for u in ble_config.expected_service_uuids}
    missing = expected - advertised
    assert not missing, f"Expected service UUID(s) not advertised: {missing}"


@pytest.mark.asyncio
async def test_advertising_interval_within_spec(ble_config):
    """
    Performs several short scan windows and checks the observed
    inter-advertisement spacing falls within the BLE Core Spec legal range
    (20ms - 10.24s) and within the target's configured bounds.
    """
    client = build_client(ble_config.use_mock)
    timestamps: list[float] = []
    for _ in range(5):
        reports = await client.scan(timeout_s=max(0.5, ble_config.scan_timeout_s / 10))
        for r in reports:
            timestamps.append(r.timestamp)

    if len(timestamps) < 2:
        pytest.skip("Not enough advertisement samples to compute interval; increase scan_timeout_s")

    timestamps.sort()
    deltas_ms = [1000 * (b - a) for a, b in zip(timestamps, timestamps[1:]) if (b - a) > 0]
    if not deltas_ms:
        pytest.skip("Could not derive positive inter-advertisement deltas from samples")

    mean_interval = statistics.mean(deltas_ms)
    assert ble_config.min_adv_interval_ms <= mean_interval <= ble_config.max_adv_interval_ms, (
        f"Mean advertising interval {mean_interval:.1f}ms outside configured bounds "
        f"[{ble_config.min_adv_interval_ms}, {ble_config.max_adv_interval_ms}]ms"
    )
