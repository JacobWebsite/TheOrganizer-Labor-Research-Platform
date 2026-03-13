"""
Shared HTML parser for union web scraper tiered extraction.

Pure utility module -- no DB connection. Imported by wordpress,
discovery, and extraction scripts.

Functions:
    extract_from_tables(html) -> list[dict]
    extract_from_lists(html) -> list[dict]
    extract_pdf_links(html, base_url) -> list[dict]
    clean_employer_name(name) -> str | None
    guess_sector(name) -> str | None
    classify_page_type(url, title) -> str
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


# ── Employer name cleaning ────────────────────────────────────────────────

# Boilerplate phrases to reject
_BOILERPLATE = {
    'click here', 'read more', 'learn more', 'sign up', 'log in',
    'contact us', 'home', 'about', 'menu', 'search', 'skip to content',
    'privacy policy', 'terms of use', 'all rights reserved',
    'powered by', 'wordpress', 'facebook', 'twitter', 'instagram',
    'subscribe', 'newsletter', 'copyright', 'back to top',
}


def clean_employer_name(name):
    """Clean and validate an employer name. Returns None if invalid."""
    if not name or not isinstance(name, str):
        return None

    # Strip whitespace, bullets, dashes, asterisks, numbering
    name = re.sub(r'^[\s\-\*\u2022\u2013\u2014\d\.\)]+', '', name)
    name = name.strip().rstrip('.,;:')

    if len(name) < 4 or len(name) > 120:
        return None

    # Reject boilerplate
    if name.lower() in _BOILERPLATE:
        return None

    # Reject strings that are all digits or look like dates/URLs
    if re.match(r'^[\d\s\-/]+$', name):
        return None
    if '://' in name or name.startswith('www.'):
        return None

    # Reject if no letters
    if not re.search(r'[a-zA-Z]', name):
        return None

    return name


# ── Sector guessing (consolidated) ───────────────────────────────────────

def guess_sector(name):
    """Guess employer sector from name keywords.

    Consolidates duplicate implementations from extract_union_data.py:276
    and fix_extraction.py:145.
    """
    if not name:
        return None
    nl = name.lower()

    if any(w in nl for w in ['city of', 'county of', 'town of', 'village of',
                              'borough of', 'municipal', 'city council']):
        return 'PUBLIC_LOCAL'
    if any(w in nl for w in ['state of', 'commonwealth', 'department of',
                              'state university']):
        return 'PUBLIC_STATE'
    if any(w in nl for w in ['university', 'college', 'school district',
                              'board of education', 'public school']):
        return 'PUBLIC_EDUCATION'
    if any(w in nl for w in ['hospital', 'health', 'medical center',
                              'nursing', 'healthcare']):
        return 'HEALTHCARE'
    if any(w in nl for w in ['federal', 'u.s.', 'united states']):
        return 'PUBLIC_FEDERAL'
    if any(w in nl for w in ['inc', 'corp', 'llc', 'ltd', 'co.']):
        return 'PRIVATE'

    return None


# ── Page classification ──────────────────────────────────────────────────

def classify_page_type(url, title=""):
    """Classify a page URL/title into a type category."""
    combined = (url + ' ' + title).lower()

    if any(w in combined for w in ['contract', 'cba', 'collective-bargaining',
                                    'bargaining', 'agreement']):
        return 'contracts'
    if any(w in combined for w in ['about', 'who-we-are', 'mission',
                                    'history', 'leadership']):
        return 'about'
    if any(w in combined for w in ['news', 'blog', 'press', 'update',
                                    'announcement']):
        return 'news'
    if any(w in combined for w in ['member', 'join', 'benefits',
                                    'resources']):
        return 'members'
    if any(w in combined for w in ['contact', 'office', 'location']):
        return 'contact'
    if any(w in combined for w in ['employer', 'workplace', 'bargaining-unit',
                                    'represented', 'where-we-work']):
        return 'employers'

    return 'unknown'


# ── Table extraction ─────────────────────────────────────────────────────

# Keywords that suggest a table column contains employer/org names
_TABLE_HEADER_KEYWORDS = [
    'employer', 'company', 'agency', 'department', 'organization',
    'bargaining unit', 'workplace', 'facility', 'institution',
    'district', 'entity', 'name',
]


def extract_from_tables(html):
    """Extract employer names from HTML tables.

    Looks for tables with header keywords suggesting employer/org names,
    then extracts cell values from those columns.

    Returns list of dicts with keys: employer_name, source_element, confidence
    """
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()

    for table in soup.find_all('table'):
        # Find header row
        headers = []
        header_row = table.find('thead')
        if header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]
        else:
            # Try first row as header
            first_row = table.find('tr')
            if first_row:
                cells = first_row.find_all(['th', 'td'])
                if cells:
                    headers = [c.get_text(strip=True).lower() for c in cells]

        if not headers:
            continue

        # Find which column(s) have employer-like headers
        name_cols = []
        for i, header in enumerate(headers):
            if any(kw in header for kw in _TABLE_HEADER_KEYWORDS):
                name_cols.append(i)

        if not name_cols:
            # If no matching header but table has a "name" column, use it
            for i, header in enumerate(headers):
                if header == 'name':
                    name_cols.append(i)

        if not name_cols:
            continue

        # Extract data rows (skip header)
        rows = table.find_all('tr')
        start = 1 if headers else 0
        if header_row:
            # thead was separate, all tbody rows are data
            body = table.find('tbody')
            if body:
                rows = body.find_all('tr')
                start = 0

        for row in rows[start:]:
            cells = row.find_all(['td', 'th'])
            for col_idx in name_cols:
                if col_idx < len(cells):
                    raw = cells[col_idx].get_text(strip=True)
                    name = clean_employer_name(raw)
                    if name and name.lower() not in seen:
                        seen.add(name.lower())
                        results.append({
                            'employer_name': name,
                            'source_element': 'table_row',
                            'confidence': 0.8,
                        })

    return results


# ── List extraction ──────────────────────────────────────────────────────

# Keywords suggesting an org name in a list item
_ORG_KEYWORDS = [
    'city of', 'county of', 'town of', 'village of', 'borough of',
    'university', 'college', 'hospital', 'district', 'authority',
    'inc', 'corp', 'llc', 'ltd', 'department',
    'board of', 'commission', 'agency', 'center', 'centre',
    'school', 'library', 'museum', 'institute',
    'state of', 'commonwealth',
]

# Parent elements that indicate navigation (skip these)
_NAV_PARENTS = ['nav', 'header', 'footer']
_NAV_CLASSES = ['nav', 'menu', 'sidebar', 'footer', 'header',
                'breadcrumb', 'pagination', 'social']


def _is_nav_list(ul_element):
    """Check if a list is likely navigation (not content)."""
    # Check parent tags
    for parent in ul_element.parents:
        if parent.name in _NAV_PARENTS:
            return True
        parent_classes = parent.get('class', [])
        if isinstance(parent_classes, list):
            parent_class_str = ' '.join(parent_classes).lower()
        else:
            parent_class_str = str(parent_classes).lower()
        if any(nc in parent_class_str for nc in _NAV_CLASSES):
            return True
        # Check id too
        parent_id = (parent.get('id') or '').lower()
        if any(nc in parent_id for nc in _NAV_CLASSES):
            return True
    return False


def extract_from_lists(html):
    """Extract employer names from HTML bullet/numbered lists.

    Skips nav/menu/header/footer lists. Checks for org-name keywords.

    Returns list of dicts with keys: employer_name, source_element, confidence
    """
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()

    for ul in soup.find_all(['ul', 'ol']):
        # Skip navigation lists
        if _is_nav_list(ul):
            continue

        items = ul.find_all('li', recursive=False)

        # Skip very short lists (likely nav) or very long lists (likely something else)
        if len(items) < 3 or len(items) > 200:
            continue

        # Check if list items look like org names
        org_count = 0
        candidates = []
        for li in items:
            text = li.get_text(strip=True)
            name = clean_employer_name(text)
            if name:
                is_org = any(kw in name.lower() for kw in _ORG_KEYWORDS)
                if is_org:
                    org_count += 1
                candidates.append((name, is_org))

        # Require at least 30% of items to look like org names,
        # or at least 3 org-like items
        if org_count < 3 and (not candidates or org_count / max(len(candidates), 1) < 0.3):
            continue

        for name, is_org in candidates:
            if name.lower() not in seen:
                seen.add(name.lower())
                results.append({
                    'employer_name': name,
                    'source_element': 'list_item',
                    'confidence': 0.7 if is_org else 0.5,
                })

    return results


# ── PDF link extraction ──────────────────────────────────────────────────

_CONTRACT_KEYWORDS = ['contract', 'cba', 'agreement', 'bargaining',
                       'memorandum', 'mou', 'moa', 'collective']


def extract_pdf_links(html, base_url=""):
    """Extract PDF links from HTML.

    Resolves relative URLs. Classifies by link text as 'contract' or 'other'.

    Returns list of dicts with keys: pdf_url, link_text, pdf_type
    """
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()

        # Check if it's a PDF link
        if not href.lower().endswith('.pdf') and '.pdf?' not in href.lower():
            continue

        # Resolve relative URL
        if base_url and not href.startswith(('http://', 'https://')):
            href = urljoin(base_url, href)

        if href in seen:
            continue
        seen.add(href)

        link_text = a.get_text(strip=True)[:200]

        # Classify
        combined = (link_text + ' ' + href).lower()
        if any(kw in combined for kw in _CONTRACT_KEYWORDS):
            pdf_type = 'contract'
        else:
            pdf_type = 'other'

        results.append({
            'pdf_url': href,
            'link_text': link_text,
            'pdf_type': pdf_type,
        })

    return results
