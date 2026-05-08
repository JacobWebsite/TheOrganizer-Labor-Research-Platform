"""Report Validation Scripts for Research Dossiers.

Automated checks that run before auto-grading:
  1. Citation completeness: every claim links to a source
  2. Placeholder detection: no "TBD", "TODO", "N/A" in real values
  3. Section coverage: all 10 sections present, empty ones marked "Verified None"
  4. Numeric consistency: key numbers don't wildly contradict
  5. Source attribution: every fact has source_type and source_name

Returns a validation report with pass/fail per check and overall pass rate.
"""

import logging
import re

from db_config import get_connection
from psycopg2.extras import RealDictCursor

_log = logging.getLogger(__name__)

_DOSSIER_SECTIONS = {
    "identity", "corporate_structure", "locations", "leadership",
    "financial", "workforce", "labor", "workplace", "assessment", "sources",
}

# Patterns that indicate placeholder/incomplete content
_PLACEHOLDER_PATTERNS = re.compile(
    r"\b(TBD|TODO|FIXME|N/A|placeholder|lorem ipsum|insert here|"
    r"fill in|to be determined|unknown at this time|"
    r"data not available|could not determine)\b",
    re.IGNORECASE,
)

# Values that are fine as-is (not placeholders)
_ALLOWED_EMPTY_VALUES = {
    "Verified None (Tools searched)",
    "Not searched",
    "No data found",
    "None found",
}


def _check_section_coverage(dossier: dict) -> dict:
    """Check that all 10 sections exist and have content."""
    missing = []
    empty = []
    filled = []

    for section in _DOSSIER_SECTIONS:
        if section not in dossier:
            missing.append(section)
        elif not dossier[section]:
            empty.append(section)
        elif isinstance(dossier[section], dict) and not any(
            v not in (None, "", "Verified None (Tools searched)", "Not searched")
            for v in dossier[section].values()
        ):
            empty.append(section)
        else:
            filled.append(section)

    return {
        "check": "section_coverage",
        "passed": len(missing) == 0,
        "filled_count": len(filled),
        "empty_count": len(empty),
        "missing_count": len(missing),
        "missing_sections": missing,
        "empty_sections": empty,
        "score": len(filled) / len(_DOSSIER_SECTIONS),
    }


def _check_placeholder_text(dossier: dict) -> dict:
    """Detect placeholder text in dossier values."""
    placeholders_found = []

    for section, content in dossier.items():
        if not isinstance(content, dict):
            continue
        for field, value in content.items():
            if not value or not isinstance(value, str):
                continue
            if value in _ALLOWED_EMPTY_VALUES:
                continue
            match = _PLACEHOLDER_PATTERNS.search(value)
            if match:
                placeholders_found.append({
                    "section": section,
                    "field": field,
                    "matched": match.group(),
                    "value_preview": value[:80],
                })

    return {
        "check": "placeholder_text",
        "passed": len(placeholders_found) == 0,
        "count": len(placeholders_found),
        "items": placeholders_found[:10],  # cap output
    }


def _check_source_attribution(facts: list) -> dict:
    """Check that every fact has source_type and source_name."""
    missing_source_type = 0
    missing_source_name = 0
    system_only = 0
    total = len(facts)

    for f in facts:
        st = f.get("source_type") or ""
        sn = f.get("source_name") or ""
        if not st:
            missing_source_type += 1
        if not sn:
            missing_source_name += 1
        if st == "system" or sn == "exhaustive_coverage":
            system_only += 1

    real_facts = total - system_only
    attribution_rate = (total - missing_source_name) / total if total > 0 else 1.0

    return {
        "check": "source_attribution",
        "passed": missing_source_name == 0 and missing_source_type == 0,
        "total_facts": total,
        "real_facts": real_facts,
        "system_facts": system_only,
        "missing_source_type": missing_source_type,
        "missing_source_name": missing_source_name,
        "attribution_rate": round(attribution_rate, 3),
    }


def _check_citation_links(dossier: dict, facts: list) -> dict:
    """Check that dossier claims can be traced to facts with sources."""
    # Count dossier fields that have real content (not "Verified None")
    claims_total = 0
    claims_with_facts = 0

    fact_attrs = {f.get("attribute_name") for f in facts if f.get("source_name") != "exhaustive_coverage"}

    for section, content in dossier.items():
        if not isinstance(content, dict):
            continue
        for field, value in content.items():
            if not value or not isinstance(value, str):
                continue
            if value in _ALLOWED_EMPTY_VALUES:
                continue
            claims_total += 1
            if field in fact_attrs:
                claims_with_facts += 1

    citation_rate = claims_with_facts / claims_total if claims_total > 0 else 1.0

    return {
        "check": "citation_links",
        "passed": citation_rate >= 0.5,  # at least half of claims have facts
        "claims_total": claims_total,
        "claims_with_facts": claims_with_facts,
        "citation_rate": round(citation_rate, 3),
    }


def _check_numeric_consistency(facts: list) -> dict:
    """Check for wildly inconsistent numeric facts."""
    from scripts.research.auto_grader import _extract_numeric

    inconsistencies = []

    # Group numeric facts by attribute
    numeric_groups = {}
    for f in facts:
        attr = f.get("attribute_name", "")
        if attr in ("employee_count", "revenue", "osha_violation_count", "whd_case_count"):
            val = _extract_numeric(f.get("attribute_value"))
            if val is not None and val > 0:
                numeric_groups.setdefault(attr, []).append({
                    "value": val,
                    "source": f.get("source_name", "unknown"),
                })

    for attr, entries in numeric_groups.items():
        if len(entries) < 2:
            continue
        values = [e["value"] for e in entries]
        min_v, max_v = min(values), max(values)
        if min_v > 0 and max_v / min_v > 3.0:
            inconsistencies.append({
                "attribute": attr,
                "min": min_v,
                "max": max_v,
                "ratio": round(max_v / min_v, 1),
                "sources": [e["source"][:40] for e in entries],
            })

    return {
        "check": "numeric_consistency",
        "passed": len(inconsistencies) == 0,
        "inconsistencies": inconsistencies,
    }


def validate_dossier(run_id: int) -> dict:
    """Run all validation checks on a research run.

    Returns validation report with per-check results and overall score.
    """
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    # Load dossier
    cur.execute("SELECT dossier_json FROM research_runs WHERE id = %s", (run_id,))
    row = cur.fetchone()
    if not row or not row.get("dossier_json"):
        conn.close()
        return {"run_id": run_id, "error": "No dossier found", "checks": [], "overall_pass_rate": 0}

    import json
    raw = row["dossier_json"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    dossier = raw.get("dossier", {})

    # Load facts
    cur.execute(
        "SELECT attribute_name, attribute_value, source_type, source_name, confidence "
        "FROM research_facts WHERE run_id = %s",
        (run_id,),
    )
    facts = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Run all checks
    checks = [
        _check_section_coverage(dossier),
        _check_placeholder_text(dossier),
        _check_source_attribution(facts),
        _check_citation_links(dossier, facts),
        _check_numeric_consistency(facts),
    ]

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)

    report = {
        "run_id": run_id,
        "checks": checks,
        "passed_count": passed,
        "total_checks": total,
        "overall_pass_rate": round(passed / total, 2) if total > 0 else 0,
    }

    _log.info(
        "Run %d validation: %d/%d checks passed (%.0f%%)",
        run_id, passed, total, report["overall_pass_rate"] * 100,
    )
    return report
