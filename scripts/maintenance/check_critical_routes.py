"""
Verify all critical routes are present in the running API.

Reads config/critical_routes.txt (newline-separated route paths matching
keys in /openapi.json `paths`) and asserts each appears in the live API.

Usage:
    py scripts/maintenance/check_critical_routes.py
    py scripts/maintenance/check_critical_routes.py --base-url http://localhost:8001

Exit codes:
    0  All critical routes present.
    1  One or more routes missing (release-blocking).
    2  Could not reach the API (e.g. server down).

Background: R7-6 (2026-04-26) caught the family-rollup endpoint missing
from the running API despite being in the codebase. The Starbucks
0-elections regression went unnoticed for ~24 hours. This script is the
deployment-hygiene check (M-1) added to the release checklist to prevent
that class of bug from recurring.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "critical_routes.txt"
DEFAULT_BASE_URL = "http://localhost:8001"


def load_manifest(path: Path) -> list[str]:
    if not path.exists():
        print(f"ERROR: manifest not found at {path}", file=sys.stderr)
        sys.exit(2)
    routes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        routes.append(s)
    return routes


def fetch_openapi_paths(base_url: str) -> set[str]:
    url = base_url.rstrip("/") + "/openapi.json"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.load(resp)
    except urllib.error.URLError as exc:
        print(f"ERROR: could not reach {url}: {exc}", file=sys.stderr)
        sys.exit(2)
    return set(data.get("paths", {}).keys())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                        help=f"Path to critical routes manifest (default: {DEFAULT_MANIFEST})")
    args = parser.parse_args()

    expected = load_manifest(Path(args.manifest))
    live = fetch_openapi_paths(args.base_url)

    missing = [r for r in expected if r not in live]
    present = [r for r in expected if r in live]

    print(f"Checked {len(expected)} critical routes against {len(live)} live routes at {args.base_url}")
    for route in present:
        print(f"  OK    {route}")
    for route in missing:
        print(f"  MISS  {route}", file=sys.stderr)

    if missing:
        print(f"\nFAIL: {len(missing)} critical route(s) missing from running API.", file=sys.stderr)
        print("This usually means the API needs a restart to pick up new code,", file=sys.stderr)
        print("or the route has been removed/renamed without updating the manifest.", file=sys.stderr)
        return 1

    print(f"\nOK: all {len(expected)} critical routes present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
