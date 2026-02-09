import os
"""Project stats summary."""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("LABOR RELATIONS RESEARCH PLATFORM - PROJECT STATS")
print("=" * 70)

# Core tables
tables = [
    ("f7_employers_deduped", "F7 Employers (deduped)"),
    ("f7_relations", "F7 Union-Employer Relations"),
    ("unions_master", "Unions Master"),
    ("nlrb_elections", "NLRB Elections"),
    ("nlrb_participants", "NLRB Participants"),
    ("nlrb_voluntary_recognition", "NLRB Voluntary Recognition"),
    ("osha_matches", "OSHA Matches"),
    ("mergent_employers", "Mergent Employers"),
    ("manual_employers", "Manual Employers"),
    ("gleif_us_entities", "GLEIF US Entities"),
    ("gleif_ownership_links", "GLEIF Ownership Links"),
    ("sec_companies", "SEC Companies"),
    ("corporate_identifier_crosswalk", "Corporate Crosswalk"),
    ("corporate_hierarchy", "Corporate Hierarchy"),
    ("ny_990_filers", "NY 990 Filers"),
    ("qcew_industry_density", "QCEW Industry Density"),
    ("usaspending_recipients", "USASpending Recipients"),
    ("splink_match_results", "Splink Match Results"),
    ("f7_employer_merge_log", "F7 Merge Log"),
]

print("\n--- CORE TABLES ---")
for tbl, label in tables:
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM %s" % tbl)
        cnt = cur.fetchone()['cnt']
        print("  %-40s %12s rows" % (label, format(cnt, ',')))
    except Exception as e:
        conn.rollback()
        print("  %-40s %s" % (label, str(e)[:50]))

# F7 employer stats
print("\n--- F7 EMPLOYER DETAILS ---")
cur.execute("""
    SELECT
        COUNT(*) as total,
        SUM(latest_unit_size) as total_workers,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
        COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded,
        COUNT(CASE WHEN corporate_parent_id IS NOT NULL THEN 1 END) as multi_location_linked,
        COUNT(DISTINCT corporate_parent_id) as multi_location_groups,
        AVG(latest_unit_size) as avg_size
    FROM f7_employers_deduped
""")
r = cur.fetchone()
print("  Total employers:          %s" % format(r['total'], ','))
print("  Total workers:            %s" % format(r['total_workers'] or 0, ','))
print("  Counted workers:          %s" % format(r['counted_workers'] or 0, ','))
print("  Excluded employers:       %s" % format(r['excluded'], ','))
print("  Multi-location linked:    %s (in %s groups)" % (format(r['multi_location_linked'], ','), format(r['multi_location_groups'], ',')))
print("  Avg unit size:            %.0f" % (r['avg_size'] or 0))

BLS = 7_200_000
pct = (r['counted_workers'] or 0) / BLS * 100
print("  BLS coverage:             %.1f%%" % pct)

# Crosswalk stats
print("\n--- CORPORATE CROSSWALK ---")
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(gleif_lei) as gleif,
        COUNT(mergent_duns) as mergent,
        COUNT(sec_cik) as sec,
        COUNT(ein) as ein,
        COUNT(f7_employer_id) as f7,
        COUNT(CASE WHEN is_federal_contractor THEN 1 END) as fed_contractors,
        SUM(federal_obligations) as total_obligations
    FROM corporate_identifier_crosswalk
""")
c = cur.fetchone()
print("  Total rows:               %s" % format(c['total'], ','))
print("  GLEIF LEI linked:         %s" % format(c['gleif'], ','))
print("  Mergent DUNS linked:      %s" % format(c['mergent'], ','))
print("  SEC CIK linked:           %s" % format(c['sec'], ','))
print("  EIN linked:               %s" % format(c['ein'], ','))
print("  F7 employer linked:       %s" % format(c['f7'], ','))
print("  Federal contractors:      %s" % format(c['fed_contractors'], ','))
print("  Total fed obligations:    $%s" % format(int(c['total_obligations'] or 0), ','))

# Multi-source linkage
cur.execute("""
    SELECT
        COUNT(CASE WHEN (CASE WHEN gleif_lei IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN mergent_duns IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN sec_cik IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN f7_employer_id IS NOT NULL THEN 1 ELSE 0 END) >= 3 THEN 1 END) as three_plus,
        COUNT(CASE WHEN gleif_lei IS NOT NULL AND mergent_duns IS NOT NULL AND sec_cik IS NOT NULL AND f7_employer_id IS NOT NULL THEN 1 END) as all_four
    FROM corporate_identifier_crosswalk
""")
ml = cur.fetchone()
print("  3+ sources linked:        %s" % format(ml['three_plus'], ','))
print("  All 4 sources linked:     %s" % format(ml['all_four'], ','))

# Merge stats
print("\n--- DEDUP MERGE HISTORY ---")
cur.execute("""
    SELECT COUNT(*) as total_merges,
           SUM(f7_relations_updated) as f7_rel,
           SUM(vr_records_updated) as vr,
           SUM(nlrb_participants_updated) as nlrb,
           SUM(osha_matches_updated) as osha,
           SUM(COALESCE(crosswalk_updated, 0)) as crosswalk
    FROM f7_employer_merge_log
""")
m = cur.fetchone()
print("  Total merges:             %s" % format(m['total_merges'] or 0, ','))
print("  F7 relations updated:     %s" % format(m['f7_rel'] or 0, ','))
print("  VR records updated:       %s" % format(m['vr'] or 0, ','))
print("  NLRB participants updated:%s" % format(m['nlrb'] or 0, ','))
print("  OSHA matches updated:     %s" % format(m['osha'] or 0, ','))
print("  Crosswalk updated:        %s" % format(m['crosswalk'] or 0, ','))

# Splink scenarios
print("\n--- SPLINK MATCH RESULTS ---")
cur.execute("""
    SELECT scenario, COUNT(*) as pairs,
           AVG(match_probability) as avg_prob,
           MIN(match_probability) as min_prob,
           MAX(match_probability) as max_prob
    FROM splink_match_results
    GROUP BY scenario
    ORDER BY scenario
""")
for row in cur.fetchall():
    print("  %-25s %8s pairs  (prob: %.2f-%.2f, avg %.2f)" % (
        row['scenario'], format(row['pairs'], ','),
        row['min_prob'] or 0, row['max_prob'] or 0, row['avg_prob'] or 0))

# NAICS coverage
print("\n--- NAICS COVERAGE ---")
cur.execute("""
    SELECT naics_source, COUNT(*) as cnt
    FROM f7_employers_deduped
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print("  %-25s %8s" % (row['naics_source'], format(row['cnt'], ',')))

# Geocoding
print("\n--- GEOCODING ---")
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as geocoded,
        COUNT(CASE WHEN latitude IS NULL THEN 1 END) as missing
    FROM f7_employers_deduped
""")
g = cur.fetchone()
print("  Geocoded:    %s / %s (%.1f%%)" % (
    format(g['geocoded'], ','), format(g['total'], ','),
    g['geocoded'] / g['total'] * 100 if g['total'] else 0))
print("  Missing:     %s" % format(g['missing'], ','))

# Matching coverage
print("\n--- MATCHING COVERAGE ---")
for tbl, label in [("nlrb_participants", "NLRB->F7"), ("osha_matches", "OSHA->F7")]:
    try:
        cur.execute("SELECT COUNT(*) as total, COUNT(f7_employer_id) as matched FROM %s" % tbl)
        row = cur.fetchone()
        pct2 = row['matched'] / row['total'] * 100 if row['total'] else 0
        print("  %-20s %8s / %8s matched (%.1f%%)" % (
            label, format(row['matched'], ','), format(row['total'], ','), pct2))
    except:
        conn.rollback()

# State coverage
print("\n--- TOP 10 STATES BY WORKERS ---")
cur.execute("""
    SELECT state, COUNT(*) as employers, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
    GROUP BY state
    ORDER BY SUM(latest_unit_size) DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print("  %-5s %6s employers  %12s workers" % (
        row['state'], format(row['employers'], ','), format(row['workers'] or 0, ',')))

# Top industries
print("\n--- TOP 10 INDUSTRIES (NAICS 2-digit) ---")
cur.execute("""
    SELECT naics, COUNT(*) as employers, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE naics IS NOT NULL AND exclude_from_counts = FALSE
    GROUP BY naics
    ORDER BY SUM(latest_unit_size) DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print("  NAICS %-5s %6s employers  %12s workers" % (
        row['naics'], format(row['employers'], ','), format(row['workers'] or 0, ',')))

print("\n" + "=" * 70)
cur.close()
conn.close()
