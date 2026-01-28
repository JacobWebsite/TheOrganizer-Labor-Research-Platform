-- CHECKPOINT 3A: Add text-based affiliation parsing to v_employer_search
-- This fixes the 31.5% of F-7 employers without file numbers
-- Run with: psql -U postgres -d olms_multiyear -f fix_employer_view_v2.sql

\echo '=== Recreating v_employer_search with text-based affiliation fallback ==='

DROP VIEW IF EXISTS v_employer_search CASCADE;

CREATE VIEW v_employer_search AS
SELECT 
    e.employer_id,
    e.employer_name,
    e.city,
    e.state,
    e.street,
    e.zip,
    e.naics,
    e.latest_unit_size as bargaining_unit_size,
    e.latest_notice_date,
    e.filing_count,
    e.healthcare_related,
    e.latitude,
    e.longitude,
    e.geocode_quality,
    e.latest_union_fnum as union_file_number,
    e.latest_union_name as union_name_f7,
    l.union_name as union_name_lm,
    -- Use LM affiliation if available, otherwise parse from F-7 union name text
    COALESCE(l.aff_abbr, 
        CASE 
            WHEN e.latest_union_name ILIKE '%SEIU%' OR e.latest_union_name ILIKE '%SERVICE EMPLOYEE%' THEN 'SEIU'
            WHEN e.latest_union_name ILIKE '%TEAMSTER%' OR e.latest_union_name ILIKE 'IBT-%' OR e.latest_union_name ILIKE 'IBT %' THEN 'IBT'
            WHEN e.latest_union_name ILIKE '%UFCW%' OR e.latest_union_name ILIKE '%FOOD%COMMERCIAL%' THEN 'UFCW'
            WHEN e.latest_union_name ILIKE '%AFSCME%' OR e.latest_union_name ILIKE '%STATE%COUNTY%MUNICIPAL%' THEN 'AFSCME'
            WHEN e.latest_union_name ILIKE '%UAW%' OR e.latest_union_name ILIKE '%AUTO WORKER%' OR e.latest_union_name ILIKE '%AUTOMOBILE%' THEN 'UAW'
            WHEN e.latest_union_name ILIKE '%CWA%' OR e.latest_union_name ILIKE '%COMMUNICATION%WORKER%' THEN 'CWA'
            WHEN e.latest_union_name ILIKE '%IBEW%' OR e.latest_union_name ILIKE '%ELECTRICAL WORKER%' THEN 'IBEW'
            WHEN e.latest_union_name ILIKE '%USW%' OR e.latest_union_name ILIKE '%STEELWORKER%' OR e.latest_union_name ILIKE '%UNITED STEEL%' THEN 'USW'
            WHEN e.latest_union_name ILIKE '%OPERATING ENGINEER%' OR e.latest_union_name ILIKE 'IUOE%' THEN 'IUOE'
            WHEN e.latest_union_name ILIKE '%SAG%' OR e.latest_union_name ILIKE '%AFTRA%' OR e.latest_union_name ILIKE '%SCREEN ACTOR%' THEN 'SAGAFTRA'
            WHEN e.latest_union_name ILIKE '%APWU%' OR e.latest_union_name ILIKE '%POSTAL WORKER%' THEN 'APWU'
            WHEN e.latest_union_name ILIKE '%AFGE%' OR e.latest_union_name ILIKE '%GOVERNMENT EMPLOYEE%' THEN 'AFGE'
            WHEN e.latest_union_name ILIKE '%UNITE HERE%' OR e.latest_union_name ILIKE '%HOTEL%RESTAURANT%' THEN 'UNITHE'
            WHEN e.latest_union_name ILIKE '%NURSE%' OR e.latest_union_name ILIKE '%NNU%' THEN 'NNU'
            WHEN e.latest_union_name ILIKE '%CARPENTER%' OR e.latest_union_name ILIKE '%CJA%' OR e.latest_union_name ILIKE '%UBC%' THEN 'CJA'
            WHEN e.latest_union_name ILIKE '%LABORER%' OR e.latest_union_name ILIKE '%LIUNA%' THEN 'LIUNA'
            WHEN e.latest_union_name ILIKE '%MACHINIST%' OR e.latest_union_name ILIKE 'IAM%' OR e.latest_union_name ILIKE 'IAMAW%' THEN 'IAM'
            WHEN e.latest_union_name ILIKE '%PLUMBER%' OR e.latest_union_name ILIKE '%PIPEFITTER%' THEN 'PPF'
            WHEN e.latest_union_name ILIKE '%AFT%' OR e.latest_union_name ILIKE '%TEACHER%FED%' THEN 'AFT'
            WHEN e.latest_union_name ILIKE '%NEA%' OR e.latest_union_name ILIKE '%EDUCATION ASSOC%' THEN 'NEA'
            WHEN e.latest_union_name ILIKE '%FIREFIGHTER%' OR e.latest_union_name ILIKE '%IAFF%' THEN 'IAFF'
            WHEN e.latest_union_name ILIKE '%OPEIU%' OR e.latest_union_name ILIKE '%OFFICE%PROFESSIONAL%' THEN 'OPEIU'
            WHEN e.latest_union_name ILIKE '%IATSE%' OR e.latest_union_name ILIKE '%THEATRICAL STAGE%' THEN 'IATSE'
            WHEN e.latest_union_name ILIKE '%ILWU%' OR e.latest_union_name ILIKE '%LONGSHORE%WAREHOUSE%' THEN 'ILWU'
            WHEN e.latest_union_name ILIKE '%ILA%' OR e.latest_union_name ILIKE '%LONGSHOREMEN%ASS%' THEN 'ILA'
            WHEN e.latest_union_name ILIKE '%SMART%' OR e.latest_union_name ILIKE '%SHEET METAL%' THEN 'SMART'
            WHEN e.latest_union_name ILIKE '%LETTER CARRIER%' OR e.latest_union_name ILIKE '%NALC%' THEN 'NALC'
            WHEN e.latest_union_name ILIKE '%WRITERS GUILD%' OR e.latest_union_name ILIKE '%WGA%' THEN 'WGAW'
            WHEN e.latest_union_name ILIKE '%BAKERY%' OR e.latest_union_name ILIKE '%BCTGM%' THEN 'BCTGMI'
            WHEN e.latest_union_name ILIKE '%BOILERMAKER%' THEN 'BSOIW'
            ELSE NULL
        END
    ) as affiliation,
    a.aff_name as affiliation_name
FROM f7_employers e
LEFT JOIN lm_data l ON e.latest_union_fnum::text = l.f_num AND l.yr_covered = 2024
LEFT JOIN crosswalk_affiliation_sector_map a ON 
    COALESCE(l.aff_abbr, 
        CASE 
            WHEN e.latest_union_name ILIKE '%SEIU%' OR e.latest_union_name ILIKE '%SERVICE EMPLOYEE%' THEN 'SEIU'
            WHEN e.latest_union_name ILIKE '%TEAMSTER%' OR e.latest_union_name ILIKE 'IBT-%' OR e.latest_union_name ILIKE 'IBT %' THEN 'IBT'
            WHEN e.latest_union_name ILIKE '%UFCW%' OR e.latest_union_name ILIKE '%FOOD%COMMERCIAL%' THEN 'UFCW'
            WHEN e.latest_union_name ILIKE '%AFSCME%' OR e.latest_union_name ILIKE '%STATE%COUNTY%MUNICIPAL%' THEN 'AFSCME'
            WHEN e.latest_union_name ILIKE '%UAW%' OR e.latest_union_name ILIKE '%AUTO WORKER%' OR e.latest_union_name ILIKE '%AUTOMOBILE%' THEN 'UAW'
            WHEN e.latest_union_name ILIKE '%CWA%' OR e.latest_union_name ILIKE '%COMMUNICATION%WORKER%' THEN 'CWA'
            WHEN e.latest_union_name ILIKE '%IBEW%' OR e.latest_union_name ILIKE '%ELECTRICAL WORKER%' THEN 'IBEW'
            WHEN e.latest_union_name ILIKE '%USW%' OR e.latest_union_name ILIKE '%STEELWORKER%' OR e.latest_union_name ILIKE '%UNITED STEEL%' THEN 'USW'
            WHEN e.latest_union_name ILIKE '%OPERATING ENGINEER%' OR e.latest_union_name ILIKE 'IUOE%' THEN 'IUOE'
            WHEN e.latest_union_name ILIKE '%SAG%' OR e.latest_union_name ILIKE '%AFTRA%' OR e.latest_union_name ILIKE '%SCREEN ACTOR%' THEN 'SAGAFTRA'
            WHEN e.latest_union_name ILIKE '%APWU%' OR e.latest_union_name ILIKE '%POSTAL WORKER%' THEN 'APWU'
            WHEN e.latest_union_name ILIKE '%AFGE%' OR e.latest_union_name ILIKE '%GOVERNMENT EMPLOYEE%' THEN 'AFGE'
            WHEN e.latest_union_name ILIKE '%UNITE HERE%' OR e.latest_union_name ILIKE '%HOTEL%RESTAURANT%' THEN 'UNITHE'
            WHEN e.latest_union_name ILIKE '%NURSE%' OR e.latest_union_name ILIKE '%NNU%' THEN 'NNU'
            WHEN e.latest_union_name ILIKE '%CARPENTER%' OR e.latest_union_name ILIKE '%CJA%' OR e.latest_union_name ILIKE '%UBC%' THEN 'CJA'
            WHEN e.latest_union_name ILIKE '%LABORER%' OR e.latest_union_name ILIKE '%LIUNA%' THEN 'LIUNA'
            WHEN e.latest_union_name ILIKE '%MACHINIST%' OR e.latest_union_name ILIKE 'IAM%' OR e.latest_union_name ILIKE 'IAMAW%' THEN 'IAM'
            WHEN e.latest_union_name ILIKE '%PLUMBER%' OR e.latest_union_name ILIKE '%PIPEFITTER%' THEN 'PPF'
            WHEN e.latest_union_name ILIKE '%AFT%' OR e.latest_union_name ILIKE '%TEACHER%FED%' THEN 'AFT'
            WHEN e.latest_union_name ILIKE '%NEA%' OR e.latest_union_name ILIKE '%EDUCATION ASSOC%' THEN 'NEA'
            WHEN e.latest_union_name ILIKE '%FIREFIGHTER%' OR e.latest_union_name ILIKE '%IAFF%' THEN 'IAFF'
            WHEN e.latest_union_name ILIKE '%OPEIU%' OR e.latest_union_name ILIKE '%OFFICE%PROFESSIONAL%' THEN 'OPEIU'
            WHEN e.latest_union_name ILIKE '%IATSE%' OR e.latest_union_name ILIKE '%THEATRICAL STAGE%' THEN 'IATSE'
            WHEN e.latest_union_name ILIKE '%ILWU%' OR e.latest_union_name ILIKE '%LONGSHORE%WAREHOUSE%' THEN 'ILWU'
            WHEN e.latest_union_name ILIKE '%ILA%' OR e.latest_union_name ILIKE '%LONGSHOREMEN%ASS%' THEN 'ILA'
            WHEN e.latest_union_name ILIKE '%SMART%' OR e.latest_union_name ILIKE '%SHEET METAL%' THEN 'SMART'
            WHEN e.latest_union_name ILIKE '%LETTER CARRIER%' OR e.latest_union_name ILIKE '%NALC%' THEN 'NALC'
            WHEN e.latest_union_name ILIKE '%WRITERS GUILD%' OR e.latest_union_name ILIKE '%WGA%' THEN 'WGAW'
            WHEN e.latest_union_name ILIKE '%BAKERY%' OR e.latest_union_name ILIKE '%BCTGM%' THEN 'BCTGMI'
            WHEN e.latest_union_name ILIKE '%BOILERMAKER%' THEN 'BSOIW'
            ELSE NULL
        END
    ) = a.aff_abbr;

-- Create indexes for performance
DROP INDEX IF EXISTS idx_employer_search_name;
DROP INDEX IF EXISTS idx_employer_search_state;
DROP INDEX IF EXISTS idx_employer_search_affiliation;

CREATE INDEX idx_employer_search_name ON f7_employers (LOWER(employer_name));
CREATE INDEX idx_employer_search_state ON f7_employers (state);

\echo ''
\echo '=== Verification: Affiliation match rates after text parsing ==='
SELECT 
    COUNT(*) as total_employers,
    SUM(CASE WHEN affiliation IS NOT NULL THEN 1 ELSE 0 END) as has_affiliation,
    SUM(CASE WHEN affiliation IS NULL THEN 1 ELSE 0 END) as no_affiliation,
    ROUND(100.0 * SUM(CASE WHEN affiliation IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as pct_matched
FROM v_employer_search;

\echo ''
\echo '=== Top affiliations after text parsing ==='
SELECT affiliation, COUNT(*) as employer_count
FROM v_employer_search
WHERE affiliation IS NOT NULL
GROUP BY affiliation
ORDER BY employer_count DESC
LIMIT 20;

\echo ''
\echo '=== Sample employers that NOW have affiliations (were NULL before) ==='
SELECT employer_name, city, state, union_name_f7, affiliation, affiliation_name
FROM v_employer_search
WHERE affiliation IS NOT NULL AND union_file_number IS NULL
ORDER BY bargaining_unit_size DESC NULLS LAST
LIMIT 15;
