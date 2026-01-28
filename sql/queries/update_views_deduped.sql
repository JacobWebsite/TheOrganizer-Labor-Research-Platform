-- CHECKPOINT 4B: Update views to use deduplicated F-7 table
-- Run with: psql -U postgres -d olms_multiyear -f update_views_deduped.sql

\echo '=== Updating v_employer_search to use deduplicated table ==='

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
            WHEN e.latest_union_name ILIKE '%WORKERS UNITED%' THEN 'WU'
            ELSE NULL
        END
    ) as affiliation,
    a.aff_name as affiliation_name
FROM f7_employers_deduped e  -- NOW USING DEDUPLICATED TABLE
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
            WHEN e.latest_union_name ILIKE '%WORKERS UNITED%' THEN 'WU'
            ELSE NULL
        END
    ) = a.aff_abbr;

\echo ''
\echo '=== Updating v_union_local_search to use deduplicated table ==='

DROP VIEW IF EXISTS v_union_local_search CASCADE;

CREATE VIEW v_union_local_search AS
SELECT 
    l.f_num as file_number,
    l.union_name,
    l.aff_abbr as affiliation,
    a.aff_name as affiliation_name,
    CASE 
        WHEN l.desig_num IS NOT NULL AND l.desig_num != '' 
        THEN COALESCE(l.aff_abbr, '') || ' ' || COALESCE(TRIM(l.desig_name), 'Local') || ' ' || TRIM(l.desig_num)
        ELSE l.union_name
    END as local_display_name,
    TRIM(l.desig_name) as desig_name,
    TRIM(l.desig_num) as local_number,
    l.city,
    l.state,
    l.members,
    l.ttl_assets as total_assets,
    l.ttl_receipts as total_receipts,
    l.ttl_disbursements as total_disbursements,
    l.yr_covered as fiscal_year,
    COALESCE(f7.employer_count, 0) as f7_employer_count,
    COALESCE(f7.total_workers, 0) as f7_total_workers
FROM lm_data l
LEFT JOIN crosswalk_affiliation_sector_map a ON l.aff_abbr = a.aff_abbr
LEFT JOIN (
    SELECT 
        latest_union_fnum,
        COUNT(*) as employer_count,
        SUM(latest_unit_size) as total_workers
    FROM f7_employers_deduped  -- NOW USING DEDUPLICATED TABLE
    GROUP BY latest_union_fnum
) f7 ON l.f_num = f7.latest_union_fnum::text
WHERE l.yr_covered = 2024;

\echo ''
\echo '=== Updating v_affiliation_summary to use deduplicated table ==='

DROP VIEW IF EXISTS v_affiliation_summary CASCADE;

CREATE VIEW v_affiliation_summary AS
SELECT 
    a.aff_abbr as affiliation,
    a.aff_name as affiliation_name,
    COALESCE(lm.local_count, 0) as local_count,
    COALESCE(lm.total_members, 0) as total_members,
    COALESCE(lm.total_assets, 0) as total_assets,
    COALESCE(lm.total_receipts, 0) as total_receipts,
    COALESCE(f7.employer_count, 0) as f7_employer_count,
    COALESCE(f7.total_workers, 0) as f7_total_workers
FROM crosswalk_affiliation_sector_map a
LEFT JOIN (
    SELECT 
        aff_abbr,
        COUNT(*) as local_count,
        SUM(members) as total_members,
        SUM(ttl_assets) as total_assets,
        SUM(ttl_receipts) as total_receipts
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY aff_abbr
) lm ON a.aff_abbr = lm.aff_abbr
LEFT JOIN (
    SELECT 
        COALESCE(l.aff_abbr, 
            CASE 
                WHEN e.latest_union_name ILIKE '%SEIU%' OR e.latest_union_name ILIKE '%SERVICE EMPLOYEE%' THEN 'SEIU'
                WHEN e.latest_union_name ILIKE '%TEAMSTER%' OR e.latest_union_name ILIKE 'IBT-%' THEN 'IBT'
                WHEN e.latest_union_name ILIKE '%UFCW%' THEN 'UFCW'
                WHEN e.latest_union_name ILIKE '%USW%' OR e.latest_union_name ILIKE '%STEELWORKER%' THEN 'USW'
                WHEN e.latest_union_name ILIKE '%IUOE%' OR e.latest_union_name ILIKE '%OPERATING ENGINEER%' THEN 'IUOE'
                WHEN e.latest_union_name ILIKE '%IAM%' OR e.latest_union_name ILIKE '%MACHINIST%' THEN 'IAM'
                WHEN e.latest_union_name ILIKE '%CWA%' OR e.latest_union_name ILIKE '%COMMUNICATION%' THEN 'CWA'
                WHEN e.latest_union_name ILIKE '%IBEW%' THEN 'IBEW'
                WHEN e.latest_union_name ILIKE '%UAW%' THEN 'UAW'
                WHEN e.latest_union_name ILIKE '%WORKERS UNITED%' THEN 'WU'
                ELSE NULL
            END
        ) as aff_abbr,
        COUNT(*) as employer_count,
        SUM(e.latest_unit_size) as total_workers
    FROM f7_employers_deduped e  -- NOW USING DEDUPLICATED TABLE
    LEFT JOIN lm_data l ON e.latest_union_fnum::text = l.f_num AND l.yr_covered = 2024
    GROUP BY 1
) f7 ON a.aff_abbr = f7.aff_abbr
ORDER BY total_members DESC NULLS LAST;

\echo ''
\echo '=== Verification: Employer count after deduplication ==='
SELECT COUNT(*) as total_employers FROM v_employer_search;

\echo ''
\echo '=== Verification: Top affiliations with F-7 counts ==='
SELECT affiliation, affiliation_name, local_count, f7_employer_count, f7_total_workers
FROM v_affiliation_summary
WHERE f7_employer_count > 0
ORDER BY f7_employer_count DESC
LIMIT 15;

\echo ''
\echo '=== Verification: Sample SEIU locals with updated F-7 counts ==='
SELECT file_number, local_display_name, local_number, city, state, members, f7_employer_count
FROM v_union_local_search
WHERE affiliation = 'SEIU' AND f7_employer_count > 0
ORDER BY f7_employer_count DESC
LIMIT 10;
