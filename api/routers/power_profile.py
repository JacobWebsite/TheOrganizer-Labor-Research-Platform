"""
Power Profile PDF endpoint (Week 6 C.5 of the 2026-05-04 launch roadmap).

GET /api/employers/master/{master_id}/power-profile.pdf
    -> 200 application/pdf -- 3-page organizer briefing
    -> 404 application/json -- master_id not found

The endpoint is "compose only" -- it pulls already-aggregated data from
the same DB views/tables the per-card endpoints use (board, executives,
SEC 13F, FEC, LDA, EPA, mv_target_scorecard, etc.) and hands a flat
payload dict to `render_power_profile_pdf` in the renderer service. We
don't HTTP-call the per-card endpoints (that would risk N+1 round trips
and complicates auth context).

Sections that have no data render with a "No data available" line, never
silently blank.

# 24Q-1 Basic / 24Q-3 Facilities / 24Q-4 Workforce / 24Q-5 Financials /
# 24Q-7 Executives / 24Q-8 Management / 24Q-9 Stockholders /
# 24Q-10/14 Board / 24Q-12 Parent / 24Q-20 Safety / 24Q-21 Environmental /
# 24Q-22 Regulatory/Legal / 24Q-24/41 Political / 24Q-39 Lobbying.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..database import get_db
from ..services.director_name_filter import is_likely_real_director_name
from ..services.power_profile_renderer import render_power_profile_pdf


router = APIRouter()
_log = logging.getLogger("api.power_profile")


# Savepoint wrapper for "best-effort" sub-queries.
#
# psycopg2 aborts the WHOLE transaction on any failed query (e.g. a column
# that doesn't exist on this DB build, or a type-mismatch error). For the
# Power Profile we want each optional sub-query to be able to fail without
# poisoning the next one. A SAVEPOINT does exactly that: if the inner
# query fails we ROLLBACK TO the savepoint, the outer transaction stays
# alive, and the next pull keeps working.
class _Savepoint:
    """Use as `with _Savepoint(cur, "name"): cur.execute(...)`. On any
    exception the savepoint is rolled back and the exception swallowed."""

    def __init__(self, cur, name: str):
        self.cur = cur
        self.name = name

    def __enter__(self):
        self.cur.execute(f"SAVEPOINT {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.cur.execute(f"RELEASE SAVEPOINT {self.name}")
            return False
        # Roll back to the savepoint and swallow the exception.
        self.cur.execute(f"ROLLBACK TO SAVEPOINT {self.name}")
        _log.warning("optional pull '%s' failed: %s", self.name, exc_val)
        return True


# ----- per-section pullers (each takes the same `cur` and `master_id`) -

def _pull_identity(cur, master_id: int) -> Optional[Dict[str, Any]]:
    """Identity + flags + ultimate parent (chained via SEC CIK or DUNS)."""
    cur.execute(
        """
        SELECT m.master_id, m.canonical_name, m.display_name,
               m.city, m.state, m.zip, m.naics, m.employee_count,
               m.employee_count_source, m.ein, m.industry_text,
               m.is_public, m.is_federal_contractor, m.is_nonprofit,
               m.data_quality_score, m.is_union,
               (SELECT COUNT(DISTINCT source_system)
                  FROM master_employer_source_ids
                 WHERE master_id = m.master_id) AS source_count
        FROM master_employers m
        WHERE m.master_id = %s
        """,
        [master_id],
    )
    row = cur.fetchone()
    if not row:
        return None

    out: Dict[str, Any] = dict(row)

    # Ultimate parent via corporate_ultimate_parents (keyed on entity_cik
    # / entity_duns, not master_id). We try CIK first (most reliable for
    # SEC filers), fall back to DUNS. Best-effort -- the table may not be
    # populated, or the entity_cik column on this DB might be int (we
    # cast both sides to text to dodge the type-mismatch error). Each
    # attempt uses its own savepoint so a column-not-found or type
    # mismatch in one branch doesn't poison the next.
    parent = None
    with _Savepoint(cur, "ultimate_parent_cik"):
        cur.execute(
            """
            SELECT cup.ultimate_parent_name, cup.chain_depth
            FROM master_employer_source_ids sid
            JOIN corporate_ultimate_parents cup
              ON cup.entity_cik::text = sid.source_id
            WHERE sid.master_id = %s
              AND sid.source_system = 'sec'
              AND cup.ultimate_parent_name IS NOT NULL
              AND cup.ultimate_parent_name <> ''
            ORDER BY cup.chain_depth DESC NULLS LAST
            LIMIT 1
            """,
            [master_id],
        )
        parent = cur.fetchone()
    if not parent:
        with _Savepoint(cur, "ultimate_parent_duns"):
            cur.execute(
                """
                SELECT cup.ultimate_parent_name, cup.chain_depth
                FROM master_employer_source_ids sid
                JOIN corporate_ultimate_parents cup
                  ON cup.entity_duns::text = sid.source_id
                WHERE sid.master_id = %s
                  AND sid.source_system IN ('mergent', 'duns')
                  AND cup.ultimate_parent_name IS NOT NULL
                ORDER BY cup.chain_depth DESC NULLS LAST
                LIMIT 1
                """,
                [master_id],
            )
            parent = cur.fetchone()
    if parent:
        out["ultimate_parent_name"] = parent.get("ultimate_parent_name")
        out["ultimate_parent_chain_depth"] = parent.get("chain_depth")

    return out


def _pull_financials(cur, master_id: int) -> Dict[str, Any]:
    """Latest revenue / assets. Tries SEC submissions first (public), then 990
    (nonprofits). Both paths surface a fiscal year for the renderer."""
    out: Dict[str, Any] = {
        "latest_revenue": None,
        "latest_assets": None,
        "financials_fiscal_year": None,
    }
    # SEC path -- we only have aggregates in mv_target_scorecard for some
    # paths but the canonical detailed financials live elsewhere; reuse
    # mv_target_scorecard's n990_* columns as the cross-source fallback
    # because they're already populated for nonprofits.
    with _Savepoint(cur, "financials"):
        cur.execute(
            """
            SELECT n990_revenue, n990_assets
            FROM mv_target_scorecard
            WHERE master_id = %s
            """,
            [master_id],
        )
        row = cur.fetchone()
        if row:
            if row.get("n990_revenue"):
                out["latest_revenue"] = float(row["n990_revenue"])
            if row.get("n990_assets"):
                out["latest_assets"] = float(row["n990_assets"])
    return out


def _pull_institutional_owners(cur, master_id: int) -> Dict[str, Any]:
    """Top-5 13F filers for the issuer the master is mapped to (latest period)."""
    out: Dict[str, Any] = {
        "owners": [],
        "period": None,
        "total_value": 0.0,
        "count": 0,
    }
    cur.execute(
        """
        SELECT to_regclass('sec_13f_issuer_master_map') AS m,
               to_regclass('sec_13f_holdings')          AS h,
               to_regclass('sec_13f_submissions')       AS s
        """
    )
    tbl = cur.fetchone() or {}
    if not (tbl.get("m") and tbl.get("h") and tbl.get("s")):
        return out

    cur.execute(
        """
        SELECT name_of_issuer_norm
        FROM sec_13f_issuer_master_map
        WHERE master_id = %s
        ORDER BY match_confidence DESC NULLS LAST
        LIMIT 1
        """,
        [master_id],
    )
    mapping = cur.fetchone()
    if not mapping:
        return out
    issuer_norm = mapping["name_of_issuer_norm"]

    cur.execute(
        """
        SELECT MAX(s.period_of_report) AS latest_period
        FROM sec_13f_holdings h
        JOIN sec_13f_submissions s ON s.accession_number = h.accession_number
        WHERE h.name_of_issuer_norm = %s
        """,
        [issuer_norm],
    )
    period_row = cur.fetchone() or {}
    latest_period = period_row.get("latest_period")
    if not latest_period:
        return out

    cur.execute(
        """
        WITH latest_filing_per_cik AS (
            SELECT DISTINCT ON (s.filer_cik)
                s.accession_number, s.filer_cik, s.filer_name, s.filer_state
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
          l.filer_cik, l.filer_name, l.filer_state,
          SUM(COALESCE(h.value, 0)) AS total_value,
          SUM(CASE WHEN h.shares_or_principal_amount_type = 'SH'
                   THEN COALESCE(h.shares_or_principal_amount, 0) ELSE 0 END) AS total_shares
        FROM latest_filing_per_cik l
        JOIN sec_13f_holdings h ON h.accession_number = l.accession_number
        WHERE h.name_of_issuer_norm = %s
        GROUP BY l.filer_cik, l.filer_name, l.filer_state
        ORDER BY total_value DESC NULLS LAST
        LIMIT 25
        """,
        [latest_period, issuer_norm, issuer_norm],
    )
    rows = cur.fetchall() or []
    owners: List[Dict[str, Any]] = []
    for r in rows:
        owners.append({
            "filer_name": r["filer_name"],
            "filer_state": r["filer_state"],
            "value": float(r["total_value"] or 0),
            "shares": int(r["total_shares"] or 0),
        })

    out["owners"] = owners
    out["count"] = len(rows)
    out["total_value"] = sum(float(r["total_value"] or 0) for r in rows)
    out["period"] = latest_period.isoformat() if hasattr(latest_period, "isoformat") else str(latest_period)
    return out


def _pull_fec(cur, master_id: int, canonical_name: str) -> Dict[str, Any]:
    """PAC + employee donation rollup. Mirrors fec_contributions.py exactly
    so totals tie out, but only fetches summary numbers (no top-recipients
    detail -- the PDF only needs the totals + counts)."""
    out: Dict[str, Any] = {
        "pac_dollars_total": 0.0,
        "employee_dollars_total": 0.0,
        "pac_committees_count": 0,
        "pac_recipients_count": 0,
        "employee_donations_count": 0,
    }
    cur.execute(
        """
        SELECT to_regclass('fec_committees') AS c,
               to_regclass('fec_committee_contributions') AS cc,
               to_regclass('fec_individual_contributions') AS ic
        """
    )
    tbl = cur.fetchone() or {}
    if not (tbl.get("c") and tbl.get("cc") and tbl.get("ic")):
        return out

    cur.execute(
        """
        SELECT source_id FROM master_employer_source_ids
        WHERE master_id = %s AND source_system = 'fec'
        """,
        [master_id],
    )
    cmte_ids = [r["source_id"] for r in cur.fetchall() or []]
    out["pac_committees_count"] = len(cmte_ids)
    if cmte_ids:
        cur.execute(
            """
            SELECT COALESCE(SUM(transaction_amt), 0) AS dollars,
                   COUNT(DISTINCT cand_id) AS recipients
            FROM fec_committee_contributions
            WHERE cmte_id = ANY(%s)
            """,
            [cmte_ids],
        )
        agg = cur.fetchone() or {}
        out["pac_dollars_total"] = float(agg.get("dollars") or 0)
        out["pac_recipients_count"] = int(agg.get("recipients") or 0)

    # Employee donations rollup -- canonical_name -> employer_norm.
    if canonical_name:
        import re
        raw = canonical_name.upper().strip()
        variants = [raw]
        s = raw
        for suffix in (" LLC", " L.L.C.", " INC", " INC.", " CORPORATION",
                       " CORP", " CO.", " COMPANY", " LP", " LTD", " PLLC", " PC"):
            if s.endswith(suffix):
                s = s[: -len(suffix)].rstrip(" ,.")
                break
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s and s != raw:
            variants.append(s)
        variants = [v for v in variants if v and len(v) >= 3]
        if variants:
            cur.execute(
                """
                SELECT COUNT(*) AS donations,
                       COALESCE(SUM(transaction_amt), 0) AS dollars
                FROM fec_individual_contributions
                WHERE employer_norm = ANY(%s)
                """,
                [variants],
            )
            agg = cur.fetchone() or {}
            out["employee_donations_count"] = int(agg.get("donations") or 0)
            out["employee_dollars_total"] = float(agg.get("dollars") or 0)
    return out


def _pull_lobbying(cur, master_id: int) -> Dict[str, Any]:
    """LDA totals. Mirrors lobbying.py shape (subset)."""
    out: Dict[str, Any] = {
        "total_spend": 0.0,
        "total_filings": 0,
        "active_quarters": 0,
        "registrants_count": 0,
        "client_name_used": None,
    }
    cur.execute(
        """
        SELECT to_regclass('lda_filings') AS f, to_regclass('lda_clients') AS c
        """
    )
    tbl = cur.fetchone() or {}
    if not (tbl.get("f") and tbl.get("c")):
        return out
    cur.execute(
        """
        SELECT source_id FROM master_employer_source_ids
        WHERE master_id = %s AND source_system = 'lda'
        """,
        [master_id],
    )
    client_ids = [r["source_id"] for r in cur.fetchall() or []]
    if not client_ids:
        return out

    cur.execute(
        """
        SELECT
          COUNT(*) AS filings,
          COUNT(DISTINCT registrant_id) AS registrants,
          COUNT(DISTINCT (filing_year, filing_period)) AS quarters,
          SUM(COALESCE(income, 0) + COALESCE(expenses, 0)) AS spend
        FROM lda_filings
        WHERE client_id::text = ANY(%s)
        """,
        [client_ids],
    )
    agg = cur.fetchone() or {}
    out["total_filings"] = int(agg.get("filings") or 0)
    out["registrants_count"] = int(agg.get("registrants") or 0)
    out["active_quarters"] = int(agg.get("quarters") or 0)
    out["total_spend"] = float(agg.get("spend") or 0)

    cur.execute(
        """
        SELECT name FROM lda_clients
        WHERE id::text = ANY(%s)
        ORDER BY length(name) DESC, name LIMIT 1
        """,
        [client_ids],
    )
    cli = cur.fetchone()
    if cli:
        out["client_name_used"] = cli.get("name")
    return out


_ACS_NO_HS_CODES = ("00", "01", "02", "03", "04", "05", "06", "07")
_ACS_BACHELORS_PLUS_CODES = ("12", "13", "14", "15")


def _pull_demographics(cur, master_id: int) -> Dict[str, Any]:
    """ACS aggregate by state x NAICS via cur_acs_workforce_demographics.

    Uses the same shape as `api.routers.demographics._build_demographics`,
    but rolled up to a single-row summary the PDF can print. We don't
    invoke the V12 QWI model here -- that path needs zip_county_crosswalk
    + state_fips_map and is overkill for a printable briefing. ACS state-
    x-NAICS4 (or NAICS2 fallback) is the same data the demographics router
    falls back to and is sufficient for organizer prep.
    """
    out: Dict[str, Any] = {"has_data": False}
    cur.execute(
        "SELECT state, naics FROM master_employers WHERE master_id = %s",
        [master_id],
    )
    me = cur.fetchone()
    if not me or not me.get("state") or not me.get("naics"):
        return out

    cur.execute("SELECT to_regclass('cur_acs_workforce_demographics') AS t")
    tbl = cur.fetchone() or {}
    if not tbl.get("t"):
        return out

    # state_fips lookup
    try:
        cur.execute(
            "SELECT state_fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1",
            [me["state"]],
        )
        row = cur.fetchone()
    except Exception:
        return out
    if not row:
        return out
    state_fips = row["state_fips"]
    naics = me["naics"]

    # Try NAICS4 first, then NAICS2 fallback (matches demographics.py logic).
    for naics4 in [(naics[:4] if naics and len(naics) >= 4 else None), None]:
        where = ["state_fips = %s"]
        params: List[Any] = [state_fips]
        if naics4:
            where.append("naics4 = %s")
            params.append(naics4)
        where_sql = " AND ".join(where)

        try:
            # Single roll-up query -- one scan, all the percentages we need.
            cur.execute(
                f"""
                SELECT
                  SUM(weighted_workers) AS total,
                  SUM(weighted_workers) FILTER (WHERE sex = '2') AS w_female,
                  SUM(weighted_workers) FILTER (
                    WHERE race <> '1' OR hispanic <> '0'
                  ) AS w_minority,
                  SUM(weighted_workers) FILTER (WHERE age_bucket = 'u25') AS w_under_25,
                  SUM(weighted_workers) FILTER (WHERE age_bucket IN ('55_64','65p')) AS w_55_plus,
                  SUM(weighted_workers) FILTER (WHERE education = ANY(%s)) AS w_no_hs,
                  SUM(weighted_workers) FILTER (WHERE education = ANY(%s)) AS w_bach_plus,
                  SUM(weighted_workers * (1 - COALESCE(pct_any_insurance, 0)/100.0))
                    AS w_uninsured_est
                FROM cur_acs_workforce_demographics
                WHERE {where_sql}
                """,
                [list(_ACS_NO_HS_CODES), list(_ACS_BACHELORS_PLUS_CODES)] + params,
            )
            row = cur.fetchone()
        except Exception as exc:
            _log.warning("ACS aggregate failed (naics4=%s): %s", naics4, exc)
            continue
        if not row or not row.get("total") or float(row["total"]) <= 0:
            continue
        total = float(row["total"])

        def pct(col: str) -> Optional[float]:
            v = row.get(col)
            return (float(v) / total * 100.0) if v is not None else None

        out.update({
            "has_data": True,
            "method": f"acs_state_naics{4 if naics4 else 2}",
            "total_workforce": int(round(total)),
            "pct_female": pct("w_female"),
            "pct_minority": pct("w_minority"),
            "pct_under_25": pct("w_under_25"),
            "pct_55_plus": pct("w_55_plus"),
            "pct_no_hs": pct("w_no_hs"),
            "pct_bachelors_plus": pct("w_bach_plus"),
            "pct_uninsured": pct("w_uninsured_est"),
            "vintage_year": "ACS 2022 5-yr PUMS",
        })

        # Top occupations within the same slice.
        try:
            cur.execute(
                f"""
                SELECT soc_code, SUM(weighted_workers) AS w
                FROM cur_acs_workforce_demographics
                WHERE {where_sql} AND soc_code IS NOT NULL
                GROUP BY soc_code
                ORDER BY w DESC
                LIMIT 5
                """,
                params,
            )
            rows = cur.fetchall() or []
            top_occs = []
            for r in rows:
                top_occs.append({
                    "name": r.get("soc_code"),
                    "pct": float(r["w"]) / total * 100.0,
                })
            out["top_occupations"] = top_occs
        except Exception as exc:
            _log.warning("ACS top occupations failed: %s", exc)
        break
    return out


def _pull_enforcement(cur, master_id: int) -> Dict[str, Any]:
    """OSHA / NLRB / WHD / EPA top-line totals via mv_target_scorecard +
    targeted enforcement-record lookups for "worst record" labels."""
    out: Dict[str, Any] = {"osha": {}, "nlrb": {}, "whd": {}, "epa": {}}
    cur.execute(
        """
        SELECT
          osha_estab_count, osha_total_violations, osha_total_penalties,
          osha_latest_inspection,
          nlrb_election_count, nlrb_win_count, nlrb_loss_count,
          nlrb_latest_election, nlrb_ulp_count, nlrb_latest_ulp,
          whd_case_count, whd_total_backwages, whd_total_penalties,
          whd_latest_finding, whd_repeat_violator
        FROM mv_target_scorecard
        WHERE master_id = %s
        """,
        [master_id],
    )
    sc = cur.fetchone() or {}

    osha = out["osha"]
    osha["inspection_count"] = int(sc.get("osha_estab_count") or 0)
    osha["violation_count"] = int(sc.get("osha_total_violations") or 0)
    osha["penalty_total"] = float(sc.get("osha_total_penalties") or 0)
    if sc.get("osha_latest_inspection"):
        osha["worst_inspection_label"] = (
            f"Last inspection: {sc['osha_latest_inspection']}"
        )

    # Pull worst inspection details (highest single penalty) for narrative.
    with _Savepoint(cur, "worst_osha"):
        cur.execute(
            """
            SELECT o.estab_name, o.site_city, o.site_state,
                   COALESCE(SUM(vs.total_penalties), 0) AS pen
            FROM master_employer_source_ids sid
            JOIN osha_establishments o ON o.establishment_id::text = sid.source_id
            LEFT JOIN osha_violation_summary vs ON vs.establishment_id = o.establishment_id
            WHERE sid.master_id = %s AND sid.source_system = 'osha'
            GROUP BY o.estab_name, o.site_city, o.site_state
            ORDER BY pen DESC
            LIMIT 1
            """,
            [master_id],
        )
        worst = cur.fetchone()
        if worst and float(worst["pen"]) > 0:
            label = (
                f"{worst['estab_name']} "
                f"({worst.get('site_city') or ''}, {worst.get('site_state') or ''}) -- "
                f"${float(worst['pen']):,.0f}"
            )
            osha["worst_inspection_label"] = label

    nlrb = out["nlrb"]
    nlrb["election_count"] = int(sc.get("nlrb_election_count") or 0)
    nlrb["union_wins"] = int(sc.get("nlrb_win_count") or 0)
    nlrb["union_losses"] = int(sc.get("nlrb_loss_count") or 0)
    nlrb["ulp_count"] = int(sc.get("nlrb_ulp_count") or 0)
    if sc.get("nlrb_latest_election"):
        nlrb["latest_election"] = str(sc["nlrb_latest_election"])
        nlrb["latest_label"] = f"Latest election {sc['nlrb_latest_election']}"
    if sc.get("nlrb_latest_ulp"):
        nlrb["latest_ulp"] = str(sc["nlrb_latest_ulp"])
        if not nlrb.get("latest_label"):
            nlrb["latest_label"] = f"Latest ULP {sc['nlrb_latest_ulp']}"

    whd = out["whd"]
    whd["case_count"] = int(sc.get("whd_case_count") or 0)
    whd["backwages_total"] = float(sc.get("whd_total_backwages") or 0)
    whd["penalty_total"] = float(sc.get("whd_total_penalties") or 0)
    whd["repeat_violator"] = bool(sc.get("whd_repeat_violator")) if sc.get("whd_repeat_violator") is not None else False
    if sc.get("whd_latest_finding"):
        whd["worst_record"] = f"Latest finding {sc['whd_latest_finding']}"
        if whd["repeat_violator"]:
            whd["worst_record"] += " (repeat violator)"
    # WHD violation_count: derive from whd_cases if available.
    whd["violation_count"] = 0
    with _Savepoint(cur, "whd_violations"):
        cur.execute(
            """
            SELECT SUM(COALESCE(total_violations, 0)) AS viol
            FROM master_employer_source_ids sid
            JOIN whd_cases w ON w.case_id::text = sid.source_id
            WHERE sid.master_id = %s AND sid.source_system = 'whd'
            """,
            [master_id],
        )
        v = cur.fetchone()
        whd["violation_count"] = int(v["viol"]) if v and v.get("viol") else 0

    # EPA -- the v1 epa_echo_facilities schema lacks a fac_air_flag column,
    # so we don't query it. The EPA section's "air-quality flag" is a v2
    # enhancement (link to AIR sub-program statuses); for now we surface
    # SNC count + total facilities, which is what the EnvironmentalCard
    # also leans on as the headline.
    epa = out["epa"]
    with _Savepoint(cur, "epa_summary"):
        cur.execute(
            """
            SELECT COUNT(*) AS facilities,
                   SUM(COALESCE(ef.fac_inspection_count, 0)) AS insp,
                   SUM(COALESCE(ef.fac_total_penalties, 0)) AS pen,
                   SUM(CASE WHEN UPPER(COALESCE(ef.fac_snc_flag,'')) = 'Y' THEN 1 ELSE 0 END) AS snc
            FROM master_employer_source_ids sid
            JOIN epa_echo_facilities ef ON ef.registry_id = sid.source_id
            WHERE sid.master_id = %s AND sid.source_system = 'epa_echo'
            """,
            [master_id],
        )
        row = cur.fetchone() or {}
        if row.get("facilities") and int(row["facilities"]) > 0:
            epa["facility_count"] = int(row["facilities"])
            epa["inspection_count"] = int(row.get("insp") or 0)
            epa["penalty_total"] = float(row.get("pen") or 0)
            epa["snc_count"] = int(row.get("snc") or 0)
            # any_air_flag intentionally False until we wire AIR sub-program data.
            epa["any_air_flag"] = False

    return out


def _pull_directors(cur, master_id: int) -> Dict[str, Any]:
    """Top 5 directors with enforcement-risk overlay."""
    out: Dict[str, Any] = {"directors": [], "network_stats": {}}
    cur.execute("SELECT to_regclass('employer_directors') AS d, to_regclass('director_interlocks') AS i")
    tbl = cur.fetchone() or {}
    if not tbl.get("d"):
        return out

    cur.execute(
        """
        SELECT director_name, age, position, director_since_year,
               primary_occupation, is_independent
        FROM employer_directors
        WHERE master_id = %s
        ORDER BY
          CASE WHEN is_independent IS FALSE THEN 0 ELSE 1 END,
          director_since_year ASC NULLS LAST,
          director_name ASC
        LIMIT 5
        """,
        [master_id],
    )
    rows = cur.fetchall() or []
    directors = []
    for r in rows:
        directors.append({
            "name": r.get("director_name"),
            "position": r.get("position"),
            "is_independent": r.get("is_independent"),
        })

    # Per-director risk via the same logic board.py uses (simplified).
    director_names = [
        d["name"] for d in directors
        if d.get("name") and is_likely_real_director_name(d["name"])
    ]
    if director_names and tbl.get("i"):
        try:
            cur.execute(
                """
                WITH other_boards AS (
                    SELECT DISTINCT d.director_name, d.master_id AS other_master_id
                    FROM employer_directors d
                    WHERE d.director_name = ANY(%s)
                      AND d.master_id <> %s
                )
                SELECT
                    ob.director_name,
                    COUNT(DISTINCT ob.other_master_id) AS other_boards_count,
                    SUM(COALESCE(ts.osha_total_violations, 0))::int AS osha_violations,
                    SUM(COALESCE(ts.nlrb_ulp_count, 0))::int AS nlrb_ulps,
                    SUM(COALESCE(ts.whd_total_backwages, 0))::numeric AS whd_backwages,
                    SUM(COALESCE(ts.osha_total_penalties, 0))::numeric AS osha_penalties
                FROM other_boards ob
                LEFT JOIN mv_target_scorecard ts ON ts.master_id = ob.other_master_id
                GROUP BY ob.director_name
                """,
                [director_names, master_id],
            )
            risk_by_name: Dict[str, Dict[str, Any]] = {}
            for r in cur.fetchall() or []:
                osha_v = int(r.get("osha_violations") or 0)
                nlrb_u = int(r.get("nlrb_ulps") or 0)
                whd_bw = float(r.get("whd_backwages") or 0)
                osha_p = float(r.get("osha_penalties") or 0)
                score = (
                    osha_v * 3.0 + nlrb_u * 5.0 + whd_bw / 50_000.0 + osha_p / 5_000.0
                )
                tier = "RED" if score >= 100 else "YELLOW" if score >= 20 else "GREEN"
                risk_by_name[r["director_name"]] = {
                    "other_boards_count": int(r.get("other_boards_count") or 0),
                    "risk_score": round(score, 1),
                    "risk_tier": tier,
                }
            for d in directors:
                d["enforcement_risk"] = risk_by_name.get(d["name"])
        except Exception as exc:
            _log.warning("director risk overlay failed: %s", exc)

    out["directors"] = directors

    # Network stats (1-hop / 2-hop counts) -- best effort.
    if tbl.get("i"):
        try:
            cur.execute(
                """
                SELECT
                  COUNT(DISTINCT CASE WHEN master_id_a = %(mid)s THEN master_id_b
                                      ELSE master_id_a END) AS one_hop,
                  COUNT(DISTINCT director_name) AS shared
                FROM director_interlocks
                WHERE master_id_a = %(mid)s OR master_id_b = %(mid)s
                """,
                {"mid": master_id},
            )
            r = cur.fetchone() or {}
            out["network_stats"] = {
                "one_hop_count": int(r.get("one_hop") or 0),
                "shared_directors_total": int(r.get("shared") or 0),
                # 2-hop count is expensive; report null instead of running the
                # full director_network query inside a synchronous render path.
                "two_hop_count": None,
            }
        except Exception as exc:
            _log.warning("network stats failed: %s", exc)
    return out


_TITLE_RANK_SQL = """
CASE
  WHEN me.title IS NULL OR btrim(me.title) = '' THEN 99
  WHEN (me.title ~* '\\m(chairman|chairperson|chairwoman|chair of the board)\\M'
        OR me.title ~* '\\m(chb)\\M')
       AND me.title !~* '\\m(vice|deputy|asst|assistant|former|emeritus)\\M' THEN 1
  WHEN me.title ~* '\\m(chief executive officer|ceo)\\M' THEN 2
  WHEN me.title ~* '\\mpresident\\M' AND me.title !~* '\\m(vice|foundation|division|region)\\M' THEN 3
  WHEN me.title ~* '\\m(chief financial officer|cfo)\\M' THEN 4
  WHEN me.title ~* '\\m(chief operating officer|coo)\\M' THEN 5
  WHEN me.title ~* '\\mchief\\M.*\\m(officer|executive)\\M' THEN 6
  WHEN me.title ~* '\\m(executive vice president|evp)\\M' THEN 7
  WHEN me.title ~* '\\m(senior vice president|svp)\\M' THEN 8
  WHEN me.title ~* '\\mvice president\\M' OR me.title ~* '\\mvice chairman\\M' THEN 9
  WHEN me.title ~* '\\m(general counsel|secretary|treasurer)\\M' THEN 10
  WHEN me.title ~* '\\mdirector\\M' THEN 11
  WHEN me.title ~* '\\mmanager\\M' THEN 12
  ELSE 50
END
"""

_TITLE_RANK_LABELS = {
    1: "Board Chair", 2: "CEO", 3: "President", 4: "CFO", 5: "COO",
    6: "C-Suite", 7: "EVP", 8: "SVP", 9: "VP",
    10: "General Counsel / Officer", 11: "Director", 12: "Manager",
    50: "Other", 99: "Unspecified",
}


def _pull_executives(cur, master_id: int) -> List[Dict[str, Any]]:
    cur.execute("SELECT to_regclass('mergent_executives') AS t")
    tbl = cur.fetchone() or {}
    if not tbl.get("t"):
        return []
    try:
        cur.execute(
            f"""
            SELECT me.first_name, me.last_name, me.title,
                   ({_TITLE_RANK_SQL}) AS title_rank
            FROM master_employer_source_ids sid
            JOIN mergent_executives me ON me.duns = sid.source_id
            WHERE sid.source_system = 'mergent'
              AND sid.master_id = %s
            ORDER BY title_rank ASC,
                     lower(coalesce(me.last_name, '')) ASC,
                     lower(coalesce(me.first_name, '')) ASC
            LIMIT 5
            """,
            [master_id],
        )
        rows = cur.fetchall() or []
    except Exception as exc:
        _log.warning("exec pull failed: %s", exc)
        return []

    out: List[Dict[str, Any]] = []
    for r in rows:
        first = (r.get("first_name") or "").strip()
        last = (r.get("last_name") or "").strip()
        nm = " ".join(p for p in [first, last] if p) or None
        rank = int(r["title_rank"])
        out.append({
            "name": nm,
            "title": r.get("title"),
            "title_rank_label": _TITLE_RANK_LABELS.get(rank, "Other"),
        })
    return out


def _pull_score_and_tier(cur, master_id: int) -> Dict[str, Any]:
    """Tier badge + headline score. Prefers unified_scorecard via F7 link;
    falls back to mv_target_scorecard's gold_standard_tier + pillar_*."""
    out: Dict[str, Any] = {}
    cur.execute(
        """
        SELECT gold_standard_tier, signals_present, has_thin_data,
               pillar_anger, pillar_leverage, pillar_stability
        FROM mv_target_scorecard
        WHERE master_id = %s
        """,
        [master_id],
    )
    sc = cur.fetchone()
    if sc:
        out["gold_standard_tier"] = sc.get("gold_standard_tier")
        out["signals_present"] = sc.get("signals_present")
        out["has_thin_data"] = bool(sc.get("has_thin_data"))
        if sc.get("pillar_anger") is not None:
            out["pillar_anger"] = float(sc["pillar_anger"])
        if sc.get("pillar_leverage") is not None:
            out["pillar_leverage"] = float(sc["pillar_leverage"])
        if sc.get("pillar_stability") is not None:
            out["pillar_stability"] = float(sc["pillar_stability"])

    # Unified scorecard via F7 source link (only union targets get one).
    try:
        cur.execute(
            """
            SELECT us.unified_score, us.weighted_score
            FROM master_employer_source_ids sid
            JOIN mv_unified_scorecard us ON us.employer_id::text = sid.source_id
            WHERE sid.master_id = %s AND sid.source_system = 'f7'
            LIMIT 1
            """,
            [master_id],
        )
        u = cur.fetchone()
        if u:
            score = u.get("unified_score") or u.get("weighted_score")
            if score is not None:
                out["score_value"] = float(score)
                out["score_kind"] = "unified"
                return out
    except Exception:
        pass

    # Fallback: use the single highest pillar as the headline number.
    pillars = [
        out.get("pillar_anger"), out.get("pillar_leverage"),
        out.get("pillar_stability"),
    ]
    pillars = [p for p in pillars if p is not None]
    if pillars:
        out["score_value"] = max(pillars)
        out["score_kind"] = "pillar-max"
    return out


# ----- endpoint ---------------------------------------------------------

@router.get("/api/employers/master/{master_id}/power-profile.pdf")
def get_power_profile_pdf(master_id: int) -> Response:
    """Generate a 3-page printable Power Profile PDF for a master employer.

    Returns 200 application/pdf on success, 404 if the master_id is unknown.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            identity = _pull_identity(cur, master_id)
            if not identity:
                raise HTTPException(status_code=404, detail="Master employer not found")

            financials = _pull_financials(cur, master_id)
            owners = _pull_institutional_owners(cur, master_id)
            fec = _pull_fec(cur, master_id, identity.get("canonical_name") or "")
            lobbying = _pull_lobbying(cur, master_id)
            demographics = _pull_demographics(cur, master_id)
            enforcement = _pull_enforcement(cur, master_id)
            directors_block = _pull_directors(cur, master_id)
            executives = _pull_executives(cur, master_id)
            score_block = _pull_score_and_tier(cur, master_id)

    payload: Dict[str, Any] = {
        **identity,
        **financials,
        "institutional_owners": owners["owners"],
        "institutional_owners_period": owners.get("period"),
        "institutional_owners_total_value": owners.get("total_value"),
        "institutional_owners_count": owners.get("count"),
        "fec": fec,
        "lobbying": lobbying,
        "demographics": demographics,
        "osha": enforcement["osha"],
        "nlrb": enforcement["nlrb"],
        "whd": enforcement["whd"],
        "epa": enforcement["epa"],
        "directors": directors_block.get("directors") or [],
        "director_network_stats": directors_block.get("network_stats") or {},
        "executives": executives,
        **score_block,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
    }

    pdf_bytes = render_power_profile_pdf(payload)

    name_for_file = (
        (identity.get("canonical_name") or f"master_{master_id}")
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
    )[:60]
    filename = f"power_profile_{name_for_file}_{master_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=120",
        },
    )
