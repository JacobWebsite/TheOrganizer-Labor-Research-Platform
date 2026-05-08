"""
Submit, poll, and download a CPS Outgoing Rotation Group (ORG) extract from IPUMS.

The IPUMS extract system is asynchronous: submission returns an extract number,
the server processes for 5-30 min, then a fixed-width .dat.gz and DDI XML are
available for download. This script handles all three phases.

Usage
-----
  # Default: submit a 2019-2023 ORG extract, poll every 60s, download when ready
  py scripts/etl/cps_pull_org_extract.py

  # Submit only (writes extract number to .extract_number, exits)
  py scripts/etl/cps_pull_org_extract.py --submit-only

  # Resume a previously submitted extract (e.g. after process restart)
  py scripts/etl/cps_pull_org_extract.py --extract-number 42

  # Smaller/larger window
  py scripts/etl/cps_pull_org_extract.py --years 2022,2023

Output
------
  New Data sources 2_27/cps_org/
    cps_org_extract_<N>.dat.gz   -- fixed-width data, one row per person-month
    cps_org_extract_<N>.xml      -- DDI codebook (variable layout + value labels)
    cps_org_extract_<N>.json     -- extract definition (for reproducibility)

Notes
-----
* CPS basic monthly samples are named cps{YYYY}_{MM}b. ORG records are a subset
  identified by EARNWT > 0 (filter at load time).
* IPUMS rate limit is 100 requests/minute. We poll once per 60s — well below.
* The API key in .env has spaces in its name ("IPUMS API Key") so we read .env
  manually rather than relying on shell env-var loading.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
OUTPUT_DIR = PROJECT_ROOT / "New Data sources 2_27" / "cps_org"

API_BASE = "https://api.ipums.org/extracts"
API_VERSION = "2"
COLLECTION = "cps"

# Variables for union density + demographics + geography + industry/occupation.
# These are IPUMS CPS variable names. Identifiers (YEAR, MONTH, SERIAL, etc.)
# are added automatically by IPUMS. Note: CPS uses Census industry/occupation
# codes; there is no separate INDNAICS or OCCSOC variable. Crosswalk to NAICS/SOC
# at curate time using IND/OCC tables.
VARIABLES = [
    # Weights
    "WTFINL",        # final basic-monthly weight
    "EARNWT",        # earnings weight (ORG-only; >0 identifies ORG records)
    # Geography
    "STATEFIP",      # state FIPS
    "METFIPS",       # MSA/CBSA FIPS (post-2014)
    "COUNTY",        # county FIPS (where disclosed; suppressed for many small counties)
    # Industry/occupation (Census codes; crosswalk to NAICS/SOC later)
    "IND",           # current Census industry code
    "IND1990",       # harmonized 1990 Census industry (for time-series consistency)
    "OCC",           # current Census occupation code
    "OCC2010",       # harmonized 2010 occupation
    # Demographics
    "AGE",
    "SEX",
    "RACE",
    "HISPAN",
    "EDUC",
    # Labor force / worker class
    "LABFORCE",
    "EMPSTAT",
    "WKSTAT",
    "CLASSWKR",
    "UHRSWORKT",     # usual hours worked
    # Union (ORG only — blank otherwise)
    "UNION",         # 1=non-member, 2=member, 3=covered non-member
    # Earnings (ORG only)
    "EARNWEEK",      # weekly earnings (top-coded)
    "HOURWAGE",      # hourly wage (paid-by-hour respondents only)
    "PAIDHOUR",      # paid by the hour flag
]


def parse_args():
    ap = argparse.ArgumentParser(description="Submit/poll/download an IPUMS CPS ORG extract")
    ap.add_argument("--years", default="2019,2020,2021,2022,2023,2024",
                    help="Comma-separated years (default: 2019-2024)")
    ap.add_argument("--description", default="LDT CPS ORG extract — sub-state union density",
                    help="Extract description (visible in IPUMS dashboard)")
    ap.add_argument("--submit-only", action="store_true",
                    help="Submit and exit; resume later via --extract-number")
    ap.add_argument("--extract-number", type=int, default=None,
                    help="Skip submission and resume polling/downloading this extract")
    ap.add_argument("--poll-interval", type=int, default=60,
                    help="Seconds between status polls (default 60)")
    ap.add_argument("--max-wait", type=int, default=3600,
                    help="Give up polling after this many seconds (default 1h)")
    return ap.parse_args()


def read_api_key() -> str:
    """Read 'IPUMS API Key' from .env (the literal name has spaces)."""
    if not ENV_PATH.exists():
        raise SystemExit(f"Missing .env at {ENV_PATH}")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() in ("IPUMS API Key", "IPUMS_API_KEY", "IPUMS_APIKEY"):
            return value.strip().strip('"').strip("'")
    raise SystemExit("IPUMS API Key not found in .env")


def fetch_available_samples(api_key: str) -> list[dict]:
    """Page through the CPS samples metadata endpoint and return all entries."""
    out: list[dict] = []
    page = 1
    while True:
        url = f"https://api.ipums.org/metadata/{COLLECTION}/samples?version={API_VERSION}&pageNumber={page}&pageSize=2500"
        r = requests.get(url, headers={"Authorization": api_key}, timeout=30)
        r.raise_for_status()
        body = r.json()
        out.extend(body.get("data", []))
        if len(out) >= body.get("totalCount", 0):
            break
        page += 1
        if page > 20:
            break
    return out


def build_samples(api_key: str, years: list[int]) -> list[str]:
    """
    Pick one CPS sample per year-month using the live metadata.
    Prefers basic-monthly (_b) over supplement (_s). Both contain the ORG
    earnings/union variables; _b is the cleaner, smaller file.
    """
    available = fetch_available_samples(api_key)
    by_ym: dict[str, str] = {}  # "YYYY_MM" -> chosen sample name
    for s in available:
        name = s.get("name", "")
        if not name.startswith("cps"):
            continue
        # cps2019_03b -> ('2019','03','b')
        try:
            y_part = name[3:7]
            m_part = name[8:10]
            suffix = name[10:]
            if int(y_part) not in years:
                continue
        except ValueError:
            continue
        ym = f"{y_part}_{m_part}"
        # Prefer _b over _s if both present
        existing = by_ym.get(ym)
        if existing is None or (suffix == "b" and not existing.endswith("b")):
            by_ym[ym] = name
    return [by_ym[k] for k in sorted(by_ym)]


def headers(api_key: str) -> dict:
    return {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }


def submit_extract(api_key: str, years: list[int], description: str) -> int:
    samples = build_samples(api_key, years)
    payload = {
        "description": description,
        "dataStructure": {"rectangular": {"on": "P"}},  # person-record format
        "dataFormat": "fixed_width",
        "samples": {s: {} for s in samples},
        "variables": {v: {} for v in VARIABLES},
    }
    url = f"{API_BASE}?collection={COLLECTION}&version={API_VERSION}"
    print(f"Submitting extract: {len(samples)} samples, {len(VARIABLES)} variables")
    print(f"  years={years} samples=[{samples[0]}...{samples[-1]}]")
    r = requests.post(url, headers=headers(api_key), data=json.dumps(payload), timeout=60)
    if r.status_code not in (200, 201):
        raise SystemExit(f"Submit failed: {r.status_code} {r.text}")
    body = r.json()
    extract_n = body.get("number") or body.get("id")
    if not extract_n:
        raise SystemExit(f"Could not parse extract number from response: {body}")
    print(f"  -> extract #{extract_n} submitted (status={body.get('status', 'unknown')})")
    # Persist extract number for resume
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".extract_number").write_text(str(extract_n))
    (OUTPUT_DIR / f"cps_org_extract_{extract_n}.json").write_text(json.dumps(payload, indent=2))
    return extract_n


def poll_status(api_key: str, extract_n: int, poll_s: int, max_wait_s: int) -> dict:
    url = f"{API_BASE}/{extract_n}?collection={COLLECTION}&version={API_VERSION}"
    deadline = time.time() + max_wait_s
    while True:
        r = requests.get(url, headers=headers(api_key), timeout=30)
        if r.status_code != 200:
            raise SystemExit(f"Status check failed: {r.status_code} {r.text}")
        body = r.json()
        status = body.get("status", "unknown")
        print(f"  extract #{extract_n} status={status}")
        if status == "completed":
            return body
        if status in ("failed", "canceled"):
            raise SystemExit(f"Extract {extract_n} ended in status {status}: {body}")
        if time.time() > deadline:
            raise SystemExit(f"Polling exceeded max_wait={max_wait_s}s; resume with --extract-number {extract_n}")
        time.sleep(poll_s)


def download_files(extract_body: dict, extract_n: int) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    links = extract_body.get("downloadLinks", {})
    data_url = (links.get("data") or {}).get("url")
    ddi_url = (links.get("ddiCodebook") or {}).get("url")
    if not data_url or not ddi_url:
        raise SystemExit(f"No download links in body: {extract_body}")

    api_key = read_api_key()  # auth on download too
    data_path = OUTPUT_DIR / f"cps_org_extract_{extract_n}.dat.gz"
    ddi_path  = OUTPUT_DIR / f"cps_org_extract_{extract_n}.xml"

    for url, dest in [(data_url, data_path), (ddi_url, ddi_path)]:
        print(f"Downloading {url} -> {dest.name}")
        with requests.get(url, headers={"Authorization": api_key}, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  -> {dest.name} ({size_mb:,.1f} MB)")

    # Spot-check the .dat.gz: count lines without decompressing fully
    with gzip.open(data_path, "rt", encoding="utf-8", errors="replace") as f:
        line_count = sum(1 for _ in f)
    print(f"  data file line count: {line_count:,}")
    return data_path, ddi_path


def main():
    args = parse_args()
    api_key = read_api_key()

    if args.extract_number is not None:
        extract_n = args.extract_number
        print(f"Resuming extract #{extract_n}")
    else:
        years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
        extract_n = submit_extract(api_key, years, args.description)
        if args.submit_only:
            print(f"Submitted #{extract_n}; exit. Resume with --extract-number {extract_n}")
            return

    body = poll_status(api_key, extract_n, args.poll_interval, args.max_wait)
    download_files(body, extract_n)
    print("Done.")


if __name__ == "__main__":
    main()
