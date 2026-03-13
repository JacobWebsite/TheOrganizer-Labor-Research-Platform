# V7 Demographics Model -- Tuning Recommendations

**Date:** 2026-03-10
**Context:** V7 passes 5/7 acceptance criteria on test holdout, 4/7 on permanent holdout. Failing metrics are P>20pp (16.25% vs <16% target), P>30pp (7.06% vs <6%), and permanent holdout Race MAE (4.62 vs <4.50). Full error distribution analysis in `V7_ERROR_DISTRIBUTION.md`.

---

## Why V7 Fails P>20 and P>30

The calibration system already corrects the **average** bias -- every expert gets a -5 to -21pp White correction and +6 to +14pp Black correction for Healthcare. That's why overall signed bias is near zero (0.15pp). **The problem is variance within sectors.**

A nursing home in rural Vermont and a hospital in Atlanta both get the same Healthcare calibration correction, but their actual workforces are completely different. The average correction helps one and hurts the other. The 161 companies above 20pp error are not random -- they are concentrated in:

- **Healthcare/Social** (41 companies, 25% of the >20pp bucket)
- **Admin/Staffing** (16 companies, 10%)
- **Southern region** (80 companies, 50% -- vs 35% of all companies)

The systematic pattern: we over-predict White and under-predict Black for diverse-workforce companies in the South and West.

---

## Recommendations

### 1. Industry x Region Calibration (Highest Impact, Easiest)

**Current:** Calibration is per-NAICS-group globally.
**Proposed:** Split into NAICS-group x Region (4 regions: South, West, Midwest, Northeast).

Healthcare-South would get a much larger White-down/Black-up correction than Healthcare-Midwest. With ~1,500 Healthcare training companies, even split 4 ways you'd have ~375 per region -- well above the 50-company threshold for segment calibration.

This directly attacks the 47-52% South concentration in the >20pp bucket. Could recover 15-25 companies from the >20pp bucket, potentially dropping P>20 below 16%.

**Effort:** Low. Only requires changes to `train_gate_v2.py` calibration logic and `validate_v6_final.py` `apply_calibration()`.

---

### 2. County Minority Share as a Calibration Axis

Even better than region: use the county's actual minority share (from LODES/ACS) as a continuous feature for calibration segmentation. Companies in >40% minority counties systematically need larger Black-up corrections than companies in <15% minority counties.

Could bin into 3 tiers (low <20%, mid 20-40%, high >40% minority) and calibrate within each tier, cross-cut with NAICS group. This captures the geographic variation more precisely than 4 broad regions.

**Effort:** Medium. Requires computing county minority share during training, adding it to the calibration key, and passing it through at prediction time.

---

### 3. Expert G is Barely Used (4 companies on test holdout)

The occupation-chain Expert G only got routed to 4 companies. Either the gate doesn't trust it (low training accuracy) or it's too similar to other experts.

Options:
- **Hard-route Expert G for Healthcare** -- it has the smallest White bias (-0.9pp vs -4.7 to -20.7 for other experts), meaning its raw estimates are closest to reality for healthcare companies
- **Investigate why the gate avoids it** -- it may need more differentiated training features
- **Drop it entirely** and reclaim the probability mass for better experts, simplifying the gate from 7 to 6 classes

**Effort:** Low (hard-routing) to Medium (investigation).

---

### 4. Reduce Expert E Over-Routing

Expert E gets 272 companies on the test holdout but was designed for Finance/Utilities (~150 companies in the holdout). It's being routed to non-Finance companies where it may not be the best choice.

The soft override already boosts E to 0.70 for Finance, but the gate is also naturally routing other companies to E. Could add a soft **penalty** for E outside Finance/Utilities (e.g., cap E probability at 0.30 for non-Finance sectors).

**Effort:** Low. Single change in `predict_v6()` soft routing logic.

---

### 5. Consider a Dedicated Healthcare Expert

Healthcare is the single worst sector (MAE 6.1, 25% of the >20pp bucket). It may warrant a dedicated Expert H that uses different source weighting:

- Heavier LODES/tract-level data (workplace-based demographics)
- Less ACS weighting (residence-based demographics)
- Possibly BLS Occupational Employment data for healthcare-specific occupation mixes (nurses, aides, etc. have very different demographics)

Healthcare workers often commute from different neighborhoods than where the facility is located. Workplace-based data should better capture actual workforce composition than residential census data.

**Effort:** High. Requires building a new expert methodology, retraining the gate, and recomputing calibration.

---

### 6. Admin/Staffing May Need a Confidence Downgrade

Staffing agencies deploy workers to client sites. The company HQ ZIP code has almost no relationship to where workers actually are. 20% of staffing companies land in the >30pp catastrophic bucket.

Rather than trying to estimate accurately with data that fundamentally doesn't apply, the honest move may be to:
- Flag NAICS 56 companies as structurally low-confidence
- Widen the RED/YELLOW confidence tier for staffing (e.g., force YELLOW minimum)
- Accept that these estimates carry a large uncertainty range

This wouldn't improve MAE or P>20, but it would correctly communicate uncertainty to downstream consumers.

**Effort:** Low. Configuration change in confidence tier logic.

---

### 7. Increase DAMPENING from 0.80 to 0.90

The calibration currently applies only 80% of the measured training bias (`DAMPENING = 0.80`). For Healthcare where the bias is massive (White off by 7-21pp raw), applying 90% might close the gap.

Dampening protects against overfitting to training data, but with 1,500+ Healthcare training samples the overfitting risk is low. Could test 0.85 and 0.90 on the test holdout without retraining the gate.

**Effort:** Minimal. Single constant change + re-run validation.

---

### 8. Architecture Simplification (V8 Consideration)

The 7-expert gate system achieves 29.2% classification accuracy (vs 14.3% random baseline for 7 classes). This adds substantial complexity -- 7 expert implementations, a trained gate model, per-expert per-segment calibration -- without proportional accuracy gains.

A simpler architecture might perform equally well or better:
- **One strong base estimator** (V6-Full or best single expert)
- **Industry x Geography stratified calibration** (the calibration is doing the heavy lifting anyway)
- **Hard-coded routing only for proven specialists** (Expert E for Finance, possibly Expert G for Healthcare)

Worth benchmarking "V6-Full + better stratified calibration" against the full gate pipeline. If the simpler approach matches or beats it, the reduced complexity is a clear win for maintainability and debuggability.

**Effort:** Medium. Requires running V6-Full-only validation and building richer calibration.

---

## Priority Order

| # | Recommendation | Expected Impact | Effort |
|---|---------------|----------------|--------|
| 7 | Increase DAMPENING to 0.90 | Low-Medium | Minimal |
| 1 | Industry x Region calibration | High | Low |
| 4 | Cap Expert E outside Finance | Medium | Low |
| 3 | Hard-route Expert G for Healthcare | Medium | Low |
| 6 | Confidence downgrade for Staffing | Quality signal | Low |
| 2 | County minority share calibration | High | Medium |
| 5 | Dedicated Healthcare expert | High | High |
| 8 | Architecture simplification | Strategic | Medium |

Recommendations 7, 1, and 4 could be implemented and tested in a single session. If Industry x Region calibration alone closes the P>20 gap, the more complex options (2, 5, 8) may not be needed.
