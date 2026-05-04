"""
FEC contributions endpoint for the master profile (24Q-41 / 24Q-24 Political).

Pulls two distinct flows of money:

  1. PAC contributions: donations FROM the company-affiliated political
     committees (cmte_id linked via master_employer_source_ids
     source_system='fec') TO candidates. The classic 'corporate PAC' flow.

  2. Employee individual contributions: donations BY individuals naming the
     company in `fec_individual_contributions.employer_norm`. Captures the
     bottom-up flow of money from execs/employees that's often much larger
     than the formal PAC (e.g. SpaceX = $323M employee, no big PAC).

The endpoint returns:
  - summary totals (PAC + employee)
  - top recipient candidates (for PAC contributions)
  - top recipient committees (for PAC contributions to other PACs)
  - top employee donors by amount
  - yearly breakdown for the time-series chart

The lobbying router (24Q-39) handles the LDA side; the political-activity
card on the frontend should call both endpoints and combine.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db


router = APIRouter()

DEFAULT_TOP = 10
MAX_TOP = 50

# Cap the employee-donation rollup at this many distinct employer_norms.
# Each scan over fec_individual_contributions (144M rows) is ~5-10 seconds,
# so we want to short-circuit if the master has no plausible name match.
_EMP_NORM_LOOKUP_LIMIT = 5


def _tables_exist(cur) -> bool:
    cur.execute(
        """
        SELECT to_regclass('fec_committees') AS c,
               to_regclass('fec_committee_contributions') AS cc,
               to_regclass('fec_individual_contributions') AS ic
        """
    )
    row = cur.fetchone()
    return bool(row and row.get("c") and row.get("cc") and row.get("ic"))


def _empty_shape() -> Dict[str, Any]:
    return {
        "summary": {
            "is_matched": False,
            "pac_committees_count": 0,
            "pac_dollars_total": 0.0,
            "pac_recipients_count": 0,
            "employee_donations_count": 0,
            "employee_dollars_total": 0.0,
            "employer_norms_used": [],
            "latest_pac_date": None,
            "latest_employee_date": None,
        },
        "top_pac_recipients": [],
        "top_employee_donors": [],
        "yearly_breakdown": [],
    }


def _employer_name_variants(canonical_name: str) -> list[str]:
    """Return employer_norm variants to try against fec_individual_contributions.

    The seed_master_fec.py rollup joins exactly on `canonical_name =
    employer_norm`, so the most reliable lookup is the raw uppercase
    canonical_name. We additionally try a suffix-stripped variant (mirrors
    load_fec.py's _norm_employer normalisation, which catches the case where
    the canonical_name was suffix-stripped at master-build time).
    """
    import re
    if not canonical_name:
        return []
    raw = canonical_name.upper().strip()
    variants = [raw]
    # Suffix-stripped variant
    s = raw
    for suffix in (" LLC", " L.L.C.", " INC", " INC.", " CORPORATION",
                   " CORP", " CO.", " COMPANY", " LP", " LTD", " PLLC", " PC"):
        if s.endswith(suffix):
            s = s[:-len(suffix)].rstrip(" ,.")
            break
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s and s != raw:
        variants.append(s)
    return [v for v in variants if v and len(v) >= 3]


@router.get("/api/employers/master/{master_id}/fec-contributions")
def get_master_fec_contributions(
    master_id: int,
    top_recipients: int = Query(default=DEFAULT_TOP, ge=1, le=MAX_TOP),
    top_donors: int = Query(default=DEFAULT_TOP, ge=1, le=MAX_TOP),
) -> Dict[str, Any]:
    """Return PAC + employee FEC contribution summary for a master employer."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT canonical_name FROM master_employers WHERE master_id = %s", [master_id])
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Master employer not found")
            canonical_name = row["canonical_name"]

            if not _tables_exist(cur):
                return _empty_shape()

            # ---- PAC side: linked committee IDs ----
            cur.execute(
                """
                SELECT source_id FROM master_employer_source_ids
                WHERE master_id = %s AND source_system = 'fec'
                """,
                [master_id],
            )
            cmte_ids = [r["source_id"] for r in cur.fetchall() or []]

            pac_summary = {
                "pac_committees_count": len(cmte_ids),
                "pac_dollars_total": 0.0,
                "pac_recipients_count": 0,
                "latest_pac_date": None,
            }
            top_pac_recipients: list = []

            if cmte_ids:
                cur.execute(
                    """
                    SELECT
                      COALESCE(SUM(transaction_amt), 0) AS dollars_total,
                      COUNT(DISTINCT cand_id) AS recipients_count,
                      MAX(transaction_dt) AS latest_dt
                    FROM fec_committee_contributions
                    WHERE cmte_id = ANY(%s)
                    """,
                    [cmte_ids],
                )
                agg = cur.fetchone() or {}
                pac_summary["pac_dollars_total"] = float(agg.get("dollars_total") or 0)
                pac_summary["pac_recipients_count"] = int(agg.get("recipients_count") or 0)
                lpd = agg.get("latest_dt")
                pac_summary["latest_pac_date"] = lpd.isoformat() if lpd else None

                cur.execute(
                    """
                    SELECT
                      cc.cand_id,
                      ca.cand_name,
                      ca.cand_pty_affiliation,
                      ca.cand_office,
                      ca.cand_office_st,
                      COUNT(*) AS contributions,
                      SUM(cc.transaction_amt) AS dollars
                    FROM fec_committee_contributions cc
                    LEFT JOIN fec_candidates ca ON ca.cand_id = cc.cand_id
                    WHERE cc.cmte_id = ANY(%s) AND cc.cand_id IS NOT NULL
                    GROUP BY cc.cand_id, ca.cand_name, ca.cand_pty_affiliation,
                             ca.cand_office, ca.cand_office_st
                    ORDER BY dollars DESC NULLS LAST
                    LIMIT %s
                    """,
                    [cmte_ids, top_recipients],
                )
                top_pac_recipients = [
                    {
                        "cand_id": r["cand_id"],
                        "name": r["cand_name"],
                        "party": r["cand_pty_affiliation"],
                        "office": r["cand_office"],
                        "state": r["cand_office_st"],
                        "contributions": int(r["contributions"]),
                        "dollars": float(r["dollars"] or 0),
                    }
                    for r in cur.fetchall() or []
                ]

            # ---- Employee individual donations side ----
            emp_summary = {
                "employee_donations_count": 0,
                "employee_dollars_total": 0.0,
                "latest_employee_date": None,
            }
            top_employee_donors: list = []
            employer_norms_used: list = _employer_name_variants(canonical_name)

            if employer_norms_used:

                cur.execute(
                    """
                    SELECT
                      COUNT(*) AS donation_count,
                      COALESCE(SUM(transaction_amt), 0) AS dollars,
                      MAX(transaction_dt) AS latest_dt
                    FROM fec_individual_contributions
                    WHERE employer_norm = ANY(%s)
                    """,
                    [employer_norms_used],
                )
                agg = cur.fetchone() or {}
                emp_summary["employee_donations_count"] = int(agg.get("donation_count") or 0)
                emp_summary["employee_dollars_total"] = float(agg.get("dollars") or 0)
                led = agg.get("latest_dt")
                emp_summary["latest_employee_date"] = led.isoformat() if led else None

                if emp_summary["employee_donations_count"] > 0:
                    cur.execute(
                        """
                        SELECT
                          name,
                          city, state,
                          occupation,
                          COUNT(*) AS contributions,
                          SUM(transaction_amt) AS dollars
                        FROM fec_individual_contributions
                        WHERE employer_norm = ANY(%s)
                        GROUP BY name, city, state, occupation
                        ORDER BY dollars DESC NULLS LAST
                        LIMIT %s
                        """,
                        [employer_norms_used, top_donors],
                    )
                    top_employee_donors = [
                        {
                            "name": r["name"],
                            "city": r["city"],
                            "state": r["state"],
                            "occupation": r["occupation"],
                            "contributions": int(r["contributions"]),
                            "dollars": float(r["dollars"] or 0),
                        }
                        for r in cur.fetchall() or []
                    ]

            # ---- Yearly breakdown (PAC + employee combined) ----
            yearly: dict[int, dict] = {}
            if cmte_ids:
                cur.execute(
                    """
                    SELECT EXTRACT(YEAR FROM transaction_dt)::int AS yr,
                           COUNT(*) AS n,
                           SUM(transaction_amt) AS dollars
                    FROM fec_committee_contributions
                    WHERE cmte_id = ANY(%s) AND transaction_dt IS NOT NULL
                    GROUP BY yr ORDER BY yr DESC LIMIT 10
                    """,
                    [cmte_ids],
                )
                for r in cur.fetchall() or []:
                    yr = int(r["yr"])
                    yearly.setdefault(yr, {"year": yr, "pac_dollars": 0.0, "employee_dollars": 0.0})
                    yearly[yr]["pac_dollars"] = float(r["dollars"] or 0)
            if employer_norms_used and emp_summary["employee_donations_count"] > 0:
                cur.execute(
                    """
                    SELECT EXTRACT(YEAR FROM transaction_dt)::int AS yr,
                           COUNT(*) AS n,
                           SUM(transaction_amt) AS dollars
                    FROM fec_individual_contributions
                    WHERE employer_norm = ANY(%s) AND transaction_dt IS NOT NULL
                    GROUP BY yr ORDER BY yr DESC LIMIT 10
                    """,
                    [employer_norms_used],
                )
                for r in cur.fetchall() or []:
                    yr = int(r["yr"])
                    yearly.setdefault(yr, {"year": yr, "pac_dollars": 0.0, "employee_dollars": 0.0})
                    yearly[yr]["employee_dollars"] = float(r["dollars"] or 0)

            yearly_list = sorted(yearly.values(), key=lambda x: -x["year"])[:10]

    is_matched = pac_summary["pac_committees_count"] > 0 or emp_summary["employee_donations_count"] > 0
    return {
        "summary": {
            "is_matched": is_matched,
            "pac_committees_count": pac_summary["pac_committees_count"],
            "pac_dollars_total": pac_summary["pac_dollars_total"],
            "pac_recipients_count": pac_summary["pac_recipients_count"],
            "employee_donations_count": emp_summary["employee_donations_count"],
            "employee_dollars_total": emp_summary["employee_dollars_total"],
            "employer_norms_used": employer_norms_used,
            "latest_pac_date": pac_summary["latest_pac_date"],
            "latest_employee_date": emp_summary["latest_employee_date"],
        },
        "top_pac_recipients": top_pac_recipients,
        "top_employee_donors": top_employee_donors,
        "yearly_breakdown": yearly_list,
    }
