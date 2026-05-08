"""
LDA (Lobbying Disclosure Act) endpoint for the master profile.

24Q-39 Political. For a given master employer, returns a summary of
federal lobbying spend + top issues + registrants engaged, sourced from
LDA filings the firm filed (or hired registrants to file on its behalf).

Resolution path:
  master_id
    -> master_employer_source_ids (source_system='lda', source_id=lda_client.id)
    -> lda_filings (joined by client_id)
    -> lda_lobbying_activities (joined by filing_uuid for issue codes)

`income` is the registrant's revenue from this client; `expenses` is
self-reported lobbying spend when the client files its own LD-2. We sum
both to capture total reported lobbying activity (a filing typically
has one or the other, not both).

Codex finding from 2026-05-02 wrapup applied: the endpoint guards against
the data tables not existing yet, so it returns the empty `is_matched=False`
shape on a fresh deployment without the matcher ever having run.
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


def _tables_exist(cur) -> bool:
    """Defensive: return False if lda_filings/lda_clients haven't been
    loaded yet so the endpoint emits the empty shape rather than 500ing."""
    cur.execute(
        """
        SELECT to_regclass('lda_filings') AS f, to_regclass('lda_clients') AS c
        """
    )
    row = cur.fetchone()
    return bool(row and row.get("f") and row.get("c"))


def _empty_shape() -> Dict[str, Any]:
    return {
        "summary": {
            "is_matched": False,
            "client_name_used": None,
            "match_method": None,
            "match_confidence": None,
            "total_filings": 0,
            "total_spend": 0.0,
            "active_quarters": 0,
            "registrants_count": 0,
            "latest_period": None,
        },
        "quarterly_spend": [],
        "top_issues": [],
        "top_registrants": [],
    }


# Period sort key: chronological ASC then DESC at render time.
_PERIOD_RANK = {
    "first_quarter": 1,
    "second_quarter": 2,
    "third_quarter": 3,
    "fourth_quarter": 4,
    "mid_year": 2,    # LD-203 mid-year contributions report
    "year_end": 4,    # LD-203 year-end report
}


@router.get("/api/employers/master/{master_id}/lobbying")
def get_master_lobbying(
    master_id: int,
    issue_limit: int = Query(default=10, ge=1, le=50),
    registrant_limit: int = Query(default=10, ge=1, le=50),
    quarter_limit: int = Query(default=20, ge=1, le=80),
) -> Dict[str, Any]:
    """Return LDA lobbying summary + quarterly spend + top issues + top
    registrants for a master employer."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 404 on unknown master.
            cur.execute("SELECT 1 FROM master_employers WHERE master_id = %s", [master_id])
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Master employer not found")

            # If LDA tables don't exist yet, emit the empty shape -- not a 500.
            if not _tables_exist(cur):
                return _empty_shape()

            # Resolve master -> set of LDA client_ids via the link table.
            cur.execute(
                """
                SELECT sid.source_id, sid.match_confidence
                FROM master_employer_source_ids sid
                WHERE sid.master_id = %s AND sid.source_system = 'lda'
                """,
                [master_id],
            )
            link_rows = cur.fetchall() or []

            if not link_rows:
                return _empty_shape()

            client_ids = [r["source_id"] for r in link_rows]
            best_conf = max(
                (float(r["match_confidence"]) for r in link_rows
                 if r.get("match_confidence") is not None),
                default=None,
            )

            # Resolve display name from lda_clients (latest by name length).
            cur.execute(
                """
                SELECT name
                FROM lda_clients
                WHERE id::text = ANY(%s)
                ORDER BY length(name) DESC, name
                LIMIT 1
                """,
                [client_ids],
            )
            cli_row = cur.fetchone()
            client_name_used = cli_row["name"] if cli_row else None
            match_method = "exact" if best_conf and best_conf >= 0.999 else "trigram"

            # Aggregate filings: total spend, # filings, registrants.
            cur.execute(
                """
                SELECT
                  COUNT(*) AS total_filings,
                  COUNT(DISTINCT registrant_id) AS registrants_count,
                  COUNT(DISTINCT (filing_year, filing_period)) AS active_quarters,
                  SUM(COALESCE(income, 0) + COALESCE(expenses, 0)) AS total_spend,
                  MAX(filing_year) AS latest_year
                FROM lda_filings
                WHERE client_id::text = ANY(%s)
                """,
                [client_ids],
            )
            agg = cur.fetchone() or {}

            if not agg.get("total_filings"):
                # Linked but no filings yet (edge case if matcher ran before
                # loader for this client).
                return {
                    "summary": {
                        "is_matched": True,
                        "client_name_used": client_name_used,
                        "match_method": match_method,
                        "match_confidence": best_conf,
                        "total_filings": 0,
                        "total_spend": 0.0,
                        "active_quarters": 0,
                        "registrants_count": 0,
                        "latest_period": None,
                    },
                    "quarterly_spend": [],
                    "top_issues": [],
                    "top_registrants": [],
                }

            # Latest filing period (year, period) for the freshness footer.
            cur.execute(
                """
                SELECT filing_year, filing_period, filing_period_display
                FROM lda_filings
                WHERE client_id::text = ANY(%s)
                ORDER BY filing_year DESC,
                         CASE filing_period
                           WHEN 'fourth_quarter' THEN 4
                           WHEN 'third_quarter'  THEN 3
                           WHEN 'second_quarter' THEN 2
                           WHEN 'first_quarter'  THEN 1
                           WHEN 'year_end'       THEN 4
                           WHEN 'mid_year'       THEN 2
                           ELSE 0
                         END DESC
                LIMIT 1
                """,
                [client_ids],
            )
            lp = cur.fetchone()
            latest_period = (
                f"{lp['filing_period_display']} {lp['filing_year']}"
                if lp and lp.get("filing_period_display")
                else None
            )

            # Quarterly spend timeline.
            cur.execute(
                """
                SELECT
                  filing_year,
                  filing_period,
                  filing_period_display,
                  COUNT(*) AS filings,
                  SUM(COALESCE(income, 0) + COALESCE(expenses, 0)) AS spend
                FROM lda_filings
                WHERE client_id::text = ANY(%s)
                GROUP BY filing_year, filing_period, filing_period_display
                ORDER BY filing_year DESC,
                         CASE filing_period
                           WHEN 'fourth_quarter' THEN 4
                           WHEN 'third_quarter'  THEN 3
                           WHEN 'second_quarter' THEN 2
                           WHEN 'first_quarter'  THEN 1
                           WHEN 'year_end'       THEN 4
                           WHEN 'mid_year'       THEN 2
                           ELSE 0
                         END DESC
                LIMIT %s
                """,
                [client_ids, quarter_limit],
            )
            quarterly = [
                {
                    "year": r["filing_year"],
                    "period": r["filing_period"],
                    "period_display": r["filing_period_display"],
                    "filings": int(r["filings"]),
                    "spend": float(r["spend"] or 0),
                }
                for r in cur.fetchall() or []
            ]

            # Top issues across all activity rows for these filings.
            cur.execute(
                """
                SELECT
                  a.general_issue_code,
                  a.general_issue_code_display,
                  COUNT(*) AS activity_count,
                  COUNT(DISTINCT a.filing_uuid) AS filings_count
                FROM lda_lobbying_activities a
                JOIN lda_filings f ON f.filing_uuid = a.filing_uuid
                WHERE f.client_id::text = ANY(%s)
                  AND a.general_issue_code IS NOT NULL
                GROUP BY a.general_issue_code, a.general_issue_code_display
                ORDER BY filings_count DESC, activity_count DESC
                LIMIT %s
                """,
                [client_ids, issue_limit],
            )
            top_issues = [
                {
                    "code": r["general_issue_code"],
                    "display": r["general_issue_code_display"],
                    "filings": int(r["filings_count"]),
                    "activity_count": int(r["activity_count"]),
                }
                for r in cur.fetchall() or []
            ]

            # Top registrants by total spend on this client.
            cur.execute(
                """
                SELECT
                  r.id AS registrant_id,
                  r.name AS registrant_name,
                  r.state AS registrant_state,
                  COUNT(*) AS filings,
                  SUM(COALESCE(f.income, 0) + COALESCE(f.expenses, 0)) AS spend
                FROM lda_filings f
                JOIN lda_registrants r ON r.id = f.registrant_id
                WHERE f.client_id::text = ANY(%s)
                GROUP BY r.id, r.name, r.state
                ORDER BY spend DESC NULLS LAST, filings DESC
                LIMIT %s
                """,
                [client_ids, registrant_limit],
            )
            top_registrants = [
                {
                    "registrant_id": r["registrant_id"],
                    "name": r["registrant_name"],
                    "state": r["registrant_state"],
                    "filings": int(r["filings"]),
                    "spend": float(r["spend"] or 0),
                }
                for r in cur.fetchall() or []
            ]

    return {
        "summary": {
            "is_matched": True,
            "client_name_used": client_name_used,
            "match_method": match_method,
            "match_confidence": best_conf,
            "total_filings": int(agg["total_filings"]),
            "total_spend": float(agg["total_spend"] or 0),
            "active_quarters": int(agg["active_quarters"] or 0),
            "registrants_count": int(agg["registrants_count"] or 0),
            "latest_period": latest_period,
        },
        "quarterly_spend": quarterly,
        "top_issues": top_issues,
        "top_registrants": top_registrants,
    }
