#!/usr/bin/env python3
"""
Standalone stress-test runner for multi-hour endurance validation.

Runs repeated connect/disconnect/read/write/MTU cycles against the
configured target, optionally alongside a live tshark packet capture, and
emits the framework's HTML report at the end.

Usage:
    python scripts/run_stress_test.py --iterations 500
    python scripts/run_stress_test.py --duration-hours 4 --capture
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ble_framework.ble_client import build_client  # noqa: E402
from ble_framework.config import CONFIG  # noqa: E402
from ble_framework.packet_analyzer import CaptureSession, PacketAnalyzerError, analyze_capture  # noqa: E402
from ble_framework.report_generator import ReportData, write_report  # noqa: E402
from ble_framework.stress_test import StressTestRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger("run_stress_test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a long-duration BLE stress test.")
    parser.add_argument("--iterations", type=int, default=CONFIG.stress_iterations,
                         help="Max connect/disconnect cycles to run.")
    parser.add_argument("--duration-hours", type=float, default=CONFIG.stress_duration_hours,
                         help="Stop after this many hours even if iterations remain (0 = no time limit).")
    parser.add_argument("--capture", action="store_true", default=CONFIG.capture_enabled,
                         help="Enable a live tshark capture for the duration of the run.")
    parser.add_argument("--address", type=str, default=CONFIG.target_address,
                         help="Target BLE MAC address (overrides BLE_TARGET_ADDRESS).")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    address = args.address or "AA:BB:CC:DD:EE:FF"
    client = build_client(CONFIG.use_mock)

    capture: CaptureSession | None = None
    if args.capture:
        try:
            capture = CaptureSession(interface=CONFIG.capture_interface, output_dir=CONFIG.capture_dir)
            capture.start()
        except PacketAnalyzerError as exc:
            logger.warning("Packet capture disabled: %s", exc)
            capture = None

    deadline = None
    if args.duration_hours > 0:
        deadline = time.monotonic() + args.duration_hours * 3600

    logger.info(
        "Starting stress run: iterations=%d duration_hours=%s target=%s mock=%s",
        args.iterations, args.duration_hours or "unbounded", address, CONFIG.use_mock,
    )

    runner = StressTestRunner(
        client=client,
        address=address,
        connect_timeout_s=CONFIG.connect_timeout_s,
        connect_retries=CONFIG.connect_retries,
    )
    result = await runner.run(iterations=args.iterations, deadline_monotonic=deadline)

    packet_result = None
    if capture is not None:
        capture_path = capture.stop()
        try:
            packet_result = analyze_capture(capture_path)
        except PacketAnalyzerError as exc:
            logger.warning("Capture analysis skipped: %s", exc)

    report = ReportData(
        title=f"{CONFIG.report_title} — Stress Run",
        target_label=address,
        stress_result=result,
        packet_result=packet_result,
    )
    out_path = write_report(report, CONFIG.report_dir)

    logger.info(
        "Stress run complete: %d/%d cycles (%.1f%% success), %d failures. Report: %s",
        result.iterations_completed, result.iterations_requested, result.success_rate_pct,
        result.connect_failures, out_path,
    )
    return 0 if result.success_rate_pct >= 95.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
