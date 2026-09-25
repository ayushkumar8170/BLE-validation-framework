"""
packet_analyzer.py

Captures over-the-air BLE traffic via tshark (Wireshark's CLI) on a Linux
HCI interface, and dissects the resulting capture to isolate packet drops
and disconnection causes.

Two modes:
  - CaptureSession: starts/stops a live `tshark` capture as a subprocess
    around a test session.
  - analyze_capture(): parses an existing .pcapng file (live or supplied by
    the user) and returns a PacketAnalysisResult summary.

Requires the `tshark` binary on PATH. Falls back gracefully (raises
PacketAnalyzerError with a clear message) if it is not available, so the
rest of the suite can still run with capture disabled.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import HCI_DISCONNECT_REASONS

logger = logging.getLogger("ble_framework.packet_analyzer")


class PacketAnalyzerError(Exception):
    pass


@dataclass
class DisconnectEvent:
    timestamp: float
    reason_code: int
    reason_text: str


@dataclass
class PacketAnalysisResult:
    capture_file: str
    total_packets: int = 0
    ble_packets: int = 0
    crc_errors: int = 0
    retransmissions: int = 0
    dropped_packets: int = 0
    disconnect_events: list[DisconnectEvent] = field(default_factory=list)

    @property
    def drop_rate_pct(self) -> float:
        if self.ble_packets == 0:
            return 0.0
        return 100.0 * self.dropped_packets / self.ble_packets


def tshark_available() -> bool:
    return shutil.which("tshark") is not None


class CaptureSession:
    """Starts and stops a `tshark` capture as a background subprocess."""

    def __init__(self, interface: str, output_dir: str, label: str = "ble_capture") -> None:
        if not tshark_available():
            raise PacketAnalyzerError(
                "tshark not found on PATH. Install Wireshark's CLI tools "
                "(`sudo apt-get install tshark`) or set BLE_CAPTURE_ENABLED=false."
            )
        self.interface = interface
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.output_path = self.output_dir / f"{label}_{ts}.pcapng"
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        cmd = ["tshark", "-i", self.interface, "-w", str(self.output_path), "-q"]
        logger.info("Starting capture: %s", " ".join(cmd))
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)  # allow tshark to attach before the test proceeds

    def stop(self) -> Path:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        logger.info("Capture stopped: %s", self.output_path)
        return self.output_path


def analyze_capture(pcap_path: str | Path) -> PacketAnalysisResult:
    """
    Parse a capture file with tshark's field-extraction mode and summarize
    BLE packet drops / disconnection reasons.

    Uses `tshark -T fields` rather than pyshark for speed and to avoid an
    asyncio event-loop dependency inside a synchronous helper.
    """
    if not tshark_available():
        raise PacketAnalyzerError("tshark not found on PATH; cannot analyze capture.")

    pcap_path = Path(pcap_path)
    if not pcap_path.exists():
        raise PacketAnalyzerError(f"Capture file not found: {pcap_path}")

    result = PacketAnalysisResult(capture_file=str(pcap_path))

    # Total packet count.
    count_cmd = ["tshark", "-r", str(pcap_path), "-T", "fields", "-e", "frame.number"]
    total = subprocess.run(count_cmd, capture_output=True, text=True, check=False)
    result.total_packets = len([l for l in total.stdout.splitlines() if l.strip()])

    # BLE-specific packets (LL/ATT/HCI layers).
    ble_cmd = ["tshark", "-r", str(pcap_path), "-Y", "btle || att || hci_evt", "-T", "fields", "-e", "frame.number"]
    ble = subprocess.run(ble_cmd, capture_output=True, text=True, check=False)
    result.ble_packets = len([l for l in ble.stdout.splitlines() if l.strip()])

    # CRC errors.
    crc_cmd = ["tshark", "-r", str(pcap_path), "-Y", "btle.crc.incorrect == 1", "-T", "fields", "-e", "frame.number"]
    crc = subprocess.run(crc_cmd, capture_output=True, text=True, check=False)
    result.crc_errors = len([l for l in crc.stdout.splitlines() if l.strip()])

    # Retransmissions (empty PDU repeats / SN not advanced — approximate via btle.data_header.sn duplicates).
    retx_cmd = [
        "tshark", "-r", str(pcap_path),
        "-Y", "btle.data_header.md == 1 && btle.data_header.length == 0",
        "-T", "fields", "-e", "frame.number",
    ]
    retx = subprocess.run(retx_cmd, capture_output=True, text=True, check=False)
    result.retransmissions = len([l for l in retx.stdout.splitlines() if l.strip()])

    result.dropped_packets = result.crc_errors  # CRC failures are the primary observable "drop" signal OTA

    # HCI disconnection events with reason codes.
    disc_cmd = [
        "tshark", "-r", str(pcap_path),
        "-Y", "hci_evt.evt_code == 0x05",  # Disconnection Complete event
        "-T", "fields", "-e", "frame.time_epoch", "-e", "hci_evt.reason",
    ]
    disc = subprocess.run(disc_cmd, capture_output=True, text=True, check=False)
    for line in disc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2 or not parts[1]:
            continue
        try:
            ts = float(parts[0])
            reason = int(parts[1], 0)
        except ValueError:
            continue
        result.disconnect_events.append(
            DisconnectEvent(
                timestamp=ts,
                reason_code=reason,
                reason_text=HCI_DISCONNECT_REASONS.get(reason, f"Unknown (0x{reason:02X})"),
            )
        )

    return result
