"""
Splink probabilistic matching configuration.

Defines settings, comparisons, and blocking rules for each matching scenario.
Uses DuckDB backend (default for Splink 4.x).
"""
import splink.comparison_library as cl
from splink import SettingsCreator, block_on

# Match probability thresholds
THRESHOLD_AUTO_ACCEPT = 0.85
THRESHOLD_REVIEW = 0.70
THRESHOLD_REJECT = 0.70  # Below this = reject

# ============================================================================
# SCENARIO: Mergent -> F7
# ============================================================================
# Mergent: company_name_normalized, state, city, zip, naics_primary, street_address
# F7: employer_name_aggressive, state, city, zip, naics, street
# Unified column names used after DataFrame prep:
#   name_normalized, state, city, zip, naics, street_address

MERGENT_F7_SETTINGS = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.LevenshteinAtThresholds("city", [1, 2]),
        cl.JaroWinklerAtThresholds("zip", [0.95, 0.80]),
        cl.ExactMatch("naics").configure(term_frequency_adjustments=True),
        cl.JaroWinklerAtThresholds("street_address", [0.90, 0.70]),
    ],
    blocking_rules_to_generate_predictions=[
        # Block 1: state + first 3 chars of name (primary)
        block_on("state", "substr(name_normalized, 1, 3)"),
        # Block 2: state + city (catches name variations)
        block_on("state", "city"),
        # Block 3: zip prefix (catches name+state typos)
        block_on("substr(zip, 1, 3)"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

# Blocking rules for EM training (must be different from prediction blocking)
MERGENT_F7_EM_BLOCKING = [
    block_on("state", "city"),
    block_on("substr(name_normalized, 1, 5)"),
]


# ============================================================================
# SCENARIO: GLEIF -> F7
# ============================================================================
# GLEIF: name_normalized, address_state (as state), address_zip (as zip)
# NOTE: GLEIF has 0% city coverage, so city comparison is excluded

GLEIF_F7_SETTINGS = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.JaroWinklerAtThresholds("zip", [0.95, 0.80]),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("state", "substr(name_normalized, 1, 3)"),
        block_on("substr(zip, 1, 3)"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

GLEIF_F7_EM_BLOCKING = [
    block_on("state", "substr(name_normalized, 1, 5)"),
    block_on("substr(zip, 1, 5)"),
]


# ============================================================================
# SCENARIO: NLRB -> F7
# ============================================================================
# Similar to Mergent->F7 but NLRB has employer name, city, state

NLRB_F7_SETTINGS = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.LevenshteinAtThresholds("city", [1, 2]),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("state", "substr(name_normalized, 1, 3)"),
        block_on("state", "city"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

NLRB_F7_EM_BLOCKING = [
    block_on("state", "city"),
    block_on("substr(name_normalized, 1, 5)"),
]


# ============================================================================
# SCENARIO: OSHA -> F7
# ============================================================================
# OSHA: estab_name, site_state, site_city, site_zip, naics_code, site_address
# F7: name_aggressive, state, city, zip, naics, street

OSHA_F7_SETTINGS = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.LevenshteinAtThresholds("city", [1, 2]),
        cl.JaroWinklerAtThresholds("zip", [0.95, 0.80]),
        cl.ExactMatch("naics").configure(term_frequency_adjustments=True),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("state", "substr(name_normalized, 1, 3)"),
        block_on("state", "city"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

OSHA_F7_EM_BLOCKING = [
    block_on("state", "city"),
    block_on("substr(name_normalized, 1, 5)"),
]


# ============================================================================
# SCENARIO: WHD -> F7
# ============================================================================
# WHD: trade_name, state, city, zip_code, naics_code, street_address
# F7:  name_aggressive, state, city, zip, naics

WHD_F7_SETTINGS = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.LevenshteinAtThresholds("city", [1, 2]),
        cl.JaroWinklerAtThresholds("zip", [0.95, 0.80]),
        cl.ExactMatch("naics").configure(term_frequency_adjustments=True),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("state", "substr(name_normalized, 1, 3)"),
        block_on("state", "city"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

WHD_F7_EM_BLOCKING = [
    block_on("state", "city"),
    block_on("substr(name_normalized, 1, 5)"),
]


# ============================================================================
# SCENARIO: Adaptive Fuzzy (Deterministic Tier 5 replacement)
# ============================================================================
# Used by deterministic_matcher._fuzzy_batch_splink() for unresolved records.
# Source and target are prepared in-memory with unified column names:
#   id, name_normalized, state, city, zip, naics, street_address, original_name

ADAPTIVE_FUZZY_SETTINGS = SettingsCreator(
    link_type="link_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.LevenshteinAtThresholds("city", [1, 2]),
        cl.JaroWinklerAtThresholds("zip", [0.95, 0.80]),
        cl.ExactMatch("naics").configure(term_frequency_adjustments=True),
        cl.JaroWinklerAtThresholds("street_address", [0.90, 0.75]),
    ],
    blocking_rules_to_generate_predictions=[
        block_on("state", "substr(name_normalized, 1, 3)"),
        block_on("state", "city"),
        block_on("substr(zip, 1, 3)", "substr(name_normalized, 1, 2)"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

ADAPTIVE_FUZZY_EM_BLOCKING = [
    block_on("state", "city"),
    block_on("substr(name_normalized, 1, 5)"),
]


# ============================================================================
# SCENARIO: F7 Self-Deduplication
# ============================================================================
# Single-source dedup using Splink's dedupe_only mode.
# All records come from f7_employers_deduped with unified column names:
#   name_normalized, state, city, zip, naics, street_address

F7_SELF_DEDUP_SETTINGS = SettingsCreator(
    link_type="dedupe_only",
    unique_id_column_name="id",
    comparisons=[
        cl.JaroWinklerAtThresholds("name_normalized", [0.95, 0.88, 0.80, 0.70]),
        cl.ExactMatch("state"),
        cl.LevenshteinAtThresholds("city", [1, 2]),
        cl.JaroWinklerAtThresholds("zip", [0.95, 0.80]),
        cl.ExactMatch("naics").configure(term_frequency_adjustments=True),
        cl.JaroWinklerAtThresholds("street_address", [0.90, 0.70]),
    ],
    blocking_rules_to_generate_predictions=[
        # Block 1: state + first 3 chars of name (primary)
        block_on("state", "substr(name_normalized, 1, 3)"),
        # Block 2: state + city (catches name variations in same city)
        block_on("state", "city"),
        # Block 3: zip prefix + name prefix (catches city/state typos)
        block_on("substr(zip, 1, 3)", "substr(name_normalized, 1, 2)"),
    ],
    retain_intermediate_calculation_columns=True,
    retain_matching_columns=True,
)

# EM training blocking (must differ from prediction blocking)
F7_SELF_DEDUP_EM_BLOCKING = [
    block_on("state", "city"),
    block_on("substr(name_normalized, 1, 5)"),
]


# ============================================================================
# SCENARIO REGISTRY
# ============================================================================

SCENARIOS = {
    "mergent_to_f7": {
        "settings": MERGENT_F7_SETTINGS,
        "em_blocking": MERGENT_F7_EM_BLOCKING,
        "source_table": "mergent_employers",
        "target_table": "f7_employers_deduped",
        "source_id": "duns",
        "target_id": "employer_id",
        "crosswalk_source_col": "mergent_duns",
        "crosswalk_target_col": "f7_employer_id",
        "source_columns": {
            "id": "duns",
            "name_normalized": "company_name_normalized",
            "state": "state",
            "city": "city",
            "zip": "zip",
            "naics": "naics_primary",
            "street_address": "street_address",
            "original_name": "company_name",
        },
        "target_columns": {
            "id": "employer_id",
            "name_normalized": "employer_name_aggressive",
            "state": "state",
            "city": "city",
            "zip": "zip",
            "naics": "naics",
            "street_address": "street",
            "original_name": "employer_name",
        },
    },
    "gleif_to_f7": {
        "settings": GLEIF_F7_SETTINGS,
        "em_blocking": GLEIF_F7_EM_BLOCKING,
        "source_table": "gleif_us_entities",
        "target_table": "f7_employers_deduped",
        "source_id": "id",
        "target_id": "employer_id",
        "crosswalk_source_col": "gleif_id",
        "crosswalk_target_col": "f7_employer_id",
        "source_columns": {
            "id": "id",
            "name_normalized": "name_normalized",
            "state": "address_state",
            "zip": "address_zip",
            "original_name": "entity_name",
        },
        "target_columns": {
            "id": "employer_id",
            "name_normalized": "employer_name_aggressive",
            "state": "state",
            "zip": "zip",
            "original_name": "employer_name",
        },
    },
    "f7_self_dedup": {
        "settings": F7_SELF_DEDUP_SETTINGS,
        "em_blocking": F7_SELF_DEDUP_EM_BLOCKING,
        "link_type": "dedupe_only",
        "source_system": "f7",
        "source_table": "f7_employers_deduped",
        "source_id": "employer_id",
        "columns": {
            "id": "employer_id",
            "name_normalized": "employer_name_aggressive",
            "state": "state",
            "city": "city",
            "zip": "zip",
            "naics": "naics",
            "street_address": "street",
            "original_name": "employer_name",
        },
    },
    "adaptive_fuzzy": {
        "settings": ADAPTIVE_FUZZY_SETTINGS,
        "em_blocking": ADAPTIVE_FUZZY_EM_BLOCKING,
        "model_path": "scripts/matching/models/adaptive_fuzzy_model.json",
    },
    "osha_to_f7": {
        "settings": OSHA_F7_SETTINGS,
        "em_blocking": OSHA_F7_EM_BLOCKING,
        "source_system": "osha",
        "source_table": "osha_establishments",
        "target_table": "f7_employers_deduped",
        "source_id": "establishment_id",
        "target_id": "employer_id",
        "source_unmatched_condition": """
            NOT EXISTS (
                SELECT 1 FROM unified_match_log u
                WHERE u.source_system = 'osha'
                  AND u.source_id = s.establishment_id::text
                  AND u.status = 'active'
            )
        """,
        "source_columns": {
            "id": "establishment_id",
            "name_normalized": "estab_name",
            "state": "site_state",
            "city": "site_city",
            "zip": "site_zip",
            "naics": "naics_code",
            "street_address": "site_address",
            "original_name": "estab_name",
        },
        "target_columns": {
            "id": "employer_id",
            "name_normalized": "name_aggressive",
            "state": "state",
            "city": "city",
            "zip": "zip",
            "naics": "naics",
            "street_address": "street",
            "original_name": "employer_name",
        },
    },
    "whd_to_f7": {
        "settings": WHD_F7_SETTINGS,
        "em_blocking": WHD_F7_EM_BLOCKING,
        "source_system": "whd",
        "source_table": "whd_cases",
        "target_table": "f7_employers_deduped",
        "source_id": "case_id",
        "target_id": "employer_id",
        "source_unmatched_condition": """
            NOT EXISTS (
                SELECT 1 FROM unified_match_log u
                WHERE u.source_system = 'whd'
                  AND u.source_id = s.case_id::text
                  AND u.status = 'active'
            )
        """,
        "source_columns": {
            "id": "case_id",
            "name_normalized": "trade_name",
            "state": "state",
            "city": "city",
            "zip": "zip_code",
            "naics": "naics_code",
            "street_address": "street_address",
            "original_name": "trade_name",
        },
        "target_columns": {
            "id": "employer_id",
            "name_normalized": "name_aggressive",
            "state": "state",
            "city": "city",
            "zip": "zip",
            "naics": "naics",
            "street_address": "street",
            "original_name": "employer_name",
        },
    },
}
