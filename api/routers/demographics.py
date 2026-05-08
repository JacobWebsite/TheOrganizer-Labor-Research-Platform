"""
Demographics API - ACS workforce demographics by state and industry.

GET /api/demographics/{state}/{naics}  - Industry workforce demographics
GET /api/demographics/{state}          - State-wide workforce demographics
"""
import logging

from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor
from db_config import get_connection

from ..services.demographics_bounds import (
    assert_demographics_plausible,
    log_warnings,
)

router = APIRouter(prefix="/api/demographics", tags=["demographics"])
_logger = logging.getLogger(__name__)

# Decode maps for IPUMS ACS coded values
SEX_LABELS = {"1": "Male", "2": "Female"}
RACE_LABELS = {
    "1": "White", "2": "Black/African American", "3": "American Indian/Alaska Native",
    "4": "Chinese", "5": "Japanese", "6": "Other Asian/Pacific Islander",
    "7": "Other race", "8": "Two major races", "9": "Three or more races",
}
AGE_LABELS = {
    "u25": "Under 25", "25_34": "25-34", "35_44": "35-44",
    "45_54": "45-54", "55_64": "55-64", "65p": "65+",
}
EDUCATION_LABELS = {
    "00": "N/A (age <3)", "01": "No schooling", "02": "Nursery-4th grade",
    "03": "5th-8th grade", "04": "9th grade", "05": "10th grade",
    "06": "11th grade", "07": "12th grade/no diploma", "08": "HS diploma/GED",
    "10": "Some college", "11": "Associate's", "12": "Bachelor's",
    "13": "Master's", "14": "Professional", "15": "Doctorate",
}
# Simplified education grouping
EDUCATION_GROUPS = {
    "No HS diploma": ["00", "01", "02", "03", "04", "05", "06", "07"],
    "HS diploma/GED": ["08"],
    "Some college/Associate's": ["10", "11"],
    "Bachelor's": ["12"],
    "Graduate/Professional": ["13", "14", "15"],
}
# IPUMS USA HISPAN encoding (used by cur_acs_workforce_demographics).
# Codes 0 and 1 had labels; 2/3/4 were rendering raw (R7-3 fix 2026-04-27).
HISPANIC_LABELS = {
    "0": "Not Hispanic",
    "1": "Mexican",
    "2": "Puerto Rican",
    "3": "Cuban",
    "4": "Other Hispanic/Latino",
}

# Data vintage for the materialized inputs used by these endpoints.
# Hardcoded for now; ETL is tracked in data_refresh_log but not all
# loaders log there yet (see Apr 17 memory note for the gap).
ACS_PUMS_VINTAGE = "2022"   # ACS 5-year PUMS feeding cur_acs_workforce_demographics
QCEW_VINTAGE = "2024"        # QCEW annual loaded 2026-04-16 (includes 2024)


def _get_state_fips(cur, state: str) -> str:
    """Convert state abbreviation to FIPS code."""
    cur.execute(
        "SELECT state_fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1",
        (state.upper(),),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown state: {state}")
    return row["state_fips"]


def _build_demographics(cur, state_fips: str, naics4: str = None):
    """Query ACS and build decoded demographics response.

    cur_acs_workforce_demographics is built from one IPUMS sample (2023 ACS
    5-year) with not-in-labor-force people excluded — every row is a leaf
    cell of the (state x metro x naics4 x soc x demographics x worker_class)
    cube, scoped to employed wage workers + self-employed. Summing without
    a grain filter gives the correct total. See newsrc_curate_all.build_acs.
    """
    where = ["state_fips = %s"]
    params = [state_fips]
    if naics4:
        where.append("naics4 = %s")
        params.append(naics4)

    where_sql = " AND ".join(where)

    # Total workers
    cur.execute(f"""
        SELECT COALESCE(SUM(weighted_workers), 0) AS total
        FROM cur_acs_workforce_demographics WHERE {where_sql}
    """, params)
    total = float(cur.fetchone()["total"])
    if total == 0:
        return None

    # Gender split
    cur.execute(f"""
        SELECT sex, SUM(weighted_workers) AS w
        FROM cur_acs_workforce_demographics WHERE {where_sql}
        GROUP BY sex ORDER BY w DESC
    """, params)
    gender = [
        {"code": r["sex"], "label": SEX_LABELS.get(r["sex"], r["sex"]),
         "pct": round(float(r["w"]) / total * 100, 1)}
        for r in cur.fetchall()
    ]

    # Race breakdown
    cur.execute(f"""
        SELECT race, SUM(weighted_workers) AS w
        FROM cur_acs_workforce_demographics WHERE {where_sql}
        GROUP BY race ORDER BY w DESC
    """, params)
    race = [
        {"code": r["race"], "label": RACE_LABELS.get(r["race"], f"Code {r['race']}"),
         "pct": round(float(r["w"]) / total * 100, 1)}
        for r in cur.fetchall()
    ]

    # Hispanic origin
    cur.execute(f"""
        SELECT hispanic, SUM(weighted_workers) AS w
        FROM cur_acs_workforce_demographics WHERE {where_sql}
        GROUP BY hispanic ORDER BY w DESC
    """, params)
    hispanic = [
        {"code": r["hispanic"], "label": HISPANIC_LABELS.get(r["hispanic"], r["hispanic"]),
         "pct": round(float(r["w"]) / total * 100, 1)}
        for r in cur.fetchall()
    ]

    # Age distribution
    cur.execute(f"""
        SELECT age_bucket, SUM(weighted_workers) AS w
        FROM cur_acs_workforce_demographics WHERE {where_sql}
        GROUP BY age_bucket ORDER BY age_bucket
    """, params)
    age_raw = {r["age_bucket"]: float(r["w"]) for r in cur.fetchall()}
    age = [
        {"bucket": k, "label": AGE_LABELS.get(k, k),
         "pct": round(age_raw.get(k, 0) / total * 100, 1)}
        for k in ["u25", "25_34", "35_44", "45_54", "55_64", "65p"]
        if k in age_raw
    ]

    # Education (grouped)
    cur.execute(f"""
        SELECT education, SUM(weighted_workers) AS w
        FROM cur_acs_workforce_demographics WHERE {where_sql}
        GROUP BY education
    """, params)
    educ_raw = {r["education"]: float(r["w"]) for r in cur.fetchall()}
    education = []
    for group_label, codes in EDUCATION_GROUPS.items():
        group_total = sum(educ_raw.get(c, 0) for c in codes)
        if group_total > 0:
            education.append({
                "group": group_label,
                "pct": round(group_total / total * 100, 1),
            })

    return {
        "total_workers": round(total),
        "gender": gender,
        "race": race,
        "hispanic": hispanic,
        "age_distribution": age,
        "education": education,
        # Data vintage for the ACS slice. R7-2 (2026-04-27) added these so
        # the frontend stops hardcoding "ACS 2022".
        "acs_year": ACS_PUMS_VINTAGE,
        "qcew_year": QCEW_VINTAGE,
    }


@router.get("/employer/{master_id}")
async def get_employer_demographics(master_id: int):
    """Estimate workforce demographics for any employer (F7 or target) by master_id.

    Uses V5 Gate model if available, falls back to ACS industry x state data.
    Requires the employer to have at least a state and NAICS code.
    """
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()

        # Look up employer
        cur.execute("""
            SELECT canonical_name, naics, state, zip, city
            FROM master_employers
            WHERE master_id = %s
        """, (master_id,))
        emp = cur.fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail=f"Employer {master_id} not found")

        state_abbr = emp.get("state")
        naics_code = emp.get("naics")
        zipcode = emp.get("zip")

        if not state_abbr:
            raise HTTPException(
                status_code=422,
                detail=f"Employer {master_id} has no state -- cannot estimate demographics")

        # Get state FIPS
        state_fips = _get_state_fips(cur, state_abbr)

        # Get county FIPS from ZIP if available. Strip the ZIP+4 suffix —
        # master_employers.zip stores values like '60064-3500' but the
        # zip_county_crosswalk table is keyed on 5-digit ZIPs only. Without
        # this strip, V12 falls back to ACS for every employer that has
        # a hyphenated ZIP+4 (most SEC filers, including Abbott which
        # carries '60064-3500'). Found while testing 2026-05-05.
        zipcode_5 = (zipcode or "").strip().split("-", 1)[0][:5]
        county_fips = None
        if zipcode_5:
            cur.execute(
                "SELECT county_fips FROM zip_county_crosswalk WHERE zip_code = %s LIMIT 1",
                (zipcode_5,))
            row = cur.fetchone()
            if row:
                county_fips = row["county_fips"]

        # Try V12 QWI model first.
        # Pass zipcode_5 (5-digit) instead of the raw `zipcode` (which can
        # carry a -1234 suffix). V12 itself only uses zipcode for trace
        # logging, but consistency keeps things clean.
        v12_result = None
        method = "acs_fallback"
        try:
            from api.services.demographics_v12 import estimate_demographics_v12
            v12_result = estimate_demographics_v12(
                cur, naics_code or "00", state_fips,
                zipcode_5 or "00000", county_fips or "00000",
                state_abbr=state_abbr, total_employees=100)
            if v12_result and v12_result.get("race"):
                method = v12_result.get("metadata", {}).get("model", "v12_qwi")
        except Exception as exc:
            # Don't silently fall back to ACS without a trace -- this swallow
            # hid two real bugs (cursor type mismatch, ZIP+4 county lookup).
            # Log at warning level so deploy logs surface the issue but
            # don't fail the response.
            import logging
            logging.getLogger("labor_api.demographics").warning(
                "V12 estimation failed for master_id=%s naics=%s county=%s: %s",
                master_id, naics_code, county_fips, exc, exc_info=True,
            )
            v12_result = None

        if v12_result and v12_result.get("race"):
            # Format V12 result
            race_data = v12_result["race"]
            hispanic_data = v12_result.get("hispanic", {}) or {}
            gender_data = v12_result.get("gender", {}) or {}

            race = [{"label": k, "pct": round(v, 1)}
                    for k, v in sorted(race_data.items(), key=lambda x: -x[1])]
            hispanic = [
                {"label": "Hispanic/Latino",
                 "pct": round(hispanic_data.get("Hispanic", 0), 1)},
                {"label": "Not Hispanic",
                 "pct": round(hispanic_data.get("Not Hispanic", 100), 1)},
            ]
            gender = [{"label": k, "pct": round(v, 1)}
                      for k, v in sorted(gender_data.items(), key=lambda x: -x[1])]

            meta = v12_result.get("metadata", {}) or {}
            confidence = meta.get("confidence_tier", "YELLOW")

            return {
                "master_id": master_id,
                "employer_name": emp["canonical_name"],
                "state": state_abbr,
                "naics": naics_code,
                "method": method,
                "methodology": (
                    f"V12 QWI county x NAICS4 model "
                    f"(QCEW {QCEW_VINTAGE} + ACS {ACS_PUMS_VINTAGE} fallback)"
                ),
                "acs_year": ACS_PUMS_VINTAGE,
                "qcew_year": QCEW_VINTAGE,
                "confidence": confidence,
                "qwi_level": meta.get("qwi_level"),
                "naics_group": meta.get("naics_group"),
                "diversity_tier": meta.get("diversity_tier"),
                "race": race,
                "hispanic": hispanic,
                "gender": gender,
            }

        # Fallback to ACS
        naics4 = naics_code[:4] if naics_code and len(naics_code) >= 4 else None
        result = _build_demographics(cur, state_fips, naics4)

        if not result:
            # Try state-wide
            result = _build_demographics(cur, state_fips)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No demographics data available for employer {master_id}")

        payload = {
            "master_id": master_id,
            "employer_name": emp["canonical_name"],
            "state": state_abbr,
            "naics": naics_code,
            "method": "acs_industry_state" if naics4 else "acs_state",
            "methodology": (
                f"ACS {ACS_PUMS_VINTAGE} 5-year PUMS aggregated by state x NAICS4"
                if naics4 else
                f"ACS {ACS_PUMS_VINTAGE} 5-year PUMS aggregated state-wide"
            ),
            "confidence": "YELLOW" if naics4 else "RED",
            **result,
        }
        log_warnings(
            assert_demographics_plausible(
                payload,
                state_abbr=state_abbr,
                context=f"GET /api/demographics/employer/{master_id}",
            ),
            _logger,
        )
        return payload
    finally:
        conn.close()


@router.get("/{state}/{naics}")
async def get_industry_demographics(state: str, naics: str):
    """Get workforce demographics for a state + industry (NAICS 2-4 digit)."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        state_fips = _get_state_fips(cur, state)
        naics4 = naics[:4]

        result = _build_demographics(cur, state_fips, naics4)
        fallback_level = None
        if not result:
            # Try broader NAICS (2-digit) if 4-digit has no data
            naics2 = naics[:2]
            result = _build_demographics(cur, state_fips, naics2)
            if result:
                fallback_level = "naics2"

        if not result:
            # Final fallback: state-wide demographics
            result = _build_demographics(cur, state_fips)
            if result:
                fallback_level = "state"

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No ACS workforce data for {state.upper()} NAICS {naics}",
            )

        # Get NAICS description if available
        naics_desc = None
        cur.execute("""
            SELECT naics_title FROM naics_codes_reference
            WHERE naics_code = %s LIMIT 1
        """, (naics4,))
        naics_row = cur.fetchone()
        if naics_row:
            naics_desc = naics_row["naics_title"].rstrip("T")

        label = f"Industry baseline for NAICS {naics} in {state.upper()}"
        if fallback_level == "naics2":
            label = f"Industry baseline for NAICS {naics[:2]} (2-digit) in {state.upper()}"
        elif fallback_level == "state":
            label = f"State-wide workforce baseline for {state.upper()}"
            naics_desc = None

        payload = {
            "state": state.upper(),
            "naics": naics,
            "naics_description": naics_desc,
            "fallback_level": fallback_level,
            "label": label,
            "methodology": (
                f"ACS {ACS_PUMS_VINTAGE} 5-year PUMS, state x NAICS{len(naics4)}"
                if fallback_level != "state" else
                f"ACS {ACS_PUMS_VINTAGE} 5-year PUMS, state-wide fallback"
            ),
            **result,
        }
        log_warnings(
            assert_demographics_plausible(
                payload,
                state_abbr=state.upper(),
                context=f"GET /api/demographics/{state}/{naics}",
            ),
            _logger,
        )
        return payload
    finally:
        conn.close()


@router.get("/{state}")
async def get_state_demographics(state: str):
    """Get workforce demographics for a state (all industries)."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        state_fips = _get_state_fips(cur, state)

        result = _build_demographics(cur, state_fips)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No ACS workforce data for {state.upper()}",
            )

        payload = {
            "state": state.upper(),
            "naics": None,
            "naics_description": None,
            "label": f"Workforce baseline for {state.upper()}",
            "methodology": f"ACS {ACS_PUMS_VINTAGE} 5-year PUMS, state-wide aggregate",
            **result,
        }
        log_warnings(
            assert_demographics_plausible(
                payload,
                state_abbr=state.upper(),
                context=f"GET /api/demographics/{state}",
            ),
            _logger,
        )
        return payload
    finally:
        conn.close()
