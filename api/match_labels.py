"""Human-readable labels and citations for match provenance data."""

SOURCE_LABELS = {
    "osha": "OSHA Establishment Records",
    "whd": "DOL Wage & Hour Division",
    "nlrb": "NLRB Case Records",
    "sec": "SEC EDGAR Filings",
    "bmf": "IRS Business Master File",
    "sam": "SAM.gov Federal Contractors",
    "corpwatch": "CorpWatch Corporate Data",
    "mergent": "Mergent Intellect",
    "web_scraper": "Union website directory",
}

METHOD_LABELS = {
    "EIN_EXACT": "EIN (exact match)",
    "NAME_CITY_STATE": "name + city + state",
    "NAME_CITY_STATE_EXACT": "name + city + state",
    "NAME_ZIP_STATE": "name + ZIP + state",
    "NAME_STATE": "name + state",
    "NAME_STATE_EXACT": "name + state",
    "AGGRESSIVE": "aggressive name normalization",
    "NAME_AGGRESSIVE_STATE": "aggressive name normalization",
    "SORTED_TOKEN_STATE": "sorted token match",
    "COLLAPSED_SPACING_STATE": "spacing-collapsed match",
    "TRUNCATED_NAME_STATE": "prefix truncation match",
    "STRIPPED_LEADING_NUMS_STATE": "leading number stripped match",
    "STEMMED_NAME_STATE": "stemmed name match",
    "PHONETIC_STATE": "phonetic encoding match",
    "FUZZY_INMEMORY_TRIGRAM": "trigram similarity",
    "FUZZY_SPLINK_ADAPTIVE": "fuzzy name matching",
    "TRIGRAM": "trigram similarity",
    "FUZZY_TRIGRAM": "trigram similarity",
}


def build_citation(source_system, match_method, confidence_score=None):
    """Build a human-readable citation string for a match.

    Examples:
        "OSHA Establishment Records matched by EIN (exact match)"
        "NLRB Case Records matched by fuzzy name matching (0.87 similarity)"
    """
    source = SOURCE_LABELS.get(source_system, source_system.upper() if source_system else "Unknown")
    method = METHOD_LABELS.get(match_method, match_method or "unknown method")

    # Append similarity score for fuzzy methods
    fuzzy_methods = ("FUZZY_SPLINK_ADAPTIVE", "TRIGRAM", "FUZZY_TRIGRAM",
                     "FUZZY_INMEMORY_TRIGRAM", "PHONETIC_STATE")
    if match_method in fuzzy_methods and confidence_score is not None:
        score_val = float(confidence_score)
        method = f"{method} ({score_val:.2f} similarity)"

    return f"{source} matched by {method}"


def build_master_citation(source_system, match_confidence=None):
    """Build a simpler citation for master employer source links.

    Examples:
        "OSHA Establishment Records (100% confidence)"
        "NLRB Case Records (85% confidence)"
    """
    source = SOURCE_LABELS.get(source_system, source_system.upper() if source_system else "Unknown")

    if match_confidence is not None:
        conf_val = float(match_confidence)
        if conf_val >= 1.0:
            return f"{source} (exact match)"
        return f"{source} ({conf_val:.0%} confidence)"

    return source
