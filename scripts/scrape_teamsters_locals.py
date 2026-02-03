"""
Scrape Teamsters locals from official website (teamster.org/locals/)
Extracts local information from HTML div.local elements
"""

import requests
from bs4 import BeautifulSoup
import csv
import re
from datetime import datetime

def scrape_teamsters_locals():
    """Fetch and parse Teamsters locals from official website."""

    url = "https://teamster.org/locals/"

    print(f"Fetching {url}...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    print(f"Response status: {response.status_code}")
    print(f"Content length: {len(response.text)} characters")

    html = response.text
    soup = BeautifulSoup(html, 'html.parser')

    locals_data = []
    locals_by_num = {}

    # Method 1: Parse embedded JavaScript array with coordinates
    # Format: ["Teamsters LU No 2", 45.905345, -112.637705, "Address", "City", "State", "ZIP", "", "Phone", "Website"]
    js_pattern = r'\["Teamsters LU[^"]*No\.?\s*(\d+)"?,\s*([-\d.]+),\s*([-\d.]+),\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)"\]'
    js_matches = re.findall(js_pattern, html)
    print(f"Found {len(js_matches)} locals in embedded JavaScript")

    for match in js_matches:
        local_num = int(match[0])
        locals_by_num[local_num] = {
            'local_number': local_num,
            'local_name': f"Teamsters LU No {local_num}",
            'latitude': float(match[1]) if match[1] else None,
            'longitude': float(match[2]) if match[2] else None,
            'address': match[3],
            'city': match[4],
            'state': match[5],
            'zip': match[6],
            'phone': match[8],
            'website': match[9] if match[9] else ''
        }

    # Method 2: Parse HTML divs for additional details (leadership, divisions, email)
    local_divs = soup.find_all('div', class_=re.compile(r'^local\s+post-\d+'))
    print(f"Found {len(local_divs)} local entries in HTML")

    for div in local_divs:
        local_info = parse_local_div(div)
        if local_info and local_info.get('local_number'):
            local_num = local_info['local_number']
            if local_num in locals_by_num:
                # Merge HTML data into JS data
                locals_by_num[local_num].update({
                    'leadership_name': local_info.get('leadership_name', ''),
                    'leadership_title': local_info.get('leadership_title', ''),
                    'divisions': local_info.get('divisions', []),
                    'email': local_info.get('email', ''),
                    'full_address': local_info.get('full_address', '')
                })
            else:
                # Local only in HTML, not in JS
                locals_by_num[local_num] = local_info

    locals_data = list(locals_by_num.values())
    print(f"\nExtracted {len(locals_data)} unique locals")

    return locals_data, html


def parse_local_div(div):
    """Parse a single local div element."""
    local_info = {}

    # Extract local number from title (e.g., "Teamsters LU No 2")
    title_elem = div.find('h4', class_='local--title')
    if title_elem:
        title_text = title_elem.get_text(strip=True)
        local_info['local_name'] = title_text

        # Extract number from title
        num_match = re.search(r'No\s*(\d+)', title_text, re.I)
        if num_match:
            local_info['local_number'] = int(num_match.group(1))
        else:
            # Try alternative patterns
            num_match = re.search(r'Local\s*(\d+)', title_text, re.I)
            if num_match:
                local_info['local_number'] = int(num_match.group(1))

    # Extract state from div class (e.g., "local-state-mt")
    div_classes = div.get('class', [])
    for cls in div_classes:
        state_match = re.match(r'local-state-(\w+)', cls)
        if state_match:
            local_info['state'] = state_match.group(1).upper()
            break

    # Extract leadership info
    sub_elems = div.find_all('p', class_='local--sub')
    for sub in sub_elems:
        text = sub.get_text(strip=True)
        if 'Secretary-Treasurer:' in text:
            name = text.replace('Secretary-Treasurer:', '').strip()
            local_info['leadership_name'] = name
            local_info['leadership_title'] = 'Secretary-Treasurer'
        elif 'President:' in text:
            name = text.replace('President:', '').strip()
            local_info['leadership_name'] = name
            local_info['leadership_title'] = 'President'
        elif 'Divisions/Conferences:' in text:
            # Extract division links
            division_links = sub.find_all('a')
            divisions = [a.get_text(strip=True) for a in division_links]
            local_info['divisions'] = divisions

    # Extract phone
    phone_elem = div.find('p', class_='local--foot tel')
    if phone_elem:
        phone_link = phone_elem.find('a', href=re.compile(r'^tel:'))
        if phone_link:
            phone = phone_link.get_text(strip=True)
            # Format phone number
            if len(phone) == 10:
                phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
            local_info['phone'] = phone

    # Extract website
    website_elem = div.find('p', class_='local--foot url')
    if website_elem:
        website_link = website_elem.find('a')
        if website_link:
            website = website_link.get('href', '')
            # Fix relative URLs
            if website.startswith('//'):
                website = 'https:' + website
            elif not website.startswith('http'):
                website = 'https://' + website
            local_info['website'] = website

    # Extract email
    email_elem = div.find('p', class_='local--foot email')
    if email_elem:
        local_info['email'] = email_elem.get_text(strip=True)

    # Extract address
    adr_elem = div.find('div', class_='local--adr')
    if adr_elem:
        street_elem = adr_elem.find('p', class_='street-address')
        if street_elem:
            # Get full address text (may have <br> tags)
            address_parts = []
            for content in street_elem.children:
                if hasattr(content, 'name'):
                    if content.name == 'br':
                        continue
                    elif content.name == 'span':
                        continue  # locality, region, postal-code handled separately
                    else:
                        address_parts.append(content.get_text(strip=True))
                else:
                    text = str(content).strip()
                    if text and text != ',':
                        address_parts.append(text)

            # Get street address (everything before locality)
            full_text = street_elem.get_text(separator=' ', strip=True)
            local_info['full_address'] = full_text

        # Get city (locality)
        locality_elem = adr_elem.find('span', class_='locality')
        if locality_elem:
            local_info['city'] = locality_elem.get_text(strip=True)

        # Get state (region)
        region_elem = adr_elem.find('span', class_='region')
        if region_elem:
            local_info['state'] = region_elem.get_text(strip=True)

        # Get ZIP
        zip_elem = adr_elem.find('span', class_='postal-code')
        if zip_elem:
            local_info['zip'] = zip_elem.get_text(strip=True)

    return local_info


def save_locals_to_csv(locals_data, filename):
    """Save locals data to CSV file."""

    if not locals_data:
        print("No data to save")
        return []

    # Sort by local number
    locals_data.sort(key=lambda x: x.get('local_number', 0))

    # Prepare normalized records
    normalized = []
    for local in locals_data:
        # Format phone number
        phone = local.get('phone', '')
        if phone and len(phone) == 10 and phone.isdigit():
            phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"

        # Format website
        website = local.get('website', '')
        if website and not website.startswith('http'):
            website = 'https://' + website

        record = {
            'local_number': local.get('local_number', ''),
            'local_name': local.get('local_name', ''),
            'city': local.get('city', ''),
            'state': local.get('state', ''),
            'zip': local.get('zip', ''),
            'phone': phone,
            'email': local.get('email', ''),
            'website': website,
            'leadership_name': local.get('leadership_name', ''),
            'leadership_title': local.get('leadership_title', ''),
            'divisions': ', '.join(local.get('divisions', [])) if isinstance(local.get('divisions'), list) else '',
            'full_address': local.get('full_address', '') or local.get('address', ''),
            'latitude': local.get('latitude', ''),
            'longitude': local.get('longitude', ''),
            'scraped_at': datetime.now().isoformat()
        }
        normalized.append(record)

    # Write CSV
    fieldnames = ['local_number', 'local_name', 'city', 'state', 'zip',
                  'phone', 'email', 'website', 'leadership_name', 'leadership_title',
                  'divisions', 'full_address', 'latitude', 'longitude', 'scraped_at']

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)

    print(f"Saved {len(normalized)} locals to {filename}")

    # Print state distribution
    states = {}
    for rec in normalized:
        state = rec['state']
        states[state] = states.get(state, 0) + 1

    print(f"\nState distribution ({len(states)} states):")
    for state in sorted(states.keys()):
        print(f"  {state}: {states[state]}")

    return normalized


def save_raw_html(html, filename):
    """Save raw HTML for debugging."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Saved raw HTML to {filename}")


if __name__ == '__main__':
    # Scrape the website
    locals_data, html = scrape_teamsters_locals()

    # Save raw HTML for debugging
    save_raw_html(html, 'teamsters_raw_page.html')

    # Save to CSV
    if locals_data:
        save_locals_to_csv(locals_data, 'teamsters_official_locals.csv')
    else:
        print("\nNo locals extracted. Check teamsters_raw_page.html to debug.")
