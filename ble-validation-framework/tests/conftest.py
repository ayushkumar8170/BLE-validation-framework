from __future__ import annotations

import asyncio
import time

import pytest

from ble_framework.ble_client import build_client
from ble_framework.config import CONFIG
from ble_framework.report_generator import ReportData, write_report


@pytest.fixture(scope="session")
def ble_config():
    return CONFIG


@pytest.fixture(scope="session")
def report_data(ble_config):
    target_label = ble_config.target_address or ble_config.target_name or "Mock Peripheral (CI)"
    return ReportData(title=ble_config.report_title, target_label=target_label)


@pytest.fixture
async def ble_client(ble_config):
    """
    Provides a connected BLE client (real Bleak or MockBleClient depending
    on BLE_USE_MOCK) for the duration of a single test, and guarantees
    disconnect on teardown even if the test fails mid-assertion.
    """
    client = build_client(ble_config.use_mock)
    address = ble_config.target_address or "AA:BB:CC:DD:EE:FF"
    await client.connect(address, timeout_s=ble_config.connect_timeout_s, retries=ble_config.connect_retries)
    try:
        yield client
    finally:
        await client.disconnect()


@pytest.fixture(autouse=True)
def _record_result(request, report_data):
    """Auto-records every test's pass/fail/skip status + duration into the report."""
    start = time.perf_counter()
    outcome_holder = {}

    yield

    duration = time.perf_counter() - start
    rep = getattr(request.node, "_last_call_report", None)
    status = "pass"
    detail = ""
    if hasattr(request.node, "_report_failed") and request.node._report_failed:
        status = "fail"
        detail = str(getattr(request.node, "_report_detail", ""))
    category = request.node.nodeid.split("::")[0].rsplit("/", 1)[-1].replace("test_", "").replace(".py", "")
    report_data.add_result(name=request.node.name, category=category, status=status, duration_s=duration, detail=detail)


def pytest_runtest_makereport(item, call):
    if call.when == "call" and call.excinfo is not None:
        item._report_failed = True
        item._report_detail = str(call.excinfo.value)


@pytest.fixture(scope="session", autouse=True)
def _write_final_report(report_data, ble_config):
    yield
    write_report(report_data, ble_config.report_dir)
