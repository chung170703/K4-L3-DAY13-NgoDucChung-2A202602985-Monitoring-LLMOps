"""Render the 6-panel dashboard contract (config/dashboard.yaml) into a static HTML
file computed from data/logs.jsonl. Lightweight alternative to Grafana/Streamlit that
needs no extra dependency - open the output file in a browser to view it live.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
DASHBOARD_CONFIG = REPO_ROOT / "config" / "dashboard.yaml"
OUTPUT_PATH = REPO_ROOT / "data" / "dashboard.html"


def load_records() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def check_threshold(value: float, threshold: dict) -> bool:
    op = threshold["operator"]
    target = threshold["value"]
    return value <= target if op == "lte" else value >= target


def build_panels(records: list[dict], window_minutes: int) -> tuple[list[dict], str, str]:
    timestamps = [r["ts"] for r in records if "ts" in r]
    if timestamps:
        window_end = max(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in timestamps)
    else:
        window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(minutes=window_minutes)

    def in_window(r: dict) -> bool:
        if "ts" not in r:
            return False
        ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
        return window_start <= ts <= window_end

    windowed = [r for r in records if in_window(r)]
    received = [r for r in windowed if r.get("event") == "request_received"]
    sent = [r for r in windowed if r.get("event") == "response_sent"]
    failed = [r for r in windowed if r.get("event") == "request_failed"]

    latencies = [r["latency_ms"] for r in sent if "latency_ms" in r]
    ttfts = [r["ttft_ms"] for r in sent if "ttft_ms" in r]
    costs = [r["cost_usd"] for r in sent if "cost_usd" in r]
    tokens_in = [r["tokens_in"] for r in sent if "tokens_in" in r]
    tokens_out = [r["tokens_out"] for r in sent if "tokens_out" in r]
    quality = [r["quality_score"] for r in sent if "quality_score" in r]

    tool_calls = [r for r in windowed if r.get("tool_success") is not None]
    tool_success = [r for r in tool_calls if r.get("tool_success") is True]

    from collections import Counter

    error_breakdown = Counter(r.get("error_type", "unknown") for r in failed)

    panels = [
        {
            "id": "latency",
            "title": "Latency percentiles and TTFT",
            "unit": "ms",
            "lines": [
                f"P50 = {percentile(latencies, 50):.0f} ms",
                f"P95 = {percentile(latencies, 95):.0f} ms",
                f"P99 = {percentile(latencies, 99):.0f} ms",
                f"TTFT P95 = {percentile(ttfts, 95):.0f} ms",
            ],
            "threshold": {"aggregation": "p95", "operator": "lte", "value": 3000},
            "value": percentile(latencies, 95),
        },
        {
            "id": "traffic",
            "title": "Request traffic",
            "unit": "requests_per_minute",
            "lines": [
                f"count = {len(received)}",
                f"rate = {len(received) / window_minutes:.2f} req/min",
            ],
            "threshold": {"aggregation": "rate_per_minute", "operator": "gte", "value": 1},
            "value": len(received) / window_minutes if window_minutes else 0.0,
        },
        {
            "id": "errors",
            "title": "Error rate and retrieval success",
            "unit": "percent",
            "lines": [
                f"error_rate = {(len(failed) / len(received) * 100) if received else 0:.2f}%",
                f"breakdown = {dict(error_breakdown) or '{}'}",
                f"tool_success_rate = {(len(tool_success) / len(tool_calls) * 100) if tool_calls else 100:.2f}%",
            ],
            "threshold": {"aggregation": "error_rate_pct", "operator": "lte", "value": 2},
            "value": (len(failed) / len(received) * 100) if received else 0.0,
        },
        {
            "id": "cost",
            "title": "Cost over time",
            "unit": "usd",
            "lines": [f"total = ${sum(costs):.4f}"],
            "threshold": {"aggregation": "total", "operator": "lte", "value": 2.5},
            "value": sum(costs),
        },
        {
            "id": "tokens",
            "title": "Input and output tokens",
            "unit": "tokens",
            "lines": [
                f"tokens_in = {sum(tokens_in)}",
                f"tokens_out = {sum(tokens_out)}",
                f"total = {sum(tokens_in) + sum(tokens_out)}",
            ],
            "threshold": {"aggregation": "sum_by_field", "operator": "lte", "value": 50000},
            "value": sum(tokens_in) + sum(tokens_out),
        },
        {
            "id": "quality",
            "title": "Quality proxy",
            "unit": "score_0_to_1",
            "lines": [f"mean = {mean(quality):.2f}" if quality else "mean = n/a"],
            "threshold": {"aggregation": "mean", "operator": "gte", "value": 0.75},
            "value": mean(quality) if quality else 0.0,
        },
    ]
    return panels, window_start.isoformat(), window_end.isoformat()


def render_html(panels: list[dict], window_start: str, window_end: str, refresh_seconds: int) -> str:
    cards = []
    for p in panels:
        ok = check_threshold(p["value"], p["threshold"])
        badge_class = "ok" if ok else "fail"
        badge_text = "OK" if ok else "BREACH"
        lines_html = "".join(f"<li>{line}</li>" for line in p["lines"])
        threshold_desc = f"{p['threshold']['aggregation']} {p['threshold']['operator']} {p['threshold']['value']} {p['unit']}"
        cards.append(
            f"""
            <div class="card">
              <div class="card-header">
                <h2>{p['title']}</h2>
                <span class="badge {badge_class}">{badge_text}</span>
              </div>
              <ul>{lines_html}</ul>
              <div class="threshold">Threshold: {threshold_desc}</div>
            </div>
            """
        )

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Day 13 Monitoring Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background: #0f1115; color: #e6e6e6; margin: 0; padding: 24px; }}
  h1 {{ margin-top: 0; }}
  .meta {{ color: #9aa0a6; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
  .card {{ background: #1a1d24; border: 1px solid #2a2e37; border-radius: 10px; padding: 16px; }}
  .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .card h2 {{ font-size: 16px; margin: 0; }}
  .badge {{ padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
  .badge.ok {{ background: #16442e; color: #4ade80; }}
  .badge.fail {{ background: #4a1d1d; color: #f87171; }}
  ul {{ margin: 8px 0; padding-left: 18px; font-family: monospace; font-size: 13px; }}
  .threshold {{ color: #9aa0a6; font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
  <h1>K4-L3A Day 13 Monitoring &amp; LLMOps</h1>
  <div class="meta">
    Time range: {window_start} &rarr; {window_end} (60 phut) | refresh_seconds: {refresh_seconds}
  </div>
  <div class="grid">
    {''.join(cards)}
  </div>
</body>
</html>
"""


def main() -> int:
    dashboard_cfg = yaml.safe_load(DASHBOARD_CONFIG.read_text(encoding="utf-8"))["dashboard"]
    records = load_records()
    if not records:
        print(f"Error: {LOG_PATH} rong hoac khong ton tai. Chay load_test.py truoc.")
        return 1

    panels, window_start, window_end = build_panels(records, dashboard_cfg["time_range_minutes"])
    html = render_html(panels, window_start, window_end, dashboard_cfg["refresh_seconds"])
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard rendered -> {OUTPUT_PATH}")
    for p in panels:
        ok = check_threshold(p["value"], p["threshold"])
        print(f"  [{'OK' if ok else 'BREACH'}] {p['title']}: {p['value']:.2f} {p['unit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
