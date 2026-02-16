#!/usr/bin/env python3
"""
Parse BLS National Employment Matrix files and load occupation-industry staffing patterns.
"""
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from psycopg2.extras import RealDictCursor, execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


INDUSTRY_CODE_RE = re.compile(r"^National Employment Matrix_IND_(.+)\.csv$")
STANDARD_INDUSTRY_CODE_RE = re.compile(r"^[0-9]{2,6}(?:-[0-9]+)?$")
OEWS_INDUSTRY_CODE_RE = re.compile(r"^[A-Z0-9-]{2,12}$")
SOC_RE = re.compile(r"([0-9]{2}-[0-9]{4})")
NULL_TOKENS = {"", "-", "--", "—", "N/A", "NA", "*"}


def extract_industry_code(filename: str) -> str:
    """
    Extract and validate industry code from matrix filename.
    """
    match = INDUSTRY_CODE_RE.match(filename)
    if not match:
        raise ValueError(f"Invalid OEWS filename format: {filename}")
    code = match.group(1).strip()
    code = re.sub(r"\s+\(\d+\)$", "", code)

    if STANDARD_INDUSTRY_CODE_RE.match(code):
        return code
    if OEWS_INDUSTRY_CODE_RE.match(code):
        return code
    raise ValueError(f"Unrecognized industry code format in filename: {filename}")


def clean_occupation_code(raw_code: str) -> Optional[str]:
    """
    Clean Excel-style SOC code strings like =\"11-1011\".
    """
    if raw_code is None:
        return None
    text = str(raw_code).strip()
    if text in NULL_TOKENS:
        return None
    soc_match = SOC_RE.search(text)
    if not soc_match:
        return None
    return soc_match.group(1)


def parse_numeric(raw_value: Optional[str]) -> Optional[float]:
    """
    Parse numeric cells that may contain commas or null markers.
    """
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if text in NULL_TOKENS:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def parse_file(filepath: Path, industry_code: str) -> List[Dict]:
    """
    Parse one employment matrix CSV file into row dictionaries.
    """
    rows: List[Dict] = []
    with filepath.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)

        expected_fields = {
            "Occupation Title",
            "Occupation Code",
            "Occupation Type",
            "2024 Employment",
            "2024 Percent of Industry",
            "2024 Percent of Occupation",
            "Projected 2034 Employment",
            "Projected 2034 Percent of Industry",
            "Projected 2034 Percent of Occupation",
            "Employment Change, 2024-2034",
            "Employment Percent Change, 2024-2034",
        }
        missing = expected_fields.difference(set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"Missing columns {sorted(missing)} in {filepath.name}")

        for record in reader:
            occupation_type = (record.get("Occupation Type") or "").strip()
            if occupation_type != "Line Item":
                continue

            occupation_code = clean_occupation_code(record.get("Occupation Code"))
            occupation_title = (record.get("Occupation Title") or "").strip()

            if not occupation_code or not occupation_title:
                continue

            rows.append(
                {
                    "industry_code": industry_code,
                    "occupation_code": occupation_code,
                    "occupation_title": occupation_title,
                    "occupation_type": occupation_type,
                    "employment_2024": parse_numeric(record.get("2024 Employment")),
                    "percent_of_industry": parse_numeric(record.get("2024 Percent of Industry")),
                    "percent_of_occupation": parse_numeric(record.get("2024 Percent of Occupation")),
                    "employment_2034": parse_numeric(record.get("Projected 2034 Employment")),
                    "percent_of_industry_2034": parse_numeric(record.get("Projected 2034 Percent of Industry")),
                    "percent_of_occupation_2034": parse_numeric(record.get("Projected 2034 Percent of Occupation")),
                    "employment_change": parse_numeric(record.get("Employment Change, 2024-2034")),
                    "employment_change_pct": parse_numeric(record.get("Employment Percent Change, 2024-2034")),
                }
            )

    return rows


def create_schema(cur) -> None:
    cur.execute(
        """
        DROP VIEW IF EXISTS v_industry_top_occupations;
        DROP VIEW IF EXISTS v_bls_occupation_census_link;

        DROP TABLE IF EXISTS bls_industry_occupation_matrix;

        CREATE TABLE IF NOT EXISTS bls_industry_occupation_matrix (
            id SERIAL PRIMARY KEY,
            industry_code VARCHAR(20),
            occupation_code VARCHAR(10),
            occupation_title VARCHAR(200),
            occupation_type VARCHAR(20),
            employment_2024 NUMERIC(12,1),
            percent_of_industry NUMERIC(5,2),
            percent_of_occupation NUMERIC(5,2),
            employment_2034 NUMERIC(12,1),
            percent_of_industry_2034 NUMERIC(5,2),
            percent_of_occupation_2034 NUMERIC(5,2),
            employment_change NUMERIC(12,1),
            employment_change_pct NUMERIC(5,2),
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
    )

    cur.execute(
        """
        ALTER TABLE bls_industry_occupation_matrix
        ADD CONSTRAINT uq_iom_industry_occupation
        UNIQUE (industry_code, occupation_code);
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_iom_industry ON bls_industry_occupation_matrix(industry_code);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_iom_occupation ON bls_industry_occupation_matrix(occupation_code);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_iom_type ON bls_industry_occupation_matrix(occupation_type);")

    cur.execute(
        """
        CREATE OR REPLACE VIEW v_industry_top_occupations AS
        SELECT
            industry_code,
            occupation_code,
            occupation_title,
            employment_2024,
            percent_of_industry,
            RANK() OVER (
                PARTITION BY industry_code
                ORDER BY percent_of_industry DESC NULLS LAST
            ) AS rank
        FROM bls_industry_occupation_matrix
        WHERE occupation_type = 'Line Item'
          AND percent_of_industry >= 1.0
        ORDER BY industry_code, percent_of_industry DESC NULLS LAST;
        """
    )


def upsert_rows(cur, rows: List[Dict]) -> int:
    if not rows:
        return 0

    query = """
        INSERT INTO bls_industry_occupation_matrix (
            industry_code,
            occupation_code,
            occupation_title,
            occupation_type,
            employment_2024,
            percent_of_industry,
            percent_of_occupation,
            employment_2034,
            percent_of_industry_2034,
            percent_of_occupation_2034,
            employment_change,
            employment_change_pct
        ) VALUES (
            %(industry_code)s,
            %(occupation_code)s,
            %(occupation_title)s,
            %(occupation_type)s,
            %(employment_2024)s,
            %(percent_of_industry)s,
            %(percent_of_occupation)s,
            %(employment_2034)s,
            %(percent_of_industry_2034)s,
            %(percent_of_occupation_2034)s,
            %(employment_change)s,
            %(employment_change_pct)s
        )
        ON CONFLICT (industry_code, occupation_code)
        DO UPDATE SET
            occupation_title = EXCLUDED.occupation_title,
            occupation_type = EXCLUDED.occupation_type,
            employment_2024 = EXCLUDED.employment_2024,
            percent_of_industry = EXCLUDED.percent_of_industry,
            percent_of_occupation = EXCLUDED.percent_of_occupation,
            employment_2034 = EXCLUDED.employment_2034,
            percent_of_industry_2034 = EXCLUDED.percent_of_industry_2034,
            percent_of_occupation_2034 = EXCLUDED.percent_of_occupation_2034,
            employment_change = EXCLUDED.employment_change,
            employment_change_pct = EXCLUDED.employment_change_pct
    """
    execute_batch(cur, query, rows, page_size=2000)
    return len(rows)


def main() -> int:
    base_dir = Path(__file__).resolve().parent.parent.parent
    matrix_dir = base_dir / "BLS industry and occupation projections"
    csv_files = sorted(matrix_dir.glob("National Employment Matrix_IND_*.csv"))

    if not csv_files:
        print(f"ERROR: No OEWS matrix files found in {matrix_dir}")
        return 1

    print("Parsing BLS National Employment Matrix files...")
    print("=" * 60)
    print(f"Processing {len(csv_files)} CSV files...")

    conn = get_connection(cursor_factory=RealDictCursor)
    processed_files = 0
    failed_files = 0
    total_rows_loaded = 0

    try:
        with conn.cursor() as cur:
            create_schema(cur)
        conn.commit()

        for index, filepath in enumerate(csv_files, start=1):
            try:
                industry_code = extract_industry_code(filepath.name)
                rows = parse_file(filepath, industry_code)
                with conn.cursor() as cur:
                    loaded = upsert_rows(cur, rows)
                conn.commit()
                total_rows_loaded += loaded
                processed_files += 1

                if index % 50 == 0 or index == len(csv_files):
                    print(f"[{index}/{len(csv_files)}] Processed industry {industry_code}... {loaded} occupations loaded")
            except Exception as exc:
                conn.rollback()
                failed_files += 1
                print(f"  ERROR [{filepath.name}]: {exc}")
                continue

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_rows,
                    COUNT(DISTINCT industry_code) AS unique_industries,
                    COUNT(DISTINCT occupation_code) AS unique_occupations
                FROM bls_industry_occupation_matrix
                """
            )
            stats = cur.fetchone()

            cur.execute(
                """
                SELECT industry_code, COUNT(*) AS occupation_count
                FROM bls_industry_occupation_matrix
                WHERE occupation_type = 'Line Item'
                GROUP BY industry_code
                ORDER BY occupation_count DESC
                LIMIT 10
                """
            )
            top_industries = cur.fetchall()

        print("\n" + "=" * 60)
        print("Load Summary:")
        print(f"  Files processed: {processed_files}")
        print(f"  Files failed: {failed_files}")
        print(f"  Total rows loaded (this run): {total_rows_loaded:,}")
        print(f"  Rows in table: {stats['total_rows']:,}")
        print(f"  Unique industries: {stats['unique_industries']}")
        print(f"  Unique occupations: {stats['unique_occupations']}")
        avg_per_ind = (
            float(stats["total_rows"]) / float(stats["unique_industries"])
            if stats["unique_industries"]
            else 0.0
        )
        print(f"  Average occupations per industry: {avg_per_ind:.1f}")

        print("\nTop 10 industries by occupation count:")
        for row in top_industries:
            print(f"  {row['industry_code']}: {row['occupation_count']}")

        print("\nView created: v_industry_top_occupations")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
