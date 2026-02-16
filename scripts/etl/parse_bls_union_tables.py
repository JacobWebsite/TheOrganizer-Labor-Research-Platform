#!/usr/bin/env python3
"""
Parse BLS Union Membership HTML Tables
Extracts data from downloaded BLS tables and loads to database
"""
import re
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from psycopg2.extras import RealDictCursor
from db_config import get_connection

# Industry code mapping (BLS categories to our codes)
INDUSTRY_MAP = {
    'Agriculture and related': 'AGR_MIN',
    'Mining, quarrying, and oil and gas extraction': 'AGR_MIN',
    'Construction': 'CONST',
    'Manufacturing': 'MFG',
    'Wholesale and retail trade': 'WHOLESALE',  # Combined - will split
    'Wholesale trade': 'WHOLESALE',
    'Retail trade': 'RETAIL',
    'Transportation and utilities': 'TRANS_UTIL',
    'Transportation and warehousing': 'TRANS_UTIL',
    'Utilities': 'TRANS_UTIL',
    'Information': 'INFO',
    'Financial activities': 'FINANCE',
    'Finance and insurance': 'FINANCE',
    'Professional and business services': 'PROF_BUS',
    'Education and health services': 'EDU_HEALTH',
    'Educational services': 'EDU_HEALTH',
    'Health care and social assistance': 'EDU_HEALTH',
    'Leisure and hospitality': 'LEISURE',
    'Other services': 'OTHER',
    'Public administration': 'PUBLIC_ADMIN'
}

# State abbreviations
US_STATES = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL',
    'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA',
    'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
    'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA',
    'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'
}


def parse_html_table(html_path):
    """Parse HTML table to pandas DataFrame"""
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')

    # Find the data table (BLS tables have class='regular')
    table = soup.find('table', {'class': 'regular'})

    if not table:
        # Try any table
        table = soup.find('table')

    if not table:
        raise ValueError(f"No table found in {html_path}")

    # Extract rows
    rows = []
    for tr in table.find_all('tr'):
        cells = []
        for td in tr.find_all(['td', 'th']):
            # Get text, strip whitespace
            text = td.get_text(strip=True)
            # Remove commas from numbers
            text = text.replace(',', '')
            cells.append(text)

        if cells:
            rows.append(cells)

    return rows


def parse_table3_industry(html_path):
    """
    Parse Table 3: Union affiliation by occupation and industry

    Table structure (2024 data):
    - Row 0: Headers (Occupation and industry, 2023, 2024)
    - Row 1: Subheaders (Total employed, Members of unions, Represented by unions)
    - Row 2: More subheaders (Total, Percent of employed, Total, ...)
    - Row 3-33: OCCUPATION section
    - Row 34: "INDUSTRY" marker
    - Row 35+: Industry data

    Each data row has columns (for 2024):
    [Industry name, Total employed 2024, Members 2024, % 2024, Represented 2024, % 2024, ...]

    Returns: List of dicts with industry union density
    """
    rows = parse_html_table(html_path)

    # Find INDUSTRY section (exact match, not just containing "INDUSTRY")
    industry_start_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip().upper() == 'INDUSTRY':
            industry_start_idx = i
            break

    if industry_start_idx is None:
        raise ValueError("Could not find INDUSTRY section in Table 3")

    # Extract industry data (starting after "INDUSTRY" marker row)
    industries = []

    # Industries we want (main categories only)
    SKIP_PATTERNS = [
        'Private sector', 'Public sector', 'Government workers',
        'Nonagricultural', 'Durable goods', 'Nondurable goods',
        'Publishing', 'Motion pictures', 'Broadcasting', 'Telecommunications',  # Information subsectors
        'Finance,', 'Insurance,', 'Real estate',  # Financial subsectors
        'Professional and technical', 'Management, administrative',  # Business subsectors
        'Educational services,', 'Health care and social',  # Edu/health subsectors (note: comma to avoid matching main categories)
    ]

    for row in rows[industry_start_idx + 1:]:
        if len(row) < 5:
            continue

        category = row[0].strip()

        # Skip empty or total rows
        if not category or category.startswith('Total'):
            continue

        # Skip subsectors and aggregates
        skip = False
        for pattern in SKIP_PATTERNS:
            if pattern in category:
                skip = True
                break

        if skip:
            continue

        # Extract 2024 data
        # Column structure: [name, 2023_employed, 2023_members, 2023_%, 2023_represented, 2023_rep_%,
        #                           2024_employed, 2024_members, 2024_%, 2024_represented, 2024_rep_%]
        try:
            # Column 6 is 2024 total employed (in thousands)
            total_employed = float(row[6].replace(',', '')) if len(row) > 6 and row[6] else None

            # Column 7 is 2024 union members (in thousands)
            union_members = float(row[7].replace(',', '')) if len(row) > 7 and row[7] else None

            # Column 8 is 2024 union percentage (already calculated by BLS)
            members_pct = float(row[8].replace(',', '')) if len(row) > 8 and row[8] else None

            # Column 9 is 2024 represented (in thousands)
            represented = float(row[9].replace(',', '')) if len(row) > 9 and row[9] else None

            # Column 10 is 2024 represented percentage (already calculated by BLS)
            represented_pct = float(row[10].replace(',', '')) if len(row) > 10 and row[10] else None

            if total_employed and total_employed > 0:

                # Map to industry code
                industry_code = INDUSTRY_MAP.get(category)

                industries.append({
                    'year': 2024,
                    'industry_name': category,
                    'industry_code': industry_code,
                    'total_employed_thousands': total_employed,
                    'union_members_thousands': union_members,
                    'represented_thousands': represented,
                    'union_density_pct': members_pct,  # Already calculated by BLS
                    'represented_density_pct': represented_pct  # Already calculated by BLS
                })

        except (ValueError, IndexError) as e:
            print(f"    Warning: Could not parse row '{category}': {e}")
            continue

    print(f"  Parsed {len(industries)} industry records")
    return industries


def parse_table5_state(html_path):
    """
    Parse Table 5: Union affiliation by state

    Returns: List of dicts with state union density
    """
    rows = parse_html_table(html_path)

    # Find header row
    header_idx = None
    for i, row in enumerate(rows):
        if 'State' in row[0] or 'Total' in row[0]:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Could not find header row in Table 5")

    # Extract state data
    states = []

    for row in rows[header_idx + 1:]:
        if len(row) < 4:
            continue

        state_name = row[0].strip()

        # Skip total/summary rows
        if state_name.startswith('Total') or not state_name:
            continue

        # Map to state abbreviation
        state_abbr = US_STATES.get(state_name)

        if not state_abbr:
            print(f"  Warning: Unknown state '{state_name}'")
            continue

        try:
            total_employed = float(row[1]) if row[1] else None
            union_members = float(row[2]) if row[2] else None
            represented = float(row[4]) if len(row) > 4 and row[4] else None

            if total_employed and total_employed > 0:
                members_pct = (union_members / total_employed * 100) if union_members else None
                represented_pct = (represented / total_employed * 100) if represented else None

                states.append({
                    'year': 2024,
                    'state': state_abbr,
                    'state_name': state_name,
                    'total_employed_thousands': total_employed,
                    'union_members_thousands': union_members,
                    'represented_thousands': represented,
                    'union_density_pct': round(members_pct, 1) if members_pct else None,
                    'represented_density_pct': round(represented_pct, 1) if represented_pct else None
                })

        except (ValueError, IndexError) as e:
            print(f"  Warning: Could not parse row for {state_name}: {e}")
            continue

    print(f"  Parsed {len(states)} state records")
    return states


def create_tables(cur):
    """Create enhanced union density tables"""

    # National industry density (replaces hardcoded bls_industry_density)
    cur.execute("""
        DROP TABLE IF EXISTS bls_national_industry_density CASCADE;
        CREATE TABLE bls_national_industry_density (
            year INTEGER,
            industry_code VARCHAR(20),
            industry_name VARCHAR(100),
            total_employed_thousands INTEGER,
            union_members_thousands INTEGER,
            represented_thousands INTEGER,
            union_density_pct DECIMAL(5,2),
            represented_density_pct DECIMAL(5,2),
            source VARCHAR(50) DEFAULT 'bls_table3',
            PRIMARY KEY (year, industry_code)
        );

        CREATE INDEX idx_bls_nat_ind_year ON bls_national_industry_density(year);
        CREATE INDEX idx_bls_nat_ind_code ON bls_national_industry_density(industry_code);
    """)

    # State overall density (from Table 5)
    cur.execute("""
        DROP TABLE IF EXISTS bls_state_density CASCADE;
        CREATE TABLE bls_state_density (
            year INTEGER,
            state VARCHAR(2),
            state_name VARCHAR(50),
            total_employed_thousands INTEGER,
            union_members_thousands INTEGER,
            represented_thousands INTEGER,
            union_density_pct DECIMAL(5,2),
            represented_density_pct DECIMAL(5,2),
            source VARCHAR(50) DEFAULT 'bls_table5',
            PRIMARY KEY (year, state)
        );

        CREATE INDEX idx_bls_state_year ON bls_state_density(year);
        CREATE INDEX idx_bls_state_state ON bls_state_density(state);
    """)

    print("  Created tables: bls_national_industry_density, bls_state_density")


def load_industry_data(cur, industries):
    """Load industry density data to database"""

    insert_query = """
        INSERT INTO bls_national_industry_density (
            year, industry_code, industry_name,
            total_employed_thousands, union_members_thousands, represented_thousands,
            union_density_pct, represented_density_pct, source
        ) VALUES (
            %(year)s, %(industry_code)s, %(industry_name)s,
            %(total_employed_thousands)s, %(union_members_thousands)s, %(represented_thousands)s,
            %(union_density_pct)s, %(represented_density_pct)s, 'bls_table3'
        )
        ON CONFLICT (year, industry_code) DO UPDATE SET
            industry_name = EXCLUDED.industry_name,
            total_employed_thousands = EXCLUDED.total_employed_thousands,
            union_members_thousands = EXCLUDED.union_members_thousands,
            represented_thousands = EXCLUDED.represented_thousands,
            union_density_pct = EXCLUDED.union_density_pct,
            represented_density_pct = EXCLUDED.represented_density_pct
    """

    # Filter out None industry_code entries
    valid_industries = [i for i in industries if i['industry_code']]

    cur.executemany(insert_query, valid_industries)

    print(f"  Loaded {len(valid_industries)} industry records")

    # Report unmapped industries
    unmapped = [i for i in industries if not i['industry_code']]
    if unmapped:
        print(f"  Warning: {len(unmapped)} unmapped industries:")
        for i in unmapped[:5]:
            print(f"    - {i['industry_name']}")


def load_state_data(cur, states):
    """Load state density data to database"""

    insert_query = """
        INSERT INTO bls_state_density (
            year, state, state_name,
            total_employed_thousands, union_members_thousands, represented_thousands,
            union_density_pct, represented_density_pct, source
        ) VALUES (
            %(year)s, %(state)s, %(state_name)s,
            %(total_employed_thousands)s, %(union_members_thousands)s, %(represented_thousands)s,
            %(union_density_pct)s, %(represented_density_pct)s, 'bls_table5'
        )
        ON CONFLICT (year, state) DO UPDATE SET
            state_name = EXCLUDED.state_name,
            total_employed_thousands = EXCLUDED.total_employed_thousands,
            union_members_thousands = EXCLUDED.union_members_thousands,
            represented_thousands = EXCLUDED.represented_thousands,
            union_density_pct = EXCLUDED.union_density_pct,
            represented_density_pct = EXCLUDED.represented_density_pct
    """

    cur.executemany(insert_query, states)

    print(f"  Loaded {len(states)} state records")


def print_summary(cur):
    """Print summary statistics"""

    print("\n" + "=" * 60)
    print("BLS UNION DENSITY DATA SUMMARY (2024)")
    print("=" * 60)

    # National industry density
    print("\nNational Industry Density:")
    cur.execute("""
        SELECT industry_code, industry_name, union_density_pct
        FROM bls_national_industry_density
        WHERE year = 2024
        ORDER BY union_density_pct DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row['industry_code']:15} {row['industry_name']:40} {row['union_density_pct']:5.1f}%")

    # State density
    print("\nTop 10 States by Union Density:")
    cur.execute("""
        SELECT state, state_name, union_density_pct
        FROM bls_state_density
        WHERE year = 2024
        ORDER BY union_density_pct DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row['state']:2} {row['state_name']:20} {row['union_density_pct']:5.1f}%")

    # Overall statistics
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE industry_code IS NOT NULL) as industries,
            ROUND(AVG(union_density_pct), 1) as avg_industry_density
        FROM bls_national_industry_density
        WHERE year = 2024
    """)
    industry_stats = cur.fetchone()

    cur.execute("""
        SELECT
            COUNT(*) as states,
            ROUND(AVG(union_density_pct), 1) as avg_state_density,
            ROUND(MIN(union_density_pct), 1) as min_density,
            ROUND(MAX(union_density_pct), 1) as max_density
        FROM bls_state_density
        WHERE year = 2024
    """)
    state_stats = cur.fetchone()

    print("\n" + "=" * 60)
    print(f"Industries loaded: {industry_stats['industries']}")
    print(f"Average industry density: {industry_stats['avg_industry_density']}%")
    print(f"\nStates loaded: {state_stats['states']}")
    print(f"Average state density: {state_stats['avg_state_density']}%")
    print(f"Range: {state_stats['min_density']}% - {state_stats['max_density']}%")


def main():
    data_dir = Path(__file__).resolve().parent.parent.parent / 'data' / 'bls'

    table3_path = data_dir / 'union_2024_table3_industry.html'
    table5_path = data_dir / 'union_2024_table5_state.html'

    # Check files exist
    if not table3_path.exists():
        print(f"ERROR: {table3_path} not found")
        print("Run download_bls_union_tables.py first")
        return 1

    print("Parsing BLS Union Membership Tables...")
    print("=" * 60)

    # Parse tables
    print("\nTable 3: Industry density...")
    industries = parse_table3_industry(table3_path)

    print("\nTable 5: State density...")
    states = parse_table5_state(table5_path)

    # Load to database
    print("\nLoading to database...")
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    try:
        create_tables(cur)
        conn.commit()

        load_industry_data(cur, industries)
        conn.commit()

        load_state_data(cur, states)
        conn.commit()

        print_summary(cur)

        print("\n[OK] BLS union density data loaded successfully")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
