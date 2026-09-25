"""
Validates GATT service discovery: expected services/characteristics are
present with the correct properties (read/write/notify permissions).
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_service_discovery_returns_services(ble_client):
    services = await ble_client.discover_services()
    assert services, "GATT service discovery returned no services"


@pytest.mark.asyncio
async def test_all_services_have_characteristics(ble_client):
    services = await ble_client.discover_services()
    empty = [s.uuid for s in services if not s.characteristics]
    assert not empty, f"Service(s) with no discoverable characteristics: {empty}"


@pytest.mark.asyncio
async def test_expected_services_present(ble_client, ble_config):
    if not ble_config.expected_services:
        pytest.skip("No BLE_EXPECTED_SERVICES mapping configured for this target")
    services = await ble_client.discover_services()
    discovered = {s.uuid.lower(): {c.uuid.lower() for c in s.characteristics} for s in services}

    for expected_svc, expected_chars in ble_config.expected_services.items():
        svc_key = expected_svc.lower()
        assert svc_key in discovered, f"Expected service {expected_svc} not found"
        missing_chars = {c.lower() for c in expected_chars} - discovered[svc_key]
        assert not missing_chars, f"Service {expected_svc} missing characteristic(s): {missing_chars}"


@pytest.mark.asyncio
async def test_battery_service_characteristic_properties(ble_client):
    """Example concrete check: Battery Level characteristic should be readable."""
    services = await ble_client.discover_services()
    battery_chars = [
        c for s in services if s.uuid.lower() == "0000180f-0000-1000-8000-00805f9b34fb"
        for c in s.characteristics
    ]
    if not battery_chars:
        pytest.skip("Target does not expose the standard Battery Service")
    battery_level = next((c for c in battery_chars if c.uuid.lower() == "00002a19-0000-1000-8000-00805f9b34fb"), None)
    assert battery_level is not None, "Battery Level characteristic not found under Battery Service"
    assert "read" in battery_level.properties, "Battery Level characteristic is not readable"
