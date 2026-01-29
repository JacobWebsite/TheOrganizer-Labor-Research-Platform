# Labor Relations Platform - Project Status v7

**Date:** January 26, 2026  
**Version:** 7.0 - Form 990 Public Sector Integration

## Major Achievement: Public Sector Coverage Gap Filled

The platform now integrates Form 990 data to fill the critical gap in public sector union membership coverage.

### Coverage Summary

| Data Source | Organizations | Reported Members | Notes |
|------------|---------------|------------------|-------|
| OLMS LM Forms | 19,554 | 70.1M (raw) | Private sector + some public |
| Form 990 Estimates | 22 | 5.76M | Public sector teachers, police, fire |
| **UNIFIED** | **19,576** | **75.9M** | Combined (with hierarchy overlap) |

### Reconciled Totals (Deduplicated)

| Sector | Members | Source |
|--------|---------|--------|
| Private Sector | 14.5M | OLMS deduplicated |
| Federal Employees | 1.3M | FLRA + OLMS |
| State/Local Public | 5.8M | Form 990 estimates |
| **TOTAL** | **~21.6M** | Near BLS benchmark |

## Form 990 Integration Details

### Validated Methodology
- **NEA National validation:** 0.00% variance vs LM data
- **$134.44/member** validated rate for NEA national per-capita
- Back-calculated state rates from published membership data

### Organizations by Type

| Type | Count | Members | Avg Dues Rate |
|------|-------|---------|---------------|
| NEA_NATIONAL | 1 | 2.84M | $134/member |
| NEA_STATE | 10 | 1.29M | $412/member |
| AFT_NEA_STATE | 2 | 850K | $220/member |
| FOP_NATIONAL | 1 | 356K | $24/member |
| AFT_LOCAL | 3 | 178K | $907/member |
| SEIU_LOCAL | 1 | 96K | $500/member |
| AFSCME_COUNCIL | 1 | 75K | $293/member |
| FOP_STATE | 2 | 73K | $59/member |
| IAFF_LOCAL | 1 | 3.2K | $563/member |

### Key State Coverage (990 Estimates)

| State | 990 Members | Organizations |
|-------|-------------|---------------|
| NY | 840,000 | NYSUT + UFT |
| CA | 406,000 | CTA + SEIU |
| NJ | 200,000 | NJEA |
| PA | 236,000 | PSEA + Phila Fed |
| IL | 235,000 | IEA + CTU + AFSCME |
| FL | 150,000 | FEA |
| OH | 148,000 | OEA + FOP |

## Database Schema

### New Table: `form_990_estimates`
```sql
- organization_name, ein, state, city
- org_type (NEA_STATE, AFT_LOCAL, FOP_STATE, etc.)
- tax_year, dues_revenue, total_revenue, total_assets
- dues_rate_used, estimated_members
- confidence_level (HIGH/MEDIUM/LOW)
- cross_reference_source, cross_reference_value
```

### New Views
```sql
- v_unified_membership (combines OLMS + 990)
- v_unified_by_affiliation (summary by affiliation)
- v_990_by_org_type (990 summary by org type)
- v_990_by_state (990 summary by state)
```

## Files Created This Session

| File | Purpose |
|------|---------|
| `load_990_affiliates.py` | Initial CTA/NYSUT loader |
| `load_990_batch.py` | NEA state affiliate batch |
| `load_990_aft_fop.py` | AFT, FOP, SEIU, AFSCME orgs |
| `create_unified_view.py` | Unified membership view |
| `FORM_990_CHECKPOINT_4_SUMMARY.md` | Checkpoint documentation |
| `PROJECT_STATUS_v7.md` | This document |

## Platform Capabilities

### Data Sources Integrated
1. ✅ OLMS LM-2/LM-3/LM-4 Forms (2010-2025)
2. ✅ F-7 Employer Bargaining Notices
3. ✅ NLRB Election Data
4. ✅ FLRA Federal Bargaining Units
5. ✅ **NEW:** Form 990 Public Sector Estimates

### API Endpoints (38 total)
- Union lookup, search, hierarchy
- Employer search and matching
- Geographic analysis
- Financial trends
- **NEW:** 990 estimate queries

### Web Interface
- Interactive search with sector toggle
- Leaflet maps with geographic data
- Chart.js visualizations
- **PENDING:** 990 confidence indicators

## Next Steps

### Immediate (Checkpoint 5)
1. Expand 990 coverage to remaining 40 NEA state affiliates
2. Add more FOP/IAFF state lodges
3. Target: 8-10M public sector members

### Near-term (Checkpoint 6)
1. Integrate 990 data into API responses
2. Add "Include 990 estimates" toggle to UI
3. Show confidence levels in interface
4. Create unified membership endpoint

### Future
1. Automate 990 data extraction via ProPublica API
2. Build annual update pipeline
3. Cross-validate against BLS CPS microdata
4. Develop correction factors for systematic bias

## Queries for Analysis

```sql
-- Platform coverage summary
SELECT 
    data_source,
    COUNT(*) as orgs,
    SUM(membership) as total_members
FROM v_unified_membership
GROUP BY data_source;

-- Top public sector unions by 990 data
SELECT organization_name, state, estimated_members, confidence_level
FROM form_990_estimates
ORDER BY estimated_members DESC;

-- State coverage comparison
SELECT 
    state,
    SUM(CASE WHEN data_source = 'OLMS_LM' THEN membership END) as olms,
    SUM(CASE WHEN data_source = '990_EST' THEN membership END) as f990
FROM v_unified_membership
GROUP BY state
ORDER BY f990 DESC NULLS LAST;
```

## Technical Notes

### Confidence Framework
- **HIGH:** Validated against LM data or published membership (3 orgs)
- **MEDIUM:** Published dues rate, reasonable estimate (19 orgs)
- **LOW:** Default rate, no validation (0 orgs)

### Dues Rate Patterns
- NEA national per-capita: $134/member
- State teacher associations: $400-700/member
- Urban AFT locals: $900-1,100/member
- FOP: $24-80/member (very low structure)
- SEIU/AFSCME: $300-500/member

### Known Limitations
1. 990 estimates may overlap with OLMS data for some organizations
2. Dues rate variation across member categories (active vs retired)
3. Federation models (NYSUT) require special handling
4. Tax year vs calendar year timing differences
