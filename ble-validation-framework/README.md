# BLE Functional Validation Framework

An end-to-end automated test harness for validating Bluetooth Low Energy (BLE)
peripheral behavior: GAP advertising, service discovery, GATT read/write
operations, connection stability, pairing latency, MTU throughput, and
over-the-air (OTA) packet-level diagnostics.

Built with **Python**, **Bleak**, **PyTest**, and **Wireshark/tshark**, and
designed to run on **Linux** (BlueZ) test rigs.

---

## Features

- **GAP validation** — verifies peripheral advertising is present, decodes
  advertisement data (flags, local name, service UUIDs, manufacturer data),
  and checks advertising interval consistency.
- **Service discovery validation** — confirms expected GATT services and
  characteristics are present and correctly permissioned (read/write/notify).
- **GATT read/write validation** — exercises characteristic read and write
  operations, verifying payloads round-trip correctly.
- **Stress testing** — repeated connect/disconnect cycles to evaluate
  connection interval stability, pairing latency distribution, and MTU
  negotiation/throughput over extended durations.
- **Packet-level diagnostics** — captures OTA traffic (via `tshark`/BTsnoop),
  dissects it, and isolates packet drops and disconnect reasons.
- **Automated HTML reporting** — every run produces a self-contained HTML
  report with embedded pass/fail assertion metrics, latency/throughput
  charts, and links to the associated packet capture.

## Project layout

```
ble-validation-framework/
├── src/ble_framework/
│   ├── ble_client.py        # Bleak wrapper: scan, connect, GATT ops
│   ├── stress_test.py       # Connection stability / latency / MTU stress suite
│   ├── packet_analyzer.py   # tshark/pyshark capture + OTA drop analysis
│   ├── report_generator.py  # HTML report generation
│   └── config.py            # Central test configuration
├── tests/
│   ├── conftest.py          # PyTest fixtures (BLE client, capture, reporting)
│   ├── test_gap_advertising.py
│   ├── test_service_discovery.py
│   ├── test_gatt_characteristics.py
│   └── test_stress.py
├── scripts/
│   └── run_stress_test.py   # Standalone long-duration stress runner
├── reports/                 # Generated HTML reports (git-ignored contents)
├── captures/                # Generated .pcapng captures (git-ignored contents)
└── docs/
    └── architecture.md
```

## Requirements

- Linux with BlueZ (`bluetoothd`) and a BLE-capable adapter
- Python 3.9+
- `tshark` (Wireshark CLI) on `PATH` for packet capture/analysis
- A target BLE peripheral (real hardware, or a simulated one such as a
  nRF Connect device / `bleak`-compatible test fixture)

```bash
sudo apt-get install -y bluetooth bluez tshark
sudo usermod -aG wireshark $USER   # allow non-root packet capture
```

## Installation

```bash
git clone https://github.com/<your-username>/ble-validation-framework.git
cd ble-validation-framework
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Configuration

Set the target device and test parameters via environment variables (see
`src/ble_framework/config.py` for the full list), e.g.:

```bash
export BLE_TARGET_NAME="MyPeripheral"
export BLE_TARGET_ADDRESS="AA:BB:CC:DD:EE:FF"   # optional, overrides name scan
export BLE_SCAN_TIMEOUT=10
export BLE_STRESS_ITERATIONS=200
export BLE_CAPTURE_ENABLED=true
```

Without a real target configured, the suite runs against the built-in
`MockBleClient` so the framework, assertions, and reporting pipeline can be
exercised in CI with no hardware attached.

## Running the tests

```bash
# Full functional suite with HTML report
pytest --html=reports/report.html --self-contained-html

# Just GAP + service discovery
pytest tests/test_gap_advertising.py tests/test_service_discovery.py -v

# Long-duration stress run (connection stability / pairing latency / MTU)
python scripts/run_stress_test.py --iterations 500 --duration-hours 4
```

Each run also produces a framework-native report via
`report_generator.py`, written to `reports/ble_validation_report_<ts>.html`,
independent of the `pytest-html` plugin output — this is the report that
embeds assertion-level metrics and (if capture is enabled) links to the
matching `.pcapng` file in `captures/`.

## Packet capture & drop analysis

When `BLE_CAPTURE_ENABLED=true`, each test session starts a `tshark` capture
on the configured HCI interface (default `bluetooth0`) and stores it under
`captures/`. After the session, `packet_analyzer.py` dissects the capture to:

- count and classify OTA packet drops (missing sequence in supervision
  timeout windows)
- extract HCI disconnection event reason codes and map them to human-readable
  causes (e.g. `0x08` Connection Timeout, `0x13` Remote User Terminated,
  `0x3E` Connection Failed to be Established)
- summarize retransmissions and CRC failures per connection

Results are folded into the HTML report automatically.

## CI

`.github/workflows/ci.yml` runs linting and the unit-level (mock-backed)
test suite on every push, without requiring real BLE hardware.

## License

MIT — see [LICENSE](LICENSE).
