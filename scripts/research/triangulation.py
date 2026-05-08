"""Triangulation: count independent sources per claim in a research run.

For each numeric claim attribute, counts how many distinct source_name values
support it. Updates research_facts.triangulation_status with:
  single-source | dual-source | triple-plus
"""

import logging
from collections import defaultdict

from db_config import get_connection
from psycopg2.extras import RealDictCursor

_log = logging.getLogger(__name__)

# Numeric attributes worth triangulating -- these are the claims where
# multiple independent sources materially increase trust.
NUMERIC_CLAIM_ATTRS = {
    "employee_count",
    "revenue",
    "osha_violation_count",
    "osha_serious_count",
    "osha_penalty_total",
    "whd_case_count",
    "nlrb_ulp_count",
    "nlrb_election_count",
    "federal_obligations",
    "year_founded",
}


def _status_label(source_count: int) -> str:
    if source_count >= 3:
        return "triple-plus"
    if source_count == 2:
        return "dual-source"
    return "single-source"


def triangulate_facts(run_id: int) -> dict:
    """Count independent sources per major claim and update triangulation_status.

    Returns summary dict:
      total_claims: int
      single_source_count: int
      dual_source_count: int
      triple_plus_count: int
      flagged_claims: list of attribute_names with single-source status
    """
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, attribute_name, source_name "
        "FROM research_facts "
        "WHERE run_id = %s AND attribute_name = ANY(%s)",
        (run_id, list(NUMERIC_CLAIM_ATTRS)),
    )
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return {
            "total_claims": 0,
            "single_source_count": 0,
            "dual_source_count": 0,
            "triple_plus_count": 0,
            "flagged_claims": [],
        }

    # Group facts by attribute_name, collecting distinct source_names
    attr_sources = defaultdict(set)   # attr_name -> set of source_names
    attr_fact_ids = defaultdict(list)  # attr_name -> list of fact IDs

    for r in rows:
        attr = r["attribute_name"]
        src = r["source_name"] or ""
        # Skip system-generated placeholder facts from exhaustive coverage
        if "exhaustive_coverage" in src.lower() or "system" in src.lower():
            continue
        attr_sources[attr].add(src)
        attr_fact_ids[attr].append(r["id"])

    # Compute status per attribute and batch-update
    summary = {
        "total_claims": 0,
        "single_source_count": 0,
        "dual_source_count": 0,
        "triple_plus_count": 0,
        "flagged_claims": [],
    }

    updates = []  # (status, fact_id)

    for attr, sources in attr_sources.items():
        count = len(sources)
        status = _status_label(count)
        summary["total_claims"] += 1

        if status == "single-source":
            summary["single_source_count"] += 1
            summary["flagged_claims"].append(attr)
        elif status == "dual-source":
            summary["dual_source_count"] += 1
        else:
            summary["triple_plus_count"] += 1

        for fid in attr_fact_ids[attr]:
            updates.append((status, fid))

    if updates:
        from psycopg2.extras import execute_batch
        execute_batch(
            cur,
            "UPDATE research_facts SET triangulation_status = %s WHERE id = %s",
            updates,
        )
        conn.commit()

    conn.close()

    _log.info(
        "Run %d triangulation: %d claims (%d single, %d dual, %d triple+)",
        run_id,
        summary["total_claims"],
        summary["single_source_count"],
        summary["dual_source_count"],
        summary["triple_plus_count"],
    )
    return summary
