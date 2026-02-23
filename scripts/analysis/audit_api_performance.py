import argparse
import os
import statistics
import sys
import time
from math import ceil

import requests

ENDPOINTS = [
    "/api/employers/unified-search?q=walmart",
    "/api/employers/unified-search?q=xyz",
    "/api/employers/unified-search?q=a",
    "/api/scorecard/unified?limit=50",
    "/api/scorecard/unified/stats",
    "/api/employers/data-coverage",
]


def p95(values):
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, ceil(0.95 * len(s)) - 1))
    return s[idx]


def main():
    parser = argparse.ArgumentParser(description="Audit API endpoint response times")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="API base URL")
    parser.add_argument(
        "--output",
        default="docs/investigations/API_PERFORMANCE_AUDIT.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    os.environ["DISABLE_AUTH"] = "true"
    headers = {"DISABLE_AUTH": "true"}

    session = requests.Session()

    # connectivity check
    try:
        session.get(args.base_url + ENDPOINTS[0], headers=headers, timeout=8)
    except requests.RequestException:
        msg = "API not running on port 8001, start with: py -m uvicorn api.main:app --port 8001"
        print(msg)
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("# API Performance Audit\n\n")
            f.write(msg + "\n")
        return

    rows = []
    for ep in ENDPOINTS:
        times = []
        sizes = []
        statuses = []
        for _ in range(5):
            t0 = time.perf_counter()
            try:
                resp = session.get(args.base_url + ep, headers=headers, timeout=20)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                times.append(elapsed_ms)
                sizes.append(len(resp.content or b""))
                statuses.append(resp.status_code)
            except requests.RequestException:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                times.append(elapsed_ms)
                sizes.append(0)
                statuses.append("ERR")

        avg_ms = statistics.mean(times) if times else 0.0
        row = {
            "endpoint": ep,
            "min_ms": min(times) if times else 0.0,
            "max_ms": max(times) if times else 0.0,
            "avg_ms": avg_ms,
            "p95_ms": p95(times),
            "avg_size": int(statistics.mean(sizes)) if sizes else 0,
            "status_set": ",".join(str(s) for s in sorted(set(statuses), key=lambda x: str(x))),
            "slow": avg_ms > 500.0,
        }
        rows.append(row)

    lines = []
    lines.append("# API Performance Audit")
    lines.append("")
    lines.append(f"Base URL: `{args.base_url}`")
    lines.append("")
    lines.append("| Endpoint | min ms | max ms | avg ms | p95 ms | avg bytes | status(es) | Flag |")
    lines.append("|---|---:|---:|---:|---:|---:|---|---|")
    for r in rows:
        flag = "slow" if r["slow"] else "ok"
        lines.append(
            f"| {r['endpoint']} | {r['min_ms']:.1f} | {r['max_ms']:.1f} | {r['avg_ms']:.1f} | {r['p95_ms']:.1f} | {r['avg_size']:,} | {r['status_set']} | {flag} |"
        )

    slow_count = sum(1 for r in rows if r["slow"])
    lines.append("")
    lines.append(f"Slow endpoints (>500ms avg): **{slow_count}**")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {args.output}")
    print(f"Slow endpoints: {slow_count}")


if __name__ == "__main__":
    main()
