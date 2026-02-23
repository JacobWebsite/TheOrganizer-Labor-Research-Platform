"""
Shared helper functions and constants used across routers.
"""
import re
import time
from typing import Any, Callable


class TTLCache:
    """Simple in-memory cache with time-to-live expiration.

    Usage:
        _cache = TTLCache(ttl_seconds=300)
        result = _cache.get("key")
        if result is None:
            result = expensive_query()
            _cache.set("key", result)
    """

    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Any:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()


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
