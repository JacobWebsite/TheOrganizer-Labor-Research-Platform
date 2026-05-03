"""
Corporate-family rollup service.

Problem: NLRB / OSHA / WHD data for a large multi-location employer is
typically filed under many respondent-name variants (e.g. "Starbucks
Corporation", "STARBUCKS CORPORATION", "Starbucks Coffee Company", CEO-prefixed
variants like "Schultz, Howard\\nStarbucks Corporation", d/b/a variants,
per-store variants like "Starbucks Corporation, Easton Store #9534"). The
master_employers table holds one row per name variant, so a direct
master_id-based lookup on the canonical parent (e.g. Starbucks Corp
master_id=4598237) undercounts the employer by orders of magnitude.

This service provides a name-variant-based rollup that aggregates NLRB
elections + ULPs + allegations + locations for a corporate family, given
either the canonical master_id or a child entity. The caller gets the full
national picture.

Usage:
    from api.services.corporate_family_rollup import get_family_rollup
    rollup = get_family_rollup(conn, master_id=4598237)

Returns a dict containing:
    - family_name: resolved canonical name
    - name_variants: list of matching participant_name / estab_name / legal_name strings
    - master_count: count of distinct master_ids covered
    - nlrb: {totals, elections_summary, elections_by_year, recent_elections, ulp_summary, top_allegation_sections, respondent_variants}
    - osha: {totals, violations_by_type}
    - whd: {totals}
    - f7: {locals_count, states_covered}
"""
from __future__ import annotations

import re
from typing import Any


# Canonical-name extraction: strip legal suffixes, store numbers, d/b/a, etc.
_LEGAL_SUFFIX_RE = re.compile(
    r"(,\s*inc\.?|,\s*llc\.?|,\s*corp\.?|,\s*corporation|,\s*co\.?|,\s*ltd\.?"
    r"|\s+inc\.?$|\s+llc\.?$|\s+corp\.?$|\s+corporation$|\s+company$|\s+co\.?$|\s+ltd\.?$)",
    re.IGNORECASE,
)
_STORE_NUM_RE = re.compile(r"[,\s]+(store|#)\s*#?\s*\d+[a-z]*", re.IGNORECASE)
_DBA_RE = re.compile(r"\s*d/?b/?a\s+.*$", re.IGNORECASE)
_CEO_PREFIX_RE = re.compile(r"^[A-Z][a-zA-Z'\-]+,?\s+[A-Z][a-zA-Z'\-]+\s*\n+", re.MULTILINE)


def _extract_root_name(display_name: str) -> str:
    """Strip legal suffixes, store numbers, d/b/a clauses to get a canonical
    name stem suitable for ILIKE matching.

    Example: "Starbucks Corporation, Easton Store #9534" -> "starbucks"
    """
    if not display_name:
        return ""
    s = display_name
    # Strip CEO name prefix ("Schultz, Howard\nStarbucks Corporation")
    s = _CEO_PREFIX_RE.sub("", s)
    # Strip d/b/a clause
    s = _DBA_RE.sub("", s)
    # Strip store numbers
    s = _STORE_NUM_RE.sub("", s)
    # Strip legal suffixes
    prev = None
    while s != prev:
        prev = s
        s = _LEGAL_SUFFIX_RE.sub("", s)
    # Normalize whitespace + case
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Take first 1-2 words as the root stem
    words = s.split()
    # For most brand names, 1 word is enough (starbucks, walmart, lowes)
    # For multi-word brands (dollar tree, bristol farms) take 2 words
    if len(words) >= 2 and len(words[0]) <= 6 and words[1] not in {"corp", "corporation", "co", "inc", "company", "llc"}:
        return " ".join(words[:2])
    return words[0] if words else ""


def _resolve_family_stem(cur, master_id: int) -> tuple[str, str]:
    """Given a master_id, return (display_name, root_stem) to drive the rollup."""
    cur.execute(
        "SELECT display_name FROM master_employers WHERE master_id = %s",
        (master_id,),
    )
    row = cur.fetchone()
    if not row:
        return ("", "")
    display_name = row["display_name"] if isinstance(row, dict) else row[0]
    return (display_name, _extract_root_name(display_name))


def _resolve_family_stem_for_f7(cur, f7_id: str) -> tuple[str, str, int | None]:
    """Given an F-7 employer_id (hex string), return (display_name, root_stem,
    optional canonical_master_id).

    The canonical master is looked up via corporate_identifier_crosswalk.f7_employer_id
    when available; otherwise None (the rollup still works from the stem alone).
    """
    cur.execute(
        "SELECT employer_id, name_standard, state "
        "FROM f7_employers_deduped WHERE employer_id = %s",
        (f7_id,),
    )
    row = cur.fetchone()
    if not row:
        return ("", "", None)
    name = (row["name_standard"] if isinstance(row, dict) else row[1]) or ""
    stem = _extract_root_name(name)

    # Try to find a canonical master for this F-7 via the cross-walk.
    master_id = None
    try:
        cur.execute(
            "SELECT id FROM corporate_identifier_crosswalk WHERE f7_employer_id = %s LIMIT 1",
            (f7_id,),
        )
        cic = cur.fetchone()
        if cic:
            # corporate_identifier_crosswalk.id IS the corporate_family_id; it
            # doubles as a master_id in most places. The rollup only uses
            # master_id for display_name + stem, both of which we already have,
            # so this is informational.
            master_id = cic["id"] if isinstance(cic, dict) else cic[0]
    except Exception:
        master_id = None
    return (name, stem, master_id)


def get_family_rollup(
    conn, master_id: int, limit_recent_elections: int = 100
) -> dict[str, Any]:
    """Aggregate NLRB/OSHA/WHD/F-7 data for the corporate family of ``master_id``.

    Conn is expected to be a psycopg2 connection with RealDictCursor available.
    """
    cur = conn.cursor()
    display_name, stem = _resolve_family_stem(cur, master_id)
    if not stem:
        return {"error": "master_id not found or name empty", "master_id": master_id}
    return _run_rollup(cur, display_name, stem, master_id=master_id,
                       limit_recent_elections=limit_recent_elections)


def get_family_rollup_for_f7(
    conn, f7_id: str, limit_recent_elections: int = 100
) -> dict[str, Any]:
    """Aggregate NLRB/OSHA/WHD/F-7 data for the corporate family of an F-7
    employer (by employer_id hex string), not a master_id. Used when the
    frontend profile page is for an F-7-sourced employer rather than a master.

    Extracts the same root stem from the F-7's `name_standard` so the
    underlying aggregation is identical -- e.g. a Starbucks store F-7 gets
    the same 2,351-case national Starbucks rollup as the canonical
    master 4598237 does.
    """
    cur = conn.cursor()
    display_name, stem, canonical_master = _resolve_family_stem_for_f7(cur, f7_id)
    if not stem:
        return {"error": "f7 employer_id not found or name empty", "f7_id": f7_id}
    return _run_rollup(cur, display_name, stem, master_id=canonical_master,
                       limit_recent_elections=limit_recent_elections, resolved_from_f7=f7_id)


def _find_secondary_stem_via_parent(cur, stem: str, display_name: str) -> str | None:
    """Look up `corporate_ultimate_parents` for an ultimate_parent whose name
    diverges from the primary stem (different root token). Returns the
    secondary stem, or None if no meaningful parent link exists.

    Example: primary stem `lowes home` (from LOWES HOME CENTERS, INC.) +
    a corporate_ultimate_parents row with ultimate_parent_name="LOWES COMPANIES
    INC" yields secondary stem `lowes companies`. Including both stems in
    the aggregation unifies the operating-sub + SEC-filer-parent view that
    a single-stem match would miss.
    """
    if not stem:
        return None
    stem_pattern = f"%{stem}%"
    try:
        cur.execute(
            """
            SELECT DISTINCT ultimate_parent_name
            FROM corporate_ultimate_parents
            WHERE entity_name ILIKE %s
              AND ultimate_parent_name IS NOT NULL
              AND ultimate_parent_name != entity_name
            LIMIT 5
            """,
            (stem_pattern,),
        )
        rows = cur.fetchall()
    except Exception:
        return None
    if not rows:
        return None
    # Pick the first parent whose extracted stem differs from the primary.
    for row in rows:
        parent_name = row["ultimate_parent_name"] if isinstance(row, dict) else row[0]
        parent_stem = _extract_root_name(parent_name)
        if parent_stem and parent_stem != stem:
            return parent_stem
    return None


def _run_rollup(
    cur, display_name: str, stem: str, *, master_id: int | None,
    limit_recent_elections: int = 100, resolved_from_f7: str | None = None,
) -> dict[str, Any]:
    """Internal: runs the full aggregation given a resolved display_name + stem.

    This is the body of the old `get_family_rollup`. Exposing it as a helper
    lets both the master_id and f7_id entry points share the exact same
    query logic.

    Secondary-stem expansion: after the primary aggregation, if
    `corporate_ultimate_parents` lists an ultimate parent whose name extracts
    to a different root stem (e.g. `lowes home` -> `lowes companies`), we
    expand the match pattern to include both stems so the parent-side
    masters also flow into the counts.
    """
    secondary_stem = _find_secondary_stem_via_parent(cur, stem, display_name)
    stems = [stem]
    if secondary_stem:
        stems.append(secondary_stem)
    # List of ILIKE patterns, one per stem. All aggregation queries use
    # `ILIKE ANY(%s)` so the primary AND secondary stems both flow in.
    stem_patterns = [f"%{s}%" for s in stems]
    # Keep stem_pattern for backward-compat -- it's what clients use when
    # they only want the primary.
    stem_pattern = stem_patterns[0]

    rollup: dict[str, Any] = {
        "master_id": master_id,
        "display_name": display_name,
        "family_stem": stem,
        "family_stems_all": stems,            # includes secondary if present
        "secondary_stem_via_parent": secondary_stem,
        "match_pattern": stem_pattern,
        "match_patterns": stem_patterns,       # list used by aggregation queries
    }
    if resolved_from_f7:
        rollup["resolved_from_f7"] = resolved_from_f7

    # Masters with any of the stem(s)
    cur.execute(
        """
        SELECT source_origin, COUNT(*) AS n,
               COUNT(*) FILTER (WHERE employee_count > 0) AS with_emp,
               SUM(employee_count) AS total_reported_emp
        FROM master_employers
        WHERE display_name ILIKE ANY(%s)
        GROUP BY source_origin
        ORDER BY n DESC
        """,
        (stem_patterns,),
    )
    rollup["masters_by_source"] = [dict(r) for r in cur.fetchall()]
    rollup["master_count"] = sum(r["n"] for r in rollup["masters_by_source"])

    # --- NLRB ---
    nlrb: dict[str, Any] = {}

    # Totals by case type
    cur.execute(
        """
        SELECT COUNT(DISTINCT p.case_number) AS total,
               COUNT(DISTINCT CASE WHEN c.case_type LIKE 'RC%%' THEN p.case_number END) AS rc,
               COUNT(DISTINCT CASE WHEN c.case_type LIKE 'CA%%' THEN p.case_number END) AS ca,
               COUNT(DISTINCT CASE WHEN c.case_type LIKE 'CB%%' THEN p.case_number END) AS cb,
               COUNT(DISTINCT CASE WHEN c.case_type LIKE 'RM%%' THEN p.case_number END) AS rm,
               COUNT(DISTINCT CASE WHEN c.case_type LIKE 'RD%%' THEN p.case_number END) AS rd,
               MIN(c.earliest_date) AS earliest,
               MAX(c.latest_date) AS latest
        FROM nlrb_participants p
        JOIN nlrb_cases c ON c.case_number = p.case_number
        WHERE p.participant_name ILIKE ANY(%s)
        """,
        (stem_patterns,),
    )
    nlrb["totals"] = dict(cur.fetchone())

    # Elections summary
    cur.execute(
        """
        SELECT COUNT(DISTINCT e.case_number) AS total_elections,
               COUNT(DISTINCT CASE WHEN e.union_won THEN e.case_number END) AS union_won,
               COUNT(DISTINCT CASE WHEN NOT e.union_won THEN e.case_number END) AS union_lost,
               SUM(e.total_votes) AS total_votes,
               SUM(e.eligible_voters) AS total_eligible
        FROM nlrb_elections e
        WHERE e.case_number IN (
            SELECT case_number FROM nlrb_participants WHERE participant_name ILIKE ANY(%s)
        )
        """,
        (stem_patterns,),
    )
    row = cur.fetchone()
    row = dict(row)
    total = row["total_elections"] or 0
    won = row["union_won"] or 0
    row["win_rate_pct"] = round(100.0 * won / max(total, 1), 1) if total else None
    nlrb["elections_summary"] = row

    # Elections by year
    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM e.election_date)::int AS year,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE e.union_won) AS won,
               COUNT(*) FILTER (WHERE NOT e.union_won) AS lost
        FROM nlrb_elections e
        WHERE e.case_number IN (SELECT case_number FROM nlrb_participants WHERE participant_name ILIKE ANY(%s))
          AND e.election_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
        """,
        (stem_patterns,),
    )
    nlrb["elections_by_year"] = [dict(r) for r in cur.fetchall()]

    # Recent elections with store locations (via participant.city/state) +
    # a link to the NLRB case docket so the frontend can surface the full
    # source record, even when city/state are NULL in the bulk participant
    # data (~43% of Starbucks rows). The URL is backfilled by the
    # `nlrb_participants_case_docket_url_migration.sql` trigger.
    cur.execute(
        """
        SELECT e.case_number, e.election_date, e.union_won, e.total_votes,
               e.eligible_voters, e.vote_margin, e.election_type,
               'https://www.nlrb.gov/case/' || e.case_number AS case_docket_url,
               (SELECT STRING_AGG(DISTINCT pu.participant_name, '; ') FROM nlrb_participants pu
                WHERE pu.case_number = e.case_number AND pu.participant_type = 'Union') AS unions,
               (SELECT STRING_AGG(DISTINCT CONCAT_WS(', ', p2.city, p2.state), '; ') FROM nlrb_participants p2
                WHERE p2.case_number = e.case_number AND p2.participant_name ILIKE ANY(%s)) AS store_locations,
               (SELECT STRING_AGG(DISTINCT p3.participant_name, '; ') FROM nlrb_participants p3
                WHERE p3.case_number = e.case_number AND p3.participant_name ILIKE ANY(%s)) AS respondent_names
        FROM nlrb_elections e
        WHERE e.case_number IN (SELECT case_number FROM nlrb_participants WHERE participant_name ILIKE ANY(%s))
        ORDER BY e.election_date DESC NULLS LAST
        LIMIT %s
        """,
        (stem_patterns, stem_patterns, stem_patterns, limit_recent_elections),
    )
    nlrb["recent_elections"] = [dict(r) for r in cur.fetchall()]

    # ULP allegations by NLRA section
    cur.execute(
        """
        SELECT a.section, COUNT(*) AS n, COUNT(DISTINCT a.case_number) AS distinct_cases
        FROM nlrb_allegations a
        WHERE a.case_number IN (SELECT case_number FROM nlrb_participants WHERE participant_name ILIKE ANY(%s))
        GROUP BY a.section
        ORDER BY n DESC
        LIMIT 30
        """,
        (stem_patterns,),
    )
    nlrb["allegations_by_section"] = [dict(r) for r in cur.fetchall()]

    # Respondent name variants
    cur.execute(
        """
        SELECT p.participant_name, COUNT(DISTINCT p.case_number) AS cases
        FROM nlrb_participants p
        WHERE p.participant_name ILIKE ANY(%s)
        GROUP BY p.participant_name
        ORDER BY cases DESC
        LIMIT 50
        """,
        (stem_patterns,),
    )
    nlrb["respondent_variants"] = [dict(r) for r in cur.fetchall()]

    # States with elections
    cur.execute(
        """
        SELECT p.state, COUNT(DISTINCT e.case_number) AS elections,
               COUNT(DISTINCT CASE WHEN e.union_won THEN e.case_number END) AS won,
               COUNT(DISTINCT CASE WHEN NOT e.union_won THEN e.case_number END) AS lost
        FROM nlrb_elections e
        JOIN nlrb_participants p ON p.case_number = e.case_number
        WHERE p.participant_name ILIKE ANY(%s) AND p.state IS NOT NULL
        GROUP BY p.state
        ORDER BY elections DESC
        """,
        (stem_patterns,),
    )
    nlrb["elections_by_state"] = [dict(r) for r in cur.fetchall()]

    rollup["nlrb"] = nlrb

    # --- OSHA ---
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS establishments,
                   COUNT(DISTINCT site_state) AS states_covered,
                   SUM(employee_count) AS total_reported_emp,
                   SUM(total_inspections) AS total_inspections,
                   MIN(first_inspection_date) AS earliest_inspection,
                   MAX(last_inspection_date) AS latest_inspection
            FROM osha_establishments
            WHERE estab_name ILIKE ANY(%s)
            """,
            (stem_patterns,),
        )
        osha = {"totals": dict(cur.fetchone())}

        cur.execute(
            """
            SELECT v.violation_type,
                   SUM(v.violation_count) AS n,
                   SUM(v.total_penalties) AS total_penalties,
                   MIN(v.first_violation_date) AS earliest,
                   MAX(v.last_violation_date) AS latest
            FROM osha_violation_summary v
            JOIN osha_establishments e ON e.establishment_id = v.establishment_id
            WHERE e.estab_name ILIKE ANY(%s)
            GROUP BY v.violation_type
            ORDER BY n DESC
            """,
            (stem_patterns,),
        )
        osha["violations_by_type"] = [dict(r) for r in cur.fetchall()]
        rollup["osha"] = osha
    except Exception as e:
        rollup["osha"] = {"error": str(e)}

    # --- WHD ---
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS cases,
                   SUM(backwages_amount::numeric) AS total_back_wages,
                   SUM(civil_penalties::numeric) AS total_civil_penalties,
                   SUM(employees_backwages) AS total_employees_backwages,
                   SUM(flsa_violations) AS total_flsa_violations,
                   SUM(flsa_child_labor_violations) AS total_child_labor_violations,
                   COUNT(DISTINCT legal_name) AS distinct_legal_names,
                   COUNT(DISTINCT state) AS states_covered,
                   MIN(findings_start_date) AS earliest,
                   MAX(findings_end_date) AS latest
            FROM whd_cases
            WHERE legal_name ILIKE ANY(%s) OR trade_name ILIKE ANY(%s)
            """,
            (stem_patterns, stem_patterns),
        )
        rollup["whd"] = {"totals": dict(cur.fetchone())}
    except Exception as e:
        rollup["whd"] = {"error": str(e)}

    # --- F-7 union locals ---
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS locals_count,
                   COUNT(DISTINCT state) AS states_covered,
                   STRING_AGG(DISTINCT state, ',' ORDER BY state) AS state_list
            FROM f7_employers_deduped
            WHERE name_standard ILIKE ANY(%s)
            """,
            (stem_patterns,),
        )
        rollup["f7"] = dict(cur.fetchone())
    except Exception as e:
        rollup["f7"] = {"error": str(e)}

    return rollup
