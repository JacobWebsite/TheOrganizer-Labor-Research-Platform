# Ideal Benchmark Employers for Model Validation

**Project:** Labor Relations Research Platform  
**Date:** March 2026  
**Purpose:** Which types of firms to use as benchmarks when testing the workforce demographic estimation model — and why

---

## What Makes a Good Benchmark Firm

A benchmark firm needs to satisfy three conditions simultaneously:

**1. You have the real answer.** You need actual known demographic data to compare your estimate against. If you don't know the true number, you can't measure whether your model is right or wrong.

**2. The firm is genuinely representative.** If all your benchmarks are similar — say, large East Coast hospitals — you'll only know the model works for that type. You need variety that covers the range of employers in your organizing target universe.

**3. The case is actually hard.** A model that only works on easy, obvious cases isn't useful. You want benchmarks that stress-test where the model might fail.

---

## Where "The Real Answer" Comes From

This shapes which firms you can even use as benchmarks. Your sources of ground truth are:

**Source A — EEO-1 FOIA release (strongest):** The ~4,500–19,000 companies now released. For any firm in this set, you have actual 2016–2020 headcounts by race × gender × job level. These are your gold standard benchmarks.

**Source B — Voluntary ESG/Diversity disclosures:** Many large public companies (Microsoft, Apple, Target, UPS, etc.) publish their own annual EEO-1 summary in corporate social responsibility reports. More recent than the FOIA release and publicly available. Less precise format but still useful.

**Source C — NLRB election records:** For employers where unions won elections, you often have detailed workforce descriptions from the election case files (the bargaining unit description specifies job types and headcounts). Useful for validating occupational composition, not demographics directly.

**Source D — Form 990 (nonprofits):** Hospitals, nursing homes, and universities disclose employee counts by compensation band. Cross-referenced with publicly available diversity reports, this gives a rich validation set.

---

## The Seven Axes Your Benchmark Set Must Cover

### Axis 1: Industries Where the Industry Signal Dominates

These are sectors where the type of work is so specific that the national industry average is always the strongest predictor, regardless of where the employer is located.

**Best examples:**

- **Nursing homes / long-term care (NAICS 6231)** — Consistently 70–85% female, disproportionately Black and Hispanic workers nationally. A nursing home in rural Iowa and one in Newark will both look more like "nursing home workers nationally" than like the surrounding county's demographics. Test whether your model captures this.
- **Defense/aerospace manufacturing (NAICS 3364)** — Very white, very male, highly educated. Lockheed, Raytheon, and Boeing are all in the EEO-1 FOIA set. The industry signal should dominate regardless of whether they're in suburban Maryland or Southern California.
- **Commercial fishing / agriculture (NAICS 1141, 111X)** — Almost exclusively male, often majority Hispanic in processing roles. Strong industry override.

**What you're testing:** Whether the model correctly gives high weight to the ACS industry constraint when that signal is dominant.

---

### Axis 2: Industries Where the Geography Signal Dominates

These are sectors where the local county demographics overwhelm the national industry pattern — because the work itself isn't highly specialized and anyone can do it.

**Best examples:**

- **Warehousing and fulfillment (NAICS 493)** — Warehouses in a majority-Hispanic county will be majority-Hispanic. Warehouses in majority-Black urban counties will reflect that. Amazon fulfillment centers are particularly good here — Amazon voluntarily publishes some workforce diversity data, and many of their facilities are in the EEO-1 set.
- **Food processing plants (NAICS 3116)** — Poultry plants in rural Georgia or North Carolina employ overwhelmingly Hispanic and Black workers because that's who is in those counties and seeking that work. A poultry plant in a predominantly white Midwestern county would look very different. Test whether LODES county data correctly drives the estimate in these cases.
- **Hotels and accommodations (NAICS 7211)** — Front desk, housekeeping, and food service roles reflect local labor markets very strongly.

**What you're testing:** Whether the model correctly gives high weight to the LODES county constraint when local demographics are the dominant signal.

---

### Axis 3: Firms With Extreme Demographic Stratification

These are employers where demographic distributions differ dramatically between job levels — many minority workers at the bottom, few at the top. This tests the EEO-1 integration specifically and the organizing inequality signal it creates.

**Best examples:**

- **Large hotel chains (Marriott, Hilton)** — Often majority-minority housekeeping and kitchen staff, predominantly white management. Both are in the EEO-1 set and in your organizing universe.
- **Large grocery chains** — Similar pattern. Cashiers and stock workers reflect local demographics; management is whiter.
- **Hospital systems** — Black and Hispanic workers heavily concentrated in Service Worker and Operative categories; Professionals (RNs, doctors) much whiter. HCA, Tenet, and Community Health Systems are all in the EEO-1 set.

**What you're testing:** Whether the EEO-1 stratification index correctly identifies firms with demographic inequality across job levels — and whether your model correctly predicts that inequality for firms you're only estimating.

---

### Axis 4: Size Extremes

You want to validate the BDS-HC firm-size dimension specifically.

| Size Band | Count | Notes |
|---|---|---|
| **Small (50–99 workers)** | 5–6 | Harder to estimate — more random variation. Use NLRB election records as ground truth. |
| **Medium (100–499)** | 8–10 | Best-covered range in EEO-1 (100-worker filing threshold). Great benchmark zone. |
| **Large (500–4,999)** | 6–8 | Well covered in EEO-1. Public company diversity reports often available. |
| **Very large (5,000+)** | 4–5 | Almost always publicly disclosed. Microsoft, UPS, Target, Amazon all publish EEO-1 summaries. Easy validation cases but important for top of scale. |

**What you're testing:** Whether BDS-HC's firm-size dimension is actually adding predictive power beyond just the industry and county signals.

---

### Axis 5: Geography Edge Cases

These stress-test the county-level demographic signal.

**Majority-minority counties with industry mismatch:** A tech employer in a county that is 80% Black (like Prince George's County, MD) — does the model correctly blend the "tech workforce is mostly white/Asian" industry signal with the heavily Black county demographic? Real data from the EEO-1 set is needed to find the right answer.

**Rural counties with highly specialized industries:** A paper mill in a county that's 95% white — the county signal and industry signal agree. This should be an easy case. If your model gets it wrong, something is fundamentally broken.

**Border regions with heavy Hispanic workforce:** Texas/Arizona/California border counties. The LODES signal will be very strong here. Good for validating that the geographic constraint actually dominates appropriately.

---

### Axis 6: Known Hard Cases

These are designed to find where the model breaks — deliberately.

**Multi-establishment firms with very different locations:** A hospital system with locations in downtown Chicago AND rural downstate Illinois. Company-level EEO-1 data won't tell you what the individual establishments look like. Your model estimates at the establishment level. Test whether your establishment-level estimate diverges from the company-level EEO-1 in a sensible direction.

**Firms that recently underwent major demographic shifts:** A company that went through rapid growth or large layoffs between 2018 and 2023. The EEO-1 (2016–2020) may not match current reality. Identify these by checking if the employer shows up in WARN Act notices or has large employment swings in QCEW data.

**Staffing agencies:** Deliberately include one or two as known "expected failures." Staffing agencies place workers at other employers, so their "workforce" is almost never at their EIN address. Your estimates will be wrong — and you should confirm they're wrong in a predictable direction, not a random one.

---

### Axis 7: Firms Already in Your Organizing Universe

The most important category — benchmark against employers your users actually care about, not just statistically convenient ones.

Look at your existing **316 priority targets** (employers with enforcement history from the Round 2 scorecard findings). Of those, how many appear in the EEO-1 FOIA release? Those are your most valuable benchmarks — they're exactly the kind of employer the platform is built for, and you now have real data to check the estimates against.

---

## Recommended Benchmark Set: ~50–75 Firms

| Industry / Category | Count | Primary Ground Truth Source |
|---|---|---|
| Nursing homes / long-term care | 8–10 | EEO-1 FOIA + voluntary disclosures |
| Warehousing / logistics | 6–8 | EEO-1 FOIA + Amazon voluntary |
| Defense / aerospace manufacturing | 5–6 | EEO-1 FOIA |
| Hotel chains | 4–5 | EEO-1 FOIA |
| Hospital systems | 6–8 | EEO-1 FOIA + 990 cross-reference |
| Food processing plants | 4–5 | EEO-1 FOIA |
| Large retail | 4–5 | EEO-1 FOIA + ESG reports |
| Tech companies (public) | 4–5 | Voluntary ESG disclosures |
| Small employers 50–100 workers | 5–6 | NLRB election records |
| Known hard cases (staffing, multi-site) | 4–5 | EEO-1 — expected to expose model limits |

This covers every axis: industry-dominated vs. geography-dominated, stratified vs. homogeneous, small vs. large, easy vs. hard.

---

## The Most Important Practical Next Step

Before building anything, run this one query:

> **Cross-reference your existing 316 priority targets against the EEO-1 FOIA release by EIN.**

Any overlap immediately becomes your highest-value benchmark — real employers, real enforcement history, real demographic data. That's your core test set for Phase 1.

The EIN is the most reliable matching key because it's the same unique tax ID number used by both your enforcement records (OSHA, WHD, NLRB) and the EEO-1 filing system. A match on EIN is unambiguous.

---

## What Good Benchmark Results Look Like

When you run the model against a benchmark firm, you're looking for three things:

**1. Directional accuracy:** Is the model pointing in the right direction? If the true workforce is 65% female, is the estimate above 50%? Even a rough estimate of 58% is directionally correct and useful. An estimate of 38% is a fundamental model failure.

**2. Systematic bias by firm type:** Does the model consistently underestimate minority representation in certain industries? Consistently overestimate it in others? Systematic bias is fixable — you can apply a correction factor. Random errors are harder to fix.

**3. Confidence calibration:** For cases where the model says it's highly confident, is it actually right more often? If your high-confidence estimates are wrong just as often as your low-confidence ones, the uncertainty bands aren't working.

---

## Key Metric to Track

For each benchmark firm, calculate:

```
error = |estimated_pct_minority - actual_pct_minority|
```

Then group by:
- Industry sector
- Firm size band
- Urban vs. rural county
- Whether county demographics match industry demographics (easy) vs. conflict (hard)

If the error is systematically higher for one group, that tells you exactly where the model needs improvement.
