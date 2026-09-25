"""
report_generator.py

Builds a self-contained HTML report embedding:
  - overall pass/fail assertion summary
  - per-test-case results with timing
  - stress-test latency/throughput/connection-interval statistics
  - packet capture drop-rate / disconnect-reason breakdown (if available)

No external JS/CSS dependencies — the report is a single file suitable for
attaching to CI artifacts or emailing.
"""
from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Template

_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
  :root { color-scheme: light; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; background: #f5f6f8; color: #1c1e21; }
  header { background: #12233d; color: #fff; padding: 24px 32px; }
  header h1 { margin: 0 0 4px 0; font-size: 22px; }
  header .meta { font-size: 13px; color: #a9b7cc; }
  main { max-width: 1100px; margin: 24px auto; padding: 0 16px 48px; }
  .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 28px; }
  .card { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .card .num { font-size: 28px; font-weight: 700; }
  .card .label { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: .04em; }
  .pass { color: #1a8754; } .fail { color: #d64545; } .neutral { color: #2563eb; }
  h2 { font-size: 16px; margin: 32px 0 12px; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  th, td { text-align: left; padding: 10px 14px; font-size: 13px; border-bottom: 1px solid #eef0f2; }
  th { background: #f0f2f5; font-weight: 600; color: #374151; }
  tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }
  .badge-pass { background: #e6f6ee; color: #1a8754; }
  .badge-fail { background: #fde8e8; color: #d64545; }
  .badge-skip { background: #f0f0f0; color: #6b7280; }
  .stat-row td:not(:first-child) { text-align: right; font-variant-numeric: tabular-nums; }
  .empty { color: #9ca3af; font-style: italic; padding: 16px; }
  footer { text-align: center; font-size: 12px; color: #9ca3af; padding: 24px; }
</style>
</head>
<body>
<header>
  <h1>{{ title }}</h1>
  <div class="meta">Generated {{ generated_at }} &middot; Target: {{ target_label }}</div>
</header>
<main>

  <div class="summary-grid">
    <div class="card"><div class="num neutral">{{ total }}</div><div class="label">Total Assertions</div></div>
    <div class="card"><div class="num pass">{{ passed }}</div><div class="label">Passed</div></div>
    <div class="card"><div class="num fail">{{ failed }}</div><div class="label">Failed</div></div>
    <div class="card"><div class="num neutral">{{ pass_rate }}%</div><div class="label">Pass Rate</div></div>
  </div>

  <h2>Test Case Results</h2>
  {% if test_cases %}
  <table>
    <tr><th>Test</th><th>Category</th><th>Status</th><th>Duration (s)</th><th>Detail</th></tr>
    {% for tc in test_cases %}
    <tr>
      <td>{{ tc.name }}</td>
      <td>{{ tc.category }}</td>
      <td><span class="badge badge-{{ tc.status }}">{{ tc.status | upper }}</span></td>
      <td>{{ '%.3f' | format(tc.duration_s) }}</td>
      <td>{{ tc.detail }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <div class="empty">No individual test case results were recorded.</div>
  {% endif %}

  <h2>Stress Test Metrics</h2>
  {% if stress %}
  <table>
    <tr><th>Metric</th><th>Count</th><th>Mean</th><th>Min</th><th>Max</th><th>Std Dev</th></tr>
    <tr class="stat-row"><td>Pairing / Connection Latency (s)</td>
      <td>{{ stress.pairing_latency_stats.count }}</td>
      <td>{{ '%.4f' | format(stress.pairing_latency_stats.mean) }}</td>
      <td>{{ '%.4f' | format(stress.pairing_latency_stats.min) }}</td>
      <td>{{ '%.4f' | format(stress.pairing_latency_stats.max) }}</td>
      <td>{{ '%.4f' | format(stress.pairing_latency_stats.stdev) }}</td></tr>
    <tr class="stat-row"><td>Connection Interval (ms)</td>
      <td>{{ stress.connection_interval_stats.count }}</td>
      <td>{{ '%.2f' | format(stress.connection_interval_stats.mean) }}</td>
      <td>{{ '%.2f' | format(stress.connection_interval_stats.min) }}</td>
      <td>{{ '%.2f' | format(stress.connection_interval_stats.max) }}</td>
      <td>{{ '%.2f' | format(stress.connection_interval_stats.stdev) }}</td></tr>
    <tr class="stat-row"><td>Throughput (bytes/s)</td>
      <td>{{ stress.throughput_stats.count }}</td>
      <td>{{ '%.0f' | format(stress.throughput_stats.mean) }}</td>
      <td>{{ '%.0f' | format(stress.throughput_stats.min) }}</td>
      <td>{{ '%.0f' | format(stress.throughput_stats.max) }}</td>
      <td>{{ '%.0f' | format(stress.throughput_stats.stdev) }}</td></tr>
  </table>
  <p style="font-size:13px;color:#374151;margin-top:10px;">
    {{ stress.iterations_completed }}/{{ stress.iterations_requested }} cycles completed
    ({{ '%.1f' | format(stress.success_rate_pct) }}% success), {{ stress.connect_failures }} connect failures,
    total duration {{ '%.1f' | format(stress.duration_s) }}s.
  </p>
  {% else %}
  <div class="empty">No stress test was run in this session.</div>
  {% endif %}

  <h2>Packet Capture Analysis</h2>
  {% if packet %}
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Capture file</td><td>{{ packet.capture_file }}</td></tr>
    <tr><td>Total packets</td><td>{{ packet.total_packets }}</td></tr>
    <tr><td>BLE packets (LL/ATT/HCI)</td><td>{{ packet.ble_packets }}</td></tr>
    <tr><td>CRC errors / dropped</td><td>{{ packet.dropped_packets }} ({{ '%.2f' | format(packet.drop_rate_pct) }}%)</td></tr>
    <tr><td>Retransmissions</td><td>{{ packet.retransmissions }}</td></tr>
  </table>
  {% if packet.disconnect_events %}
  <table style="margin-top:12px;">
    <tr><th>Timestamp</th><th>Reason Code</th><th>Reason</th></tr>
    {% for ev in packet.disconnect_events %}
    <tr><td>{{ '%.3f' | format(ev.timestamp) }}</td><td>0x{{ '%02X' | format(ev.reason_code) }}</td><td>{{ ev.reason_text }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}
  {% else %}
  <div class="empty">Packet capture was not enabled for this session.</div>
  {% endif %}

</main>
<footer>BLE Functional Validation Framework &middot; automated report</footer>
</body>
</html>
"""
)


@dataclass
class TestCaseResult:
    name: str
    category: str
    status: str  # "pass" | "fail" | "skip"
    duration_s: float
    detail: str = ""


@dataclass
class ReportData:
    title: str
    target_label: str
    test_cases: list[TestCaseResult] = field(default_factory=list)
    stress_result: object | None = None  # StressTestResult, kept loosely typed to avoid circular import
    packet_result: object | None = None  # PacketAnalysisResult

    def add_result(self, name: str, category: str, status: str, duration_s: float, detail: str = "") -> None:
        self.test_cases.append(
            TestCaseResult(name=name, category=category, status=status, duration_s=duration_s, detail=html.escape(detail))
        )

    @property
    def total(self) -> int:
        return len(self.test_cases)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.test_cases if t.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for t in self.test_cases if t.status == "fail")

    @property
    def pass_rate(self) -> float:
        return round(100.0 * self.passed / self.total, 1) if self.total else 0.0


def render_report(data: ReportData) -> str:
    return _TEMPLATE.render(
        title=data.title,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        target_label=data.target_label,
        total=data.total,
        passed=data.passed,
        failed=data.failed,
        pass_rate=data.pass_rate,
        test_cases=data.test_cases,
        stress=data.stress_result,
        packet=data.packet_result,
    )


def write_report(data: ReportData, output_dir: str) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"ble_validation_report_{ts}.html"
    out_path.write_text(render_report(data), encoding="utf-8")
    return out_path
