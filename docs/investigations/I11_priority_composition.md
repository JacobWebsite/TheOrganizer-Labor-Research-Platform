# I11 - Priority Tier Composition

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
For `mv_unified_scorecard` rows in `score_tier = 'Priority'`:
- What % have zero enforcement data (`has_osha = false`, `has_nlrb = false`, `has_whd = false`)?
- What drives Priority membership (size + proximity vs enforcement)?
- What does factor coverage look like?

## SQL Used
```sql
SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_tier = 'Priority';

SELECT
  COUNT(*) FILTER (
    WHERE COALESCE(has_osha,false)=false
      AND COALESCE(has_nlrb,false)=false
      AND COALESCE(has_whd,false)=false
  ) AS zero_enf,
  COUNT(*) FILTER (
    WHERE COALESCE(has_osha,false)
       OR COALESCE(has_nlrb,false)
       OR COALESCE(has_whd,false)
  ) AS has_any_enf,
  COUNT(*) AS total
FROM mv_unified_scorecard
WHERE score_tier='Priority';

SELECT factors_available, COUNT(*)
FROM mv_unified_scorecard
WHERE score_tier='Priority'
GROUP BY factors_available
ORDER BY factors_available;

SELECT
  COUNT(*) FILTER (WHERE score_size IS NOT NULL) AS has_size,
  COUNT(*) FILTER (WHERE score_union_proximity IS NOT NULL) AS has_proximity,
  COUNT(*) FILTER (WHERE score_industry_growth IS NOT NULL) AS has_growth,
  COUNT(*) FILTER (WHERE score_contracts IS NOT NULL) AS has_contracts,
  COUNT(*) FILTER (WHERE score_osha IS NOT NULL) AS has_osha_score,
  COUNT(*) FILTER (WHERE score_nlrb IS NOT NULL) AS has_nlrb_score,
  COUNT(*) FILTER (WHERE score_whd IS NOT NULL) AS has_whd_score
FROM mv_unified_scorecard
WHERE score_tier='Priority';
```

## Findings
- Priority total: `2,332`
- Zero enforcement (no OSHA/NLRB/WHD): `2,009` (`86.1%`)
- Any enforcement present: `323` (`13.9%`)

### Factor coverage (Priority tier)
- `score_size` present: `2,332` (`100%`)
- `score_union_proximity` present: `2,225` (`95.4%`)
- `score_industry_growth` present: `2,265` (`97.1%`)
- `score_contracts` present: `80` (`3.4%`)
- Enforcement factor scores:
  - `score_osha`: `170` (`7.3%`)
  - `score_nlrb`: `150` (`6.4%`)
  - `score_whd`: `54` (`2.3%`)

### `factors_available` distribution
- 3 factors: `1,978` (`84.8%`)
- 4 factors: `287`
- 5 factors: `50`
- 6+ factors: `17`

## Conclusion
Priority is predominantly a structural tier in current data:
- mostly `size + union_proximity + growth`
- limited enforcement signal coverage
- most Priority rows are at the minimum factor floor (`factors_available = 3`).

