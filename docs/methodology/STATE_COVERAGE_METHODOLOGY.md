# State-Level Coverage Analysis Reference

## Summary Metrics (Excluding DC)

| Sector | EPI 2024 Benchmark | Platform Coverage | Coverage % |
|--------|-------------------|-------------------|------------|
| **Private** | 7,211,458 | 6,272,420 | **87.0%** |
| **Public** | 6,995,000 | 5,298,619 | **75.7%** |
| **TOTAL** | 14,206,458 | 11,571,039 | **81.4%** |

---

## Data Sources

### EPI Benchmarks (CPS-based)
- **Private sector**: EPI union_membership.csv - annual CPS estimates
- **Public sector**: EPI Table 6b - 12-month rolling averages (resolves sample size issues)
- Reference year: 2024

### Platform Private Sector (~6.25M)
- **Source**: F-7 Employer Bargaining Notices (OLMS)
- **Exclusions**: Federal affiliations, government union names, public employer patterns
- **Adjustment factors**:
  - MATCHED employers: Actual reconciled estimate
  - UNMATCHED: 35% of raw F-7 reported workers
  - NAME_INFERRED: 15% of raw F-7 reported workers

### Platform Public Sector (~5.3M excl DC)
- **Source**: OLMS state/local union LM filings + FLRA federal bargaining units
- **Gap cause**: Many states lack collective bargaining or don't file with OLMS

---

## Interpretation Flags

| Flag | Definition | Action |
|------|------------|--------|
| `PRIVATE_OVER` | Platform >115% of EPI | Check multi-employer double-counting |
| `PRIVATE_UNDER` | Platform <65% of EPI | Coverage gap - need additional sources |
| `PUBLIC_OVER` | Platform >115% of EPI | HQ effects or filing artifacts |
| `PUBLIC_GAP` | Platform <50% but data exists | Partial coverage |
| `NO_PUBLIC_DATA` | Platform ~0% | State doesn't file with OLMS |
| `HQ_EFFECT` | DC-specific | Always exclude DC from analysis |

---

## States Requiring Investigation

### Double-Counting Risk (Private >130%)
- AR (140%), KS (142%), MN (137%), UT (132%)
- **Check**: Multi-employer master agreements, regional council structures

### Major Private Gaps (<50%)
- ME (19%), VT (23%), WY (26%), NH (28%), MT (43%)
- **Check**: Small sample sizes, industry composition

### No Public Sector Data (10 states)
AL, AR, ID, MS, ND, OK, SC, SD, UT, WY
- **Cause**: No collective bargaining laws or no OLMS filing requirement
- **Future**: State PERB databases, open records requests

### Public Sector Overcounted (>115%)
- CT (117%), IL (172%), MN (112%), NY (145%), PA (141%), VT (119%)
- **Check**: HQ location effects, multi-local aggregation

---

## Key Files

| File | Description |
|------|-------------|
| `FINAL_COVERAGE_BY_STATE.csv` | Raw comparison data |
| `COVERAGE_REFERENCE_ANNOTATED.csv` | With flags and methodology notes |
| `state_union_membership_COMPLETE_2024.csv` | EPI benchmark source data |

---

## Usage Guidelines

1. **Always exclude DC** when calculating national totals - HQ effects distort both sectors
2. **Private >100% is expected** in some states due to multi-employer agreement coverage
3. **Public 0%** indicates structural data gap, not error - these states need alternative sources
4. **Cross-reference flags** when investigating specific employers or unions
5. **Update quarterly** as new LM filings and F-7 notices become available

---

*Generated: January 2025*
*Platform Version: 6.1*
