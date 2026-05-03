"""
SEC Form 13F institutional ownership endpoint for the master profile.

24Q-9: Stockholders. For a given master employer, returns the top
institutional investors that report holding its stock, sourced from SEC
Form 13F bulk data.

Resolution path:
  master_id
    -> sec_13f_issuer_master_map (issuer name match)
    -> sec_13f_holdings (filtered to that issuer name, latest period)
    -> sec_13f_submissions (filer name + CIK)

We collapse multiple holdings per filer per quarter into a single row
(sum of value across share types). The card cares about "who owns me"
not "what kind of share class".
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db

router = APIRouter()

DEFAULT_LIMIT = 25
MAX_LIMIT = 200


def _safe_iso(d) -> Optional[str]:
    if d is None:
        return None
    if hasattr(d, "isoformat"):
        try:
            return d.isoformat()
        except Exception:  # pragma: no cover
            return None
    return str(d)


@router.get("/api/employers/master/{master_id}/institutional-owners")
def get_master_institutional_owners(
    master_id: int,
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Max owners returned in the owners array (sorted by value DESC)",
    ),
) -> Dict[str, Any]:
    """Return SEC 13F institutional owners + summary for a master employer.

    Response shape:
        {
            "summary": {
                "is_matched": bool,
                "issuer_name_used": str | null,
                "match_method": str | null,
                "match_confidence": float | null,
                "total_owners": int,        # distinct filers in latest period
                "total_value": float,       # sum across owners (USD)
                "total_shares": int,        # sum across owners (SH-type only)
                "latest_period": iso | null,
            },
            "owners": [
                {
                    "filer_name": str,
                    "filer_cik": str,
                    "filer_state": str,
                    "value": float,
                    "shares": int,
                    "share_type": "SH" | "PRN",
                    "investment_discretion": str | null,
                    "period_of_report": iso str,
                },
                ...
            ],
        }
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 404 on unknown master, mirroring the other 24Q endpoints.
            cur.execute("SELECT 1 FROM master_employers WHERE master_id = %s", [master_id])
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Master employer not found")

            # Codex 2026-05-02 finding #3 fix: gate every read on the
            # presence of the 13F tables. If the matcher (or even the
            # loader) hasn't run yet, return the empty `is_matched=False`
            # shape rather than raising UndefinedTable -> 500.
            cur.execute(
                """
                SELECT to_regclass('sec_13f_issuer_master_map') AS m,
                       to_regclass('sec_13f_holdings')          AS h,
                       to_regclass('sec_13f_submissions')       AS s
                """
            )
            tbl = cur.fetchone() or {}
            if not (tbl.get("m") and tbl.get("h") and tbl.get("s")):
                return {
                    "summary": {
                        "is_matched": False,
                        "issuer_name_used": None,
                        "match_method": None,
                        "match_confidence": None,
                        "total_owners": 0,
                        "total_value": 0.0,
                        "total_shares": 0,
                        "latest_period": None,
                    },
                    "owners": [],
                }

            # Step 1: Resolve master to a 13F issuer-name match.
            cur.execute(
                """
                SELECT name_of_issuer_norm, canonical_name, match_method, match_confidence
                FROM sec_13f_issuer_master_map
                WHERE master_id = %s
                ORDER BY match_confidence DESC, name_of_issuer_norm
                LIMIT 1
                """,
                [master_id],
            )
            mapping = cur.fetchone()

            if not mapping:
                # No issuer match -> nothing to show. Return an empty shape
                # so the card can render its 'no match' state without 404.
                return {
                    "summary": {
                        "is_matched": False,
                        "issuer_name_used": None,
                        "match_method": None,
                        "match_confidence": None,
                        "total_owners": 0,
                        "total_value": 0.0,
                        "total_shares": 0,
                        "latest_period": None,
                    },
                    "owners": [],
                }

            issuer_norm = mapping["name_of_issuer_norm"]
            match_method = mapping["match_method"]
            match_conf = float(mapping["match_confidence"]) if mapping["match_confidence"] is not None else None
            issuer_canonical = mapping["canonical_name"]

            # Step 2: Latest period of report we have for this issuer.
            cur.execute(
                """
                SELECT MAX(s.period_of_report) AS latest_period
                FROM sec_13f_holdings h
                JOIN sec_13f_submissions s ON s.accession_number = h.accession_number
                WHERE h.name_of_issuer_norm = %s
                """,
                [issuer_norm],
            )
            row = cur.fetchone()
            latest_period = row["latest_period"] if row else None

            if not latest_period:
                return {
                    "summary": {
                        "is_matched": True,
                        "issuer_name_used": issuer_canonical,
                        "match_method": match_method,
                        "match_confidence": match_conf,
                        "total_owners": 0,
                        "total_value": 0.0,
                        "total_shares": 0,
                        "latest_period": None,
                    },
                    "owners": [],
                }

            # Step 3: Aggregate by filer for the latest period.
            #
            # Codex 2026-05-02 finding #4 fix: collapse to one accession
            # per (filer_cik, period) before summing. Without this, a
            # filer with both an original 13F-HR and a 13F-HR/A amendment
            # would appear as two rows in the response and inflate
            # `total_owners`. We use DISTINCT ON to pick the latest
            # filing_date per filer (amendments typically post later).
            #
            # Also fixes a previously-undetected column-not-found bug:
            # the prior version referenced `s.investment_discretion`
            # which is not on sec_13f_submissions (only on
            # sec_13f_holdings). We surface investment_discretion from
            # the holding row instead via MAX().
            cur.execute(
                """
                WITH latest_filing_per_cik AS (
                    SELECT DISTINCT ON (s.filer_cik)
                        s.accession_number,
                        s.filer_cik,
                        s.filer_name,
                        s.filer_state
                    FROM sec_13f_submissions s
                    WHERE s.period_of_report = %s
                      AND EXISTS (
                          SELECT 1 FROM sec_13f_holdings h
                          WHERE h.accession_number = s.accession_number
                            AND h.name_of_issuer_norm = %s
                      )
                    ORDER BY s.filer_cik, s.filing_date DESC NULLS LAST,
                             s.accession_number DESC
                )
                SELECT
                  l.filer_cik,
                  l.filer_name,
                  l.filer_state,
                  SUM(COALESCE(h.value, 0))                              AS total_value,
                  SUM(CASE WHEN h.shares_or_principal_amount_type = 'SH'
                           THEN COALESCE(h.shares_or_principal_amount, 0)
                           ELSE 0 END)                                   AS total_shares,
                  MAX(h.investment_discretion)                           AS holding_discretion
                FROM latest_filing_per_cik l
                JOIN sec_13f_holdings h ON h.accession_number = l.accession_number
                WHERE h.name_of_issuer_norm = %s
                GROUP BY l.filer_cik, l.filer_name, l.filer_state
                ORDER BY total_value DESC NULLS LAST, l.filer_name
                """,
                [latest_period, issuer_norm, issuer_norm],
            )
            rows = cur.fetchall() or []

    # InvestmentDiscretion comes from the per-holding row in INFOTABLE.tsv
    # (post finding #4 fix the same field is no longer pulled from the
    # submission cover page, which doesn't carry it in our schema).
    owners = []
    total_value = 0.0
    total_shares = 0
    for r in rows[:limit]:
        v = float(r["total_value"] or 0)
        sh = int(r["total_shares"] or 0)
        owners.append(
            {
                "filer_name": r["filer_name"],
                "filer_cik": r["filer_cik"],
                "filer_state": r["filer_state"],
                "value": v,
                "shares": sh,
                "share_type": "SH" if sh > 0 else "PRN",
                "investment_discretion": r.get("holding_discretion"),
                "period_of_report": _safe_iso(latest_period),
            }
        )
    # Aggregate totals across the FULL match set, not the truncated array.
    for r in rows:
        total_value += float(r["total_value"] or 0)
        total_shares += int(r["total_shares"] or 0)

    return {
        "summary": {
            "is_matched": True,
            "issuer_name_used": issuer_canonical,
            "match_method": match_method,
            "match_confidence": match_conf,
            "total_owners": len(rows),
            "total_value": total_value,
            "total_shares": total_shares,
            "latest_period": _safe_iso(latest_period),
        },
        "owners": owners,
    }
