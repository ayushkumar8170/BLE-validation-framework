"""
ble_client.py

Thin async wrapper around Bleak that exposes exactly the operations the
validation suite needs: scanning/advertisement capture, connect/disconnect,
GATT service discovery, characteristic read/write, and MTU negotiation.

A MockBleClient with an identical interface is provided so the full test
suite (assertions + reporting pipeline) can run in CI without real BLE
hardware attached. Swap in the real client by setting BLE_USE_MOCK=false
and BLE_TARGET_ADDRESS / BLE_TARGET_NAME.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ble_framework.client")


@dataclass
class AdvertisementReport:
    address: str
    local_name: Optional[str]
    rssi: int
    service_uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class GattCharacteristicInfo:
    uuid: str
    properties: list[str]
    handle: int


@dataclass
class GattServiceInfo:
    uuid: str
    characteristics: list[GattCharacteristicInfo]


class BLEClientError(Exception):
    """Raised for connection, discovery, or GATT operation failures."""


class BaseBLEClient:
    """Interface both the real and mock clients implement."""

    async def scan(self, timeout_s: float) -> list[AdvertisementReport]:
        raise NotImplementedError

    async def connect(self, address: str, timeout_s: float, retries: int = 1) -> float:
        """Connect and return the elapsed connection latency in seconds."""
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def discover_services(self) -> list[GattServiceInfo]:
        raise NotImplementedError

    async def read_characteristic(self, uuid: str) -> bytes:
        raise NotImplementedError

    async def write_characteristic(self, uuid: str, data: bytes, response: bool = True) -> None:
        raise NotImplementedError

    async def request_mtu(self, mtu: int) -> int:
        """Negotiate MTU and return the value actually granted."""
        raise NotImplementedError

    async def get_connection_interval_ms(self) -> float:
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError


class BleakBLEClient(BaseBLEClient):
    """Real Bleak-backed implementation for Linux/BlueZ targets."""

    def __init__(self) -> None:
        self._client = None  # bleak.BleakClient, imported lazily
        self._connected_address: Optional[str] = None

    async def scan(self, timeout_s: float) -> list[AdvertisementReport]:
        from bleak import BleakScanner

        reports: list[AdvertisementReport] = []

        def _callback(device, advertisement_data):
            reports.append(
                AdvertisementReport(
                    address=device.address,
                    local_name=advertisement_data.local_name or device.name,
                    rssi=advertisement_data.rssi,
                    service_uuids=list(advertisement_data.service_uuids or []),
                    manufacturer_data=dict(advertisement_data.manufacturer_data or {}),
                )
            )

        scanner = BleakScanner(detection_callback=_callback)
        await scanner.start()
        await asyncio.sleep(timeout_s)
        await scanner.stop()
        return reports

    async def connect(self, address: str, timeout_s: float, retries: int = 1) -> float:
        from bleak import BleakClient

        last_exc: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            start = time.perf_counter()
            try:
                self._client = BleakClient(address, timeout=timeout_s)
                await self._client.connect()
                self._connected_address = address
                return time.perf_counter() - start
            except Exception as exc:  # noqa: BLE001 - surfaced to caller as BLEClientError
                last_exc = exc
                logger.warning("Connect attempt %d/%d failed: %s", attempt, retries, exc)
                await asyncio.sleep(0.5 * attempt)
        raise BLEClientError(f"Failed to connect to {address} after {retries} attempts: {last_exc}")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
        self._connected_address = None

    async def discover_services(self) -> list[GattServiceInfo]:
        if self._client is None:
            raise BLEClientError("Not connected")
        services = []
        for svc in self._client.services:
            chars = [
                GattCharacteristicInfo(uuid=c.uuid, properties=list(c.properties), handle=c.handle)
                for c in svc.characteristics
            ]
            services.append(GattServiceInfo(uuid=svc.uuid, characteristics=chars))
        return services

    async def read_characteristic(self, uuid: str) -> bytes:
        if self._client is None:
            raise BLEClientError("Not connected")
        return bytes(await self._client.read_gatt_char(uuid))

    async def write_characteristic(self, uuid: str, data: bytes, response: bool = True) -> None:
        if self._client is None:
            raise BLEClientError("Not connected")
        await self._client.write_gatt_char(uuid, data, response=response)

    async def request_mtu(self, mtu: int) -> int:
        if self._client is None:
            raise BLEClientError("Not connected")
        # Bleak negotiates MTU automatically on BlueZ; expose the granted value.
        return self._client.mtu_size

    async def get_connection_interval_ms(self) -> float:
        # BlueZ does not expose the live connection interval through Bleak's
        # public API; callers on Linux should read it via `btmgmt`/`hcitool`
        # or a vendor HCI snoop if precise interval telemetry is required.
        raise NotImplementedError(
            "Connection interval readback requires a platform-specific HCI query; "
            "see docs/architecture.md for the BlueZ hcitool workaround."
        )

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)


class MockBleClient(BaseBLEClient):
    """
    Deterministic-but-randomized fake peripheral used for CI and local
    development without hardware. Simulates realistic latency, occasional
    transient failures, and a small GATT table.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)
        self._connected = False
        self._nominal_interval_ms = 30.0
        self._char_store: dict[str, bytes] = {
            "0000180a-0000-1000-8000-00805f9b34fb": b"MockDevice-FW1.2.0",
            "00002a19-0000-1000-8000-00805f9b34fb": bytes([87]),  # battery level
        }

    async def scan(self, timeout_s: float) -> list[AdvertisementReport]:
        await asyncio.sleep(min(timeout_s, 0.05))
        return [
            AdvertisementReport(
                address="AA:BB:CC:DD:EE:FF",
                local_name="MockPeripheral",
                rssi=-1 * self._rng.randint(40, 70),
                service_uuids=["0000180a-0000-1000-8000-00805f9b34fb"],
                manufacturer_data={0x004C: b"\x02\x15"},
            )
        ]

    async def connect(self, address: str, timeout_s: float, retries: int = 1) -> float:
        start = time.perf_counter()
        # ~2% transient failure rate to exercise retry logic realistically.
        for attempt in range(1, retries + 1):
            await asyncio.sleep(self._rng.uniform(0.01, 0.08))
            if self._rng.random() < 0.02 and attempt < retries:
                continue
            self._connected = True
            return time.perf_counter() - start
        raise BLEClientError(f"Mock connection to {address} failed after {retries} attempts")

    async def disconnect(self) -> None:
        await asyncio.sleep(0.01)
        self._connected = False

    async def discover_services(self) -> list[GattServiceInfo]:
        return [
            GattServiceInfo(
                uuid="0000180a-0000-1000-8000-00805f9b34fb",
                characteristics=[
                    GattCharacteristicInfo(
                        uuid="0000180a-0000-1000-8000-00805f9b34fb", properties=["read"], handle=0x0003
                    )
                ],
            ),
            GattServiceInfo(
                uuid="0000180f-0000-1000-8000-00805f9b34fb",
                characteristics=[
                    GattCharacteristicInfo(
                        uuid="00002a19-0000-1000-8000-00805f9b34fb",
                        properties=["read", "notify"],
                        handle=0x0006,
                    )
                ],
            ),
        ]

    async def read_characteristic(self, uuid: str) -> bytes:
        if not self._connected:
            raise BLEClientError("Not connected")
        if uuid not in self._char_store:
            raise BLEClientError(f"Unknown characteristic {uuid}")
        await asyncio.sleep(self._rng.uniform(0.002, 0.01))
        return self._char_store[uuid]

    async def write_characteristic(self, uuid: str, data: bytes, response: bool = True) -> None:
        if not self._connected:
            raise BLEClientError("Not connected")
        await asyncio.sleep(self._rng.uniform(0.002, 0.01))
        self._char_store[uuid] = bytes(data)

    async def request_mtu(self, mtu: int) -> int:
        # Simulate a peripheral that caps MTU at 247.
        return min(mtu, 247)

    async def get_connection_interval_ms(self) -> float:
        jitter = self._rng.uniform(-1.5, 1.5)
        return self._nominal_interval_ms + jitter

    @property
    def is_connected(self) -> bool:
        return self._connected


def build_client(use_mock: bool) -> BaseBLEClient:
    return MockBleClient() if use_mock else BleakBLEClient()
