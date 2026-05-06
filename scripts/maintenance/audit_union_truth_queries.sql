-- ============================================================
-- Union Explorer Audit — Layer 1 Truth Queries
-- ============================================================
-- Population-wide deterministic invariants for the Union Explorer
-- surface (api/routers/unions.py + frontend/src/features/union-explorer).
--
-- Hard-gate checks (gate=hard): block release if any row returned.
-- Advisory checks (gate=advisory): report only, do not block.
--
-- Each check block must follow this format so the runner can parse it:
--   -- @check: <snake_case_name>
--   -- @gate: hard | advisory
--   -- @description: <one-line>
--   -- @expect: zero rows | <expression>
--   -- @sql:
--   <multi-line SQL ending with semicolon>
--
-- Runner: scripts/maintenance/audit_union_layer1.py
-- Last updated: 2026-05-04
-- ============================================================


-- ------------------------------------------------------------
-- FK / orphan integrity
-- ------------------------------------------------------------

-- @check: parent_fnum_orphans
-- @gate: hard
-- @description: Every non-NULL unions_master.parent_fnum must reference an existing f_num
-- @expect: zero rows
-- @sql:
SELECT u1.f_num, u1.union_name, u1.parent_fnum
FROM unions_master u1
WHERE u1.parent_fnum IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM unions_master u2 WHERE u2.f_num = u1.parent_fnum)
LIMIT 100;


-- @check: lm_data_f_num_orphans
-- @gate: advisory
-- @description: lm_data rows whose f_num has no row in unions_master and is not in resolution_log
-- @expect: zero rows
-- @sql:
SELECT lm.f_num, COUNT(*) AS filings
FROM lm_data lm
LEFT JOIN unions_master um ON um.f_num = lm.f_num
LEFT JOIN union_fnum_resolution_log r ON r.orphan_fnum::text = lm.f_num
WHERE um.f_num IS NULL
  AND r.orphan_fnum IS NULL
GROUP BY lm.f_num
ORDER BY filings DESC
LIMIT 100;


-- @check: f7_employers_orphan_fnum
-- @gate: advisory
-- @description: f7_employers_deduped rows whose latest_union_fnum has no unions_master row and is not in resolution_log (NOTE: latest_union_fnum is INT, f_num is varchar)
-- @expect: zero rows
-- @sql:
SELECT e.latest_union_fnum, COUNT(*) AS employer_count
FROM f7_employers_deduped e
LEFT JOIN unions_master um ON um.f_num = e.latest_union_fnum::text
LEFT JOIN union_fnum_resolution_log r ON r.orphan_fnum = e.latest_union_fnum
WHERE e.latest_union_fnum IS NOT NULL
  AND um.f_num IS NULL
  AND r.orphan_fnum IS NULL
GROUP BY e.latest_union_fnum
ORDER BY employer_count DESC
LIMIT 100;


-- @check: ar_membership_rpt_id_orphans
-- @gate: hard
-- @description: ar_membership rows whose rpt_id has no row in lm_data
-- @expect: zero rows
-- @sql:
SELECT am.rpt_id, COUNT(*) AS membership_rows
FROM ar_membership am
WHERE NOT EXISTS (SELECT 1 FROM lm_data lm WHERE lm.rpt_id = am.rpt_id)
GROUP BY am.rpt_id
ORDER BY membership_rows DESC
LIMIT 100;


-- @check: ar_disbursements_total_rpt_id_orphans
-- @gate: hard
-- @description: ar_disbursements_total rows whose rpt_id has no row in lm_data
-- @expect: zero rows
-- @sql:
SELECT adt.rpt_id
FROM ar_disbursements_total adt
WHERE NOT EXISTS (SELECT 1 FROM lm_data lm WHERE lm.rpt_id = adt.rpt_id)
LIMIT 100;


-- ------------------------------------------------------------
-- Bug 1 regression guard — financial_trends overcount
-- ------------------------------------------------------------

-- @check: financial_trends_data_shape_sanity
-- @gate: hard
-- @description: Sanity check that the post-Bug-1-fix CTE formula produces equal totals to raw lm_data (must be an identity, since the CTE join is 1-to-1). NOT a code-regression guard for the endpoint -- a code regression that reverts api/routers/unions.py to the buggy LEFT JOIN would not be caught here. The actual regression catch lives at Layer 6 (see audit_union_layer6.py: SEIU Local 1 sentinel asserts assets ~$14.6M not $262M) and Layer 2 (per-union financial_trend_assets check). Codex 2026-05-05 review noted this limitation.
-- @expect: zero rows
-- @sql:
WITH members_per_rpt AS (
    SELECT rpt_id,
           SUM(number) FILTER (WHERE voting_eligibility = 'T') AS members
    FROM ar_membership
    GROUP BY rpt_id
),
endpoint_formula AS (
    SELECT lm.f_num, lm.yr_covered,
           SUM(COALESCE(lm.ttl_assets, 0)) AS endpoint_assets,
           SUM(COALESCE(lm.ttl_receipts, 0)) AS endpoint_receipts,
           SUM(COALESCE(lm.ttl_disbursements, 0)) AS endpoint_disbursements
    FROM lm_data lm
    LEFT JOIN members_per_rpt mp ON mp.rpt_id = lm.rpt_id
    GROUP BY lm.f_num, lm.yr_covered
),
truth AS (
    SELECT f_num, yr_covered,
           SUM(COALESCE(ttl_assets, 0)) AS truth_assets,
           SUM(COALESCE(ttl_receipts, 0)) AS truth_receipts,
           SUM(COALESCE(ttl_disbursements, 0)) AS truth_disbursements
    FROM lm_data
    GROUP BY f_num, yr_covered
)
SELECT e.f_num, e.yr_covered,
       e.endpoint_assets, t.truth_assets,
       e.endpoint_receipts, t.truth_receipts,
       e.endpoint_disbursements, t.truth_disbursements
FROM endpoint_formula e
JOIN truth t ON t.f_num = e.f_num AND t.yr_covered = e.yr_covered
WHERE e.endpoint_assets <> t.truth_assets
   OR e.endpoint_receipts <> t.truth_receipts
   OR e.endpoint_disbursements <> t.truth_disbursements
LIMIT 100;


-- ------------------------------------------------------------
-- LM-2 disbursement bucket math — 7 frontend buckets sum to ttl_disbursements ±1%
-- ------------------------------------------------------------

-- @check: lm2_disbursement_outlier_buckets
-- @gate: advisory
-- @description: Flag filings where any single frontend bucket exceeds 5x ttl_disbursements (parsing-bug indicator). NOTE: LM-2 ttl_disbursements is Statement A (cash-basis summary) and is NOT expected to equal SUM of itemized schedule lines — disbursement schedules can use different accounting bases. Strict reconciliation produces 92% false positives across 200K+ filings.
-- @expect: zero rows
-- @sql:
WITH buckets AS (
    SELECT lm.f_num, lm.yr_covered, lm.rpt_id,
           GREATEST(COALESCE(lm.ttl_disbursements, 0), 1) AS ttl,
           COALESCE(adt.representational, 0) AS representational,
           COALESCE(adt.political, 0) + COALESCE(adt.contributions, 0) AS political_lobbying,
           COALESCE(adt.to_officers, 0) + COALESCE(adt.to_employees, 0)
               + COALESCE(adt.direct_taxes, 0) + COALESCE(adt.withheld, 0) AS staff_officers,
           COALESCE(adt.benefits, 0) + COALESCE(adt.strike_benefits, 0)
               + COALESCE(adt.members, 0) AS member_benefits,
           COALESCE(adt.general_overhead, 0) + COALESCE(adt.union_administration, 0)
               + COALESCE(adt.supplies, 0) + COALESCE(adt.fees, 0)
               + COALESCE(adt.administration, 0) AS operations,
           COALESCE(adt.per_capita_tax, 0) + COALESCE(adt.affiliates, 0) AS affiliation_dues,
           COALESCE(adt.investments, 0) + COALESCE(adt.loans_made, 0)
               + COALESCE(adt.loans_payment, 0) + COALESCE(adt.other_disbursements, 0) AS financial
    FROM lm_data lm
    JOIN ar_disbursements_total adt ON adt.rpt_id = lm.rpt_id
    WHERE lm.ttl_disbursements > 10000
)
SELECT f_num, yr_covered, rpt_id, ttl,
       representational, political_lobbying, staff_officers,
       member_benefits, operations, affiliation_dues, financial,
       GREATEST(representational, political_lobbying, staff_officers,
                member_benefits, operations, affiliation_dues, financial) AS max_bucket
FROM buckets
WHERE GREATEST(representational, political_lobbying, staff_officers,
               member_benefits, operations, affiliation_dues, financial) > 5 * ttl
ORDER BY GREATEST(representational, political_lobbying, staff_officers,
                  member_benefits, operations, affiliation_dues, financial) / ttl DESC
LIMIT 100;


-- ------------------------------------------------------------
-- 30M-bug class — affiliation rollup must match v_union_members_counted
-- ------------------------------------------------------------

-- @check: national_endpoint_dedup_matches_canonical_view
-- @gate: hard
-- @description: /api/unions/national deduplicated_members per aff_abbr must match v_union_members_counted aggregation; protects against the 30M-bug class regressing
-- @expect: zero rows
-- @sql:
WITH endpoint_dedup AS (
    SELECT um.aff_abbr,
           SUM(CASE WHEN uh.count_members THEN um.members ELSE 0 END) AS endpoint_dedup_members
    FROM unions_master um
    LEFT JOIN union_hierarchy uh ON um.f_num = uh.f_num
    WHERE um.aff_abbr IS NOT NULL AND um.aff_abbr != ''
      AND um.aff_abbr NOT IN ('SOC')
    GROUP BY um.aff_abbr
),
canonical_dedup AS (
    SELECT aff_abbr,
           SUM(CASE WHEN count_members THEN members ELSE 0 END) AS canonical_dedup_members
    FROM v_union_members_counted
    WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
      AND aff_abbr NOT IN ('SOC')
    GROUP BY aff_abbr
)
SELECT e.aff_abbr,
       e.endpoint_dedup_members,
       c.canonical_dedup_members,
       e.endpoint_dedup_members - COALESCE(c.canonical_dedup_members, 0) AS delta
FROM endpoint_dedup e
LEFT JOIN canonical_dedup c ON c.aff_abbr = e.aff_abbr
WHERE COALESCE(e.endpoint_dedup_members, 0) <> COALESCE(c.canonical_dedup_members, 0)
ORDER BY ABS(e.endpoint_dedup_members - COALESCE(c.canonical_dedup_members, 0)) DESC
LIMIT 100;


-- @check: hierarchy_classifier_picks_dominant_row
-- @gate: hard
-- @description: For each affiliation, the union_hierarchy.count_members=TRUE row should be the dominant member-count row in unions_master. If a sibling has 10x more members AND the counted row has <100 members, the classifier likely picked the wrong row (e.g., CWA had counted_f=38750 with 43 members while f_num=188 had 682,324). This catches the same misclassification across CWA/AFSCME/IATSE/IBEW/USW/PPF/AFGE.
-- @expect: zero rows
-- @sql:
WITH counted AS (
    SELECT um.f_num, um.aff_abbr, um.members AS counted_members, um.union_name
    FROM unions_master um
    JOIN union_hierarchy uh ON uh.f_num = um.f_num
    WHERE uh.count_members = TRUE
      AND um.aff_abbr IS NOT NULL AND um.aff_abbr != ''
),
max_per_aff AS (
    SELECT aff_abbr, MAX(members) AS max_members
    FROM unions_master
    WHERE NOT is_likely_inactive
    GROUP BY aff_abbr
)
SELECT c.aff_abbr, c.f_num AS counted_f_num, c.counted_members,
       m.max_members,
       ROUND(m.max_members::numeric / NULLIF(c.counted_members, 0), 1) AS dominance_ratio
FROM counted c
JOIN max_per_aff m ON m.aff_abbr = c.aff_abbr
WHERE m.max_members >= c.counted_members * 10
  AND m.max_members >= 1000   -- ignore tiny affiliations where small absolute differences swing big ratios
  AND c.counted_members < (m.max_members / 10)
ORDER BY (m.max_members - c.counted_members) DESC
LIMIT 100;


-- @check: overview_canonical_total_sane
-- @gate: hard
-- @description: v_union_members_counted total (the canonical movement-wide member count) must be in a sane range (~10M-50M); guards against the view being silently broken
-- @expect: zero rows
-- @sql:
SELECT total
FROM (
    SELECT SUM(CASE WHEN count_members THEN members ELSE 0 END) AS total
    FROM v_union_members_counted
) sub
WHERE total < 10000000 OR total > 50000000;


-- ------------------------------------------------------------
-- SOC / federation-coalition exclusion across all browse surfaces
-- ------------------------------------------------------------

-- @check: soc_excluded_from_canonical_view
-- @gate: hard
-- @description: SOC must contribute zero counted members to the canonical view (it's a federation, not a union)
-- @expect: zero rows
-- @sql:
SELECT f_num, union_name, members, count_members
FROM v_union_members_counted
WHERE aff_abbr = 'SOC'
  AND count_members = TRUE
LIMIT 10;


-- @check: soc_inactive_filter_does_not_resurface
-- @gate: advisory
-- @description: SOC rows in unions_master must remain marked excluded (sanity: row count for SOC should not balloon over time)
-- @expect: zero rows
-- @sql:
SELECT COUNT(*) AS soc_row_count
FROM unions_master
WHERE aff_abbr = 'SOC'
HAVING COUNT(*) > 5;


-- ------------------------------------------------------------
-- Coverage metrics — advisory, just observed and reported
-- ------------------------------------------------------------

-- @check: coverage_lm2_filings
-- @gate: advisory
-- @description: % of unions_master with at least one lm_data filing (LEFT JOIN to distinct lm.f_num for speed)
-- @expect: report_only
-- @sql:
WITH lm_fnums AS (
    SELECT DISTINCT f_num FROM lm_data
)
SELECT
    COUNT(*) AS unions_total,
    COUNT(lf.f_num) AS unions_with_lm2,
    ROUND(100.0 * COUNT(lf.f_num) / NULLIF(COUNT(*), 0), 1) AS pct_with_lm2
FROM unions_master um
LEFT JOIN lm_fnums lf ON lf.f_num = um.f_num;


-- @check: coverage_f7_links
-- @gate: advisory
-- @description: % of unions_master with at least one f7_employers_deduped row pointing to it
-- @expect: report_only
-- @sql:
WITH f7_fnums AS (
    SELECT DISTINCT latest_union_fnum::text AS f_num
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NOT NULL
)
SELECT
    COUNT(*) AS unions_total,
    COUNT(f7.f_num) AS unions_with_f7,
    ROUND(100.0 * COUNT(f7.f_num) / NULLIF(COUNT(*), 0), 1) AS pct_with_f7
FROM unions_master um
LEFT JOIN f7_fnums f7 ON f7.f_num = um.f_num;


-- @check: coverage_nlrb_matches
-- @gate: advisory
-- @description: % of unions_master with at least one nlrb_tallies row matched to it
-- @expect: report_only
-- @sql:
WITH nlrb_fnums AS (
    SELECT DISTINCT matched_olms_fnum AS f_num
    FROM nlrb_tallies
    WHERE matched_olms_fnum IS NOT NULL
)
SELECT
    COUNT(*) AS unions_total,
    COUNT(nf.f_num) AS unions_with_nlrb,
    ROUND(100.0 * COUNT(nf.f_num) / NULLIF(COUNT(*), 0), 1) AS pct_with_nlrb
FROM unions_master um
LEFT JOIN nlrb_fnums nf ON nf.f_num = um.f_num;


-- @check: latest_lm2_staleness
-- @gate: advisory
-- @description: Active unions with no LM-2 filing since 2022 (stale data)
-- @expect: report_only (count, no failure)
-- @sql:
WITH latest_lm AS (
    SELECT f_num, MAX(yr_covered) AS latest_year
    FROM lm_data
    GROUP BY f_num
)
SELECT
    COUNT(*) AS active_unions_total,
    COUNT(*) FILTER (WHERE l.latest_year < 2022 OR l.latest_year IS NULL) AS stale_or_missing,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.latest_year < 2022 OR l.latest_year IS NULL)
          / NULLIF(COUNT(*), 0), 1) AS pct_stale
FROM unions_master um
LEFT JOIN latest_lm l ON l.f_num = um.f_num
WHERE NOT um.is_likely_inactive;


-- @check: nlrb_tallies_match_rate
-- @gate: advisory
-- @description: % of nlrb_tallies rows with non-NULL matched_olms_fnum (the 47.78% match rate from P6-3 work log)
-- @expect: report_only
-- @sql:
SELECT
    COUNT(*) AS tallies_total,
    COUNT(*) FILTER (WHERE matched_olms_fnum IS NOT NULL) AS tallies_matched,
    ROUND(100.0 * COUNT(*) FILTER (WHERE matched_olms_fnum IS NOT NULL)
          / NULLIF(COUNT(*), 0), 2) AS match_pct
FROM nlrb_tallies;


-- ------------------------------------------------------------
-- Anomaly counts — advisory, surface to Layer 5 anomaly set
-- ------------------------------------------------------------

-- @check: anomaly_active_with_no_recent_filing
-- @gate: advisory
-- @description: Unions marked active but no LM-2 filing in last 5 years
-- @expect: report_only
-- @sql:
WITH recent_filers AS (
    SELECT DISTINCT f_num FROM lm_data WHERE yr_covered >= 2020
)
SELECT COUNT(*) AS count
FROM unions_master um
LEFT JOIN recent_filers rf ON rf.f_num = um.f_num
WHERE NOT um.is_likely_inactive
  AND rf.f_num IS NULL;


-- @check: anomaly_large_active_zero_nlrb
-- @gate: advisory
-- @description: Active unions with >10K members but zero NLRB matches (legitimate for public/federal/RLA, suspicious otherwise)
-- @expect: report_only
-- @sql:
WITH nlrb_matched AS (
    SELECT DISTINCT matched_olms_fnum AS f_num FROM nlrb_tallies WHERE matched_olms_fnum IS NOT NULL
)
SELECT COUNT(*) AS count
FROM unions_master um
LEFT JOIN nlrb_matched nm ON nm.f_num = um.f_num
WHERE NOT um.is_likely_inactive
  AND um.members > 10000
  AND nm.f_num IS NULL;


-- @check: anomaly_missing_aff_abbr
-- @gate: advisory
-- @description: Unions with NULL or empty aff_abbr (not classifiable into a national rollup)
-- @expect: report_only
-- @sql:
SELECT COUNT(*) AS count
FROM unions_master
WHERE NOT is_likely_inactive
  AND (aff_abbr IS NULL OR aff_abbr = '');


-- @check: anomaly_employer_linked_to_multiple_unions
-- @gate: advisory
-- @description: Same employer_id appears under more than one current union (bargaining unit transfer or matching collision?)
-- @expect: report_only
-- @sql:
SELECT COUNT(*) AS count
FROM (
    SELECT employer_id
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NOT NULL
    GROUP BY employer_id
    HAVING COUNT(DISTINCT latest_union_fnum) > 1
) sub;
