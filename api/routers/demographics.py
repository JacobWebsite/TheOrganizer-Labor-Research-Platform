"""
Demographics API - ACS workforce demographics by state and industry.

GET /api/demographics/{state}/{naics}  - Industry workforce demographics
GET /api/demographics/{state}          - State-wide workforce demographics
"""
from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor
from db_config import get_connection

router = APIRouter(prefix="/api/demographics", tags=["demographics"])

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
HISPANIC_LABELS = {"0": "Not Hispanic", "1": "Hispanic/Latino"}


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
    """Query ACS and build decoded demographics response."""
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
    }


@router.get("/{state}/{naics}")
async def get_industry_demographics(state: str, naics: str):
    """Get workforce demographics for a state + industry (NAICS 2-4 digit)."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        state_fips = _get_state_fips(cur, state)
        naics4 = naics[:4]

        result = _build_demographics(cur, state_fips, naics4)
        if not result:
            # Try broader NAICS (2-digit) if 4-digit has no data
            naics2 = naics[:2]
            result = _build_demographics(cur, state_fips, naics2)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No ACS workforce data for {state.upper()} NAICS {naics}",
            )

        # Get NAICS description if available
        cur.execute(
            "SELECT title FROM bls_industry_occupation_matrix WHERE matrix_code = %s LIMIT 1",
            (naics4 + "00",),
        )
        naics_row = cur.fetchone()
        naics_desc = naics_row["title"] if naics_row else None

        return {
            "state": state.upper(),
            "naics": naics,
            "naics_description": naics_desc,
            "label": f"Industry baseline for NAICS {naics} in {state.upper()}",
            **result,
        }
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

        return {
            "state": state.upper(),
            "naics": None,
            "naics_description": None,
            "label": f"Workforce baseline for {state.upper()}",
            **result,
        }
    finally:
        conn.close()
