"""BLE Functional Validation Framework — public API surface."""
from .ble_client import BaseBLEClient, BleakBLEClient, MockBleClient, build_client
from .config import CONFIG, BLEConfig
from .packet_analyzer import CaptureSession, PacketAnalysisResult, analyze_capture
from .report_generator import ReportData, render_report, write_report
from .stress_test import StressTestResult, StressTestRunner

__all__ = [
    "BaseBLEClient",
    "BleakBLEClient",
    "MockBleClient",
    "build_client",
    "CONFIG",
    "BLEConfig",
    "CaptureSession",
    "PacketAnalysisResult",
    "analyze_capture",
    "ReportData",
    "render_report",
    "write_report",
    "StressTestResult",
    "StressTestRunner",
]

__version__ = "1.0.0"
