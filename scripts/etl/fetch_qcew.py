"""
Download and load BLS QCEW annual data into PostgreSQL.

QCEW is aggregated data: establishment counts, employment, and wages
by industry (NAICS) x geography (county FIPS) x ownership.

Useful for:
- Validating F7 establishment counts by industry/geography
- Industry composition analysis for density scoring
- Establishment count data for organizing targets

Data source: BLS QCEW annual CSV files
URL pattern: https://data.bls.gov/cew/data/files/{year}/csv/{year}_annual_singlefile.zip
"""
import os
import csv
import io
import zipfile
import time
import requests
import psycopg2
from psycopg2.extras import execute_values

from db_config import get_connection
DOWNLOAD_DIR = r"C:\Users\jakew\Downloads"

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def create_table(conn):
    """Create qcew_annual table."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS qcew_annual (
            id SERIAL PRIMARY KEY,
            area_fips TEXT,
            own_code TEXT,
            industry_code TEXT,
            agglvl_code TEXT,
            size_code TEXT,
            year INTEGER,
            disclosure_code TEXT,
            annual_avg_estabs INTEGER,
            annual_avg_emplvl INTEGER,
            total_annual_wages BIGINT,
            taxable_annual_wages BIGINT,
            annual_contributions BIGINT,
            annual_avg_wkly_wage INTEGER,
            avg_annual_pay INTEGER,
            lq_annual_avg_estabs NUMERIC,
            lq_annual_avg_emplvl NUMERIC,
            lq_total_annual_wages NUMERIC,
            lq_avg_annual_pay NUMERIC
        )
    """)
    conn.commit()
    print("  qcew_annual table ready")


def download_qcew_year(year):
    """Download QCEW annual singlefile for a year."""
    url = f"https://data.bls.gov/cew/data/files/{year}/csv/{year}_annual_singlefile.zip"
    local_path = os.path.join(DOWNLOAD_DIR, f"qcew_{year}_annual.zip")

    if os.path.exists(local_path):
        size_mb = os.path.getsize(local_path) / (1024*1024)
        print(f"  Using existing file: {local_path} ({size_mb:.1f} MB)")
        return local_path

    print(f"  Downloading: {url}")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    total = int(resp.headers.get('content-length', 0))
    downloaded = 0

    with open(local_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192*16):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0 and downloaded % (10 * 1024 * 1024) < 8192*16:
                pct = 100 * downloaded / total
                print(f"    {downloaded/(1024*1024):.0f}/{total/(1024*1024):.0f} MB ({pct:.1f}%)")

    size_mb = os.path.getsize(local_path) / (1024*1024)
    print(f"  Downloaded {size_mb:.1f} MB")
    return local_path


def parse_int(val):
    """Parse integer, returning None for empty/invalid."""
    if not val or val.strip() == '':
        return None
    try:
        return int(val.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None


def parse_float(val):
    """Parse float, returning None for empty/invalid."""
    if not val or val.strip() == '':
        return None
    try:
        return float(val.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None


def load_qcew_year(conn, zip_path, year):
    """Parse and load QCEW data for a year."""
    cur = conn.cursor()

    # Delete previous data for this year
    cur.execute("DELETE FROM qcew_annual WHERE year = %s", (year,))
    deleted = cur.rowcount
    if deleted > 0:
        print(f"  Cleared {deleted:,} previous rows for {year}")
    conn.commit()

    row_count = 0
    batch = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
        print(f"  CSV files: {csv_files}")

        for csv_name in csv_files:
            print(f"  Processing: {csv_name}")

            with zf.open(csv_name) as f:
                text_wrapper = io.TextIOWrapper(f, encoding='utf-8', errors='replace')
                reader = csv.DictReader(text_wrapper)

                if row_count == 0:
                    print(f"  Columns: {reader.fieldnames[:15]}...")

                for row in reader:
                    # Only keep county-level and state-level aggregations
                    # agglvl_code: 50=county+NAICS3, 51=county+NAICS4, 70=state+NAICS6
                    agglvl = row.get('agglvl_code', '').strip()

                    # Keep useful aggregation levels:
                    # 40=State, NAICS Supersector
                    # 50=County, NAICS 3-digit
                    # 70=State, NAICS 6-digit
                    # 74=County, NAICS 6-digit (if available)
                    if agglvl not in ('40', '41', '50', '51', '52', '53', '70', '71', '72', '73', '74', '75'):
                        continue

                    batch.append((
                        row.get('area_fips', '').strip(),
                        row.get('own_code', '').strip(),
                        row.get('industry_code', '').strip(),
                        agglvl,
                        row.get('size_code', '').strip(),
                        year,
                        row.get('disclosure_code', '').strip(),
                        parse_int(row.get('annual_avg_estabs')),
                        parse_int(row.get('annual_avg_emplvl')),
                        parse_int(row.get('total_annual_wages')),
                        parse_int(row.get('taxable_annual_wages')),
                        parse_int(row.get('annual_contributions')),
                        parse_int(row.get('annual_avg_wkly_wage')),
                        parse_int(row.get('avg_annual_pay')),
                        parse_float(row.get('lq_annual_avg_estabs')),
                        parse_float(row.get('lq_annual_avg_emplvl')),
                        parse_float(row.get('lq_total_annual_wages')),
                        parse_float(row.get('lq_avg_annual_pay')),
                    ))

                    row_count += 1

                    if len(batch) >= 10000:
                        execute_values(cur, """
                            INSERT INTO qcew_annual
                                (area_fips, own_code, industry_code, agglvl_code, size_code,
                                 year, disclosure_code, annual_avg_estabs, annual_avg_emplvl,
                                 total_annual_wages, taxable_annual_wages, annual_contributions,
                                 annual_avg_wkly_wage, avg_annual_pay,
                                 lq_annual_avg_estabs, lq_annual_avg_emplvl,
                                 lq_total_annual_wages, lq_avg_annual_pay)
                            VALUES %s
                        """, batch, page_size=5000)
                        conn.commit()
                        batch = []

                        if row_count % 100000 == 0:
                            print(f"    {row_count:,} rows loaded")

    # Insert remaining
    if batch:
        execute_values(cur, """
            INSERT INTO qcew_annual
                (area_fips, own_code, industry_code, agglvl_code, size_code,
                 year, disclosure_code, annual_avg_estabs, annual_avg_emplvl,
                 total_annual_wages, taxable_annual_wages, annual_contributions,
                 annual_avg_wkly_wage, avg_annual_pay,
                 lq_annual_avg_estabs, lq_annual_avg_emplvl,
                 lq_total_annual_wages, lq_avg_annual_pay)
            VALUES %s
        """, batch, page_size=5000)
        conn.commit()

    print(f"  Loaded {row_count:,} rows for {year}")
    return row_count


def create_indexes(conn):
    """Create indexes for efficient querying."""
    cur = conn.cursor()
    print("\n=== Creating indexes ===")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_qcew_area ON qcew_annual(area_fips)",
        "CREATE INDEX IF NOT EXISTS idx_qcew_industry ON qcew_annual(industry_code)",
        "CREATE INDEX IF NOT EXISTS idx_qcew_year ON qcew_annual(year)",
        "CREATE INDEX IF NOT EXISTS idx_qcew_own ON qcew_annual(own_code)",
        "CREATE INDEX IF NOT EXISTS idx_qcew_area_ind ON qcew_annual(area_fips, industry_code)",
        "CREATE INDEX IF NOT EXISTS idx_qcew_agglvl ON qcew_annual(agglvl_code)",
    ]
    for idx in indexes:
        cur.execute(idx)
    conn.commit()
    print(f"  {len(indexes)} indexes created")


def print_summary(conn):
    """Print summary stats."""
    cur = conn.cursor()
    print("\n=== QCEW DATA SUMMARY ===")

    cur.execute("SELECT year, COUNT(*) FROM qcew_annual GROUP BY year ORDER BY year")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} rows")

    cur.execute("SELECT COUNT(*) FROM qcew_annual")
    print(f"  TOTAL: {cur.fetchone()[0]:,}")

    # Sample: top industries by establishment count (private sector, 2023)
    print("\n  Top 10 industries by establishment count (private, latest year):")
    cur.execute("""
        SELECT industry_code, MAX(annual_avg_estabs) as estabs, MAX(annual_avg_emplvl) as empl
        FROM qcew_annual
        WHERE own_code = '5' AND agglvl_code IN ('40','41') AND area_fips = 'US000'
        GROUP BY industry_code
        ORDER BY estabs DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        estabs = row[1] or 0
        empl = row[2] or 0
        print(f"    {row[0]}: {estabs:,} establishments, {empl:,} employees")


def main():
    conn = get_connection()
    conn.autocommit = False
    create_table(conn)

    total_rows = 0
    years = [2023, 2022, 2021, 2020]  # 2024 may not be available yet

    for year in years:
        print(f"\n=== QCEW {year} ===")
        try:
            zip_path = download_qcew_year(year)
            rows = load_qcew_year(conn, zip_path, year)
            total_rows += rows
        except requests.HTTPError as e:
            print(f"  Year {year} not available: {e}")
            continue

    create_indexes(conn)
    print_summary(conn)

    print(f"\n=== TOTAL LOADED: {total_rows:,} rows ===")
    conn.close()


if __name__ == "__main__":
    main()
