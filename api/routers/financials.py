"""SEC XBRL financial data endpoint with 990 nonprofit fallback."""

from fastapi import APIRouter
from ..database import get_db

router = APIRouter()


def _float(val):
    """Convert Decimal/numeric to float, or None."""
    if val is None:
        return None
    return float(val)


def _row_to_floats(row, keys):
    """Convert specified keys in a RealDictRow to floats."""
    return {k: _float(row.get(k)) for k in keys}


FINANCIAL_COLS = [
    "revenue", "net_income", "total_assets", "total_liabilities",
    "cash", "long_term_debt",
]


@router.get("/api/employers/{employer_id}/financials")
def get_employer_financials(employer_id: str):
    """Return SEC XBRL financials for an employer, with 990 fallback for nonprofits."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Step 1: Find SEC CIK via crosswalk
            cur.execute("""
                SELECT c.sec_cik, s.company_name, s.ticker,
                       COALESCE(c.is_public, s.is_public, FALSE) AS is_public
                FROM corporate_identifier_crosswalk c
                JOIN sec_companies s ON s.cik::int = c.sec_cik
                WHERE c.f7_employer_id = %s AND c.sec_cik IS NOT NULL
                ORDER BY c.federal_obligations DESC NULLS LAST
                LIMIT 1
            """, [employer_id])
            cw = cur.fetchone()

            sec_data = None
            trends = []
            latest = None
            revenue_growth = None
            income_growth = None

            if cw:
                cik = cw["sec_cik"]

                # Step 2: Get up to 5 years of financials
                cur.execute("""
                    SELECT fiscal_year_end, form_type, filed_date,
                           revenue, net_income, total_assets, total_liabilities,
                           cash, long_term_debt, employee_count
                    FROM sec_xbrl_financials
                    WHERE cik = %s
                    ORDER BY fiscal_year_end DESC
                    LIMIT 5
                """, [cik])
                rows = cur.fetchall()

                if rows:
                    r = rows[0]
                    rev = _float(r["revenue"])
                    ni = _float(r["net_income"])

                    latest = {
                        "fiscal_year_end": r["fiscal_year_end"].isoformat() if r["fiscal_year_end"] else None,
                        "form_type": r["form_type"],
                        **_row_to_floats(r, FINANCIAL_COLS),
                        "employee_count": r["employee_count"],
                        "profit_margin": round(ni / rev * 100, 1) if rev and ni and rev != 0 else None,
                    }

                    trends = [
                        {
                            "fiscal_year_end": row["fiscal_year_end"].isoformat() if row["fiscal_year_end"] else None,
                            "revenue": _float(row["revenue"]),
                            "net_income": _float(row["net_income"]),
                            "total_assets": _float(row["total_assets"]),
                        }
                        for row in rows
                    ]

                    # YoY growth (latest vs prior year)
                    if len(rows) >= 2:
                        prev_rev = _float(rows[1]["revenue"])
                        prev_ni = _float(rows[1]["net_income"])
                        if rev and prev_rev and prev_rev != 0:
                            revenue_growth = round((rev - prev_rev) / abs(prev_rev) * 100, 1)
                        if ni is not None and prev_ni and prev_ni != 0:
                            income_growth = round((ni - prev_ni) / abs(prev_ni) * 100, 1)

                sec_data = {
                    "cik": cik,
                    "company_name": cw["company_name"],
                    "ticker": cw["ticker"],
                    "is_public": cw["is_public"],
                }

            # Step 3: 990 fallback when no SEC financials
            n990_fallback = None
            if not latest:
                cur.execute("""
                    SELECT MAX(f.total_revenue) AS revenue,
                           MAX(f.total_assets) AS assets,
                           MAX(f.total_expenses) AS expenses
                    FROM national_990_f7_matches m
                    JOIN national_990_filers f ON f.id = m.n990_id
                    WHERE m.f7_employer_id = %s
                      AND f.total_revenue IS NOT NULL
                      AND m.score_eligible = TRUE
                """, [employer_id])
                n990 = cur.fetchone()
                if n990 and n990["revenue"]:
                    n990_fallback = {
                        "revenue": _float(n990["revenue"]),
                        "assets": _float(n990["assets"]),
                        "expenses": _float(n990["expenses"]),
                    }

            return {
                "employer_id": employer_id,
                "has_sec_financials": latest is not None,
                "has_990_financials": n990_fallback is not None,
                "source": "sec" if latest else ("990" if n990_fallback else None),
                "sec_company": sec_data,
                "latest": latest,
                "trends": trends,
                "revenue_growth_pct": revenue_growth,
                "income_growth_pct": income_growth,
                "n990_fallback": n990_fallback,
            }
