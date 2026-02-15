"""
Simple API endpoint benchmark utility.

Usage:
  py scripts/analysis/benchmark_endpoints.py --base-url http://127.0.0.1:8001 --runs 3
"""
from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass

import requests


DEFAULT_ENDPOINTS = [
    "/api/summary",
    "/api/lookups/sectors",
    "/api/employers/search?q=hospital&limit=10",
    "/api/unions/search?name=afscme&limit=10",
    "/api/nlrb/elections/search?state=CA&limit=10",
    "/api/density/by-state",
    "/api/osha/summary",
    "/api/trends/national",
    "/api/organizing/scorecard?limit=20",
]


@dataclass
class Metric:
    endpoint: str
    status: int
    p50_ms: float
    p95_ms: float
    avg_ms: float


def run_endpoint(base_url: str, endpoint: str, runs: int, timeout: int) -> Metric:
    durations = []
    status = 0
    for _ in range(runs):
        t0 = time.perf_counter()
        response = requests.get(f"{base_url}{endpoint}", timeout=timeout)
        status = response.status_code
        _ = response.text
        durations.append((time.perf_counter() - t0) * 1000)

    durations.sort()
    p50 = statistics.median(durations)
    p95_index = max(0, int(len(durations) * 0.95) - 1)
    p95 = durations[p95_index]
    avg = statistics.mean(durations)
    return Metric(endpoint, status, p50, p95, avg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark API endpoints")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    print(f"Benchmarking {len(DEFAULT_ENDPOINTS)} endpoints x {args.runs} runs")
    print(f"Base URL: {args.base_url}")
    print("")
    print("status  avg_ms   p50_ms   p95_ms   endpoint")
    print("-" * 80)

    for ep in DEFAULT_ENDPOINTS:
        try:
            m = run_endpoint(args.base_url, ep, args.runs, args.timeout)
            print(
                f"{m.status:<6}  {m.avg_ms:>7.1f}  {m.p50_ms:>7.1f}  {m.p95_ms:>7.1f}   {m.endpoint}"
            )
        except Exception as exc:
            print(f"ERROR   {'-':>7}  {'-':>7}  {'-':>7}   {ep} ({exc})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

