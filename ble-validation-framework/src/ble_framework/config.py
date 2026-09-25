"""
Central configuration for the BLE validation framework.

All settings are overridable via environment variables so the same test
suite can run unmodified against different targets/rigs and in CI (mock
mode, no hardware required).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


@dataclass
class BLEConfig:
    # --- Target device ---
    target_name: str | None = field(default_factory=lambda: os.getenv("BLE_TARGET_NAME"))
    target_address: str | None = field(default_factory=lambda: os.getenv("BLE_TARGET_ADDRESS"))
    use_mock: bool = field(
        default_factory=lambda: _env_bool(
            "BLE_USE_MOCK", os.getenv("BLE_TARGET_ADDRESS") is None and os.getenv("BLE_TARGET_NAME") is None
        )
    )

    # --- Scan / connect ---
    scan_timeout_s: float = field(default_factory=lambda: _env_float("BLE_SCAN_TIMEOUT", 10.0))
    connect_timeout_s: float = field(default_factory=lambda: _env_float("BLE_CONNECT_TIMEOUT", 10.0))
    connect_retries: int = field(default_factory=lambda: _env_int("BLE_CONNECT_RETRIES", 3))

    # --- Expected GAP advertisement (used by test_gap_advertising) ---
    expected_service_uuids: list[str] = field(
        default_factory=lambda: [
            u.strip() for u in os.getenv("BLE_EXPECTED_SERVICE_UUIDS", "").split(",") if u.strip()
        ]
    )
    max_adv_interval_ms: float = field(default_factory=lambda: _env_float("BLE_MAX_ADV_INTERVAL_MS", 1285.0))
    min_adv_interval_ms: float = field(default_factory=lambda: _env_float("BLE_MIN_ADV_INTERVAL_MS", 20.0))

    # --- Expected GATT layout (used by test_service_discovery / gatt) ---
    expected_services: dict[str, list[str]] = field(default_factory=dict)
    """Mapping of expected service UUID -> list of expected characteristic UUIDs."""

    # --- Stress testing ---
    stress_iterations: int = field(default_factory=lambda: _env_int("BLE_STRESS_ITERATIONS", 100))
    stress_duration_hours: float = field(default_factory=lambda: _env_float("BLE_STRESS_DURATION_HOURS", 0.0))
    connection_interval_tolerance_pct: float = field(
        default_factory=lambda: _env_float("BLE_CONN_INTERVAL_TOLERANCE_PCT", 20.0)
    )
    max_pairing_latency_s: float = field(default_factory=lambda: _env_float("BLE_MAX_PAIRING_LATENCY_S", 5.0))
    mtu_test_payload_bytes: int = field(default_factory=lambda: _env_int("BLE_MTU_PAYLOAD_BYTES", 16384))

    # --- Packet capture ---
    capture_enabled: bool = field(default_factory=lambda: _env_bool("BLE_CAPTURE_ENABLED", False))
    capture_interface: str = field(default_factory=lambda: os.getenv("BLE_CAPTURE_INTERFACE", "bluetooth0"))
    capture_dir: str = field(default_factory=lambda: os.getenv("BLE_CAPTURE_DIR", "captures"))

    # --- Reporting ---
    report_dir: str = field(default_factory=lambda: os.getenv("BLE_REPORT_DIR", "reports"))
    report_title: str = field(default_factory=lambda: os.getenv("BLE_REPORT_TITLE", "BLE Functional Validation Report"))


CONFIG = BLEConfig()

# HCI disconnect reason codes -> human-readable cause (Bluetooth Core Spec Vol 2, Part D)
HCI_DISCONNECT_REASONS: dict[int, str] = {
    0x05: "Authentication Failure",
    0x08: "Connection Timeout",
    0x13: "Remote User Terminated Connection",
    0x14: "Remote Device Terminated (Low Resources)",
    0x15: "Remote Device Terminated (Power Off)",
    0x16: "Connection Terminated by Local Host",
    0x1A: "Unsupported Remote Feature",
    0x22: "LL Response Timeout",
    0x28: "Instant Passed",
    0x29: "Pairing with Unit Key Not Supported",
    0x3B: "Unacceptable Connection Parameters",
    0x3D: "Connection Failed to be Established / Sync Timeout",
    0x3E: "Connection Failed to be Established",
}
