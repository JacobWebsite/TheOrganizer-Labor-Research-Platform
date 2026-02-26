"""
Research Agent Auto-Grader (Phase 5.3, updated Phase 5.7)

Deterministic quality grading for completed research runs.
Computes 6 dimension scores (each 0-10) and a weighted overall score.

Weights (D16 decision, updated Phase 5.7):
  Coverage 20%, Source Quality 35%, Consistency 15%, Actionability 15%,
  Freshness 10%, Efficiency 5%

Phase 5.7 changes:
  - Coverage: field-level scoring (not section-level) + placeholder penalty
  - New: Actionability dimension (recommended_approach, campaign detail, etc.)
  - Consistency weight reduced 25% -> 15% (was rewarding shallowness)
  - Freshness weight reduced 15% -> 10%

Usage:
  py scripts/research/auto_grader.py            # backfill all unscored runs
  py scripts/research/auto_grader.py --run-id 5  # grade a specific run
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Allow running from project root
sys.path.insert(0, ".")
from db_config import get_connection

_log = logging.getLogger("auto_grader")

# D16 weights (updated Phase 5.7 — added actionability, rebalanced)
WEIGHTS = {
    "coverage": 0.20,
    "source_quality": 0.35,
    "consistency": 0.15,
    "actionability": 0.15,
    "freshness": 0.10,
    "efficiency": 0.05,
}

TOTAL_SECTIONS = 7  # identity, labor, assessment, workforce, workplace, financial, sources

SOURCE_TYPE_RANK = {
    "database": 1.0,
    "api": 0.9,
    "web_scrape": 0.7,
    "web_search": 0.6,
    "news": 0.5,
}

# Known placeholder/generic values that shouldn't count as real data
_PLACEHOLDER_VALUES = re.compile(
    r'^(unknown|no data|not found|not available|n/a|none|null|'
    r'no\s+(?:results?|information|data)\s+(?:found|available))$',
    re.IGNORECASE,
)

# BLS generic baseline values (from get_workforce_demographics fallback)
_GENERIC_BASELINE_MARKERS = re.compile(
    r'race_white[=:]\s*76.*race_black[=:]\s*12.*gender_male[=:]\s*53.*avg_age[=:]\s*42',
    re.IGNORECASE,
)


def _score_coverage(facts_by_section: Dict[str, List[dict]],
                    dossier_json: Optional[dict] = None) -> float:
    """Coverage: field-level scoring across all dossier sections.

    Phase 5.7: Counts non-null, non-placeholder fields instead of just sections.
    Also penalizes known generic/placeholder values.
    """
    if dossier_json and "dossier" in dossier_json:
        # Field-level scoring from the dossier JSON
        body = dossier_json["dossier"]
        total_fields = 0
        filled_fields = 0
        placeholder_count = 0

        for sec_name in ["identity", "financial", "workforce", "labor",
                         "workplace", "assessment", "sources"]:
            sec_dict = body.get(sec_name)
            if not isinstance(sec_dict, dict):
                continue
            for key, val in sec_dict.items():
                total_fields += 1
                if val is None or val == "" or val == []:
                    continue
                # Check for placeholder values
                val_str = str(val).strip() if not isinstance(val, (dict, list)) else ""
                if val_str and _PLACEHOLDER_VALUES.match(val_str):
                    placeholder_count += 1
                    continue
                # Check for unlabeled generic BLS baseline
                if key == "demographic_profile" and isinstance(val, str):
                    if _GENERIC_BASELINE_MARKERS.search(val) and "INDUSTRY BASELINE" not in val:
                        placeholder_count += 1
                        continue
                filled_fields += 1

        if total_fields == 0:
            return 0.0

        fill_rate = filled_fields / total_fields
        score = fill_rate * 10.0

        # Penalty for placeholders: -0.5 each, max -2.0
        placeholder_penalty = min(placeholder_count * 0.5, 2.0)
        score -= placeholder_penalty

        return max(min(score, 10.0), 0.0)

    # Fallback: section-level scoring (for runs without dossier_json)
    sections_filled = len(facts_by_section)
    base = (sections_filled / TOTAL_SECTIONS) * 8.0

    # Bonus for rich sections (3+ facts)
    bonus = 0.0
    for facts in facts_by_section.values():
        if len(facts) >= 3:
            bonus += 0.4
    bonus = min(bonus, 2.0)

    return min(base + bonus, 10.0)


def _score_source_quality(facts: List[dict]) -> float:
    """Source Quality: based on source types and confidence levels."""
    if not facts:
        return 0.0

    # Average source type score
    source_scores = []
    null_source_count = 0
    for f in facts:
        st = (f.get("source_type") or "").lower()
        source_scores.append(SOURCE_TYPE_RANK.get(st, 0.5))
        if not f.get("source_name"):
            null_source_count += 1

    avg_source = sum(source_scores) / len(source_scores) if source_scores else 0.5

    # Average confidence
    confidences = []
    for f in facts:
        c = f.get("confidence")
        if c is not None:
            confidences.append(float(c))
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

    combined = (0.5 * avg_source + 0.5 * avg_confidence) * 10.0

    # Penalty for missing source names
    if len(facts) > 0 and (null_source_count / len(facts)) > 0.30:
        combined -= 1.0

    return max(min(combined, 10.0), 0.0)


def _extract_numeric(val: Any) -> Optional[float]:
    """Extract a float from various types, including strings with suffixes/commas."""
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return float(val)
    if isinstance(val, str):
        # Remove commas and common suffixes
        cleaned = re.sub(r'[^\d.]', '', val.split(' ')[0].replace(',', ''))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _score_consistency(facts: List[dict]) -> float:
    """Consistency: penalize contradictions and large numeric divergences."""
    score = 10.0

    # Count contradictions
    contradictions = sum(1 for f in facts if f.get("contradicts_fact_id") is not None)
    score -= contradictions * 2.0

    # Check employee_count divergence
    emp_values = []
    for f in facts:
        if f.get("attribute_name") == "employee_count":
            val = _extract_numeric(f.get("attribute_value"))
            if val:
                emp_values.append(val)
    if len(emp_values) > 1:
        min_val = min(emp_values)
        max_val = max(emp_values)
        if min_val > 0 and (max_val / min_val) > 2.0:
            score -= 2.0

    # Check revenue divergence
    rev_values = []
    for f in facts:
        if f.get("attribute_name") == "revenue":
            val = _extract_numeric(f.get("attribute_value"))
            if val:
                rev_values.append(val)
    if len(rev_values) > 1:
        min_val = min(rev_values)
        max_val = max(rev_values)
        if min_val > 0 and (max_val / min_val) > 2.0:
            score -= 2.0

    # DB-vs-web cross-check: violation mismatch
    # If DB says 0 violations but web/api facts mention violation keywords
    _VIOLATION_ATTRS = {"osha_violation_count", "osha_serious_count", "whd_case_count", "nlrb_ulp_count"}
    _VIOLATION_KEYWORDS = re.compile(
        r"\b(violations?|fined?|penalt(?:y|ies)|cited|citations?|injur(?:y|ies)|deaths?|fatalit(?:y|ies)|fatal)\b",
        re.IGNORECASE,
    )
    db_zero_attrs = set()
    for f in facts:
        attr = f.get("attribute_name", "")
        if attr in _VIOLATION_ATTRS:
            st = (f.get("source_type") or "").lower()
            if st == "database":
                val = _extract_numeric(f.get("attribute_value"))
                if val is not None and val == 0:
                    db_zero_attrs.add(attr)

    if db_zero_attrs:
        # Check web/api facts for contradiction keywords
        web_texts = []
        for f in facts:
            st = (f.get("source_type") or "").lower()
            if st in ("web_scrape", "web_search", "api", "news"):
                val_str = str(f.get("attribute_value") or "")
                web_texts.append(val_str)
        combined_web = " ".join(web_texts)
        if _VIOLATION_KEYWORDS.search(combined_web):
            # Deduct once per zero-DB-attr that's contradicted (max 1.0 each)
            penalty = min(len(db_zero_attrs), 4) * 1.0
            score -= penalty

    # DB-vs-web cross-check: organizing mismatch
    # If no NLRB DB facts but web mentions organizing keywords
    _ORGANIZING_KEYWORDS = re.compile(
        r"\b(union\w*|organiz\w*|campaigns?|elections?|bargain\w*|strikes?|walkouts?|petitions?|nlrb)\b",
        re.IGNORECASE,
    )
    has_nlrb_db = any(
        f.get("attribute_name", "").startswith("nlrb_")
        and (f.get("source_type") or "").lower() == "database"
        and f.get("attribute_value") not in (None, "", "0", 0)
        for f in facts
    )
    if not has_nlrb_db:
        web_texts_org = []
        for f in facts:
            st = (f.get("source_type") or "").lower()
            if st in ("web_scrape", "web_search", "api", "news"):
                val_str = str(f.get("attribute_value") or "")
                web_texts_org.append(val_str)
        combined_web_org = " ".join(web_texts_org)
        if _ORGANIZING_KEYWORDS.search(combined_web_org):
            score -= 0.5

    return max(score, 0.0)


def _score_actionability(dossier_json: Optional[dict] = None) -> float:
    """Actionability: can an organizer act on this dossier? (Phase 5.7)

    Scores based on:
    - recommended_approach present and substantive (+3)
    - campaign_strengths has 3+ items (+2)
    - campaign_challenges has 3+ items (+2)
    - source_contradictions is non-null (+1)
    - financial_trend is non-null (+1)
    - exec_compensation is non-null for public companies (+1)
    """
    if not dossier_json or "dossier" not in dossier_json:
        return 0.0

    body = dossier_json["dossier"]
    assessment = body.get("assessment", {}) or {}
    financial = body.get("financial", {}) or {}
    score = 0.0

    # recommended_approach: +3 if present and > 50 chars
    rec = assessment.get("recommended_approach")
    if rec and isinstance(rec, str) and len(rec.strip()) > 50:
        score += 3.0

    # campaign_strengths: +2 if 3+ items
    strengths = assessment.get("campaign_strengths")
    if isinstance(strengths, list) and len(strengths) >= 3:
        score += 2.0

    # campaign_challenges: +2 if 3+ items
    challenges = assessment.get("campaign_challenges")
    if isinstance(challenges, list) and len(challenges) >= 3:
        score += 2.0

    # source_contradictions: +1 if non-null
    contradictions = assessment.get("source_contradictions")
    if contradictions and contradictions != []:
        score += 1.0

    # financial_trend: +1 if non-null
    trend = assessment.get("financial_trend")
    if trend and isinstance(trend, str) and len(trend.strip()) > 3:
        score += 1.0

    # exec_compensation: +1 if present (public companies)
    exec_comp = financial.get("exec_compensation")
    if exec_comp and exec_comp != [] and exec_comp != {}:
        score += 1.0

    return min(score, 10.0)


def _score_freshness(facts: List[dict], today: Optional[date] = None) -> float:
    """Freshness: how recent the fact data is."""
    if not facts:
        return 5.0  # neutral

    today = today or date.today()
    scores = []
    for f in facts:
        as_of = f.get("as_of_date")
        if as_of is None:
            scores.append(5.0)  # neutral for undated facts
            continue

        if isinstance(as_of, str):
            try:
                as_of = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                scores.append(5.0)
                continue
        elif isinstance(as_of, datetime):
            as_of = as_of.date()

        age_days = (today - as_of).days
        if age_days < 183:       # < 6 months
            scores.append(10.0)
        elif age_days < 365:     # 6-12 months
            scores.append(8.0)
        elif age_days < 730:     # 1-2 years
            scores.append(6.0)
        elif age_days < 1095:    # 2-3 years
            scores.append(4.0)
        elif age_days < 1825:    # 3-5 years
            scores.append(2.0)
        else:                    # > 5 years
            scores.append(1.0)

    return sum(scores) / len(scores) if scores else 5.0


def _score_efficiency(total_facts: int, total_tools: int, actions: List[dict]) -> float:
    """Efficiency: facts per tool call and speed."""
    facts_per_tool = total_facts / max(total_tools, 1)

    if facts_per_tool >= 3:
        score = 10.0
    elif facts_per_tool >= 2:
        score = 8.0
    elif facts_per_tool >= 1:
        score = 6.0
    elif facts_per_tool >= 0.5:
        score = 4.0
    else:
        score = 2.0

    # Speed bonus
    latencies = [float(a["latency_ms"]) for a in actions if a.get("latency_ms") is not None]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        if avg_latency < 500:
            score += 1.0

    return min(score, 10.0)


def grade_research_run(run_id: int, conn=None) -> dict:
    """
    Compute 6 dimension scores and weighted overall for a research run.

    Returns dict with keys: coverage, source_quality, consistency, actionability,
    freshness, efficiency, overall, and metadata about the computation.
    """
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()

        # Verify run exists and is completed
        cur.execute(
            "SELECT id, total_tools_called, total_facts_found, sections_filled, dossier_json "
            "FROM research_runs WHERE id = %s",
            (run_id,),
        )
        run = cur.fetchone()
        if not run:
            raise ValueError(f"Research run {run_id} not found")
        if run.get("total_facts_found") is None:
            raise ValueError(f"Research run {run_id} has no facts data (likely not completed)")

        total_tools = run["total_tools_called"] or 0
        total_facts = run["total_facts_found"] or 0

        # Parse dossier JSON for field-level scoring
        dossier_json = None
        raw_dossier = run.get("dossier_json")
        if raw_dossier:
            if isinstance(raw_dossier, dict):
                dossier_json = raw_dossier
            elif isinstance(raw_dossier, str):
                try:
                    dossier_json = json.loads(raw_dossier)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Get all facts
        cur.execute(
            "SELECT dossier_section, attribute_name, attribute_value, "
            "source_type, source_name, confidence, as_of_date, contradicts_fact_id "
            "FROM research_facts WHERE run_id = %s",
            (run_id,),
        )
        all_facts = [dict(r) for r in cur.fetchall()]

        # Group by section
        facts_by_section: Dict[str, List[dict]] = {}
        for f in all_facts:
            sec = f["dossier_section"]
            if sec not in facts_by_section:
                facts_by_section[sec] = []
            facts_by_section[sec].append(f)

        # Get actions for efficiency scoring
        cur.execute(
            "SELECT latency_ms FROM research_actions WHERE run_id = %s",
            (run_id,),
        )
        actions = [dict(r) for r in cur.fetchall()]

        # Compute each dimension
        coverage = round(_score_coverage(facts_by_section, dossier_json=dossier_json), 2)
        source_quality = round(_score_source_quality(all_facts), 2)
        consistency = round(_score_consistency(all_facts), 2)
        actionability = round(_score_actionability(dossier_json=dossier_json), 2)
        freshness = round(_score_freshness(all_facts), 2)
        efficiency = round(_score_efficiency(total_facts, total_tools, actions), 2)

        overall = round(
            coverage * WEIGHTS["coverage"]
            + source_quality * WEIGHTS["source_quality"]
            + consistency * WEIGHTS["consistency"]
            + actionability * WEIGHTS["actionability"]
            + freshness * WEIGHTS["freshness"]
            + efficiency * WEIGHTS["efficiency"],
            2,
        )

        return {
            "coverage": coverage,
            "source_quality": source_quality,
            "consistency": consistency,
            "actionability": actionability,
            "freshness": freshness,
            "efficiency": efficiency,
            "overall": overall,
            "facts_count": len(all_facts),
            "sections_count": len(facts_by_section),
            "actions_count": len(actions),
        }
    finally:
        if close_conn:
            conn.close()


def grade_and_save(run_id: int, conn=None) -> dict:
    """Grade a run and persist scores to research_runs."""
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        result = grade_research_run(run_id, conn=conn)

        dimensions = {
            "coverage": result["coverage"],
            "source_quality": result["source_quality"],
            "consistency": result["consistency"],
            "actionability": result["actionability"],
            "freshness": result["freshness"],
            "efficiency": result["efficiency"],
        }

        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()
        cur.execute(
            "UPDATE research_runs "
            "SET overall_quality_score = %s, quality_dimensions = %s, updated_at = NOW() "
            "WHERE id = %s",
            (result["overall"], json.dumps(dimensions), run_id),
        )
        conn.commit()

        _log.info("Run %d graded: overall=%.2f (%s)", run_id, result["overall"], dimensions)
        return result
    finally:
        if close_conn:
            conn.close()


def compute_research_enhancements(run_id: int, conn=None) -> Optional[int]:
    """Compute scorecard factor scores from a research dossier and UPSERT into
    research_score_enhancements.

    Returns the enhancement row id, or None if skipped (quality gate, no employer_id).
    """
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()

        # Load run metadata
        cur.execute(
            "SELECT id, employer_id, dossier_json, overall_quality_score "
            "FROM research_runs WHERE id = %s",
            (run_id,),
        )
        run = cur.fetchone()
        if not run:
            _log.warning("Enhancement skipped: run %d not found", run_id)
            return None

        employer_id = run.get("employer_id")
        if not employer_id:
            _log.info("Enhancement skipped: run %d has no employer_id", run_id)
            return None

        quality = float(run["overall_quality_score"]) if run["overall_quality_score"] else 0.0
        if quality < 7.0:
            _log.info("Enhancement skipped: run %d quality %.2f < 7.0", run_id, quality)
            return None

        # Parse dossier
        raw = run.get("dossier_json")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        if not isinstance(raw, dict) or "dossier" not in raw:
            return None
        body = raw["dossier"]

        # Determine path: is this employer in f7_employers_deduped?
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM f7_employers_deduped WHERE employer_id = %s) AS e",
            (employer_id,),
        )
        is_union_ref = cur.fetchone()["e"]

        # Extract raw values from dossier sections
        identity = body.get("identity", {}) or {}
        financial = body.get("financial", {}) or {}
        workplace = body.get("workplace", {}) or {}
        labor = body.get("labor", {}) or {}
        assessment = body.get("assessment", {}) or {}

        osha_violations = _extract_int(workplace.get("osha_violation_count"))
        osha_serious = _extract_int(workplace.get("osha_serious_count"))
        osha_penalty = _extract_numeric(workplace.get("osha_penalty_total"))
        nlrb_elections = _extract_int(labor.get("nlrb_election_count"))
        nlrb_ulp = _extract_int(labor.get("nlrb_ulp_count"))
        whd_cases = _extract_int(workplace.get("whd_case_count"))
        employee_count = _extract_int(
            financial.get("employee_count") or identity.get("employee_count")
        )
        revenue = _extract_int(financial.get("revenue"))
        fed_obligations = _extract_int(financial.get("federal_obligations"))
        year_founded = _extract_int(identity.get("year_founded"))
        naics_found = identity.get("naics_code")
        if isinstance(naics_found, str):
            naics_found = naics_found.strip()[:10] or None
        else:
            naics_found = None

        # Compute factor scores using same logic as build_unified_scorecard.py
        # Only set a score if research found positive data
        s_osha = None
        if osha_violations and osha_violations > 0:
            # Simplified: violations / industry avg (2.23 default) capped at 10
            ratio = osha_violations / 2.23
            s_osha = min(10.0, round(ratio, 2))
            if osha_serious and osha_serious > 0:
                s_osha = min(10.0, s_osha + 1)

        s_nlrb = None
        if nlrb_elections and nlrb_elections > 0 or nlrb_ulp and nlrb_ulp > 0:
            election_score = (nlrb_elections or 0) * 2  # simplified: count elections
            ulp_boost = 0
            ulp_n = nlrb_ulp or 0
            if ulp_n >= 10:
                ulp_boost = 8
            elif ulp_n >= 4:
                ulp_boost = 6
            elif ulp_n >= 2:
                ulp_boost = 4
            elif ulp_n == 1:
                ulp_boost = 2
            s_nlrb = min(10.0, round(float(election_score + ulp_boost), 2))

        s_whd = None
        if whd_cases and whd_cases > 0:
            if whd_cases == 1:
                s_whd = 5.0
            elif whd_cases <= 3:
                s_whd = 7.0
            else:
                s_whd = 10.0

        s_contracts = None
        if fed_obligations and fed_obligations > 0:
            if fed_obligations >= 100_000_000:
                s_contracts = 10.0
            elif fed_obligations >= 10_000_000:
                s_contracts = 8.0
            elif fed_obligations >= 1_000_000:
                s_contracts = 6.0
            elif fed_obligations >= 100_000:
                s_contracts = 4.0
            else:
                s_contracts = 2.0

        s_financial = None
        if revenue and revenue > 0:
            if revenue >= 10_000_000:
                s_financial = 6.0
            elif revenue >= 1_000_000:
                s_financial = 4.0
            elif revenue >= 100_000:
                s_financial = 2.0
            else:
                s_financial = 0.0

        s_size = None
        if employee_count and employee_count > 0:
            if employee_count < 15:
                s_size = 0.0
            elif employee_count >= 500:
                s_size = 10.0
            else:
                s_size = round(((employee_count - 15) / 485) * 10, 2)

        # Extract assessment fields
        rec_approach = assessment.get("recommended_approach")
        if isinstance(rec_approach, str) and len(rec_approach.strip()) < 10:
            rec_approach = None
        strengths = assessment.get("campaign_strengths")
        if not isinstance(strengths, list):
            strengths = None
        challenges = assessment.get("campaign_challenges")
        if not isinstance(challenges, list):
            challenges = None
        contradictions = assessment.get("source_contradictions")
        if not isinstance(contradictions, (list, dict)):
            contradictions = None
        fin_trend = assessment.get("financial_trend")
        if isinstance(fin_trend, str) and len(fin_trend.strip()) < 5:
            fin_trend = None

        # Compute average confidence from facts
        cur.execute(
            "SELECT AVG(confidence) AS avg_conf FROM research_facts "
            "WHERE run_id = %s AND confidence IS NOT NULL",
            (run_id,),
        )
        avg_conf_row = cur.fetchone()
        confidence_avg = round(float(avg_conf_row["avg_conf"]), 2) if avg_conf_row and avg_conf_row["avg_conf"] else None

        # UPSERT: replace if new run has higher quality
        cur.execute("""
            INSERT INTO research_score_enhancements (
                employer_id, run_id, run_quality, is_union_reference,
                score_osha, score_nlrb, score_whd, score_contracts,
                score_financial, score_size,
                osha_violations_found, osha_serious_found, osha_penalty_total_found,
                nlrb_elections_found, nlrb_ulp_found, whd_cases_found,
                employee_count_found, revenue_found, federal_obligations_found,
                year_founded_found, naics_found,
                recommended_approach, campaign_strengths, campaign_challenges,
                source_contradictions, financial_trend,
                confidence_avg, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (employer_id) DO UPDATE SET
                run_id = EXCLUDED.run_id,
                run_quality = EXCLUDED.run_quality,
                is_union_reference = EXCLUDED.is_union_reference,
                score_osha = COALESCE(EXCLUDED.score_osha, research_score_enhancements.score_osha),
                score_nlrb = COALESCE(EXCLUDED.score_nlrb, research_score_enhancements.score_nlrb),
                score_whd = COALESCE(EXCLUDED.score_whd, research_score_enhancements.score_whd),
                score_contracts = COALESCE(EXCLUDED.score_contracts, research_score_enhancements.score_contracts),
                score_financial = COALESCE(EXCLUDED.score_financial, research_score_enhancements.score_financial),
                score_size = COALESCE(EXCLUDED.score_size, research_score_enhancements.score_size),
                osha_violations_found = COALESCE(EXCLUDED.osha_violations_found, research_score_enhancements.osha_violations_found),
                osha_serious_found = COALESCE(EXCLUDED.osha_serious_found, research_score_enhancements.osha_serious_found),
                osha_penalty_total_found = COALESCE(EXCLUDED.osha_penalty_total_found, research_score_enhancements.osha_penalty_total_found),
                nlrb_elections_found = COALESCE(EXCLUDED.nlrb_elections_found, research_score_enhancements.nlrb_elections_found),
                nlrb_ulp_found = COALESCE(EXCLUDED.nlrb_ulp_found, research_score_enhancements.nlrb_ulp_found),
                whd_cases_found = COALESCE(EXCLUDED.whd_cases_found, research_score_enhancements.whd_cases_found),
                employee_count_found = COALESCE(EXCLUDED.employee_count_found, research_score_enhancements.employee_count_found),
                revenue_found = COALESCE(EXCLUDED.revenue_found, research_score_enhancements.revenue_found),
                federal_obligations_found = COALESCE(EXCLUDED.federal_obligations_found, research_score_enhancements.federal_obligations_found),
                year_founded_found = COALESCE(EXCLUDED.year_founded_found, research_score_enhancements.year_founded_found),
                naics_found = COALESCE(EXCLUDED.naics_found, research_score_enhancements.naics_found),
                recommended_approach = COALESCE(EXCLUDED.recommended_approach, research_score_enhancements.recommended_approach),
                campaign_strengths = COALESCE(EXCLUDED.campaign_strengths, research_score_enhancements.campaign_strengths),
                campaign_challenges = COALESCE(EXCLUDED.campaign_challenges, research_score_enhancements.campaign_challenges),
                source_contradictions = COALESCE(EXCLUDED.source_contradictions, research_score_enhancements.source_contradictions),
                financial_trend = COALESCE(EXCLUDED.financial_trend, research_score_enhancements.financial_trend),
                confidence_avg = EXCLUDED.confidence_avg,
                updated_at = NOW()
            WHERE EXCLUDED.run_quality >= COALESCE(research_score_enhancements.run_quality, 0)
            RETURNING id
        """, (
            employer_id, run_id, quality, is_union_ref,
            s_osha, s_nlrb, s_whd, s_contracts, s_financial, s_size,
            osha_violations, osha_serious, osha_penalty,
            nlrb_elections, nlrb_ulp, whd_cases,
            employee_count, revenue, fed_obligations,
            year_founded, naics_found,
            rec_approach,
            json.dumps(strengths) if strengths else None,
            json.dumps(challenges) if challenges else None,
            json.dumps(contradictions) if contradictions else None,
            fin_trend,
            confidence_avg,
        ))
        row = cur.fetchone()
        conn.commit()

        if row:
            _log.info(
                "Enhancement saved for employer %s (run %d, union_ref=%s): "
                "osha=%s nlrb=%s whd=%s contracts=%s financial=%s size=%s",
                employer_id, run_id, is_union_ref,
                s_osha, s_nlrb, s_whd, s_contracts, s_financial, s_size,
            )
            return row["id"]
        else:
            _log.info("Enhancement skipped for employer %s: existing run has higher quality", employer_id)
            return None

    finally:
        if close_conn:
            conn.close()


def _extract_int(val: Any) -> Optional[int]:
    """Extract an integer from various types."""
    n = _extract_numeric(val)
    return int(n) if n is not None else None


def backfill_enhancements() -> int:
    """Backfill research_score_enhancements from all completed, graded runs."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM research_runs "
            "WHERE status = 'completed' AND overall_quality_score >= 7.0 "
            "AND employer_id IS NOT NULL "
            "ORDER BY id"
        )
        run_ids = [r["id"] for r in cur.fetchall()]

        if not run_ids:
            _log.info("No eligible runs for enhancement backfill.")
            return 0

        _log.info("Backfilling enhancements for %d runs...", len(run_ids))
        saved = 0
        for rid in run_ids:
            try:
                result = compute_research_enhancements(rid, conn=conn)
                if result:
                    saved += 1
            except Exception as e:
                _log.warning("  Enhancement run %d failed: %s", rid, e)

        _log.info("Enhancement backfill complete: %d/%d saved.", saved, len(run_ids))
        return saved
    finally:
        conn.close()


def backfill_all_scores() -> int:
    """Grade all completed runs that have no quality score yet."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM research_runs "
            "WHERE status = 'completed' AND overall_quality_score IS NULL "
            "ORDER BY id"
        )
        run_ids = [r["id"] for r in cur.fetchall()]

        if not run_ids:
            _log.info("No unscored completed runs found.")
            return 0

        _log.info("Backfilling scores for %d runs...", len(run_ids))
        graded = 0
        for rid in run_ids:
            try:
                result = grade_and_save(rid, conn=conn)
                _log.info("  Run %d: overall=%.2f", rid, result["overall"])
                graded += 1
            except Exception as e:
                _log.warning("  Run %d failed: %s", rid, e)

        _log.info("Backfill complete: %d/%d runs graded.", graded, len(run_ids))

        # Update strategy quality after backfill
        try:
            update_strategy_quality(conn=conn)
        except Exception as e:
            _log.warning("Strategy quality update failed: %s", e)

        return graded
    finally:
        conn.close()


def update_strategy_quality(conn=None) -> int:
    """
    Seed and update research_strategies from completed research runs.

    Uses UPSERT: INSERT rows from research_actions JOIN research_runs grouped
    by (industry 2-digit NAICS, company_type, size_bucket, tool_name), then
    updates avg_quality, hit_rate, avg_latency_ms from graded runs.

    Returns the number of rows upserted.
    """
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()

        cur.execute("""
            INSERT INTO research_strategies
                (industry_naics_2digit, company_type, company_size_bucket, tool_name,
                 times_tried, times_found_data, hit_rate, avg_quality, avg_latency_ms,
                 last_updated)
            SELECT
                COALESCE(LEFT(rr.industry_naics, 2), ''),
                COALESCE(rr.company_type, ''),
                COALESCE(rr.employee_size_bucket, ''),
                ra.tool_name,
                COUNT(*) AS times_tried,
                COUNT(*) FILTER (WHERE ra.data_found = TRUE) AS times_found_data,
                ROUND(
                    COUNT(*) FILTER (WHERE ra.data_found = TRUE)::numeric
                    / NULLIF(COUNT(*), 0), 4
                ) AS hit_rate,
                ROUND(AVG(rr.overall_quality_score) FILTER (WHERE ra.data_found = TRUE), 2),
                COALESCE(AVG(ra.latency_ms)::integer, 0),
                NOW()
            FROM research_actions ra
            JOIN research_runs rr ON rr.id = ra.run_id
            WHERE rr.status = 'completed'
            GROUP BY LEFT(rr.industry_naics, 2), rr.company_type,
                     rr.employee_size_bucket, ra.tool_name
            ON CONFLICT (industry_naics_2digit, company_type, company_size_bucket, tool_name)
            DO UPDATE SET
                times_tried = EXCLUDED.times_tried,
                times_found_data = EXCLUDED.times_found_data,
                hit_rate = EXCLUDED.hit_rate,
                avg_quality = COALESCE(EXCLUDED.avg_quality, research_strategies.avg_quality),
                avg_latency_ms = EXCLUDED.avg_latency_ms,
                last_updated = NOW()
        """)
        upserted = cur.rowcount
        conn.commit()
        _log.info("Upserted %d strategy rows.", upserted)
        return upserted
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Auto-grade research runs")
    parser.add_argument("--run-id", type=int, help="Grade a specific run")
    parser.add_argument("--backfill-enhancements", action="store_true",
                        help="Backfill research_score_enhancements from graded runs")
    args = parser.parse_args()

    if args.backfill_enhancements:
        count = backfill_enhancements()
        print(f"Backfilled {count} enhancement rows.")
    elif args.run_id:
        result = grade_and_save(args.run_id)
        print(f"Run {args.run_id}: overall={result['overall']}")
        for dim in ["coverage", "source_quality", "consistency", "actionability",
                     "freshness", "efficiency"]:
            print(f"  {dim}: {result[dim]}")
    else:
        count = backfill_all_scores()
        print(f"Backfilled {count} runs.")
