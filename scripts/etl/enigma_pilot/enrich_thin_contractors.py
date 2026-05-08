"""
Pilot test: enrich thin-data state contractors via Enigma GraphQL.

Tests whether Enigma's card-transaction revenue, operating status, and
firmographic data fill the gap on private state contractors that don't
appear in Mergent or SEC. Limited to NY/VA/OH Tier A state-local matches
where master_employers has no employee count and no Mergent/SEC coverage.

Usage:
    py scripts/etl/enigma_pilot/enrich_thin_contractors.py --pick-only
    py scripts/etl/enigma_pilot/enrich_thin_contractors.py --limit 1 --query minimal
    py scripts/etl/enigma_pilot/enrich_thin_contractors.py --limit 50 --query full
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection  # noqa: E402

ENV_PATH = PROJECT_ROOT / ".env"
OUT_DIR = Path(__file__).resolve().parent / "output"
ENIGMA_URL = "https://api.enigma.com/graphql"


def read_api_key() -> str:
    """Read 'Enigma API Key' from .env (var name has spaces)."""
    if not ENV_PATH.exists():
        raise SystemExit(f"Missing .env at {ENV_PATH}")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() in ("Enigma API Key", "ENIGMA_API_KEY"):
            return value.strip().strip('"').strip("'")
    raise SystemExit("Enigma API Key not found in .env")


CANDIDATE_SQL = """
SELECT
    mts.master_id,
    mts.display_name,
    mts.city,
    mts.state,
    mts.zip,
    mts.naics,
    slm.contract_row_count,
    slm.source_count,
    slm.last_award_date
FROM mv_target_scorecard mts
JOIN state_local_contracts_master_matches slm ON slm.master_id = mts.master_id
WHERE mts.state IN ('NY','VA','OH')
  AND slm.match_tier = 'tier_A_auto_merge'
  AND (mts.effective_employee_count IS NULL OR mts.effective_employee_count = 0)
  AND NOT mts.has_mergent
  AND NOT mts.has_sec
  AND mts.display_name IS NOT NULL
  AND LENGTH(mts.display_name) > 3
  AND mts.city IS NOT NULL
  AND LENGTH(mts.city) > 1
ORDER BY slm.contract_row_count DESC
LIMIT %s OFFSET %s;
"""


# Minimal query: name + address only. Core tier (~1 credit/entity).
QUERY_MINIMAL = """
query Search($name: String!, $state: String!, $city: String) {
  search(searchInput: {
    name: $name,
    entityType: OPERATING_LOCATION,
    address: { state: $state, city: $city }
  }) {
    __typename
    ... on OperatingLocation {
      id
      names(first: 1) { edges { node { name } } }
      addresses(first: 1) {
        edges { node { fullAddress city state zip } }
      }
    }
  }
}
"""

# Full query: BRAND entity type — much higher recall than OPERATING_LOCATION
# (Rumpke/OST went 0→1 by switching). Pulls Plus-tier card transactions,
# industries (NAICS/SIC/MCC), legal entities, all operating locations, and
# affiliated brands (parent/sub signal).
QUERY_FULL = """
query Enrich($name: String!, $state: String!, $city: String) {
  search(searchInput: {
    name: $name,
    entityType: BRAND,
    address: { state: $state, city: $city }
  }) {
    __typename
    ... on Brand {
      id
      names(first: 3) { edges { node { name } } }
      websites(first: 3) { edges { node { website domain } } }
      industries(first: 5) {
        edges { node { industryCode industryType industryDesc } }
      }
      cardTransactions(first: 8) {
        edges {
          node {
            quantityType
            period
            projectedQuantity
            periodStartDate
            periodEndDate
          }
        }
      }
      legalEntities(first: 2) {
        edges {
          node {
            id
            names(first: 1) { edges { node { name } } }
            types(first: 1) { edges { node { legalEntityType } } }
          }
        }
      }
      operatingLocations(first: 4) {
        edges {
          node {
            id
            addresses(first: 1) {
              edges { node { fullAddress city state zip } }
            }
            phoneNumbers(first: 1) { edges { node { phoneNumber } } }
          }
        }
      }
      affiliatedBrands(first: 5) {
        edges {
          node { id names(first: 1) { edges { node { name } } } }
        }
      }
    }
  }
}
"""


def fetch_candidates(limit: int, offset: int) -> list[dict]:
    rows = []
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(CANDIDATE_SQL, (limit, offset))
        cols = [c[0] for c in cur.description]
        for r in cur.fetchall():
            rows.append(dict(zip(cols, r)))
    return rows


def call_enigma(api_key: str, query: str, variables: dict, timeout: int = 30):
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"query": query, "variables": variables}
    resp = requests.post(ENIGMA_URL, headers=headers, json=payload, timeout=timeout)
    return {
        "status_code": resp.status_code,
        "headers": {k: v for k, v in resp.headers.items()
                    if k.lower().startswith(("x-", "ratelimit", "credit"))},
        "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
    }


def _edges(node, field):
    return ((node or {}).get(field) or {}).get("edges") or []


def _first(node, field):
    edges = _edges(node, field)
    return edges[0]["node"] if edges else {}


def _all(node, field):
    return [e["node"] for e in _edges(node, field)]


def parse_search_result(body: dict) -> dict:
    """Extract a flat summary from the Enigma response (Brand-shaped)."""
    out = {"errors": body.get("errors"), "match_count": 0, "best_match": None}
    data = (body or {}).get("data") or {}
    hits = data.get("search") or []
    if isinstance(hits, dict):
        hits = [hits]
    out["match_count"] = len(hits)
    if not hits:
        return out

    h = hits[0]

    legal = _first(h, "legalEntities")
    legal_name = (_first(legal, "names") or {}).get("name", "") if legal else ""
    legal_type = (_first(legal, "types") or {}).get("legalEntityType", "") if legal else ""

    locs = []
    for ln in _all(h, "operatingLocations"):
        addr = _first(ln, "addresses")
        phone = _first(ln, "phoneNumbers")
        locs.append({
            "address": addr.get("fullAddress") if addr else None,
            "city": addr.get("city") if addr else None,
            "state": addr.get("state") if addr else None,
            "zip": addr.get("zip") if addr else None,
            "phone": phone.get("phoneNumber") if phone else None,
        })

    industries = [
        {
            "code": n.get("industryCode"),
            "type": n.get("industryType"),
            "desc": n.get("industryDesc"),
        }
        for n in _all(h, "industries")
    ]
    affiliates = [
        (_first(b, "names") or {}).get("name", "")
        for b in _all(h, "affiliatedBrands")
    ]

    out["best_match"] = {
        "id": h.get("id"),
        "typename": h.get("__typename"),
        "name": (_first(h, "names") or {}).get("name"),
        "websites": [n.get("domain") or n.get("website") for n in _all(h, "websites")],
        "industries": industries,
        "card_transactions": _all(h, "cardTransactions"),
        "legal_entity_name": legal_name,
        "legal_entity_type": legal_type,
        "operating_locations": locs,
        "affiliated_brands": affiliates,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--query", choices=["minimal", "full"], default="minimal")
    ap.add_argument("--pick-only", action="store_true",
                    help="Print candidates and exit (no API calls)")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="Seconds between API calls")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidates = fetch_candidates(args.limit, args.offset)
    print(f"[fetch] {len(candidates)} candidates (limit={args.limit}, offset={args.offset})")

    cand_csv = OUT_DIR / f"candidates_{ts}.csv"
    with cand_csv.open("w", newline="", encoding="utf-8") as f:
        if candidates:
            w = csv.DictWriter(f, fieldnames=list(candidates[0].keys()))
            w.writeheader()
            for r in candidates:
                w.writerow({k: ("" if v is None else str(v)) for k, v in r.items()})
    print(f"[saved] candidates -> {cand_csv}")

    for i, r in enumerate(candidates[:5], 1):
        print(f"  {i:>2}. [{r['state']}] {r['display_name']!s:50.50} "
              f"city={r['city']} naics={r['naics']} rows={r['contract_row_count']}")
    if len(candidates) > 5:
        print(f"  ... +{len(candidates)-5} more")

    if args.pick_only:
        return

    api_key = read_api_key()
    query = QUERY_MINIMAL if args.query == "minimal" else QUERY_FULL
    print(f"[enigma] using query={args.query}, sleeping {args.sleep}s between calls")

    results = []
    raw_path = OUT_DIR / f"results_{args.query}_{ts}.jsonl"
    summary_path = OUT_DIR / f"summary_{args.query}_{ts}.csv"
    with raw_path.open("w", encoding="utf-8") as raw_f:
        for i, cand in enumerate(candidates, 1):
            variables = {
                "name": cand["display_name"],
                "state": cand["state"],
                "city": cand["city"] or None,
            }
            print(f"[{i}/{len(candidates)}] {cand['display_name']!s:50.50} ", end="", flush=True)
            try:
                resp = call_enigma(api_key, query, variables)
            except Exception as e:
                print(f"FAIL ({e})")
                resp = {"status_code": -1, "error": str(e), "headers": {}, "body": {}}

            parsed = parse_search_result(resp.get("body") or {}) if resp.get("status_code") == 200 else {
                "errors": resp.get("body"),
                "match_count": 0,
                "best_match": None,
            }
            entry = {
                "master_id": cand["master_id"],
                "input": variables,
                "candidate": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in cand.items()},
                "http_status": resp["status_code"],
                "headers": resp["headers"],
                "raw": resp.get("body"),
                "parsed": parsed,
            }
            raw_f.write(json.dumps(entry, default=str) + "\n")
            results.append(entry)

            if resp["status_code"] == 200:
                hit = parsed["match_count"] > 0
                bm = parsed.get("best_match") or {}
                if hit:
                    web = (bm.get("websites") or ["-"])[0] or "-"
                    cards = len(bm.get("card_transactions") or [])
                    locs = len(bm.get("operating_locations") or [])
                    inds = len(bm.get("industries") or [])
                    affs = len(bm.get("affiliated_brands") or [])
                    print(f"OK  matches={parsed['match_count']} web={web!s:25.25} "
                          f"locs={locs} card_txns={cards} ind={inds} aff={affs}")
                else:
                    print("OK  matches=0")
            else:
                print(f"HTTP {resp['status_code']}")

            time.sleep(args.sleep)

    # Summary CSV
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "master_id", "input_name", "input_state", "http_status",
            "match_count", "matched_name", "first_website", "first_phone",
            "first_address", "naics_code", "n_industries", "n_card_txns",
            "card_revenue_12m", "card_txns_12m", "n_locations",
            "n_affiliated_brands", "legal_entity_name", "legal_entity_type",
            "errors",
        ])
        for e in results:
            bm = (e["parsed"].get("best_match") or {})
            cards = bm.get("card_transactions") or []
            rev_12m = ""
            txns_12m = ""
            for c in cards:
                qt = c.get("quantityType")
                if qt == "card_revenue_amount" and c.get("period") == "12m":
                    rev_12m = c.get("projectedQuantity") or c.get("rawQuantity") or ""
                if qt == "card_transactions_count" and c.get("period") == "12m":
                    txns_12m = c.get("projectedQuantity") or c.get("rawQuantity") or ""
            inds = bm.get("industries") or []
            naics_code = ""
            for i in inds:
                t = (i.get("type") or "").lower()
                if "naics" in t:
                    naics_code = i.get("code") or ""
                    break
            locs = bm.get("operating_locations") or []
            first_loc = locs[0] if locs else {}
            w.writerow([
                e["master_id"],
                e["input"]["name"],
                e["input"]["state"],
                e["http_status"],
                e["parsed"]["match_count"],
                bm.get("name") or "",
                (bm.get("websites") or [""])[0] or "",
                first_loc.get("phone") or "",
                first_loc.get("address") or "",
                naics_code,
                len(inds),
                len(cards),
                rev_12m,
                txns_12m,
                len(locs),
                len(bm.get("affiliated_brands") or []),
                bm.get("legal_entity_name") or "",
                bm.get("legal_entity_type") or "",
                json.dumps(e["parsed"].get("errors")) if e["parsed"].get("errors") else "",
            ])

    # Final stats
    n = len(results)
    def has(field):
        def _f(e):
            v = (e["parsed"].get("best_match") or {}).get(field)
            return bool(v)
        return _f
    hits = sum(1 for e in results if e["parsed"]["match_count"] > 0)
    with_web = sum(1 for e in results if any((e["parsed"].get("best_match") or {}).get("websites") or []))
    with_cards = sum(1 for e in results if (e["parsed"].get("best_match") or {}).get("card_transactions"))
    with_locs = sum(1 for e in results if (e["parsed"].get("best_match") or {}).get("operating_locations"))
    with_inds = sum(1 for e in results if (e["parsed"].get("best_match") or {}).get("industries"))
    with_legal = sum(1 for e in results if (e["parsed"].get("best_match") or {}).get("legal_entity_name"))
    with_aff = sum(1 for e in results if (e["parsed"].get("best_match") or {}).get("affiliated_brands"))
    print()
    print(f"[stats] tested={n}")
    print(f"[stats] hits (any match)        = {hits}/{n} ({100*hits/n:.0f}%)")
    print(f"[stats] with websites           = {with_web}/{n} ({100*with_web/n:.0f}%)")
    print(f"[stats] with industries         = {with_inds}/{n} ({100*with_inds/n:.0f}%)")
    print(f"[stats] with operating_locations= {with_locs}/{n} ({100*with_locs/n:.0f}%)")
    print(f"[stats] with card_transactions  = {with_cards}/{n} ({100*with_cards/n:.0f}%)")
    print(f"[stats] with legal_entity_name  = {with_legal}/{n} ({100*with_legal/n:.0f}%)")
    print(f"[stats] with affiliated_brands  = {with_aff}/{n} ({100*with_aff/n:.0f}%)")
    print(f"[saved] raw    -> {raw_path}")
    print(f"[saved] summary-> {summary_path}")


if __name__ == "__main__":
    main()
