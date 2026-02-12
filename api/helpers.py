"""
Shared helper functions and constants used across routers.
"""
import re


def safe_sort_col(sort_by: str, allowed: dict, default: str) -> str:
    """Validate sort column against whitelist. Prevents SQL injection in ORDER BY."""
    result = allowed.get(sort_by)
    if result is None:
        return allowed.get(default, default)
    return result


def safe_order_dir(order: str) -> str:
    """Validate sort direction. Only ASC or DESC allowed."""
    return "DESC" if order.lower() == "desc" else "ASC"


# Law firm detection patterns for NLRB data quality
LAW_FIRM_PATTERNS = [
    r'\bLLP\b', r'\bLLC\b.*LAW', r'\bATTORNEY',
    r'\bLAW\s+(FIRM|OFFICE|GROUP|OFFICES)', r'\bESQ\.?\b', r'\bCOUNSEL\b',
    r'\bLAW\s+&\s+', r'\b&\s+LAW\b', r'\bLAWYERS?\b', r'\bLEGAL\s+SERVICES',
]


def is_likely_law_firm(name: str) -> bool:
    """Detect if an employer name is likely a law firm (data quality issue in NLRB)."""
    if not name:
        return False
    for pattern in LAW_FIRM_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


# Valid sectors with their view names (sector_category values in mergent_employers)
SECTOR_VIEWS = {
    'civic_organizations': 'civic_organizations',
    'building_services': 'building_services',
    'education': 'education',
    'social_services': 'social_services',
    'broadcasting': 'broadcasting',
    'publishing': 'publishing',
    'waste_mgmt': 'waste_mgmt',
    'government': 'government',
    'repair_services': 'repair_services',
    'museums': 'museums',
    'information': 'information',
    'other': 'other',
    'professional': 'professional',
    'healthcare_ambulatory': 'healthcare_ambulatory',
    'healthcare_nursing': 'healthcare_nursing',
    'healthcare_hospitals': 'healthcare_hospitals',
    'transit': 'transit',
    'utilities': 'utilities',
    'hospitality': 'hospitality',
    'food_service': 'food_service',
    'arts_entertainment': 'arts_entertainment',
}
