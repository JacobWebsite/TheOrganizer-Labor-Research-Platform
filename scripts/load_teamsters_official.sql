-- Create reference table for official Teamsters locals data
-- This table stores scraped data from teamster.org/locals/

DROP TABLE IF EXISTS teamsters_official_locals CASCADE;

CREATE TABLE teamsters_official_locals (
    local_number INTEGER PRIMARY KEY,
    local_name VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(20),
    zip VARCHAR(20),
    phone VARCHAR(30),
    email VARCHAR(255),
    website VARCHAR(500),
    leadership_name VARCHAR(255),
    leadership_title VARCHAR(100),
    divisions TEXT,
    full_address TEXT,
    scraped_at TIMESTAMP DEFAULT NOW()
);

-- Load data from CSV (run after table creation)
-- Note: Use \copy in psql or import via pgAdmin/DBeaver
-- COPY teamsters_official_locals FROM 'teamsters_official_locals.csv' CSV HEADER;

-- Create comparison view
CREATE OR REPLACE VIEW v_teamsters_comparison AS
SELECT
    COALESCE(o.local_number, d.local_number::integer) as local_number,
    CASE
        WHEN o.local_number IS NULL THEN 'DB_ONLY'
        WHEN d.local_number IS NULL THEN 'WEB_ONLY'
        WHEN o.state != d.state THEN 'STATE_MISMATCH'
        WHEN UPPER(o.city) != UPPER(d.city) THEN 'CITY_MISMATCH'
        ELSE 'MATCH'
    END as match_status,
    o.local_name as official_name,
    d.union_name as db_name,
    o.city as official_city,
    d.city as db_city,
    o.state as official_state,
    d.state as db_state,
    o.phone as official_phone,
    o.email as official_email,
    o.website as official_website,
    o.leadership_name,
    o.leadership_title,
    o.divisions,
    d.f_num,
    d.members,
    d.yr_covered
FROM teamsters_official_locals o
FULL OUTER JOIN (
    SELECT f_num, union_name, local_number, city, state, members, yr_covered
    FROM unions_master
    WHERE aff_abbr = 'IBT'
    AND desig_name IN ('LU', 'LU   ')
    AND local_number IS NOT NULL
    AND local_number != '0'
) d ON o.local_number = d.local_number::integer
ORDER BY COALESCE(o.local_number, d.local_number::integer);

-- Summary statistics
SELECT
    'Total Official Locals' as metric,
    COUNT(*) as value
FROM teamsters_official_locals
UNION ALL
SELECT
    'Total DB IBT Locals (LU)' as metric,
    COUNT(*) as value
FROM unions_master
WHERE aff_abbr = 'IBT'
AND desig_name IN ('LU', 'LU   ')
AND local_number IS NOT NULL
AND local_number != '0'
UNION ALL
SELECT
    'Matched' as metric,
    COUNT(*) as value
FROM v_teamsters_comparison
WHERE match_status = 'MATCH'
UNION ALL
SELECT
    'City/State Discrepancies' as metric,
    COUNT(*) as value
FROM v_teamsters_comparison
WHERE match_status IN ('CITY_MISMATCH', 'STATE_MISMATCH')
UNION ALL
SELECT
    'DB Only (not on website)' as metric,
    COUNT(*) as value
FROM v_teamsters_comparison
WHERE match_status = 'DB_ONLY'
UNION ALL
SELECT
    'Website Only (missing from DB)' as metric,
    COUNT(*) as value
FROM v_teamsters_comparison
WHERE match_status = 'WEB_ONLY';
