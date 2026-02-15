"""
Create and populate union organization level classification table
For membership deduplication
"""

import psycopg2
import os

from db_config import get_connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

SCHEMA_SQL = """
-- ============================================================================
-- MEMBERSHIP DEDUPLICATION SCHEMA
-- ============================================================================

DROP VIEW IF EXISTS v_deduplicated_membership CASCADE;
DROP VIEW IF EXISTS v_dedup_summary_by_affiliation CASCADE;
DROP VIEW IF EXISTS v_dedup_summary_by_level CASCADE;
DROP TABLE IF EXISTS union_organization_level CASCADE;

-- Organization level classification
CREATE TABLE union_organization_level (
    f_num VARCHAR(20) PRIMARY KEY,
    org_level VARCHAR(30) NOT NULL,
    is_leaf_level BOOLEAN NOT NULL DEFAULT FALSE,
    dedup_category VARCHAR(50),
    classification_rule TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_uol_org_level ON union_organization_level(org_level);
CREATE INDEX idx_uol_is_leaf ON union_organization_level(is_leaf_level);
CREATE INDEX idx_uol_category ON union_organization_level(dedup_category);

COMMENT ON TABLE union_organization_level IS 'Classification of unions for membership deduplication';
COMMENT ON COLUMN union_organization_level.org_level IS 'federation, national, intermediate, local, specialized';
COMMENT ON COLUMN union_organization_level.is_leaf_level IS 'TRUE if members should be counted (not double-counted elsewhere)';
"""

CLASSIFICATION_SQL = """
-- ============================================================================
-- POPULATE CLASSIFICATION BASED ON ANALYSIS
-- ============================================================================

-- Clear existing
TRUNCATE union_organization_level;

-- 1. FEDERATIONS - Never count (members counted by constituent unions)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'federation', FALSE, 'federation', 'aff_abbr IN (AFLCIO, SOC, TTD)'
FROM lm_data
WHERE yr_covered = 2024
AND aff_abbr IN ('AFLCIO', 'SOC', 'TTD');

-- 2. NATIONAL HQ - Count only for teacher unions (AFT, NEA)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'national', TRUE, 'teacher_national', 'Teacher union NHQ - count (locals are duplicates)'
FROM lm_data
WHERE yr_covered = 2024
AND aff_abbr IN ('AFT', 'NEA')
AND TRIM(desig_name) = 'NHQ'
ON CONFLICT (f_num) DO NOTHING;

-- 3. TEACHER LOCALS/CHAPTERS - Don't count (duplicates of NHQ)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', FALSE, 'teacher_local_duplicate', 'Teacher local - members reported by NHQ'
FROM lm_data
WHERE yr_covered = 2024
AND aff_abbr IN ('AFT', 'NEA')
AND TRIM(desig_name) != 'NHQ'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 4. TRADITIONAL UNION NATIONAL HQ - Don't count
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'national', FALSE, 'traditional_national', 'National HQ - members counted by locals'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) = 'NHQ'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 5. JOINT/DISTRICT COUNCILS - Don't count (aggregates)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'intermediate', FALSE, 'council_aggregate', 'Joint/District Council - aggregates locals'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('JC', 'DC', 'JATC', 'JAC')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 6. CONFERENCE/STATE BODIES - Don't count (aggregates)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'intermediate', FALSE, 'state_conference_aggregate', 'State/Conference body - aggregates locals'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('CONF', 'COUNCIL', 'STATE', 'STC', 'MTC', 'SFED')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 7. LEADC UNITS (Leadership/Large locals that aggregate) - Don't count
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'intermediate', FALSE, 'leadc_aggregate', 'LEADC unit - typically aggregates'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) = 'LEADC'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 8. BCTC (Building Trades Councils) - Don't count (aggregates)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'intermediate', FALSE, 'bctc_aggregate', 'Building Trades Council - aggregates'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) = 'BCTC'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 9. LOCAL UNIONS (LU, LG, etc.) - COUNT (leaf level)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', TRUE, 'local_union', 'Local union - count members'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'SLG', 'DLG', 'LOCAL')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 10. BRANCHES - COUNT (typically leaf level)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', TRUE, 'branch', 'Branch - count members'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('BR', 'BRANCH', 'LBR', 'SLB')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 11. DIVISIONS - COUNT (typically leaf level for RLA unions)
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', TRUE, 'division', 'Division - count members'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('DIV', 'LDIV', 'DIST', 'D')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 12. CHAPTERS - Analyze by affiliation
-- ACT chapters are large aggregates, don't count
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', FALSE, 'act_chapter_aggregate', 'ACT Chapter - appears to aggregate'
FROM lm_data
WHERE yr_covered = 2024
AND aff_abbr = 'ACT'
AND TRIM(desig_name) IN ('CH', 'LCH', 'CAP')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- UAW chapters under CAP - need review
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', FALSE, 'uaw_cap_aggregate', 'UAW CAP - likely aggregate'
FROM lm_data
WHERE yr_covered = 2024
AND aff_abbr = 'UAW'
AND TRIM(desig_name) = 'CAP'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- Other chapters - count if small
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'local', 
    CASE WHEN COALESCE(members, 0) <= 10000 THEN TRUE ELSE FALSE END,
    CASE WHEN COALESCE(members, 0) <= 10000 THEN 'chapter_small' ELSE 'chapter_large_exclude' END,
    'Chapter - count if small'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('CH', 'LCH', 'CAP', 'ASSN')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 13. SPECIALIZED UNITS (SA, GCA, MEC, LEC) - Mixed
-- SA (System Adjustment) boards in railroad - count
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'specialized', TRUE, 'sa_board', 'System Adjustment board - count'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) = 'SA'
AND aff_abbr IN ('BLET', 'BMWE', 'BRS', 'SMART', 'TCU')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- MEC/LEC (Master/Local Executive Council) in airlines - intermediate
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'intermediate', FALSE, 'airline_council', 'Airline MEC/LEC - aggregate'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) IN ('MEC', 'LEC')
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- Other SA units - count if small
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'specialized',
    CASE WHEN COALESCE(members, 0) <= 10000 THEN TRUE ELSE FALSE END,
    CASE WHEN COALESCE(members, 0) <= 10000 THEN 'sa_small' ELSE 'sa_large_exclude' END,
    'SA unit - count if small'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) = 'SA'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- GCA (General Chairman's Assn) - intermediate
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'intermediate', FALSE, 'gca_aggregate', 'General Chairman Assn - aggregate'
FROM lm_data
WHERE yr_covered = 2024
AND TRIM(desig_name) = 'GCA'
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 14. NO DESIGNATION - Analyze by size
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 
    CASE 
        WHEN COALESCE(members, 0) > 100000 THEN 'national'
        WHEN COALESCE(members, 0) > 10000 THEN 'intermediate'
        ELSE 'local'
    END,
    CASE WHEN COALESCE(members, 0) <= 10000 THEN TRUE ELSE FALSE END,
    CASE 
        WHEN COALESCE(members, 0) > 100000 THEN 'no_desig_large_exclude'
        WHEN COALESCE(members, 0) > 10000 THEN 'no_desig_medium_exclude'
        ELSE 'no_desig_small_count'
    END,
    'No designation - size-based'
FROM lm_data
WHERE yr_covered = 2024
AND (TRIM(desig_name) = '' OR desig_name IS NULL)
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;

-- 15. REMAINING - Default rules
INSERT INTO union_organization_level (f_num, org_level, is_leaf_level, dedup_category, classification_rule)
SELECT DISTINCT f_num, 'other',
    CASE WHEN COALESCE(members, 0) <= 50000 THEN TRUE ELSE FALSE END,
    CASE WHEN COALESCE(members, 0) <= 50000 THEN 'other_small_count' ELSE 'other_large_exclude' END,
    'Remaining - size-based default'
FROM lm_data
WHERE yr_covered = 2024
AND f_num NOT IN (SELECT f_num FROM union_organization_level)
ON CONFLICT (f_num) DO NOTHING;
"""

VIEW_SQL = """
-- ============================================================================
-- DEDUPLICATION VIEWS
-- ============================================================================

-- Main deduplicated membership view
CREATE OR REPLACE VIEW v_deduplicated_membership AS
SELECT 
    l.f_num,
    l.union_name,
    l.aff_abbr,
    l.state,
    l.members as reported_members,
    ol.org_level,
    ol.is_leaf_level,
    ol.dedup_category,
    CASE WHEN ol.is_leaf_level THEN COALESCE(l.members, 0) ELSE 0 END as counted_members
FROM lm_data l
LEFT JOIN union_organization_level ol ON l.f_num = ol.f_num
WHERE l.yr_covered = 2024;

-- Summary by affiliation
CREATE OR REPLACE VIEW v_dedup_summary_by_affiliation AS
SELECT 
    aff_abbr,
    COUNT(*) as total_filings,
    SUM(reported_members) as total_reported,
    SUM(counted_members) as total_counted,
    SUM(CASE WHEN is_leaf_level THEN 1 ELSE 0 END) as leaf_orgs,
    ROUND(100.0 * SUM(counted_members) / NULLIF(SUM(reported_members), 0), 1) as pct_counted
FROM v_deduplicated_membership
GROUP BY aff_abbr
ORDER BY total_reported DESC;

-- Summary by organization level
CREATE OR REPLACE VIEW v_dedup_summary_by_level AS
SELECT 
    org_level,
    is_leaf_level,
    COUNT(*) as org_count,
    SUM(reported_members) as total_reported,
    SUM(counted_members) as total_counted
FROM v_deduplicated_membership
GROUP BY org_level, is_leaf_level
ORDER BY total_reported DESC;
"""

def main():
    print("="*60)
    print("CREATING DEDUPLICATION SCHEMA")
    print("="*60)
    
    conn = get_connection()
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("\n1. Creating schema...")
    cursor.execute(SCHEMA_SQL)
    print("   Done.")
    
    print("\n2. Populating classification rules...")
    cursor.execute(CLASSIFICATION_SQL)
    print("   Done.")
    
    print("\n3. Creating views...")
    cursor.execute(VIEW_SQL)
    print("   Done.")
    
    # Verification
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    cursor.execute("SELECT COUNT(*) FROM union_organization_level")
    print(f"\nClassified organizations: {cursor.fetchone()[0]:,}")
    
    cursor.execute("""
        SELECT org_level, is_leaf_level, COUNT(*), SUM(COALESCE(
            (SELECT members FROM lm_data WHERE lm_data.f_num = union_organization_level.f_num AND yr_covered = 2024 LIMIT 1), 0
        ))
        FROM union_organization_level
        GROUP BY org_level, is_leaf_level
        ORDER BY org_level, is_leaf_level
    """)
    print("\nBy organization level:")
    print(f"  {'Level':<15} {'Leaf?':<6} {'Count':>8} {'Members':>15}")
    for row in cursor.fetchall():
        print(f"  {row[0]:<15} {str(row[1]):<6} {row[2]:>8,} {row[3] or 0:>15,}")
    
    # Test the deduplicated view
    cursor.execute("""
        SELECT 
            SUM(reported_members) as total_reported,
            SUM(counted_members) as total_counted
        FROM v_deduplicated_membership
    """)
    row = cursor.fetchone()
    print(f"\nDeduplication result:")
    print(f"  Total reported: {row[0]:,}")
    print(f"  Total counted:  {row[1]:,}")
    print(f"  BLS target:     14,300,000")
    print(f"  Difference:     {row[1] - 14300000:+,}")
    
    # Top affiliations
    cursor.execute("""
        SELECT * FROM v_dedup_summary_by_affiliation
        LIMIT 15
    """)
    print(f"\nTop affiliations (deduplicated):")
    print(f"  {'Affil':<10} {'Filings':>8} {'Reported':>12} {'Counted':>12} {'Leaf':>6} {'%':>6}")
    for row in cursor.fetchall():
        print(f"  {row[0]:<10} {row[1]:>8,} {row[2] or 0:>12,} {row[3] or 0:>12,} {row[4]:>6,} {row[5] or 0:>6.1f}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
