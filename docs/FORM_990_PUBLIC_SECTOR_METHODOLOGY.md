# Form 990 Membership Estimation Methodology
## Filling Public Sector Gaps in OLMS Data

---

## Problem Statement

The OLMS LM database captures unions subject to LMRDA reporting requirements, but **public sector employees are exempt** from LMRDA. This creates systematic gaps:

| Sector | LMRDA Coverage | Result |
|--------|----------------|--------|
| Private sector | Covered | Good OLMS data |
| Federal employees | Exempt (FSLMRA) | Gap - use FLRA data |
| State/local government | Exempt | **Major gap** - use Form 990s |
| Railroad/airline | Exempt (RLA) | Partial gap |

### Magnitude of the Gap

BLS reports ~7 million public sector union members (2024), but our OLMS-based platform captures far fewer. The gap is concentrated in:

1. **State teacher associations** (NEA affiliates) - ~3 million members nationally
2. **Police unions** (FOP lodges) - ~350,000+ members
3. **State employee associations** (independent, not AFSCME) - varies by state
4. **Local firefighter associations** (not IAFF-affiliated)
5. **Public university faculty** (AAUP chapters, independent associations)

---

## Data Source: IRS Form 990

Public sector unions typically organize as 501(c)(5) labor organizations or 501(c)(6) professional associations. They must file annual Form 990 with the IRS if gross receipts exceed $50,000.

### Where to Access Form 990s

| Source | Access | Format |
|--------|--------|--------|
| **ProPublica Nonprofit Explorer** | https://projects.propublica.org/nonprofits/ | Searchable, XML downloads |
| **IRS Tax Exempt Organization Search** | https://apps.irs.gov/app/eos/ | Official source |
| **Open990** | https://www.open990.org/ | Machine-readable extracts |
| **Candid (GuideStar)** | https://www.guidestar.org/ | Requires registration |

### Key Form 990 Fields for Membership Estimation

```
Part I, Line 8: Contributions & grants (may include dues)
Part I, Line 2: Program service revenue
Part VIII, Line 1a: Federated campaigns
Part VIII, Line 1b: Membership dues (PRIMARY FIELD)
Part VIII, Line 1c: Fundraising events
Part IX, Line 5: Compensation of current officers
Part IX, Line 7: Other salaries and wages
Schedule A: Public charity status
```

**Critical field**: Part VIII, Line 1b reports **gross membership dues** directly.

---

## Estimation Methodology

### Approach 1: Direct Dues Division (PRIMARY)

**Formula:**
```
Estimated Members = Total Dues Revenue / Average Annual Dues per Member
```

**Steps:**
1. Extract dues revenue from Form 990 Part VIII, Line 1b
2. Research the organization's published dues rate
3. Account for member categories (full-rate, reduced, ESP, retired)
4. Apply weighted average if multiple rates exist

**Example: Oklahoma Education Association**
```
Dues Revenue (990): $5,126,961
Research shows: ~$520/year total unified (NEA + OEA + local)
NEA portion: ~$205
Local portion: ~$50 (varies)
OEA state portion: ~$265

Calculation: $5,126,961 / $265 = 19,347 full-rate equivalent
Adjusted for ESP/reduced: ~14,000-16,000 full-rate, ~28,000 total
```

### Approach 2: Cross-Reference Published Membership

Many organizations publicly report membership:
- Press releases ("35,000 OEA members")
- Annual reports
- NEA/AFT affiliate rankings
- State federation reports

**Use for validation:**
```
Back-calculated dues rate = 990 Dues Revenue / Published Membership
```

This validates or refines Approach 1 estimates.

### Approach 3: Expense-Based Validation

**Formula:**
```
Estimated Members = Membership Processing Expenses / Cost per Member
```

**Typical cost ranges:**
- Large associations: $10-15/member
- Medium associations: $15-25/member
- Small locals: $25-40/member

**Example: OEA**
```
Membership processing expense: $514,197
Estimated cost/member: $15-20

$514,197 / $17.50 = 29,383 members
```

### Approach 4: Staff-to-Member Ratio

**Formula:**
```
Estimated Members = Full-time Staff × Typical Members per Staff
```

**Typical ratios:**
- State teacher associations: 500-800 members per staff
- State employee associations: 400-600 members per staff  
- Police/FOP lodges: 200-400 members per staff

---

## Dues Rate Research Sources

### NEA Affiliates (Teacher Associations)

NEA publishes state affiliate dues rates. 2017-18 data showed:

| State | State Dues | + NEA ($189) | Total |
|-------|-----------|--------------|-------|
| California (CTA) | $644 | $833 | Highest |
| New York (NYSUT) | $556 | $745 | |
| Oklahoma (OEA) | ~$265 | ~$454 | |
| Texas (TSTA) | ~$285 | ~$474 | |
| Average | $424 | $613 | National |

**Note:** NEA dues are formula-based (0.00225 × national average teacher salary).

### AFT Affiliates

AFT dues vary more widely:
- Per-capita to national: ~$18-22/month
- State and local portions vary significantly
- Total often $500-700/year for full-time

### Fraternal Order of Police

FOP structure:
- National dues: ~$15-25/year
- State lodge: ~$20-40/year
- Local lodge: ~$50-150/year
- **State 990s capture state + proportional national**

### State Employee Associations

Highly variable:
- Independent associations: $100-300/year
- AFSCME-affiliated: $400-600/year
- Many have tiered rates by salary

---

## Adjustments and Corrections

### 1. Member Category Weighting

Not all members pay full dues:

| Category | Typical Rate | Weight |
|----------|-------------|--------|
| Active professional | 100% | 1.0 |
| Education Support (ESP) | 50-60% | 0.55 |
| Part-time | 50% | 0.5 |
| Retired | 20-30% | 0.25 |
| Life member | $0 | 0.0 |
| Student | 10-15% | 0.12 |

**Adjustment formula:**
```
Full-Rate Equivalent = Dues Revenue / Full-Rate Dues
Total Members = FRE / Weighted Average Factor

Where weighted factor might be 0.6-0.8 depending on category mix
```

### 2. Fiscal Year Alignment

Form 990 fiscal years may not match calendar years:
- Many education associations: Sept 1 - Aug 31
- Calendar year organizations: Jan 1 - Dec 31
- Match to appropriate BLS comparison year

### 3. Multi-Organization Structures

Some 990s may include:
- State association only (our target)
- State + regional councils combined
- Foundation/PAC as separate filers

Verify the 990 represents the membership organization, not a foundation.

---

## Data Quality Assessment

### Confidence Levels

| Level | Criteria | Uncertainty |
|-------|----------|-------------|
| **HIGH** | Published dues rate verified, membership cross-referenced | ±10% |
| **MEDIUM** | Dues rate estimated from similar orgs, no cross-reference | ±25% |
| **LOW** | National average dues assumed, no validation | ±40% |

### Documentation Requirements

For each 990-based estimate, record:
1. Organization name and EIN
2. 990 fiscal year
3. Dues revenue (Part VIII, Line 1b)
4. Dues rate source and value
5. Estimation method used
6. Confidence level
7. Any cross-reference validation

---

## Integration with Platform

### Recommended Database Fields

```sql
CREATE TABLE form_990_estimates (
    organization_name VARCHAR(255),
    ein VARCHAR(12),
    fiscal_year INT,
    state VARCHAR(2),
    sector VARCHAR(50),  -- 'PUBLIC_SECTOR', 'EDUCATION', 'PUBLIC_SAFETY'
    dues_revenue DECIMAL(12,2),
    dues_rate_used DECIMAL(8,2),
    dues_rate_source VARCHAR(255),
    estimated_members INT,
    estimation_method VARCHAR(50),
    confidence_level VARCHAR(10),
    cross_reference_source VARCHAR(255),
    cross_reference_value INT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Sector Classification

Map 990 organizations to platform sectors:
- NEA/AFT affiliates → PUBLIC_SECTOR (education)
- FOP lodges → PUBLIC_SECTOR (public safety)
- State employee associations → PUBLIC_SECTOR (general government)
- AFSCME councils → PUBLIC_SECTOR (general government)

---

## Limitations and Caveats

1. **Dues rates change annually** - historical 990s need historical rates
2. **Member categories not disclosed** - must estimate category mix
3. **Multi-state organizations** - some 990s cover multiple states
4. **Agency fee payers** - may or may not be included in dues revenue
5. **Timing mismatches** - 990 fiscal year vs. BLS calendar year
6. **Non-dues revenue** - some orgs have significant non-dues income

---

## Validation Checklist

Before integrating a 990-based estimate:

- [ ] Verified 990 is for membership organization (not foundation/PAC)
- [ ] Dues revenue field populated and reasonable
- [ ] Dues rate researched and documented
- [ ] Member categories considered in estimate
- [ ] Cross-referenced against published membership if available
- [ ] Confidence level assigned
- [ ] State/sector classification correct
- [ ] No double-counting with existing OLMS data

---

## References

- IRS Form 990 Instructions: https://www.irs.gov/pub/irs-pdf/i990.pdf
- NEA State Affiliate Dues: https://www.eiaonline.com/intercepts/
- ProPublica Nonprofit Explorer: https://projects.propublica.org/nonprofits/
- Unionstats.com State Data: https://unionstats.com/state/

---

*Methodology developed: January 2026*
*For use with Labor Relations Research Platform v6*
