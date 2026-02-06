"""
Matching Configuration

Defines MatchConfig dataclass, tier thresholds, and predefined scenarios.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class MatchConfig:
    """Configuration for a matching scenario."""
    # Required fields (no defaults) - must come first
    name: str
    source_table: str
    target_table: str
    source_id_col: str
    source_name_col: str
    target_id_col: str
    target_name_col: str

    # Optional column names in source table
    source_state_col: Optional[str] = None
    source_city_col: Optional[str] = None
    source_ein_col: Optional[str] = None
    source_address_col: Optional[str] = None

    # Optional column names in target table
    target_state_col: Optional[str] = None
    target_city_col: Optional[str] = None
    target_ein_col: Optional[str] = None
    target_address_col: Optional[str] = None

    # Existing normalized columns (if any)
    source_normalized_col: Optional[str] = None
    target_normalized_col: Optional[str] = None

    # Output columns to include in results
    output_cols: List[str] = field(default_factory=list)

    # Tier thresholds (override defaults)
    fuzzy_threshold: float = 0.65

    # Filter conditions
    source_filter: Optional[str] = None
    target_filter: Optional[str] = None

    # Matching options
    require_state_match: bool = True
    require_city_match: bool = False


# Tier definitions
TIER_EIN = 1
TIER_NORMALIZED = 2
TIER_ADDRESS = 3
TIER_AGGRESSIVE = 4
TIER_FUZZY = 5

TIER_NAMES = {
    TIER_EIN: "EIN",
    TIER_NORMALIZED: "NORMALIZED",
    TIER_ADDRESS: "ADDRESS",
    TIER_AGGRESSIVE: "AGGRESSIVE",
    TIER_FUZZY: "FUZZY",
}

CONFIDENCE_LEVELS = {
    TIER_EIN: "HIGH",
    TIER_NORMALIZED: "HIGH",
    TIER_ADDRESS: "HIGH",
    TIER_AGGRESSIVE: "MEDIUM",
    TIER_FUZZY: "LOW",
}

# Default fuzzy threshold
DEFAULT_FUZZY_THRESHOLD = 0.65


# ============================================================================
# PREDEFINED MATCHING SCENARIOS
# ============================================================================

SCENARIOS: Dict[str, MatchConfig] = {

    # NLRB Participants → F7 Employers
    "nlrb_to_f7": MatchConfig(
        name="nlrb_to_f7",
        source_table="nlrb_participants",
        target_table="f7_employers_deduped",
        source_id_col="id",
        source_name_col="participant_name",
        source_state_col="state",
        source_city_col="city",
        source_ein_col=None,  # NLRB doesn't have EIN
        source_address_col="address",
        target_id_col="employer_id",
        target_name_col="employer_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col=None,  # F7 doesn't have EIN
        target_address_col="street",
        target_normalized_col="employer_name_aggressive",  # Column name in f7
        source_filter="participant_type = 'Employer'",
        output_cols=["participant_name", "employer_name", "city", "state"],
    ),

    # OSHA Establishments → F7 Employers
    "osha_to_f7": MatchConfig(
        name="osha_to_f7",
        source_table="osha_establishments",
        target_table="f7_employers_deduped",
        source_id_col="establishment_id",
        source_name_col="estab_name",
        source_state_col="site_state",
        source_city_col="site_city",
        source_ein_col=None,
        source_address_col="site_address",
        target_id_col="employer_id",
        target_name_col="employer_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col=None,
        target_address_col="street",
        source_normalized_col="estab_name_normalized",
        target_normalized_col="employer_name_aggressive",  # F7 uses aggressive col
        output_cols=["estab_name", "employer_name", "site_city", "city"],
    ),

    # Mergent Employers → F7 Employers
    "mergent_to_f7": MatchConfig(
        name="mergent_to_f7",
        source_table="mergent_employers",
        target_table="f7_employers_deduped",
        source_id_col="duns",
        source_name_col="company_name",
        source_state_col="state",
        source_city_col="city",
        source_ein_col="ein",
        source_address_col="street_address",
        target_id_col="employer_id",
        target_name_col="employer_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col=None,
        target_address_col="street",
        source_normalized_col="company_name_normalized",
        target_normalized_col="employer_name_aggressive",  # F7 uses aggressive col
        output_cols=["company_name", "employer_name", "sector_category"],
    ),

    # Mergent Employers → NY 990 Filers
    "mergent_to_990": MatchConfig(
        name="mergent_to_990",
        source_table="mergent_employers",
        target_table="ny_990_filers",
        source_id_col="duns",
        source_name_col="company_name",
        source_state_col="state",
        source_city_col="city",
        source_ein_col="ein",
        target_id_col="id",
        target_name_col="business_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col="ein",
        source_normalized_col="company_name_normalized",
        output_cols=["company_name", "business_name", "total_employees", "total_revenue"],
    ),

    # Mergent Employers → NLRB Participants
    "mergent_to_nlrb": MatchConfig(
        name="mergent_to_nlrb",
        source_table="mergent_employers",
        target_table="nlrb_participants",
        source_id_col="duns",
        source_name_col="company_name",
        source_state_col="state",
        source_city_col="city",
        source_ein_col="ein",
        target_id_col="id",
        target_name_col="participant_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col=None,
        source_normalized_col="company_name_normalized",
        target_filter="participant_type = 'Employer'",
        output_cols=["company_name", "participant_name", "case_number"],
    ),

    # Mergent Employers → OSHA Establishments
    "mergent_to_osha": MatchConfig(
        name="mergent_to_osha",
        source_table="mergent_employers",
        target_table="osha_establishments",
        source_id_col="duns",
        source_name_col="company_name",
        source_state_col="state",
        source_city_col="city",
        source_ein_col="ein",
        target_id_col="establishment_id",
        target_name_col="estab_name",
        target_state_col="site_state",
        target_city_col="site_city",
        target_ein_col=None,
        source_normalized_col="company_name_normalized",
        target_normalized_col="estab_name_normalized",
        output_cols=["company_name", "estab_name", "total_violations"],
    ),

    # NYC Violations → Mergent Employers (for labor violations scoring)
    "violations_to_mergent": MatchConfig(
        name="violations_to_mergent",
        source_table="nyc_wage_theft_nys",  # Primary violations table
        target_table="mergent_employers",
        source_id_col="id",
        source_name_col="employer_name",
        source_state_col=None,  # NYC only
        source_city_col="city",
        source_ein_col=None,
        target_id_col="duns",
        target_name_col="company_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col="ein",
        source_normalized_col="employer_name_normalized",
        target_normalized_col="company_name_normalized",
        target_filter="state = 'NY'",
        require_state_match=False,  # All violations are NY
        output_cols=["employer_name", "company_name", "wages_owed"],
    ),

    # NY State Contracts → Employers 990
    "contracts_to_990": MatchConfig(
        name="contracts_to_990",
        source_table="ny_state_contracts",
        target_table="employers_990",
        source_id_col="id",
        source_name_col="vendor_name",
        source_state_col=None,
        source_city_col=None,
        source_ein_col=None,  # Contracts don't have EIN
        target_id_col="id",
        target_name_col="name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col="ein",
        source_normalized_col="vendor_name_normalized",
        require_state_match=False,
        output_cols=["vendor_name", "name", "contract_amount"],
    ),

    # Voluntary Recognition → F7 Employers
    "vr_to_f7": MatchConfig(
        name="vr_to_f7",
        source_table="nlrb_voluntary_recognition",
        target_table="f7_employers_deduped",
        source_id_col="id",
        source_name_col="employer_name",
        source_state_col="unit_state",  # VR table uses unit_state
        source_city_col="unit_city",    # VR table uses unit_city
        source_ein_col=None,
        target_id_col="employer_id",
        target_name_col="employer_name",
        target_state_col="state",
        target_city_col="city",
        target_ein_col=None,
        target_normalized_col="employer_name_aggressive",  # F7 uses aggressive col
        output_cols=["employer_name", "case_number", "union_name"],
    ),
}


def get_scenario(name: str) -> MatchConfig:
    """Get a predefined scenario by name."""
    if name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(f"Unknown scenario: {name}. Available: {available}")
    return SCENARIOS[name]


def list_scenarios() -> List[str]:
    """List all available scenario names."""
    return list(SCENARIOS.keys())
