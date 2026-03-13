"""Configuration for demographics methodology comparison.

Validation companies are populated after running select_companies.py
and user confirmation.
"""
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
EEO1_CSV = os.path.join(PROJECT_ROOT, 'EEO_1', 'objectors_with_corrected_demographics_2026_02_25.csv')
EEO1_DIR = os.path.join(PROJECT_ROOT, 'EEO_1')
# All EEO-1 CSV files (objectors + nonobjectors + small supplemental files)
EEO1_ALL_CSVS = [
    os.path.join(EEO1_DIR, 'nonobjectors_with_corrected_demographics-Updated.csv'),
    os.path.join(EEO1_DIR, 'objectors_with_corrected_demographics_2026_02_25.csv'),
    os.path.join(EEO1_DIR, 'affirmativelydidnotobject_with_corrected_demographics.csv'),
    os.path.join(EEO1_DIR, 'agreeingtodisclosure_with_corrected_demographics.csv'),
    os.path.join(EEO1_DIR, 'Bellwether-EEO1-Data.csv'),
]
BDS_DIR = os.path.join(PROJECT_ROOT, 'BDS 2021')

# Variable-weight industry groups (Method 5)
INDUSTRY_WEIGHTS = {
    # Local labor dominant: agriculture, construction, food mfg, food services
    'local_labor': {
        'prefixes': ['11', '23', '311', '312', '722'],
        'acs_weight': 0.40,
        'lodes_weight': 0.60,
    },
    # Occupation dominant: finance, professional services, healthcare
    'occupation': {
        'prefixes': ['52', '54', '62'],
        'acs_weight': 0.75,
        'lodes_weight': 0.25,
    },
    # Manufacturing
    'manufacturing': {
        'prefixes': ['31', '32', '33'],
        'acs_weight': 0.55,
        'lodes_weight': 0.45,
    },
    # Default
    'default': {
        'prefixes': [],
        'acs_weight': 0.60,
        'lodes_weight': 0.40,
    },
}

# Race categories for comparison (EEO-1 mutually exclusive non-Hispanic race)
RACE_CATEGORIES = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
GENDER_CATEGORIES = ['Male', 'Female']
HISPANIC_CATEGORIES = ['Hispanic', 'Not Hispanic']

# After user confirms 10 companies from select_companies.py output,
# populate this list. Each entry:
# {
#     'name': str,          # Company name from EEO-1
#     'company_code': str,  # COMPANY column (unique ID)
#     'year': int,          # FY year
#     'naics': str,         # 6-digit NAICS
#     'state': str,         # 2-letter state
#     'zipcode': str,       # ZIP code
#     'axis': str,          # Which benchmark axis this covers
#     'axis_label': str,    # Human-readable axis description
# }
VALIDATION_COMPANIES = [
    # Axis 1: Industry signal dominates (nursing home)
    {
        'name': 'CARE INITIATIVES',
        'company_code': 'P00688',
        'year': 2020,
        'naics': '623110',
        'state': 'IA',
        'zipcode': '50266',
        'axis': '1',
        'axis_label': 'Industry dominant (nursing home)',
    },
    # Axis 1: Industry signal dominates (defense mfg)
    {
        'name': 'UNITED LAUNCH ALLIANCE',
        'company_code': 'CK2299',
        'year': 2020,
        'naics': '336414',
        'state': 'CO',
        'zipcode': '80112',
        'axis': '1',
        'axis_label': 'Industry dominant (aerospace mfg)',
    },
    # Axis 2: Geography signal dominates (food processing)
    {
        'name': 'BUTTERBALL LLC',
        'company_code': 'M01805',
        'year': 2020,
        'naics': '311615',
        'state': 'NC',
        'zipcode': '27529',
        'axis': '2',
        'axis_label': 'Geography dominant (poultry processing)',
    },
    # Axis 2: Geography signal dominates (food mfg)
    {
        'name': 'OSI INDUSTRIES LLC',
        'company_code': '776059',
        'year': 2020,
        'naics': '311612',
        'state': 'IL',
        'zipcode': '60505',
        'axis': '2',
        'axis_label': 'Geography dominant (meat processing)',
    },
    # Axis 3: Demographic stratification (large hotel)
    {
        'name': 'ESA MANAGEMENT LLC',
        'company_code': 'X50049',
        'year': 2020,
        'naics': '721110',
        'state': 'NC',
        'zipcode': '28277',
        'axis': '3',
        'axis_label': 'Demographic stratification (hotel chain)',
    },
    # Axis 4: Size extreme (large, 121K employees)
    {
        'name': 'TYSON FOODS INC',
        'company_code': '924292',
        'year': 2020,
        'naics': '311615',
        'state': 'AR',
        'zipcode': '72762',
        'axis': '4',
        'axis_label': 'Size extreme (large, 121K)',
    },
    # Axis 4: Size extreme (small hotel, ~1K)
    {
        'name': 'PRISM HOTEL PARTNERS GP',
        'company_code': 'A57288',
        'year': 2020,
        'naics': '721110',
        'state': 'TX',
        'zipcode': '75254',
        'axis': '4',
        'axis_label': 'Size extreme (small, ~1K)',
    },
    # Axis 5: Geography edge case (majority-minority county, HI)
    {
        'name': 'ALEXANDER & BALDWIN INC',
        'company_code': '59736',
        'year': 2020,
        'naics': '531210',
        'state': 'HI',
        'zipcode': '96813',
        'axis': '5',
        'axis_label': 'Geography edge (majority-minority, HI)',
    },
    # Axis 6: Known hard case (staffing agency)
    {
        'name': 'HOWROYD WRIGHT EMPLOYMENT AGENCY',
        'company_code': 'JK3926',
        'year': 2020,
        'naics': '561311',
        'state': 'CA',
        'zipcode': '91204',
        'axis': '6',
        'axis_label': 'Known hard case (staffing agency)',
    },
    # Axis 1+mfg: Aerospace manufacturer (CA)
    {
        'name': 'DUCOMMUN INCORPORATED',
        'company_code': '551651',
        'year': 2020,
        'naics': '336413',
        'state': 'CA',
        'zipcode': '92707',
        'axis': '1',
        'axis_label': 'Industry dominant (aerospace parts mfg)',
    },
]


def get_industry_weights(naics):
    """Return (acs_weight, lodes_weight) for a NAICS code based on industry group."""
    for group_name, group in INDUSTRY_WEIGHTS.items():
        if group_name == 'default':
            continue
        for prefix in group['prefixes']:
            if naics.startswith(prefix):
                return group['acs_weight'], group['lodes_weight']
    default = INDUSTRY_WEIGHTS['default']
    return default['acs_weight'], default['lodes_weight']


# ============================================================
# V4 parameters
# ============================================================

# M4e: max White deviation (pp) before excluding an occupation
M4_VARIANCE_THRESHOLD = 8.0

# M3f: county minority share threshold for switching from IPF to dampened IPF
# Updated by compute_m3f_threshold.py
OPTIMAL_M3F_THRESHOLD = 0.15

# M8: industries where M1b wins Hispanic dimension
M8_M1B_HISPANIC_INDUSTRIES = [
    'Admin/Staffing (56)',
    'Healthcare/Social (62)',
    'Other',
    'Retail Trade (44-45)',
    'Transport Equip Mfg (336)',
]

# ============================================================
# V6 parameters
# ============================================================

# NAICS 2-digit to LODES CNS industry code mapping
# WAC files use CNS01-CNS20 for employment by NAICS supersector
NAICS_TO_CNS = {
    '11': 'CNS01',  # Agriculture
    '21': 'CNS02',  # Mining
    '22': 'CNS03',  # Utilities
    '23': 'CNS04',  # Construction
    '31': 'CNS05',  # Manufacturing
    '32': 'CNS05',  # Manufacturing
    '33': 'CNS05',  # Manufacturing
    '42': 'CNS06',  # Wholesale Trade
    '44': 'CNS07',  # Retail Trade
    '45': 'CNS07',  # Retail Trade
    '48': 'CNS08',  # Transportation/Warehousing
    '49': 'CNS08',  # Transportation/Warehousing
    '51': 'CNS09',  # Information
    '52': 'CNS10',  # Finance/Insurance
    '53': 'CNS11',  # Real Estate
    '54': 'CNS12',  # Professional/Technical
    '55': 'CNS13',  # Management of Companies
    '56': 'CNS14',  # Admin/Staffing
    '61': 'CNS15',  # Education
    '62': 'CNS16',  # Healthcare/Social
    '71': 'CNS17',  # Arts/Entertainment
    '72': 'CNS18',  # Accommodation/Food
    '81': 'CNS19',  # Other Services
    '92': 'CNS20',  # Public Administration
}

# Industry-specific gender bounds (soft/hard) by NAICS 2-digit
# Based on CPS Table 11 national benchmarks with wide margins
# soft bounds = flag for review; hard bounds = clamp estimate
GENDER_BOUNDS = {
    '11': {'soft_min': 10, 'soft_max': 50, 'hard_min': 5, 'hard_max': 60},   # Agriculture
    '21': {'soft_min': 5, 'soft_max': 35, 'hard_min': 2, 'hard_max': 45},    # Mining
    '22': {'soft_min': 10, 'soft_max': 45, 'hard_min': 5, 'hard_max': 55},   # Utilities
    '23': {'soft_min': 3, 'soft_max': 25, 'hard_min': 1, 'hard_max': 35},    # Construction
    '31': {'soft_min': 15, 'soft_max': 55, 'hard_min': 5, 'hard_max': 65},   # Manufacturing
    '32': {'soft_min': 15, 'soft_max': 55, 'hard_min': 5, 'hard_max': 65},   # Manufacturing
    '33': {'soft_min': 15, 'soft_max': 55, 'hard_min': 5, 'hard_max': 65},   # Manufacturing
    '42': {'soft_min': 15, 'soft_max': 50, 'hard_min': 5, 'hard_max': 60},   # Wholesale
    '44': {'soft_min': 25, 'soft_max': 65, 'hard_min': 15, 'hard_max': 75},  # Retail
    '45': {'soft_min': 25, 'soft_max': 65, 'hard_min': 15, 'hard_max': 75},  # Retail
    '48': {'soft_min': 10, 'soft_max': 45, 'hard_min': 5, 'hard_max': 55},   # Transportation
    '49': {'soft_min': 10, 'soft_max': 45, 'hard_min': 5, 'hard_max': 55},   # Warehousing
    '51': {'soft_min': 20, 'soft_max': 55, 'hard_min': 10, 'hard_max': 65},  # Information
    '52': {'soft_min': 30, 'soft_max': 70, 'hard_min': 20, 'hard_max': 80},  # Finance
    '54': {'soft_min': 25, 'soft_max': 60, 'hard_min': 15, 'hard_max': 70},  # Professional
    '56': {'soft_min': 20, 'soft_max': 65, 'hard_min': 10, 'hard_max': 75},  # Admin/Staffing
    '62': {'soft_min': 55, 'soft_max': 90, 'hard_min': 40, 'hard_max': 95},  # Healthcare
    '72': {'soft_min': 30, 'soft_max': 70, 'hard_min': 20, 'hard_max': 80},  # Accommodation/Food
}

# NAICS gender benchmarks from CPS national data (for post-processing reference)
NAICS_GENDER_BENCHMARKS = {
    '11': 27.0, '21': 15.0, '22': 24.0, '23': 11.0,
    '31': 29.0, '32': 29.0, '33': 29.0,
    '42': 30.0, '44': 50.0, '45': 50.0,
    '48': 25.0, '49': 25.0, '51': 40.0,
    '52': 53.0, '54': 44.0, '56': 40.0,
    '62': 77.0, '72': 53.0, '81': 47.0,
}

# Expert E hard-route NAICS groups
EXPERT_E_INDUSTRIES = {'Finance/Insurance (52)', 'Utilities (22)'}

# Expert F occupation-weighted NAICS groups
EXPERT_F_INDUSTRIES = {
    'Chemical/Material Mfg (325-327)', 'Computer/Electrical Mfg (334-335)',
    'Food/Bev Manufacturing (311,312)', 'Metal/Machinery Mfg (331-333)',
    'Other Manufacturing', 'Transport Equip Mfg (336)',
    'Transportation/Warehousing (48-49)', 'Admin/Staffing (56)',
}

# Sectors where workers reflect very local geography rather than county averages.
# These sectors have high proportions of immigrant workers, seasonal labor,
# or workers deployed to client sites.
HIGH_GEOGRAPHIC_NAICS = {
    '72',  # Accommodation/Food -- immigrant-heavy, neighborhood-level clusters
    '56',  # Admin/Staffing -- workers deployed to client sites, not company address
    '23',  # Construction -- project-based workers, follow construction sites
}

# ============================================================
# V8 parameters: Regional calibration
# ============================================================

STATE_TO_CENSUS_REGION = {
    # Northeast
    'CT': 'Northeast', 'ME': 'Northeast', 'MA': 'Northeast', 'NH': 'Northeast',
    'RI': 'Northeast', 'VT': 'Northeast', 'NJ': 'Northeast', 'NY': 'Northeast',
    'PA': 'Northeast',
    # Midwest
    'IL': 'Midwest', 'IN': 'Midwest', 'MI': 'Midwest', 'OH': 'Midwest',
    'WI': 'Midwest', 'IA': 'Midwest', 'KS': 'Midwest', 'MN': 'Midwest',
    'MO': 'Midwest', 'NE': 'Midwest', 'ND': 'Midwest', 'SD': 'Midwest',
    # South
    'DE': 'South', 'FL': 'South', 'GA': 'South', 'MD': 'South',
    'NC': 'South', 'SC': 'South', 'VA': 'South', 'DC': 'South',
    'WV': 'South', 'AL': 'South', 'KY': 'South', 'MS': 'South',
    'TN': 'South', 'AR': 'South', 'LA': 'South', 'OK': 'South',
    'TX': 'South',
    # West
    'AZ': 'West', 'CO': 'West', 'ID': 'West', 'MT': 'West',
    'NV': 'West', 'NM': 'West', 'UT': 'West', 'WY': 'West',
    'AK': 'West', 'CA': 'West', 'HI': 'West', 'OR': 'West',
    'WA': 'West',
}


def get_census_region(state_abbr):
    """Return Census region for a state abbreviation."""
    return STATE_TO_CENSUS_REGION.get(state_abbr, 'Other')


def get_county_minority_tier(county_minority_pct):
    """Classify county minority percentage into a tier.

    Returns 'low', 'medium', or 'high' based on county minority share.
    """
    if county_minority_pct is None:
        return 'medium'
    if county_minority_pct < 25:
        return 'low'
    elif county_minority_pct <= 50:
        return 'medium'
    else:
        return 'high'


# Industries that benefit from regional/county-tier calibration sub-keys
REGIONAL_CALIBRATION_INDUSTRIES = {
    'Healthcare/Social (62)',
    'Admin/Staffing (56)',
}

# Minimum sample size for regional calibration cells
REGIONAL_CAL_MIN_N = 30
