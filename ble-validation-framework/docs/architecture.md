# Architecture

## Overview

```
                ┌───────────────────────┐
                │      pytest suite     │
                │  test_gap_advertising │
                │  test_service_discovery
                │  test_gatt_characteristics
                │  test_stress           │
                └──────────┬─────────────┘
                           │ uses
                           ▼
   ┌─────────────┐   ┌──────────────┐   ┌────────────────┐
   │ ble_client.py│   │stress_test.py│   │packet_analyzer.py│
   │ (Bleak wrap) │   │ (endurance   │   │ (tshark capture  │
   │ + MockClient │   │  cycles)     │   │  + drop analysis)│
   └──────┬───────┘   └──────┬───────┘   └────────┬─────────┘
          │                  │                     │
          └────────┬─────────┴─────────┬───────────┘
                    ▼                   ▼
              ┌───────────────────────────────┐
              │      report_generator.py       │
              │  ReportData -> self-contained  │
              │       HTML report              │
              └───────────────────────────────┘
```

## Component responsibilities

- **`ble_client.py`** — the only module that talks to Bleak/BlueZ. Exposes
  `BaseBLEClient`, an abstract interface (`scan`, `connect`, `disconnect`,
  `discover_services`, `read_characteristic`, `write_characteristic`,
  `request_mtu`, `get_connection_interval_ms`). Two implementations:
  - `BleakBLEClient` — real hardware, Linux/BlueZ.
  - `MockBleClient` — deterministic-ish simulated peripheral for CI/dev.

  All test and stress code depends on `BaseBLEClient`, never on Bleak
  directly, so hardware and mock runs are interchangeable.

- **`stress_test.py`** — `StressTestRunner.run(iterations, deadline)` drives
  N connect → negotiate MTU → measure interval → write-throughput →
  disconnect cycles and aggregates a `StressTestResult` with latency,
  interval, and throughput distributions plus failure counts.

- **`packet_analyzer.py`** — `CaptureSession` wraps a background `tshark`
  process bound to the configured HCI interface. `analyze_capture()` runs
  targeted `tshark -Y <filter> -T fields` queries against the resulting
  `.pcapng` to count CRC errors, retransmissions, and to extract HCI
  Disconnection Complete events with decoded reason codes
  (`config.HCI_DISCONNECT_REASONS`).

- **`report_generator.py`** — a single Jinja2 template rendered into a
  self-contained HTML file. `ReportData` accumulates per-test results
  (`add_result`) plus the optional `StressTestResult` /
  `PacketAnalysisResult`. `tests/conftest.py` wires an autouse fixture that
  records every PyTest test's outcome into the shared `ReportData` and
  writes the final report at session teardown.

## Why an abstract client + mock

BLE hardware is not available in most CI runners. Every module above the
`ble_client` layer is written against `BaseBLEClient`, so:

- `BLE_USE_MOCK=true` (the default when no target is configured) runs the
  entire suite — assertions, stress statistics, and HTML report generation
  — against `MockBleClient`, exercising the framework itself in CI.
- Pointing `BLE_TARGET_ADDRESS` at a real MAC address and unsetting
  `BLE_USE_MOCK` switches every module to `BleakBLEClient` with zero code
  changes in the tests.

## Known platform limitation: connection interval readback

BlueZ does not expose the live connection interval through Bleak's public
API. `BleakBLEClient.get_connection_interval_ms()` raises
`NotImplementedError`, and stress tests treat that as "metric unavailable"
rather than a failure. To capture real interval data on Linux, either:

1. Poll `btmgmt` / `hcitool con` in a side thread during the stress run, or
2. Parse `LL_CONNECTION_UPDATE_IND` PDUs from the tshark capture
   (`packet_analyzer.py` is the natural place to add this — the capture is
   already running when `BLE_CAPTURE_ENABLED=true`).

## Extending the framework

- **New assertions**: add a test function in the relevant `tests/test_*.py`
  file; the autouse `_record_result` fixture picks it up automatically.
- **New target GATT layout**: set `BLE_EXPECTED_SERVICE_UUIDS` and populate
  `BLEConfig.expected_services` (or extend `config.py` to read it from a
  YAML/JSON fixture file for multi-target rigs).
- **New report sections**: extend `ReportData` and the Jinja2 template in
  `report_generator.py`; both are intentionally single-file/dependency-free.
