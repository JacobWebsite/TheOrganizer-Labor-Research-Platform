-- ============================================================
-- Union Membership Deduplication Schema
-- ============================================================
-- Generated: January 23, 2025
-- Database: olms_multiyear (PostgreSQL)
-- 
-- This schema provides deduplicated union membership counts that align
-- with BLS benchmark of 14.3 million union members (2024).
--
-- Raw LM data reports 70.1M members due to:
--   1. Hierarchy double-counting (federation + international + local)
--   2. Multi-employer bargaining (same unit counted per employer)
--   3. Data quality issues (erroneous entries)
--
-- The union_hierarchy table flags which unions should be counted.
-- ============================================================

-- ============================================================
-- CORE TABLE: union_hierarchy
-- ============================================================
-- Key columns:
--   f_num           - File number (primary key)
--   hierarchy_level - FEDERATION, INTERNATIONAL, INTERMEDIATE, LOCAL
--   count_members   - TRUE if this union's members should be counted
--   parent_fnum     - f_num of parent union (for locals)
--   count_reason    - Explanation of why counted/not counted

-- ============================================================
-- VIEW: v_union_members_deduplicated
-- ============================================================
-- Main view joining hierarchy with LM data and unions_master

DROP VIEW IF EXISTS v_union_members_deduplicated CASCADE;

CREATE VIEW v_union_members_deduplicated AS
SELECT 
    h.f_num,
    h.union_name,
    h.aff_abbr,
    h.hierarchy_level,
    h.parent_fnum,
    h.parent_name,
    h.count_members,
    h.count_reason,
    h.members_2024 as members,
    COALESCE(um.sector, 'UNKNOWN') as sector,
    um.f7_employer_count,
    um.f7_total_workers,
    um.has_f7_employers,
    l.ttl_assets,
    l.ttl_receipts,
    l.ttl_disbursements,
    l.city,
    l.state
FROM union_hierarchy h
LEFT JOIN unions_master um ON h.f_num = um.f_num
LEFT JOIN lm_data l ON h.f_num = l.f_num AND l.yr_covered = 2024;

-- ============================================================
-- VIEW: v_union_members_counted
-- ============================================================
-- PRIMARY VIEW - Only unions that should be counted (for totals)
-- USE THIS VIEW for membership statistics

DROP VIEW IF EXISTS v_union_members_counted CASCADE;

CREATE VIEW v_union_members_counted AS
SELECT * FROM v_union_members_deduplicated
WHERE count_members = TRUE;

-- ============================================================
-- VIEW: v_hierarchy_summary
-- ============================================================
-- Summary by hierarchy level

DROP VIEW IF EXISTS v_hierarchy_summary CASCADE;

CREATE VIEW v_hierarchy_summary AS
SELECT 
    hierarchy_level,
    COUNT(*) as union_count,
    SUM(members) as total_members,
    SUM(CASE WHEN count_members THEN members ELSE 0 END) as counted_members,
    SUM(CASE WHEN count_members THEN 1 ELSE 0 END) as counted_unions
FROM v_union_members_deduplicated
GROUP BY hierarchy_level
ORDER BY 
    CASE hierarchy_level
        WHEN 'FEDERATION' THEN 1
        WHEN 'INTERNATIONAL' THEN 2
        WHEN 'INTERMEDIATE' THEN 3
        WHEN 'LOCAL' THEN 4
    END;

-- ============================================================
-- VIEW: v_membership_by_sector
-- ============================================================
-- Membership totals by sector

DROP VIEW IF EXISTS v_membership_by_sector CASCADE;

CREATE VIEW v_membership_by_sector AS
SELECT 
    sector,
    COUNT(*) as union_count,
    SUM(members) as total_members,
    SUM(CASE WHEN count_members THEN members ELSE 0 END) as counted_members,
    SUM(f7_employer_count) as total_employers,
    SUM(f7_total_workers) as total_workers_covered
FROM v_union_members_deduplicated
GROUP BY sector
ORDER BY counted_members DESC;

-- ============================================================
-- VIEW: v_membership_by_affiliation
-- ============================================================
-- Membership by union affiliation

DROP VIEW IF EXISTS v_membership_by_affiliation CASCADE;

CREATE VIEW v_membership_by_affiliation AS
SELECT 
    aff_abbr,
    COUNT(*) as total_filings,
    SUM(CASE WHEN hierarchy_level = 'INTERNATIONAL' THEN 1 ELSE 0 END) as internationals,
    SUM(CASE WHEN hierarchy_level = 'LOCAL' THEN 1 ELSE 0 END) as locals,
    SUM(members) as reported_members,
    SUM(CASE WHEN count_members THEN members ELSE 0 END) as counted_members,
    ROUND(100.0 * SUM(CASE WHEN count_members THEN members ELSE 0 END) / 
          NULLIF(SUM(members), 0), 1) as count_pct
FROM v_union_members_deduplicated
GROUP BY aff_abbr
ORDER BY counted_members DESC;

-- ============================================================
-- VIEW: v_membership_by_state
-- ============================================================
-- Membership totals by state (counted only)

DROP VIEW IF EXISTS v_membership_by_state CASCADE;

CREATE VIEW v_membership_by_state AS
SELECT 
    state,
    COUNT(*) as union_count,
    SUM(members) as total_members,
    SUM(f7_employer_count) as employer_count
FROM v_union_members_counted
WHERE state IS NOT NULL
GROUP BY state
ORDER BY total_members DESC;

-- ============================================================
-- VIEW: v_top_unions_by_membership
-- ============================================================
-- Top 100 unions by counted membership

DROP VIEW IF EXISTS v_top_unions_by_membership CASCADE;

CREATE VIEW v_top_unions_by_membership AS
SELECT 
    f_num,
    union_name,
    aff_abbr,
    hierarchy_level,
    members,
    sector,
    f7_employer_count,
    state
FROM v_union_members_counted
ORDER BY members DESC
LIMIT 100;

-- ============================================================
-- VIEW: v_deduplication_comparison
-- ============================================================
-- Compare raw vs deduplicated vs BLS benchmark

DROP VIEW IF EXISTS v_deduplication_comparison CASCADE;

CREATE VIEW v_deduplication_comparison AS
WITH raw_totals AS (
    SELECT 
        'Raw LM Data' as source,
        COUNT(*) as filings,
        SUM(members) as total_members
    FROM lm_data
    WHERE yr_covered = 2024 AND members > 0
),
deduped_totals AS (
    SELECT 
        'Deduplicated' as source,
        COUNT(*) as filings,
        SUM(members) as total_members
    FROM v_union_members_counted
),
bls_benchmark AS (
    SELECT 
        'BLS Benchmark' as source,
        NULL::bigint as filings,
        14300000 as total_members
)
SELECT * FROM raw_totals
UNION ALL SELECT * FROM deduped_totals
UNION ALL SELECT * FROM bls_benchmark;

-- ============================================================
-- EXAMPLE QUERIES
-- ============================================================

-- Get deduplicated total membership:
-- SELECT SUM(members) FROM v_union_members_counted;
-- Result: ~14,507,549

-- Get membership by major union:
-- SELECT * FROM v_union_members_counted ORDER BY members DESC LIMIT 20;

-- Compare raw vs deduplicated:
-- SELECT * FROM v_deduplication_comparison;

-- Get sector breakdown:
-- SELECT * FROM v_membership_by_sector;

-- Check hierarchy summary:
-- SELECT * FROM v_hierarchy_summary;

-- Find a specific union's status:
-- SELECT f_num, union_name, hierarchy_level, count_members, count_reason
-- FROM union_hierarchy WHERE f_num = '137';  -- SEIU
