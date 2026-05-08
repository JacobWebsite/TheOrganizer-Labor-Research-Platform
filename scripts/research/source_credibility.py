"""Source Credibility Scoring for Research Facts.

Scores each research fact 0-100 based on four weighted dimensions:
  Domain Authority (35), Recency (20), Expertise (25), Bias (20).

Rule-based only -- no API calls, no expensive computation.
"""

import logging
from datetime import date
from typing import Optional

from db_config import get_connection
from psycopg2.extras import RealDictCursor

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain Authority Lookup (prefix-matched against source_name)
# ---------------------------------------------------------------------------

_DOMAIN_AUTHORITY = [
    # Government enforcement databases -- highest trust
    ("database:osha", 95),
    ("database:nlrb", 95),
    ("database:whd", 90),
    ("database:sec", 90),
    ("database:bls", 90),
    ("database:qcew", 90),
    # Government reference databases
    ("database:sam", 85),
    ("database:f7", 85),
    ("database:cur_acs", 85),
    ("database:cur_cbp", 85),
    ("database:cur_lodes", 85),
    ("database:union_density", 80),
    # Structured filings
    ("database:national_990", 80),
    ("database:cur_form5500", 80),
    ("database:gleif", 80),
    ("database:nyc_enforcement", 80),
    ("database:state_enforcement", 80),
    # Commercial / aggregated databases
    ("database:mergent", 75),
    ("database:cur_ppp", 75),
    ("database:cur_abs", 80),
    ("database:corporate", 70),
    ("database:employer_locations", 70),
    ("database:leadership", 65),
    # External APIs -- government-adjacent
    ("api:fec", 80),
    ("api:warn_notices", 80),
    ("api:sos_filings", 75),
    ("api:wage_comparison", 75),
    ("api:subsidies", 70),
    ("api:local_demographics", 70),
    # External APIs -- commercial
    ("api:company_enrich", 70),
    ("api:brave_search", 55),
    ("api:google_search", 50),
    ("api:worker_sentiment", 45),
    # Web scrape
    ("web_scrape:employer_website", 50),
    ("web_scrape", 50),
]

_SOURCE_TYPE_DEFAULTS = {
    "database": 80,
    "api": 60,
    "web_scrape": 50,
    "web_search": 55,
    "news": 50,
    "system": 30,
}

# ---------------------------------------------------------------------------
# Expertise Map: attribute prefix -> expert source prefixes
# ---------------------------------------------------------------------------

_EXPERTISE_MAP = {
    "osha_": ["database:osha", "database:state_enforcement"],
    "nlrb_": ["database:nlrb"],
    "whd_": ["database:whd"],
    "sec_": ["database:sec"],
    "employee_count": ["api:company_enrich", "database:mergent", "database:cur_form5500", "database:sec"],
    "revenue": ["database:sec", "api:company_enrich", "database:mergent"],
    "federal_obligations": ["database:sam"],
    "union_": ["database:f7", "database:nlrb"],
    "year_founded": ["api:company_enrich", "database:mergent", "api:sos_filings"],
    "website": ["api:company_enrich", "web_scrape:employer_website"],
    "political_": ["api:fec"],
    "wage_": ["database:bls", "database:qcew", "api:wage_comparison"],
}

# ---------------------------------------------------------------------------
# Bias scores by source type
# ---------------------------------------------------------------------------

_BIAS_SCORES = [
    ("database:", 19),
    ("api:fec", 18),
    ("api:sos_filings", 17),
    ("api:company_enrich", 15),
    ("api:wage_comparison", 15),
    ("api:local_demographics", 15),
    ("api:subsidies", 15),
    ("api:brave_search", 12),
    ("api:worker_sentiment", 12),
    ("api:google_search", 12),
    ("web_scrape:employer_website", 8),
    ("web_scrape", 10),
    ("news", 11),
]

_BIAS_TYPE_DEFAULTS = {
    "database": 19,
    "api": 14,
    "web_scrape": 10,
    "web_search": 11,
    "news": 11,
    "system": 10,
}


# Keyword-based fallback for unprefixed source_name values.
# Gemini generates source_name inconsistently: "database:osha_violations_detail",
# "OSHA Violations", "search_osha", "osha_violations_detail" are all equivalent.
_KEYWORD_AUTHORITY = [
    # Government enforcement
    (["osha", "osha_violations"], 95),
    (["nlrb", "nlrb_cases", "nlrb_election", "nlrb_ulp", "unfair_labor"], 95),
    (["whd", "whd_cases", "wage_hour", "wage & hour", "wage and hour"], 90),
    (["sec_", "sec_companies", "sec_edgar", "sec filings", "sec xbrl"], 90),
    (["bls_", "bls ", "bls_industry", "industry_occupation_matrix", "industry_profile"], 90),
    (["qcew"], 90),
    # Government reference
    (["sam_entities", "sam.gov", "sam "], 85),
    (["f7_", "f7 ", "f-7", "f7_employers", "f7_union", "union_employer_relations"], 85),
    (["acs_", "acs "], 85),
    (["cbp_", "cbp "], 85),
    (["lodes_", "lodes "], 85),
    (["union_density"], 80),
    # Filings
    (["990", "national_990", "irs 990", "irs_990"], 80),
    (["form5500", "form_5500", "form 5500", "benefit plan"], 80),
    (["gleif", "lei"], 80),
    # Commercial
    (["mergent"], 75),
    (["ppp_", "ppp "], 75),
    (["corporate_structure", "corporate_identifier"], 70),
    # APIs
    (["fec", "political_donations", "political donations"], 80),
    (["warn_", "warn "], 80),
    (["sos_", "sos ", "corporate filings", "registered_agent"], 75),
    (["company_enrich", "companyenrich"], 70),
    (["brave_search", "brave search", "brave web"], 55),
    (["google_search", "google search"], 50),
    (["worker_sentiment", "glassdoor", "reddit"], 45),
    (["job_posting", "job posting", "indeed"], 50),
    (["subsidies", "subsid"], 70),
    # Web
    (["employer_website", "scrape_employer", "employer website"], 50),
    (["web_findings", "web_search", "web findings"], 50),
    # System / AI
    (["exhaustive_coverage"], 30),
    (["agent_inference", "model_inference", "ai_synthesis", "agent_synthesis"], 35),
    (["user_input", "user_provided", "user_query", "user_prompt", "initial_prompt", "prompt"], 40),
    (["common_knowledge", "general_knowledge"], 35),
]


def _match_prefix(value: str, lookup: list) -> Optional[int]:
    """Find the first prefix match in a list of (prefix, score) tuples."""
    if not value:
        return None
    v = value.lower()
    for prefix, score in lookup:
        if v.startswith(prefix):
            return score
    return None


def _match_keywords(value: str) -> Optional[int]:
    """Keyword-based matching for unprefixed source_name values."""
    if not value:
        return None
    v = value.lower()
    for keywords, score in _KEYWORD_AUTHORITY:
        for kw in keywords:
            if kw in v:
                return score
    return None


def _recency_score(as_of_date) -> int:
    """Score recency 0-100 based on age of the fact."""
    if not as_of_date:
        return 50  # neutral for undated

    try:
        if isinstance(as_of_date, str):
            # Handle YYYY-MM-DD or YYYY formats
            if len(as_of_date) == 4 and as_of_date.isdigit():
                fact_date = date(int(as_of_date), 7, 1)
            else:
                fact_date = date.fromisoformat(as_of_date[:10])
        elif isinstance(as_of_date, date):
            fact_date = as_of_date
        else:
            return 50
    except (ValueError, TypeError):
        return 50

    age_days = (date.today() - fact_date).days
    if age_days < 0:
        return 100  # future date (likely current fiscal year)
    if age_days < 183:   # <6 months
        return 100
    if age_days < 365:   # 6-12 months
        return 80
    if age_days < 730:   # 1-2 years
        return 60
    if age_days < 1095:  # 2-3 years
        return 40
    if age_days < 1825:  # 3-5 years
        return 20
    return 10            # 5+ years


def _expertise_score(attribute_name: str, source_name: str) -> int:
    """Score 0-25 based on whether the source is an expert for this attribute."""
    if not attribute_name or not source_name:
        return 12  # neutral default

    sn_lower = source_name.lower()

    for attr_prefix, expert_sources in _EXPERTISE_MAP.items():
        if attribute_name.startswith(attr_prefix):
            # Check prefix match (e.g., "database:osha")
            for expert in expert_sources:
                if sn_lower.startswith(expert):
                    return 25  # expert match
            # Also check keyword containment for unprefixed names
            # e.g., attribute "osha_violation_count" + source_name "OSHA Violations"
            attr_domain = attr_prefix.rstrip("_")
            if attr_domain in sn_lower:
                return 22  # likely expert (keyword match)
            return 10  # known domain, wrong source

    # No specific mapping -- give moderate score based on source trust level
    if sn_lower.startswith("database:"):
        return 18
    kw = _match_keywords(source_name)
    if kw is not None and kw >= 80:
        return 18  # government-grade source
    if kw is not None and kw >= 60:
        return 15
    return 12


def score_credibility(fact: dict) -> int:
    """Score a research fact's source credibility 0-100.

    Uses source_name (prefix-matched), as_of_date, attribute_name.
    Pure function -- no DB or API calls.
    """
    source_name = fact.get("source_name") or ""
    source_type = (fact.get("source_type") or "").lower()
    attribute_name = fact.get("attribute_name") or ""
    as_of_date = fact.get("as_of_date")

    # 1. Domain Authority (35 points max)
    # Try prefix match first, then keyword match, then source_type default
    authority_raw = _match_prefix(source_name, _DOMAIN_AUTHORITY)
    if authority_raw is None:
        authority_raw = _match_keywords(source_name)
    if authority_raw is None:
        authority_raw = _SOURCE_TYPE_DEFAULTS.get(source_type, 30)
    authority = round(authority_raw * 0.35)

    # 2. Recency (20 points max)
    recency_raw = _recency_score(as_of_date)
    recency = round(recency_raw * 0.20)

    # 3. Expertise (25 points max)
    expertise = _expertise_score(attribute_name, source_name)

    # 4. Bias (20 points max)
    bias_raw = _match_prefix(source_name, _BIAS_SCORES)
    if bias_raw is None:
        # Use keyword matching to infer bias from source_name content
        kw_score = _match_keywords(source_name)
        if kw_score is not None:
            # Map authority score to approximate bias score
            if kw_score >= 85:
                bias_raw = 19  # government-grade
            elif kw_score >= 70:
                bias_raw = 15  # structured commercial
            elif kw_score >= 50:
                bias_raw = 12  # web/search
            elif kw_score >= 40:
                bias_raw = 10  # user input / AI inference
            else:
                bias_raw = 8   # low-trust
        else:
            bias_raw = _BIAS_TYPE_DEFAULTS.get(source_type, 10)
    bias = bias_raw  # already on 0-20 scale

    total = authority + recency + expertise + bias
    return max(0, min(100, total))


def score_facts_credibility(run_id: int) -> int:
    """Score all facts for a research run and update credibility_score column.

    Returns count of facts scored.
    """
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, source_type, source_name, attribute_name, as_of_date "
        "FROM research_facts WHERE run_id = %s",
        (run_id,),
    )
    facts = cur.fetchall()

    if not facts:
        conn.close()
        return 0

    updates = []
    for f in facts:
        score = score_credibility(f)
        updates.append((score, f["id"]))

    # Batch update
    from psycopg2.extras import execute_batch
    execute_batch(
        cur,
        "UPDATE research_facts SET credibility_score = %s WHERE id = %s",
        updates,
    )
    conn.commit()
    conn.close()

    _log.info("Scored credibility for %d facts in run %d", len(updates), run_id)
    return len(updates)
