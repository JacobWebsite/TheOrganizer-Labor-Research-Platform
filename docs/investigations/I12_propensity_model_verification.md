# I12 - Propensity Model Verification

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
- What % of scored employers have AUC > 0.7?
- For top 20 propensity scores, is there observed organizing activity?
- Does propensity add signal beyond the 8-factor scorecard?

## Important Schema Note
`ml_election_propensity_scores` does **not** have an employer-level `auc` column in this DB.  
AUC is stored at model-version level in `ml_model_versions.test_auc`.

## SQL Used
```sql
SELECT model_version_id, COUNT(*)
FROM ml_election_propensity_scores
GROUP BY model_version_id
ORDER BY model_version_id;

SELECT model_version_id, model_name, version_string, test_auc, is_active
FROM ml_model_versions
ORDER BY model_version_id;

WITH scored AS (
  SELECT model_version_id, COUNT(*) AS scored_employers
  FROM ml_election_propensity_scores
  GROUP BY model_version_id
)
SELECT
  SUM(scored_employers) AS total_scored,
  SUM(scored_employers) FILTER (WHERE mv.test_auc > 0.7) AS scored_with_auc_gt_07,
  ROUND(
    100.0 * SUM(scored_employers) FILTER (WHERE mv.test_auc > 0.7)
    / NULLIF(SUM(scored_employers),0), 2
  ) AS pct_scored_with_auc_gt_07
FROM scored sc
LEFT JOIN ml_model_versions mv ON mv.model_version_id = sc.model_version_id;

WITH top AS (
  SELECT employer_id, propensity_score
  FROM ml_election_propensity_scores
  ORDER BY propensity_score DESC NULLS LAST
  LIMIT 20
)
SELECT
  COUNT(*) AS top20,
  COUNT(*) FILTER (
    WHERE COALESCE(u.nlrb_election_count,0) > 0 OR COALESCE(u.nlrb_ulp_count,0) > 0
  ) AS with_org_activity,
  ROUND(
    100.0 * COUNT(*) FILTER (
      WHERE COALESCE(u.nlrb_election_count,0) > 0 OR COALESCE(u.nlrb_ulp_count,0) > 0
    ) / NULLIF(COUNT(*),0), 1
  ) AS pct_with_org_activity,
  COUNT(*) FILTER (WHERE u.score_tier IN ('Priority','Strong')) AS priority_or_strong,
  ROUND(AVG(u.unified_score)::numeric,2) AS avg_unified_score
FROM top t
LEFT JOIN mv_unified_scorecard u ON u.employer_id = t.employer_id;

WITH j AS (
  SELECT
    m.employer_id,
    m.propensity_score,
    u.unified_score,
    CASE WHEN COALESCE(u.nlrb_election_count,0)>0 OR COALESCE(u.nlrb_ulp_count,0)>0 THEN 1 ELSE 0 END AS has_org_activity
  FROM ml_election_propensity_scores m
  JOIN mv_unified_scorecard u ON u.employer_id=m.employer_id
  WHERE m.propensity_score IS NOT NULL
    AND u.unified_score IS NOT NULL
)
SELECT CORR(propensity_score, unified_score) FROM j;
```

## Findings
- Scored employers: `146,693`
- Scored rows tied to model versions with `test_auc > 0.7`: `1,121` (`0.76%`)
  - Model v1 (`model_a`) has `test_auc = 0.7197`
  - Model v2 (`model_b`) has `test_auc = 0.5347`
- Top 20 propensity employers:
  - with observed NLRB activity (`nlrb_election_count > 0` or `nlrb_ulp_count > 0`): `2/20` (`10.0%`)
  - `Priority/Strong` by unified score: `2/20`
  - average unified score: `3.49`
- Correlation (`propensity_score`, `unified_score`): `0.0224` (near-zero)

## Conclusion
- Most currently scored employers are linked to a model version below AUC 0.7.
- Top propensity outputs have limited observed organizing activity in this sample.
- Propensity appears largely orthogonal to unified score (very low correlation), but current quality metrics suggest retraining/recalibration is needed before trusting it as an additive ranking signal.

