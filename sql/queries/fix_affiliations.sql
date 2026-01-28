-- CHECKPOINT 2: Add Missing Affiliations to Crosswalk
-- Run with: psql -U postgres -d olms_multiyear -f fix_affiliations.sql

\echo '=== Adding missing affiliations ==='

-- Insert missing affiliations with proper names and sector codes
INSERT INTO crosswalk_affiliation_sector_map (aff_abbr, aff_name, sector_code) VALUES
-- Major missing unions (>100K members)
('CWA', 'Communications Workers of America', 'PRIVATE'),
('ACT', 'Associated Craft Technicians', 'PRIVATE'),
('SOC', 'Service Organization Counsel', 'OTHER'),
('TTD', 'Transportation Trades Department', 'OTHER'),
('BCTD', 'Building and Construction Trades Department', 'PRIVATE'),
('UNITHE', 'UNITE HERE', 'PRIVATE'),
('SAGAFTRA', 'Screen Actors Guild - American Federation of Television and Radio Artists', 'PRIVATE'),
('NFOP', 'National Fraternal Order of Police', 'PUBLIC_SECTOR'),
('BSOIW', 'International Brotherhood of Boilermakers', 'PRIVATE'),
('NNU', 'National Nurses United', 'PRIVATE'),
('AAA', 'American Arbitration Association', 'OTHER'),
('OPEIU', 'Office and Professional Employees International Union', 'PRIVATE'),
('WU', 'Workers United', 'PRIVATE'),
('IUJAT', 'International Union of Journeymen and Allied Trades', 'PRIVATE'),
('AFM', 'American Federation of Musicians', 'PRIVATE'),
('ILA', 'International Longshoremen''s Association', 'PRIVATE'),
('BCTGMI', 'Bakery Confectionery Tobacco Workers and Grain Millers International', 'PRIVATE'),
('ILWU', 'International Longshore and Warehouse Union', 'PRIVATE'),
('OPCM', 'Operative Plasterers and Cement Masons International', 'PRIVATE'),
('PTE', 'Professional and Technical Engineers', 'PRIVATE'),
('RWDSU', 'Retail Wholesale and Department Store Union', 'PRIVATE'),
('UWU', 'United Workers Union', 'PRIVATE'),
('PPPWU', 'Pacific Pulp Paper and Woodworkers Union', 'PRIVATE'),
('TCU/IAM', 'Transportation Communications Union/IAM', 'RAILROAD_AIRLINE_RLA'),
('AAUP', 'American Association of University Professors', 'PUBLIC_SECTOR'),
('IUEC', 'International Union of Elevator Constructors', 'PRIVATE'),
('USWU', 'United Service Workers Union', 'PRIVATE'),
('HFIA', 'Heat and Frost Insulators and Allied Workers', 'PRIVATE'),
('UE', 'United Electrical Workers', 'PRIVATE'),
('SIUNA', 'Seafarers International Union of North America', 'PRIVATE'),
('NPW', 'Newspaper and Periodical Workers', 'PRIVATE'),
('MEBA', 'Marine Engineers Beneficial Association', 'PRIVATE'),
('AFOSA', 'American Foreign Service Association', 'FEDERAL'),
('WPPW', 'Western Pulp and Paper Workers', 'PRIVATE'),
('SPFPA', 'Security Police and Fire Professionals of America', 'PRIVATE'),
('APA', 'Allied Pilots Association', 'RAILROAD_AIRLINE_RLA'),
('OCC', 'Office and Clerical Council', 'PRIVATE'),
('ANA', 'American Nurses Association', 'PRIVATE'),
('MTD', 'Metal Trades Department', 'PRIVATE'),
('FPA', 'Federation of Professional Athletes', 'PRIVATE'),
('UGSOA', 'United Government Security Officers of America', 'FEDERAL'),
('WGAW', 'Writers Guild of America West', 'PRIVATE'),
('IWW', 'Industrial Workers of the World', 'PRIVATE'),
('NOITU', 'National Organization of Industrial Trade Unions', 'PRIVATE'),
('NAPFE', 'National Alliance of Postal and Federal Employees', 'FEDERAL'),
('UNAP', 'United Nurses Associations of Pennsylvania', 'PRIVATE'),
('NSOI', 'National Staff Organization International', 'OTHER'),
('FAAM', 'Flight Attendants Association of America', 'RAILROAD_AIRLINE_RLA'),
('WGAE', 'Writers Guild of America East', 'PRIVATE'),
('AGMA', 'American Guild of Musical Artists', 'PRIVATE'),
('MTTD', 'Metal Trades and Textile Division', 'PRIVATE'),
('GUA', 'Guards Union of America', 'PRIVATE'),
('UFW', 'United Farm Workers', 'PRIVATE'),
('UAPD', 'Union of American Physicians and Dentists', 'PRIVATE'),
('PAFCA', 'Professional Air Traffic Controllers Association', 'FEDERAL'),
('IBU', 'Inlandboatmen''s Union', 'PRIVATE'),
('AGVA', 'American Guild of Variety Artists', 'PRIVATE')
ON CONFLICT (aff_abbr) DO UPDATE SET 
    aff_name = EXCLUDED.aff_name,
    sector_code = EXCLUDED.sector_code;

\echo ''
\echo '=== Verification: Count affiliations now ==='
SELECT COUNT(*) as total_affiliations FROM crosswalk_affiliation_sector_map;

\echo ''
\echo '=== Check CWA is now present ==='
SELECT * FROM crosswalk_affiliation_sector_map WHERE aff_abbr = 'CWA';

\echo ''
\echo '=== Recheck: Affiliations still missing (should be fewer) ==='
SELECT DISTINCT l.aff_abbr, COUNT(*) as union_count, SUM(l.members) as total_members
FROM lm_data l
LEFT JOIN crosswalk_affiliation_sector_map a ON l.aff_abbr = a.aff_abbr
WHERE l.yr_covered = 2024 AND l.aff_abbr IS NOT NULL AND a.aff_abbr IS NULL
GROUP BY l.aff_abbr
ORDER BY total_members DESC NULLS LAST
LIMIT 20;

\echo ''
\echo '=== Recheck: F-7 employers without affiliation ==='
-- Need to refresh the view first since it depends on the mapping
SELECT COUNT(*) as total_employers,
       SUM(CASE WHEN affiliation IS NULL THEN 1 ELSE 0 END) as no_affiliation,
       ROUND(100.0 * SUM(CASE WHEN affiliation IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as pct_no_match
FROM v_employer_search;
