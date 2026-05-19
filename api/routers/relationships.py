"""
SEC 10-K relationship-link endpoints for the master profile.

Closes the 24Q "Missing" tier:
  Q16 Suppliers   -> /api/employers/master/{master_id}/suppliers
  Q19 Customers   -> /api/employers/master/{master_id}/customers
  Q17 Distribution-> /api/employers/master/{master_id}/distribution-partners

All three are thin wrappers around `sec_10k_relationship_links`, which is
populated by a 10-K text-mining loader (built in parallel). Each row links
a parent master to either:
  - a child master (when the named text was matched by exact / trigram /
    alias to an existing master_employer), or
  - a free-text mention only (child_master_id IS NULL, match_method
    'unmatched') so we still surface what the filing said even if we
    haven't deduped the counterparty yet.

We join back to `sec_10k_extracted_entities` for the source filing
context (CIK, accession_number, filing_date) and the original sentence
the entity was extracted from.

Defensive design notes:
  - If the relationship_links / extracted_entities tables don't exist
    yet (fresh deployment, loader not yet run), every endpoint returns
    the empty `items: []` shape with HTTP 200 -- not 500 -- so the
    frontend renders an empty card instead of an error.
  - 404 only if `master_id` itself is unknown in `master_employers`.
    Empty links for a known master is `items: []`, status 200.
  - `stale = true` when MAX(source_filing_date) for this master's links
    is older than 18 months (10-K filings are annual, so anything older
    than the most recent fiscal year is conventionally stale).

Indexes the loader must create for fast lookup:
  CREATE INDEX ON sec_10k_relationship_links (parent_master_id, relationship_type);
  CREATE INDEX ON sec_10k_relationship_links (source_entity_id);
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db


router = APIRouter()

DEFAULT_LIMIT = 20
MAX_LIMIT = 200

# 10-K data is annual. Anything older than 18 months is stale.
STALE_DAYS = 18 * 30  # ~547 days


def _tables_exist(cur) -> bool:
    """Return True iff both backing tables exist.

    Either one missing -> empty shape, not 500. We check both because
    the endpoints can technically render without the entities table
    (just no context strings) but we'd rather wait for the full pair.
    """
    cur.execute(
        """
        SELECT to_regclass('sec_10k_relationship_links') AS l,
               to_regclass('sec_10k_extracted_entities') AS e
        """
    )
    row = cur.fetchone()
    return bool(row and row.get("l") and row.get("e"))


def _safe_iso(d) -> Optional[str]:
    if d is None:
        return None
    if hasattr(d, "isoformat"):
        try:
            return d.isoformat()
        except Exception:  # pragma: no cover
            return None
    return str(d)


def _today_utc() -> date:
    return datetime.now(tz=timezone.utc).date()


def _is_stale(latest_filing: Optional[date]) -> bool:
    """A relationship set is stale when the most recent filing is more
    than STALE_DAYS old, OR when there is no filing date at all."""
    if latest_filing is None:
        return True
    if isinstance(latest_filing, datetime):
        latest_filing = latest_filing.date()
    return (_today_utc() - latest_filing).days > STALE_DAYS


def _empty_response(master_id: int, relationship_type: str) -> Dict[str, Any]:
    return {
        "master_id": master_id,
        "relationship_type": relationship_type,
        "source": "10-K text mining",
        "as_of": _today_utc().isoformat(),
        "items": [],
        "total_extracted": 0,
        "total_matched": 0,
        "stale": False,
    }


def _fetch_relationships(
    cur,
    master_id: int,
    relationship_type: str,
    limit: int,
) -> Dict[str, Any]:
    """Shared core for all three endpoints.

    Returns the full response dict (caller just returns it).
    """
    # Master existence check first -- 404 if unknown.
    cur.execute("SELECT 1 FROM master_employers WHERE master_id = %s", [master_id])
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Master employer not found")

    # If tables aren't loaded yet, return empty shape (not 500).
    if not _tables_exist(cur):
        return _empty_response(master_id, relationship_type)

    # Aggregates across the FULL link set (not truncated by limit).
    cur.execute(
        """
        SELECT
          COUNT(*) AS total_extracted,
          COUNT(*) FILTER (WHERE child_master_id IS NOT NULL) AS total_matched,
          MAX(source_filing_date) AS latest_filing
        FROM sec_10k_relationship_links
        WHERE parent_master_id = %s
          AND relationship_type = %s
        """,
        [master_id, relationship_type],
    )
    agg = cur.fetchone() or {}
    total_extracted = int(agg.get("total_extracted") or 0)
    total_matched = int(agg.get("total_matched") or 0)
    latest_filing = agg.get("latest_filing")

    if total_extracted == 0:
        return _empty_response(master_id, relationship_type)

    # Page of items, ordered by confidence DESC NULLS LAST then filing
    # date DESC. We LEFT JOIN to extracted_entities since some rows may
    # have a NULL source_entity_id (defensive: the loader currently
    # always sets it, but we don't want a missing entity row to drop
    # the link from the response).
    cur.execute(
        """
        SELECT
          l.child_master_id,
          l.child_text,
          l.confidence,
          l.match_method,
          l.source_filing_date,
          e.cik,
          e.accession_number,
          e.context AS context_text,
          m.canonical_name AS child_canonical_name
        FROM sec_10k_relationship_links l
        LEFT JOIN sec_10k_extracted_entities e ON e.id = l.source_entity_id
        LEFT JOIN master_employers m ON m.master_id = l.child_master_id
        WHERE l.parent_master_id = %s
          AND l.relationship_type = %s
        ORDER BY l.confidence DESC NULLS LAST,
                 l.source_filing_date DESC NULLS LAST,
                 l.id ASC
        LIMIT %s
        """,
        [master_id, relationship_type, limit],
    )
    rows = cur.fetchall() or []

    items: List[Dict[str, Any]] = []
    for r in rows:
        # Display name preference:
        #   1. matched master's canonical_name (clean, deduped)
        #   2. child_text (raw 10-K mention)
        name = r.get("child_canonical_name") or r.get("child_text")
        items.append(
            {
                "child_master_id": r.get("child_master_id"),
                "name": name,
                "confidence": (
                    float(r["confidence"]) if r.get("confidence") is not None else None
                ),
                "match_method": r.get("match_method") or "unmatched",
                "source_filing": {
                    "cik": r.get("cik"),
                    "accession_number": r.get("accession_number"),
                    "filing_date": _safe_iso(r.get("source_filing_date")),
                },
                "context": r.get("context_text"),
            }
        )

    return {
        "master_id": master_id,
        "relationship_type": relationship_type,
        "source": "10-K text mining",
        "as_of": _today_utc().isoformat(),
        "items": items,
        "total_extracted": total_extracted,
        "total_matched": total_matched,
        "stale": _is_stale(latest_filing),
    }


@router.get("/api/employers/master/{master_id}/suppliers")
def get_master_suppliers(
    master_id: int,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """24Q-16: Suppliers named in the company's 10-K filings."""
    with get_db() as conn:
        with conn.cursor() as cur:
            return _fetch_relationships(cur, master_id, "supplier", limit)


@router.get("/api/employers/master/{master_id}/customers")
def get_master_customers(
    master_id: int,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """24Q-19: Customers named in the company's 10-K filings."""
    with get_db() as conn:
        with conn.cursor() as cur:
            return _fetch_relationships(cur, master_id, "customer", limit)


@router.get("/api/employers/master/{master_id}/distribution-partners")
def get_master_distribution_partners(
    master_id: int,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """24Q-17: Distribution partners named in the company's 10-K filings."""
    with get_db() as conn:
        with conn.cursor() as cur:
            return _fetch_relationships(cur, master_id, "distribution", limit)
