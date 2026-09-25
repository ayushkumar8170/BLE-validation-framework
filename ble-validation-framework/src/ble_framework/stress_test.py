"""
stress_test.py

Repeated connect/disconnect and throughput cycles used to characterize:
  - connection interval stability across many connection events
  - pairing/connection latency distribution
  - MTU negotiation and effective GATT write throughput

Designed to run either inline as part of the PyTest suite (small iteration
counts) or standalone via scripts/run_stress_test.py for multi-hour
endurance runs.
"""
from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field

from .ble_client import BaseBLEClient, BLEClientError

logger = logging.getLogger("ble_framework.stress")


@dataclass
class StressTestResult:
    iterations_requested: int
    iterations_completed: int
    connect_failures: int
    connection_latencies_s: list[float] = field(default_factory=list)
    connection_intervals_ms: list[float] = field(default_factory=list)
    mtu_negotiated: list[int] = field(default_factory=list)
    throughput_bytes_per_s: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float = field(default=0.0)

    # --- derived stats -------------------------------------------------
    def _stats(self, values: list[float]) -> dict[str, float]:
        if not values:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0, "stdev": 0.0}
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        }

    @property
    def pairing_latency_stats(self) -> dict[str, float]:
        return self._stats(self.connection_latencies_s)

    @property
    def connection_interval_stats(self) -> dict[str, float]:
        return self._stats(self.connection_intervals_ms)

    @property
    def throughput_stats(self) -> dict[str, float]:
        return self._stats(self.throughput_bytes_per_s)

    @property
    def success_rate_pct(self) -> float:
        if self.iterations_requested == 0:
            return 0.0
        return 100.0 * self.iterations_completed / self.iterations_requested

    @property
    def duration_s(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at


class StressTestRunner:
    """
    Drives repeated connect -> measure -> disconnect cycles against a
    BaseBLEClient (real or mock) and aggregates timing/throughput metrics.
    """

    def __init__(
        self,
        client: BaseBLEClient,
        address: str,
        connect_timeout_s: float = 10.0,
        connect_retries: int = 3,
        mtu_target: int = 247,
        write_char_uuid: str = "00002a19-0000-1000-8000-00805f9b34fb",
    ) -> None:
        self.client = client
        self.address = address
        self.connect_timeout_s = connect_timeout_s
        self.connect_retries = connect_retries
        self.mtu_target = mtu_target
        self.write_char_uuid = write_char_uuid

    async def _measure_throughput(self, payload_bytes: int) -> float:
        # A repeating 512-byte pattern is enough to fill any chunk size we use.
        payload = bytes([i % 256 for i in range(min(payload_bytes, 512))])
        start = time.perf_counter()
        # Write in chunks approximating the negotiated MTU minus ATT header (3 bytes).
        chunk_size = max(20, self.mtu_target - 3)
        total_written = 0
        while total_written < payload_bytes:
            chunk = payload[: min(chunk_size, len(payload))]
            await self.client.write_characteristic(self.write_char_uuid, chunk, response=False)
            total_written += len(chunk)
        elapsed = max(time.perf_counter() - start, 1e-6)
        return total_written / elapsed

    async def run(self, iterations: int, deadline_monotonic: float | None = None) -> StressTestResult:
        result = StressTestResult(iterations_requested=iterations, iterations_completed=0, connect_failures=0)

        for i in range(iterations):
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                logger.info("Stress run stopped early at iteration %d: duration deadline reached", i)
                break

            try:
                latency = await self.client.connect(
                    self.address, timeout_s=self.connect_timeout_s, retries=self.connect_retries
                )
                result.connection_latencies_s.append(latency)

                mtu = await self.client.request_mtu(self.mtu_target)
                result.mtu_negotiated.append(mtu)

                try:
                    interval = await self.client.get_connection_interval_ms()
                    result.connection_intervals_ms.append(interval)
                except NotImplementedError:
                    pass  # platform doesn't expose interval readback; skip metric

                throughput = await self._measure_throughput(4096)
                result.throughput_bytes_per_s.append(throughput)

                result.iterations_completed += 1
            except BLEClientError as exc:
                result.connect_failures += 1
                result.errors.append(f"iteration {i}: {exc}")
                logger.warning("Stress iteration %d failed: %s", i, exc)
            finally:
                try:
                    await self.client.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Disconnect cleanup error (ignored): %s", exc)

        result.finished_at = time.time()
        return result
