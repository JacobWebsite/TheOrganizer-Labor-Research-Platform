import os
"""
Splink Phase 2 - Data Analysis for Blocking Design
Analyzes unmatched records, data quality, and blocking space estimates.
"""

import psycopg2
import psycopg2.extras
from collections import OrderedDict

DB_CONFIG = {
    "host": "localhost",
    "dbname": "olms_multiyear",
    "user": "postgres",
    "password": os.environ.get('DB_PASSWORD', ''),
}


def run_query(cur, sql, label=None):
    if label:
        print(f"\n{'='*70}")
        print(f"  {label}")
        print(f"{'='*70}")
    cur.execute(sql)
    return cur.fetchall()


def print_table(rows, headers, col_widths=None):
    if not rows:
        print("  (no rows)")
        return
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            w = len(str(h))
            for r in rows:
                w = max(w, len(str(r[i])) if i < len(r) else 0)
            col_widths.append(min(w + 2, 60))
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print("  " + fmt.format(*headers))
    print("  " + "  ".join("-" * w for w in col_widths))
    for r in rows:
        vals = [str(v) if v is not None else "" for v in r]
        print("  " + fmt.format(*vals))


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # =====================================================================
    # 1. UNMATCHED RECORD COUNTS
    # =====================================================================
    print("\n" + "=" * 70)
    print("  1. UNMATCHED RECORD COUNTS")
    print("=" * 70)

    unmatched_queries = OrderedDict([
        ("Mergent employers NOT in crosswalk", """
            SELECT COUNT(*) FROM mergent_employers m
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c
                WHERE c.mergent_duns = m.duns
            )
        """),
        ("Mergent employers TOTAL", "SELECT COUNT(*) FROM mergent_employers"),
        ("F7 employers NOT in crosswalk", """
            SELECT COUNT(*) FROM f7_employers_deduped f
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c
                WHERE c.f7_employer_id = f.employer_id
            )
        """),
        ("F7 employers TOTAL", "SELECT COUNT(*) FROM f7_employers_deduped"),
        ("GLEIF US entities NOT in crosswalk", """
            SELECT COUNT(*) FROM gleif_us_entities g
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c
                WHERE c.gleif_id = g.id
            )
        """),
        ("GLEIF US entities TOTAL", "SELECT COUNT(*) FROM gleif_us_entities"),
        ("SEC companies NOT in crosswalk", """
            SELECT COUNT(*) FROM sec_companies s
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c
                WHERE c.sec_cik::text = s.cik::text
            )
        """),
        ("SEC companies TOTAL", "SELECT COUNT(*) FROM sec_companies"),
    ])

    for label, sql in unmatched_queries.items():
        cur.execute(sql)
        count = cur.fetchone()[0]
        print(f"  {label}: {count:,}")

    # =====================================================================
    # 2. AVAILABLE COLUMNS PER TABLE
    # =====================================================================
    tables = ["f7_employers_deduped", "mergent_employers", "gleif_us_entities", "sec_companies"]

    for tbl in tables:
        rows = run_query(cur, f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = '{tbl}'
            ORDER BY ordinal_position
        """, label=f"2. COLUMNS: {tbl}")
        print_table(rows, ["Column", "Type", "Nullable"])

    # =====================================================================
    # 3. DATA QUALITY FOR KEY MATCHING COLUMNS
    # =====================================================================
    print("\n" + "=" * 70)
    print("  3. DATA QUALITY - NOT NULL COUNTS FOR KEY COLUMNS")
    print("=" * 70)

    # Check which columns actually exist in each table first
    quality_checks = {
        "f7_employers_deduped": {
            "name_cols": ["employer_name", "employer_name_aggressive"],
            "geo_cols": ["state", "city", "zip_code"],
            "other_cols": ["naics_code", "address"],
        },
        "mergent_employers": {
            "name_cols": ["company_name", "normalized_name"],
            "geo_cols": ["state", "city", "zip_code", "zip"],
            "other_cols": ["naics_code", "naics", "address", "street_address", "duns"],
        },
        "gleif_us_entities": {
            "name_cols": ["legal_name", "normalized_name"],
            "geo_cols": ["region", "state", "city", "postal_code"],
            "other_cols": ["lei", "address_line1", "address"],
        },
        "sec_companies": {
            "name_cols": ["company_name", "normalized_name", "name"],
            "geo_cols": ["state", "state_of_incorp", "city"],
            "other_cols": ["sic", "cik", "lei"],
        },
    }

    for tbl, col_groups in quality_checks.items():
        # Get actual columns
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{tbl}'
        """)
        actual_cols = {r[0] for r in cur.fetchall()}

        print(f"\n  -- {tbl} --")
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        total = cur.fetchone()[0]
        print(f"  Total rows: {total:,}")

        all_cols = []
        for group_cols in col_groups.values():
            all_cols.extend(group_cols)

        for col in all_cols:
            if col in actual_cols:
                cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NOT NULL AND {col}::text != ''")
                cnt = cur.fetchone()[0]
                pct = (cnt / total * 100) if total > 0 else 0
                print(f"    {col:<30s} NOT NULL: {cnt:>10,}  ({pct:5.1f}%)")
            else:
                print(f"    {col:<30s} [column does not exist]")

    # =====================================================================
    # 4. STATE DISTRIBUTION OF UNMATCHED RECORDS (TOP 15)
    # =====================================================================

    # First figure out which state column exists for each
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'mergent_employers'
    """)
    mergent_cols = {r[0] for r in cur.fetchall()}

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'f7_employers_deduped'
    """)
    f7_cols = {r[0] for r in cur.fetchall()}

    # Determine state column for mergent
    mergent_state_col = "state" if "state" in mergent_cols else None
    if not mergent_state_col:
        for c in ["state_code", "physical_state", "mailing_state"]:
            if c in mergent_cols:
                mergent_state_col = c
                break

    # Determine state column for f7
    f7_state_col = "state" if "state" in f7_cols else None

    if mergent_state_col:
        rows = run_query(cur, f"""
            SELECT COALESCE(m.{mergent_state_col}, '(null)') as state, COUNT(*) as cnt
            FROM mergent_employers m
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.mergent_duns = m.duns
            )
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        """, label="4a. STATE DISTRIBUTION - UNMATCHED MERGENT (top 15)")
        print_table(rows, ["State", "Count"])
    else:
        print("\n  [Could not find state column for mergent_employers]")
        print(f"  Available columns: {sorted(mergent_cols)}")

    if f7_state_col:
        rows = run_query(cur, f"""
            SELECT COALESCE(f.{f7_state_col}, '(null)') as state, COUNT(*) as cnt
            FROM f7_employers_deduped f
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
            )
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        """, label="4b. STATE DISTRIBUTION - UNMATCHED F7 (top 15)")
        print_table(rows, ["State", "Count"])
    else:
        print("\n  [Could not find state column for f7_employers_deduped]")
        print(f"  Available columns: {sorted(f7_cols)}")

    # =====================================================================
    # 5. BLOCKING SPACE ESTIMATES
    # =====================================================================

    # Determine name columns
    mergent_name_col = None
    for c in ["normalized_name", "company_name"]:
        if c in mergent_cols:
            mergent_name_col = c
            break

    f7_name_col = None
    for c in ["employer_name_aggressive", "employer_name"]:
        if c in f7_cols:
            f7_name_col = c
            break

    if mergent_state_col and f7_state_col:
        rows = run_query(cur, f"""
            WITH unmatched_mergent AS (
                SELECT m.{mergent_state_col} as state, m.{mergent_name_col} as name
                FROM mergent_employers m
                WHERE NOT EXISTS (
                    SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.mergent_duns = m.duns
                )
                AND m.{mergent_state_col} IS NOT NULL
            ),
            unmatched_f7 AS (
                SELECT f.{f7_state_col} as state, f.{f7_name_col} as name
                FROM f7_employers_deduped f
                WHERE NOT EXISTS (
                    SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
                )
                AND f.{f7_state_col} IS NOT NULL
            ),
            state_counts AS (
                SELECT
                    COALESCE(um.state, uf7.state) as state,
                    COALESCE(um.m_count, 0) as mergent_count,
                    COALESCE(uf7.f_count, 0) as f7_count,
                    COALESCE(um.m_count, 0)::bigint * COALESCE(uf7.f_count, 0)::bigint as pair_count
                FROM
                    (SELECT state, COUNT(*) as m_count FROM unmatched_mergent GROUP BY state) um
                FULL OUTER JOIN
                    (SELECT state, COUNT(*) as f_count FROM unmatched_f7 GROUP BY state) uf7
                ON um.state = uf7.state
            )
            SELECT state, mergent_count, f7_count, pair_count
            FROM state_counts
            ORDER BY pair_count DESC
            LIMIT 10
        """, label="5a. BLOCKING SPACE: Mergent x F7 by STATE (top 10)")
        print_table(rows, ["State", "Mergent", "F7", "Pairs"])

        # Total pairs with state-only blocking
        cur.execute(f"""
            WITH unmatched_mergent AS (
                SELECT m.{mergent_state_col} as state
                FROM mergent_employers m
                WHERE NOT EXISTS (
                    SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.mergent_duns = m.duns
                )
                AND m.{mergent_state_col} IS NOT NULL
            ),
            unmatched_f7 AS (
                SELECT f.{f7_state_col} as state
                FROM f7_employers_deduped f
                WHERE NOT EXISTS (
                    SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
                )
                AND f.{f7_state_col} IS NOT NULL
            )
            SELECT SUM(mc::bigint * fc::bigint)
            FROM (SELECT state, COUNT(*) as mc FROM unmatched_mergent GROUP BY state) a
            JOIN (SELECT state, COUNT(*) as fc FROM unmatched_f7 GROUP BY state) b
            USING (state)
        """)
        state_only_pairs = cur.fetchone()[0] or 0
        print(f"\n  Total pairs (state-only blocking): {state_only_pairs:,}")

        # State + first 3 chars of name blocking
        cur.execute(f"""
            WITH unmatched_mergent AS (
                SELECT m.{mergent_state_col} as state,
                       LEFT(UPPER(COALESCE(m.{mergent_name_col}, '')), 3) as name_prefix
                FROM mergent_employers m
                WHERE NOT EXISTS (
                    SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.mergent_duns = m.duns
                )
                AND m.{mergent_state_col} IS NOT NULL
            ),
            unmatched_f7 AS (
                SELECT f.{f7_state_col} as state,
                       LEFT(UPPER(COALESCE(f.{f7_name_col}, '')), 3) as name_prefix
                FROM f7_employers_deduped f
                WHERE NOT EXISTS (
                    SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
                )
                AND f.{f7_state_col} IS NOT NULL
            )
            SELECT SUM(mc::bigint * fc::bigint)
            FROM (SELECT state, name_prefix, COUNT(*) as mc FROM unmatched_mergent GROUP BY state, name_prefix) a
            JOIN (SELECT state, name_prefix, COUNT(*) as fc FROM unmatched_f7 GROUP BY state, name_prefix) b
            USING (state, name_prefix)
        """)
        prefix_pairs = cur.fetchone()[0] or 0
        print(f"  Total pairs (state + 3-char name prefix): {prefix_pairs:,}")
        if state_only_pairs > 0:
            reduction = (1 - prefix_pairs / state_only_pairs) * 100
            print(f"  Reduction from name prefix blocking: {reduction:.1f}%")

    # =====================================================================
    # 6. NAME LENGTH DISTRIBUTION FOR UNMATCHED RECORDS
    # =====================================================================

    if mergent_name_col and mergent_state_col:
        rows = run_query(cur, f"""
            SELECT
                'Mergent' as source,
                COUNT(*) as n,
                ROUND(AVG(LENGTH({mergent_name_col})), 1) as avg_len,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH({mergent_name_col}))::int as median_len,
                MIN(LENGTH({mergent_name_col})) as min_len,
                MAX(LENGTH({mergent_name_col})) as max_len
            FROM mergent_employers m
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.mergent_duns = m.duns
            )
            AND {mergent_name_col} IS NOT NULL
        """, label="6. NAME LENGTH DISTRIBUTION (unmatched records)")
        print_table(rows, ["Source", "N", "Avg", "Median", "Min", "Max"])

    if f7_name_col and f7_state_col:
        cur.execute(f"""
            SELECT
                'F7' as source,
                COUNT(*) as n,
                ROUND(AVG(LENGTH({f7_name_col})), 1) as avg_len,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH({f7_name_col}))::int as median_len,
                MIN(LENGTH({f7_name_col})) as min_len,
                MAX(LENGTH({f7_name_col})) as max_len
            FROM f7_employers_deduped f
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
            )
            AND {f7_name_col} IS NOT NULL
        """)
        rows = cur.fetchall()
        print_table(rows, ["Source", "N", "Avg", "Median", "Min", "Max"])

    # GLEIF name stats
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'gleif_us_entities'
    """)
    gleif_cols = {r[0] for r in cur.fetchall()}
    gleif_name_col = None
    for c in ["normalized_name", "legal_name"]:
        if c in gleif_cols:
            gleif_name_col = c
            break

    if gleif_name_col:
        cur.execute(f"""
            SELECT
                'GLEIF' as source,
                COUNT(*) as n,
                ROUND(AVG(LENGTH({gleif_name_col})), 1) as avg_len,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH({gleif_name_col}))::int as median_len,
                MIN(LENGTH({gleif_name_col})) as min_len,
                MAX(LENGTH({gleif_name_col})) as max_len
            FROM gleif_us_entities g
            WHERE NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.gleif_id = g.id
            )
            AND {gleif_name_col} IS NOT NULL
        """)
        rows = cur.fetchall()
        print_table(rows, ["Source", "N", "Avg", "Median", "Min", "Max"])

    print("\n" + "=" * 70)
    print("  ANALYSIS COMPLETE")
    print("=" * 70)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
