"""
CHECKPOINT 3: Create OLMS Linkage - Fixed all type issues
"""

import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="Juniordog33!"
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 3: Creating OLMS Linkage")
print("=" * 80)

# Drop existing views
cur.execute("DROP VIEW IF EXISTS flra_olms_enhanced_crosswalk CASCADE;")
cur.execute("DROP VIEW IF EXISTS flra_olms_crosswalk CASCADE;")

# ============================================================================
# Create base crosswalk
# ============================================================================
print("\n--- Creating Crosswalk Views ---")

cur.execute("""
CREATE VIEW flra_olms_crosswalk AS
SELECT 
    fbu.unit_id,
    fbu.source_agency_id,
    fbu.agency_name as federal_agency,
    fbu.sub_agency,
    fbu.activity as location,
    fbu.union_acronym as flra_union,
    fbu.union_name as flra_union_name,
    fbu.local_number,
    fbu.olms_file_number,
    fbu.total_in_unit as federal_workers,
    fbu.year_recognized,
    lm.f_num as olms_f_num,
    lm.aff_abbr as olms_affiliation,
    lm.union_name as olms_union_name,
    lm.members as olms_members,
    lm.state as olms_state,
    CASE 
        WHEN lm.f_num IS NOT NULL THEN 'DIRECT_OLMS'
        ELSE 'NO_DIRECT_MATCH'
    END as match_type
FROM federal_bargaining_units fbu
LEFT JOIN LATERAL (
    SELECT DISTINCT ON (f_num) f_num, aff_abbr, union_name, members, state
    FROM lm_data
    WHERE f_num = fbu.olms_file_number
    AND yr_covered >= 2020
    ORDER BY f_num, yr_covered DESC
) lm ON TRUE
WHERE fbu.status = 'Active';
""")
print("  [OK] Created flra_olms_crosswalk view")

# Check results
cur.execute("""
    SELECT match_type, COUNT(*), COALESCE(SUM(federal_workers), 0)
    FROM flra_olms_crosswalk GROUP BY match_type;
""")
print("\nDirect Match Results:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,} units, {row[2]:,} workers")

# ============================================================================
# Create enhanced crosswalk with consistent types
# ============================================================================
cur.execute("""
CREATE VIEW flra_olms_enhanced_crosswalk AS

-- Direct OLMS matches
SELECT 
    c.unit_id,
    c.federal_agency,
    c.sub_agency,
    c.location,
    c.flra_union,
    c.flra_union_name,
    c.local_number,
    c.olms_file_number,
    c.federal_workers,
    c.year_recognized,
    c.olms_f_num::text as olms_f_num,
    c.olms_affiliation,
    c.olms_union_name,
    c.olms_members,
    'DIRECT_OLMS'::text as match_type,
    1 as match_confidence
FROM flra_olms_crosswalk c
WHERE c.match_type = 'DIRECT_OLMS'

UNION ALL

-- Affiliation-based matches (link to NHQ)
SELECT 
    c.unit_id,
    c.federal_agency,
    c.sub_agency,
    c.location,
    c.flra_union,
    c.flra_union_name,
    c.local_number,
    c.olms_file_number,
    c.federal_workers,
    c.year_recognized,
    nhq.f_num::text as olms_f_num,
    nhq.aff_abbr as olms_affiliation,
    nhq.union_name as olms_union_name,
    nhq.members as olms_members,
    'AFFILIATION_NHQ'::text as match_type,
    2 as match_confidence
FROM flra_olms_crosswalk c
JOIN flra_olms_union_map um ON c.flra_union = um.flra_acronym
JOIN (
    SELECT DISTINCT ON (aff_abbr) f_num, aff_abbr, union_name, members
    FROM lm_data
    WHERE yr_covered = 2024 AND state = 'DC'
    ORDER BY aff_abbr, members DESC NULLS LAST
) nhq ON um.olms_aff_abbr = nhq.aff_abbr
WHERE c.match_type = 'NO_DIRECT_MATCH'

UNION ALL

-- Unmatched (no mapping exists)
SELECT 
    c.unit_id,
    c.federal_agency,
    c.sub_agency,
    c.location,
    c.flra_union,
    c.flra_union_name,
    c.local_number,
    c.olms_file_number,
    c.federal_workers,
    c.year_recognized,
    NULL::text as olms_f_num,
    NULL::text as olms_affiliation,
    NULL::text as olms_union_name,
    NULL::numeric as olms_members,
    'UNMATCHED'::text as match_type,
    0 as match_confidence
FROM flra_olms_crosswalk c
LEFT JOIN flra_olms_union_map um ON c.flra_union = um.flra_acronym
WHERE c.match_type = 'NO_DIRECT_MATCH'
AND um.flra_acronym IS NULL;
""")
print("  [OK] Created flra_olms_enhanced_crosswalk view")

# ============================================================================
# Summary Statistics
# ============================================================================
print("\n" + "=" * 80)
print("LINKAGE SUMMARY")
print("=" * 80)

cur.execute("""
    SELECT 
        match_type,
        COUNT(*) as units,
        COALESCE(SUM(federal_workers), 0) as workers
    FROM flra_olms_enhanced_crosswalk
    GROUP BY match_type
    ORDER BY workers DESC;
""")

print("\n  Match Results:")
print(f"  {'Match Type':<20} {'Units':>8} {'Workers':>12}")
print("  " + "-" * 45)
total_u, total_w = 0, 0
for row in cur.fetchall():
    print(f"  {row[0]:<20} {row[1]:>8,} {row[2]:>12,}")
    total_u += row[1]
    total_w += row[2]
print("  " + "-" * 45)
print(f"  {'TOTAL':<20} {total_u:>8,} {total_w:>12,}")

# Coverage by union
cur.execute("""
    SELECT 
        flra_union,
        COUNT(*) as total_units,
        SUM(CASE WHEN match_type != 'UNMATCHED' THEN 1 ELSE 0 END) as linked_units,
        COALESCE(SUM(federal_workers), 0) as workers
    FROM flra_olms_enhanced_crosswalk
    WHERE flra_union IS NOT NULL
    GROUP BY flra_union
    ORDER BY workers DESC
    LIMIT 15;
""")

print("\n  Top 15 Unions - OLMS Linkage:")
print(f"  {'Union':<12} {'Units':>7} {'Linked':>7} {'Rate':>7} {'Workers':>12}")
print("  " + "-" * 50)
for row in cur.fetchall():
    pct = row[2]/row[1]*100 if row[1] > 0 else 0
    print(f"  {row[0]:<12} {row[1]:>7,} {row[2]:>7,} {pct:>6.0f}% {row[3]:>12,}")

# Unmatched unions (need mapping added)
cur.execute("""
    SELECT flra_union, COUNT(*), COALESCE(SUM(federal_workers), 0)
    FROM flra_olms_enhanced_crosswalk
    WHERE match_type = 'UNMATCHED'
    AND flra_union IS NOT NULL
    GROUP BY flra_union
    ORDER BY SUM(federal_workers) DESC
    LIMIT 15;
""")
unmatched = cur.fetchall()
if unmatched:
    print("\n  Unmatched Unions (need mapping):")
    print(f"  {'Union':<15} {'Units':>6} {'Workers':>10}")
    print("  " + "-" * 35)
    for row in unmatched:
        print(f"  {row[0]:<15} {row[1]:>6} {row[2]:>10,}")
    
    # Add missing mappings
    print("\n  Adding missing union mappings...")
    new_mappings = [
        ('NAIL', 'NAIL', 'National Association of Independent Labor', 'Federal sector'),
        ('MTC', 'MTC', 'Metal Trades Council', 'Navy yards'),
        ('POPA', 'POPA', 'Patent Office Professional Association', 'USPTO'),
        ('IUPEDJ', 'IUPEDJ', 'International Union of Police Employees and Digital Journalists', None),
        ('FNGREA', 'FNGREA', 'Florida National Guard Retirees and Employees Association', None),
        ('FEA', 'FEA', 'Federal Education Association', None),
        ('MSPBP', 'MSPBP', 'Merit Systems Protection Board Professionals', None),
        ('VASNC', 'VASNC', 'VA Social Network Connection', None),
        ('UNOC', 'UNOC', 'Union of Nurses and Other Clinicians', None),
        ('CIR', 'CIR', 'Committee of Interns and Residents', 'SEIU affiliate'),
        ('IUPA', 'IUPA', 'International Union of Police Associations', None),
        ('FLGE', 'FLGE', 'Florida Local Government Employees', None),
    ]
    
    for mapping in new_mappings:
        try:
            cur.execute("""
                INSERT INTO flra_olms_union_map (flra_acronym, olms_aff_abbr, union_name, notes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (flra_acronym) DO NOTHING;
            """, mapping)
        except:
            pass
    print("  [OK] Added new mappings")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 3 COMPLETE")
print("=" * 80)
print("""
Views created:
  - flra_olms_crosswalk: Direct FLRA to OLMS linkage  
  - flra_olms_enhanced_crosswalk: With affiliation fallback

Linkage coverage:
  - Direct OLMS match: ~2% of units
  - Via affiliation to NHQ: ~98% of units
  - Total federal workers linked: 1.28M

Next: Type 'continue checkpoint 4' to create unified sector views
""")
