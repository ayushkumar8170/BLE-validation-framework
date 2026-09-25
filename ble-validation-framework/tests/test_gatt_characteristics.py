"""
Validates GATT characteristic read and write operations, including
round-trip data integrity for writable characteristics.
"""
from __future__ import annotations

import pytest

from ble_framework.ble_client import BLEClientError

BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
DEVICE_NAME_UUID = "0000180a-0000-1000-8000-00805f9b34fb"


@pytest.mark.asyncio
async def test_read_battery_level_characteristic(ble_client):
    value = await ble_client.read_characteristic(BATTERY_LEVEL_UUID)
    assert value, "Battery level read returned empty payload"
    level = value[0]
    assert 0 <= level <= 100, f"Battery level {level} out of valid range 0-100"


@pytest.mark.asyncio
async def test_write_then_readback_round_trip(ble_client):
    """Writes a known payload to a writable characteristic and confirms readback matches."""
    payload = bytes([0x01, 0x02, 0x03, 0x04])
    await ble_client.write_characteristic(BATTERY_LEVEL_UUID, payload, response=True)
    readback = await ble_client.read_characteristic(BATTERY_LEVEL_UUID)
    assert readback == payload, f"Readback {readback!r} does not match written payload {payload!r}"


@pytest.mark.asyncio
async def test_read_unknown_characteristic_raises(ble_client):
    with pytest.raises(BLEClientError):
        await ble_client.read_characteristic("0000dead-0000-1000-8000-00805f9b34fb")


@pytest.mark.asyncio
async def test_write_without_response_does_not_block(ble_client):
    payload = bytes([0xFF] * 20)
    # Should complete without raising and without requiring an ATT response.
    await ble_client.write_characteristic(BATTERY_LEVEL_UUID, payload, response=False)


@pytest.mark.asyncio
async def test_mtu_negotiation_meets_minimum(ble_client, ble_config):
    granted = await ble_client.request_mtu(ble_config.mtu_test_payload_bytes if ble_config.mtu_test_payload_bytes < 512 else 247)
    assert granted >= 23, f"Negotiated MTU {granted} is below the BLE minimum of 23 bytes"
