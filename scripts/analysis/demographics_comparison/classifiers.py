"""5-dimensional company classification for demographics comparison.

Dimensions:
1. NAICS Group (19 groups)
2. Workforce Size (4 buckets)
3. Census Region (4 regions)
4. Minority Share (3 levels from EEO-1 truth)
5. Urbanicity (3 levels from CBSA)
"""

# NAICS Groups -- ordered most-specific first for prefix matching
NAICS_GROUPS = [
    ('Food/Bev Manufacturing (311,312)', ['311', '312']),
    ('Chemical/Material Mfg (325-327)', ['325', '326', '327']),
    ('Metal/Machinery Mfg (331-333)', ['331', '332', '333']),
    ('Computer/Electrical Mfg (334-335)', ['334', '335']),
    ('Transport Equip Mfg (336)', ['336']),
    ('Agriculture/Mining (11,21)', ['11', '21']),
    ('Utilities (22)', ['22']),
    ('Construction (23)', ['23']),
    ('Other Manufacturing', ['31', '32', '33']),  # catch-all after specific mfg
    ('Wholesale Trade (42)', ['42']),
    ('Retail Trade (44-45)', ['44', '45']),
    ('Transportation/Warehousing (48-49)', ['48', '49']),
    ('Information (51)', ['51']),
    ('Finance/Insurance (52)', ['52']),
    ('Professional/Technical (54)', ['54']),
    ('Admin/Staffing (56)', ['56']),
    ('Healthcare/Social (62)', ['62']),
    ('Accommodation/Food Svc (72)', ['72']),
]

SIZE_BUCKETS = [
    ('1-99', 1, 99),
    ('100-999', 100, 999),
    ('1k-9999', 1000, 9999),
    ('10000+', 10000, float('inf')),
]

REGION_STATES = {
    'Northeast': {'CT', 'ME', 'MA', 'NH', 'RI', 'VT', 'NJ', 'NY', 'PA'},
    'South': {'AL', 'AR', 'DE', 'DC', 'FL', 'GA', 'KY', 'LA', 'MD', 'MS',
              'NC', 'OK', 'SC', 'TN', 'TX', 'VA', 'WV'},
    'Midwest': {'IL', 'IN', 'IA', 'KS', 'MI', 'MN', 'MO', 'NE', 'ND',
                'OH', 'SD', 'WI'},
    'West': {'AK', 'AZ', 'CA', 'CO', 'HI', 'ID', 'MT', 'NV', 'NM',
             'OR', 'UT', 'WA', 'WY'},
}


def classify_region(state_abbr):
    """Classify state abbreviation into Census region."""
    for region, states in REGION_STATES.items():
        if state_abbr in states:
            return region
    return 'Other'


def classify_naics_group(naics):
    """Classify NAICS code into industry group. Match longest prefix first."""
    if not naics:
        return 'Other'
    # Sort each group's prefixes by length desc so longest matches first
    for group_label, prefixes in NAICS_GROUPS:
        for prefix in sorted(prefixes, key=len, reverse=True):
            if naics.startswith(prefix):
                return group_label
    return 'Other'


def classify_size(total):
    """Classify workforce size into bucket."""
    for label, lo, hi in SIZE_BUCKETS:
        if lo <= total <= hi:
            return label
    return '10000+'


def classify_minority(eeo1_truth):
    """Classify minority share from EEO-1 ground truth.

    eeo1_truth: parsed truth dict with 'race' key containing 'White' pct.
    Minority = 100 - White.
    """
    white_pct = eeo1_truth.get('race', {}).get('White', 0)
    minority = 100.0 - white_pct
    if minority < 25:
        return 'Low (<25%)'
    elif minority <= 50:
        return 'Medium (25-50%)'
    else:
        return 'High (>50%)'


def classify_urbanicity(cur, county_fips):
    """Classify county urbanicity via CBSA tables.

    Metropolitan + Central = Urban
    Metropolitan + Outlying OR Micropolitan = Suburban
    No match = Rural
    """
    if not county_fips:
        return 'Rural'
    cur.execute("""
        SELECT cd.cbsa_type, cc.central_outlying
        FROM cbsa_counties cc
        JOIN cbsa_definitions cd ON cd.cbsa_code = cc.cbsa_code
        WHERE cc.fips_full = %s
        LIMIT 1
    """, [county_fips])
    row = cur.fetchone()
    if not row:
        return 'Rural'
    cbsa_type = (row['cbsa_type'] or '').strip()
    central = (row['central_outlying'] or '').strip()
    if cbsa_type == 'Metropolitan' and central == 'Central':
        return 'Urban'
    elif cbsa_type in ('Metropolitan', 'Micropolitan'):
        return 'Suburban'
    return 'Rural'


def batch_classify_urbanicity(cur, county_fips_set):
    """Classify urbanicity for all counties in one query.

    Returns dict {county_fips: urbanicity_label}.
    """
    if not county_fips_set:
        return {}

    fips_list = list(county_fips_set)
    cur.execute("""
        SELECT cc.fips_full, cd.cbsa_type, cc.central_outlying
        FROM cbsa_counties cc
        JOIN cbsa_definitions cd ON cd.cbsa_code = cc.cbsa_code
        WHERE cc.fips_full = ANY(%s)
    """, [fips_list])
    rows = cur.fetchall()

    result = {}
    for row in rows:
        fips = row['fips_full']
        cbsa_type = (row['cbsa_type'] or '').strip()
        central = (row['central_outlying'] or '').strip()
        if cbsa_type == 'Metropolitan' and central == 'Central':
            result[fips] = 'Urban'
        elif cbsa_type in ('Metropolitan', 'Micropolitan'):
            result.setdefault(fips, 'Suburban')
        # Don't overwrite Urban with Suburban if multiple entries
    # Everything not found is Rural
    for fips in fips_list:
        if fips not in result:
            result[fips] = 'Rural'
    return result


def classify_all(state, naics, total, truth, urbanicity):
    """Return full 5D classification dict."""
    return {
        'naics_group': classify_naics_group(naics),
        'size': classify_size(total),
        'region': classify_region(state),
        'minority_share': classify_minority(truth),
        'urbanicity': urbanicity,
    }
