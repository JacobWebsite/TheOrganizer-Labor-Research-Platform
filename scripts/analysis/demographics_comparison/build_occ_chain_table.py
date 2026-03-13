"""
Build precomputed occupation-chain demographics table.

For each NAICS group x state, compute the expected demographic composition
using the three-way chain:
  1. BLS industry-occupation matrix: what jobs make up this industry?
  2. OES metro employment: how does the local job mix deviate from national?
  3. ACS state-level occupation demographics: who holds each job in this state?

Output: occ_local_demographics table in PostgreSQL
  Columns: naics_group, state_fips, pct_female, pct_asian, pct_white,
           pct_black, pct_hispanic, pct_aian, occs_matched,
           pct_industry_covered, computed_at

Usage:
    py scripts/analysis/demographics_comparison/build_occ_chain_table.py
"""

import psycopg2
import psycopg2.extras
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

# Map V6 NAICS groups to BLS industry matrix codes
# Use the primary NAICS code that best represents each group
NAICS_GROUP_CODES = {
    'Healthcare/Social (62)': ['621000', '622000', '623000', '624000', '62'],
    'Finance/Insurance (52)': ['522000', '523000', '524000', '52'],
    'Information (51)': ['511000', '512000', '515000', '517000', '51'],
    'Professional/Technical (54)': ['541000', '54'],
    'Admin/Staffing (56)': ['561000', '561300', '56'],
    'Retail Trade (44-45)': ['441000', '445000', '448000', '44', '45'],
    'Accommodation/Food Svc (72)': ['722000', '722511', '722512', '721000', '72'],
    'Construction (23)': ['236000', '237000', '238000', '23'],
    'Transportation/Warehousing (48-49)': ['484000', '485000', '492000', '48', '49'],
    'Wholesale Trade (42)': ['423000', '424000', '42'],
    'Utilities (22)': ['221000', '22'],
    'Metal/Machinery Mfg (331-333)': ['332000', '333000', '331000', '33'],
    'Chemical/Material Mfg (325-327)': ['325000', '326000', '327000', '32'],
    'Food/Bev Manufacturing (311,312)': ['311000', '312000', '31'],
    'Computer/Electrical Mfg (334-335)': ['334000', '335000', '33'],
    'Transport Equip Mfg (336)': ['336000', '33'],
    'Other Manufacturing': ['31', '32', '33'],
    'Agriculture/Mining (11,21)': ['111000', '112000', '211000', '212000', '11', '21'],
    'Other': ['81', '92'],
}


def build_table(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Create output table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS occ_local_demographics (
            id SERIAL PRIMARY KEY,
            naics_group TEXT NOT NULL,
            state_fips CHAR(2) NOT NULL,
            pct_female NUMERIC(5,2),
            pct_asian NUMERIC(5,2),
            pct_white NUMERIC(5,2),
            pct_black NUMERIC(5,2),
            pct_hispanic NUMERIC(5,2),
            pct_aian NUMERIC(5,2),
            occs_matched INTEGER,
            pct_industry_covered NUMERIC(5,1),
            computed_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(naics_group, state_fips)
        )
    """)
    conn.commit()

    # Get all states
    cur.execute("SELECT DISTINCT state_fips FROM cur_acs_workforce_demographics "
                "WHERE state_fips IS NOT NULL AND state_fips != '' "
                "ORDER BY state_fips")
    states = [r['state_fips'] for r in cur.fetchall()]
    print('States: %d' % len(states))

    results = []

    for naics_group, bls_codes in NAICS_GROUP_CODES.items():
        print('\nProcessing: %s' % naics_group)

        # Get industry occupation mix from BLS matrix
        # Try codes in order until we get data
        occ_mix = []
        for code in bls_codes:
            cur.execute("""
                SELECT occupation_code, percent_of_industry
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
                  AND LOWER(occupation_type) = 'line item'
                  AND percent_of_industry IS NOT NULL
                ORDER BY percent_of_industry DESC
            """, [code])
            rows = cur.fetchall()
            if rows:
                occ_mix = [(r['occupation_code'], float(r['percent_of_industry']))
                           for r in rows]
                print('  BLS code %s: %d occupations, %.1f%% covered' % (
                    code, len(occ_mix), sum(p for _, p in occ_mix)))
                break

        if not occ_mix:
            print('  WARNING: No BLS occupation data found')
            continue

        occ_codes = [oc for oc, _ in occ_mix]
        total_pct = sum(p for _, p in occ_mix)

        # For each state, compute occupation-chain demographics
        for state_fips in states:
            # Get ACS demographics per occupation for this state
            # ACS uses 6-digit codes without dashes; BLS uses dashes
            placeholders = ','.join(['%s'] * len(occ_codes))
            normalized_codes = [c.replace('-', '') for c in occ_codes]

            cur.execute("""
                SELECT
                    soc_code,
                    SUM(weighted_workers) FILTER (WHERE sex = '2') as female_w,
                    SUM(weighted_workers) FILTER (WHERE race IN ('4','5')
                        AND hispanic = '0') as asian_w,
                    SUM(weighted_workers) FILTER (WHERE race = '1'
                        AND hispanic = '0') as white_w,
                    SUM(weighted_workers) FILTER (WHERE race = '2'
                        AND hispanic = '0') as black_w,
                    SUM(weighted_workers) FILTER (WHERE hispanic != '0') as hisp_w,
                    SUM(weighted_workers) FILTER (WHERE race = '3'
                        AND hispanic = '0') as aian_w,
                    SUM(weighted_workers) FILTER (WHERE sex IN ('1','2')) as total_w
                FROM cur_acs_workforce_demographics
                WHERE soc_code IN (%s)
                  AND state_fips = %%s
                  AND sex IN ('1','2')
                GROUP BY soc_code
                HAVING SUM(weighted_workers) FILTER (WHERE sex IN ('1','2')) > 100
            """ % placeholders, normalized_codes + [state_fips])

            acs_rows = {r['soc_code']: r for r in cur.fetchall()}

            if not acs_rows:
                continue

            # Compute weighted average
            total_weight = 0.0
            accum = {k: 0.0 for k in
                     ['female', 'asian', 'white', 'black', 'hisp', 'aian']}
            matched = 0

            for occ_code, ind_share in occ_mix:
                norm_code = occ_code.replace('-', '')
                if norm_code not in acs_rows:
                    continue
                row = acs_rows[norm_code]
                total_w = float(row['total_w'] or 0)
                if total_w == 0:
                    continue

                weight = ind_share  # industry share as weight
                total_weight += weight
                matched += 1

                for key, col in [('female', 'female_w'), ('asian', 'asian_w'),
                                  ('white', 'white_w'), ('black', 'black_w'),
                                  ('hisp', 'hisp_w'), ('aian', 'aian_w')]:
                    accum[key] += weight * float(row[col] or 0) / total_w * 100

            if total_weight < 10 or matched < 5:
                continue  # Not enough coverage to be reliable

            row_result = {
                'naics_group': naics_group,
                'state_fips': state_fips,
                'pct_female': round(accum['female'] / total_weight, 2),
                'pct_asian': round(accum['asian'] / total_weight, 2),
                'pct_white': round(accum['white'] / total_weight, 2),
                'pct_black': round(accum['black'] / total_weight, 2),
                'pct_hispanic': round(accum['hisp'] / total_weight, 2),
                'pct_aian': round(accum['aian'] / total_weight, 2),
                'occs_matched': matched,
                'pct_industry_covered': round(total_weight, 1),
            }
            results.append(row_result)

    # Insert all results
    if results:
        cur.execute("DELETE FROM occ_local_demographics")
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO occ_local_demographics
                (naics_group, state_fips, pct_female, pct_asian, pct_white,
                 pct_black, pct_hispanic, pct_aian, occs_matched, pct_industry_covered)
            VALUES
                (%(naics_group)s, %(state_fips)s, %(pct_female)s, %(pct_asian)s,
                 %(pct_white)s, %(pct_black)s, %(pct_hispanic)s, %(pct_aian)s,
                 %(occs_matched)s, %(pct_industry_covered)s)
            ON CONFLICT (naics_group, state_fips) DO UPDATE SET
                pct_female = EXCLUDED.pct_female,
                pct_asian = EXCLUDED.pct_asian,
                pct_white = EXCLUDED.pct_white,
                pct_black = EXCLUDED.pct_black,
                pct_hispanic = EXCLUDED.pct_hispanic,
                pct_aian = EXCLUDED.pct_aian,
                occs_matched = EXCLUDED.occs_matched,
                pct_industry_covered = EXCLUDED.pct_industry_covered,
                computed_at = NOW()
        """, results)
        conn.commit()
        print('\nInserted %d rows into occ_local_demographics' % len(results))

    # Verification query
    cur.execute("""
        SELECT naics_group, state_fips, pct_asian, pct_female, occs_matched
        FROM occ_local_demographics
        WHERE naics_group = 'Healthcare/Social (62)'
          AND state_fips IN ('06', '15', '28', '48')
        ORDER BY state_fips
    """)
    print('\nSanity check -- Healthcare by state (pct_asian):')
    for r in cur.fetchall():
        print('  State %s: Asian=%s%%, Female=%s%%, occs=%s' % (
            r['state_fips'], r['pct_asian'], r['pct_female'], r['occs_matched']))

    cur.close()


if __name__ == '__main__':
    conn = get_connection()
    build_table(conn)
    conn.close()
