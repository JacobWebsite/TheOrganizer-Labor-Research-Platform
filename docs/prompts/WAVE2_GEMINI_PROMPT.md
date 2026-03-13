# Gemini Prompt: 5.4 Gower Enhancement Architecture Review

**When to send:** Now (Wave 2)

---

TASK: Review the proposed Gower distance enhancement for the organizing scorecard's similarity factor (Factor 9), and recommend whether/how to proceed with weighted dimensions and occupation similarity integration.

## CURRENT STATE

The platform has an `employer_comparables` table with 269,785 Gower distance pairs between employers. Factor 9 (similarity) currently reads from `mergent_employers.similarity_score` (53,957 rows with scores) using simple thresholds:

```sql
-- Factor 9: Similarity (10 pts)
CASE
    WHEN md.similarity_score >= 0.80 THEN 10
    WHEN md.similarity_score >= 0.60 THEN 7
    WHEN md.similarity_score >= 0.40 THEN 4
    WHEN md.similarity_score IS NOT NULL THEN 1
    ELSE 0
END AS score_similarity,
```

### employer_comparables schema (269,785 rows):
```
id: integer (PK)
employer_id: integer (FK to mergent_employers)
comparable_employer_id: integer
rank: integer (1 = most similar)
gower_distance: numeric (0 = identical, 1 = maximally different)
feature_breakdown: jsonb
computed_at: timestamp
```

### Sample feature_breakdown JSONB:
```json
{
  "state": 0.0,
  "county": 0.0,
  "naics_4": 0.0,
  "company_age": null,
  "revenue_log": null,
  "company_type": 0.0,
  "is_subsidiary": 0.0,
  "bls_growth_pct": 0.0,
  "employees_here_log": 0.0652,
  "whd_violation_rate": 0.0,
  "employees_total_log": 0.0538,
  "osha_violation_rate": 0.0,
  "is_federal_contractor": 0.0
}
```

Current Gower dimensions (13 features, all equally weighted):
- Geographic: `state`, `county`
- Industry: `naics_4`
- Size: `employees_here_log`, `employees_total_log`, `revenue_log`
- Age: `company_age`
- Compliance: `osha_violation_rate`, `whd_violation_rate`
- Structure: `company_type`, `is_subsidiary`, `is_federal_contractor`
- Growth: `bls_growth_pct`

### occupation_similarity table (8,731 rows):
```
occupation_code_1: varchar
occupation_code_2: varchar
similarity_score: numeric (cosine similarity, 0.30-1.0 range)
shared_industries: integer
method: varchar (always "cosine_industry_cooccurrence")
```

Built from BLS OEWS staffing patterns — occupations that co-occur in the same industries are similar. 832 unique occupations, 422 industries.

### MV architecture constraint:
The MV (`mv_organizing_scorecard`) covers OSHA establishments NOT matched to F7 (the `WHERE fm.establishment_id IS NULL` filter). The `mergent_data` CTE joins through `osha_f7_matches`, so Factor 9 is always NULL/0 for MV rows. It only activates for F7-matched employers queried through the detail endpoint.

This means Factor 9 enhancement only affects the detail endpoint path, not the 22K MV rows.

## PROPOSED ENHANCEMENTS

### 1. Weighted Gower Dimensions
Replace equal weighting with domain-informed weights:
- **Industry (naics_4):** 3x weight — industry is the strongest predictor of organizing patterns
- **Compliance (osha_violation_rate, whd_violation_rate):** 2x weight — violation history signals employer behavior
- **Geographic (state, county):** 1x weight
- **Size (employees):** 1x weight
- **Other (company_type, etc.):** 1x weight

### 2. "Nearest Unionized Sibling" Metric
For each employer, find the closest comparable that HAS a union (`has_union = TRUE` in mergent_employers). Use that distance as a direct scoring signal — closer to a unionized peer = higher organizing potential.

### 3. Occupation Similarity Integration
Use the `occupation_similarity` table to add an occupation-based dimension to the Gower distance. If two employers share similar occupation mixes (high cosine similarity), they should be considered more comparable even if their NAICS codes differ slightly.

## REVIEW QUESTIONS

1. **WEIGHT RATIONALE:** Are the proposed 3x/2x/1x/1x weights defensible? What evidence or literature supports industry being 3x more important than geography for organizing similarity? Should we use data-driven weight selection instead (e.g., weights that maximize correlation with election outcomes)?

2. **DOUBLE-COUNTING RISK:** OSHA violation rate is already Factor 5 (scored 0-10 with temporal decay). If we also weight it 2x in the Gower distance for Factor 9, are we double-counting? The same concern applies to geographic factors (already Factor 3). How significant is this correlation, and does it inflate scores for certain employer profiles?

3. **NEAREST UNIONIZED SIBLING:**
   - What if the nearest unionized employer is in a completely different industry but happens to be geographically close? Is distance alone sufficient, or do we need industry-gated distance?
   - What fraction of employers have ANY unionized comparable within a reasonable distance threshold?
   - What if the "nearest" is distance 0.95 — essentially not similar at all? Should there be a maximum distance cutoff?

4. **OCCUPATION INTEGRATION:**
   - Cosine similarity (0.30-1.0) is a different scale than Gower component distances (0.0-1.0 where 0=identical). How should these be reconciled? Convert cosine to distance (1 - cosine)? Normalize to same range?
   - The occupation similarity is at the occupation level, but Gower is at the employer level. How to bridge this? Use the employer's primary NAICS to look up dominant occupations, then compute occupation-weighted similarity?
   - Is this adding real signal, or is it largely redundant with the NAICS-based industry dimension?

5. **RECOMPUTATION COST:**
   - If we change Gower weights, all 269K comparables need recomputation. Is this a one-time migration cost, or does it recur with new data?
   - The current computation script: what's its runtime? Is batch recomputation feasible on each data refresh?
   - Should we precompute the "nearest unionized" metric separately from the general comparables?

6. **COLD START / COVERAGE:**
   - Factor 9 is always 0 for MV rows (22,389 establishments) because they lack F7 matches.
   - Of the ~54K mergent employers with similarity scores, how many are actually surfaced to users?
   - Should we rethink Factor 9 to work for unmatched establishments too (e.g., industry-level similarity averages as fallback)?

7. **ALTERNATIVE APPROACH:**
   - Instead of reweighting Gower dimensions, should we train a simple model to learn optimal weights from election outcomes? (This connects to the propensity model in 5.5.)
   - Could we replace the hand-tuned Gower with a learned embedding distance?

## DELIVERABLE

Architecture review document with:
- Recommendation for each question (proceed / modify / defer / skip)
- If proceed: specific implementation guidance (weight values, distance thresholds, integration formula)
- If skip: what should Factor 9 look like in its current form for the Phase 5 release?
- Risk assessment for each enhancement
- Estimated implementation complexity (hours, not days)

Do NOT write implementation code. This is architecture + design only.
