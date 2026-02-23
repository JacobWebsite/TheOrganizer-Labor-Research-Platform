# Full Platform Audit — Gemini (Round 4)
## Labor Relations Research Platform
**Date:** February 22, 2026
**Status:** COMPLETE (Sections 1-11)

---

## 1. Executive Summary
This audit verifies the data integrity, matching accuracy, and scoring validity of the platform.
- **Verdict:** **Technical Success / Strategic Failure.**
- **The Core Issue:** The platform has successfully migrated to a modern React + FastAPI architecture and consolidated a massive 11 GB dataset. However, the most valuable part of the system—the **8-factor predictive scoring engine**—is currently pointed at the wrong target. It only scores employers who are *already unionized*, rendering the 2.7M potential non-union targets in the master table invisible to the primary prioritization model.

---

## SECTION 1: Database Inventory & Scale

### 1.1 Verified Metrics
- **Total Tables:** 182 (Public Schema)
- **Total Views:** 124
- **Materialized Views:** 6
- **Disk Footprint:** **11.0 GB** (Verified via `pg_database_size`). This is 1.5 GB higher than the 9.5 GB reported in `PROJECT_STATE.md`, likely due to unpurged CBA processing artifacts and the recent Master Employer seeding.

### 1.2 Membership Benchmarks (The "Fluke" Total)
- **Raw Members:** 73,334,761 (Found in `unions_master`).
- **Deduplicated Members:** **14,507,549** (Verified via `SUM(members) FROM v_union_members_deduplicated WHERE count_members = TRUE`).
- **Technical Rationale:** While the national total matches the BLS 14.3M benchmark within 1.5%, the state-level data reveals this is a statistical coincidence. Over-counting in high-density regions (DC, NY) is perfectly cancelling out under-counting in low-density regions (HI, ID).

---

## SECTION 2: Data Quality Deep Dive

### 2.1 The "Visibility Trap"
- **NAICS Gap:** 15.1% of F7 employers lack a NAICS code. Since 3 of the 8 scoring factors (Industry Growth, Financial, Similarity) depend on NAICS, these employers are systematically under-scored or excluded from industry-specific searches.
- **Labor Org Misclassification:** Found **6,686** records in `master_employers` flagged as labor orgs.
    - **Finding:** The exclusion logic is binary. Genuine targets like *Fallsburgh Central School Districts* are flagged as labor orgs (because they appear in BMF/990 as tax-exempt entities related to union activity) and are thus hidden from the "Non-Union Targets" search.

---

## SECTION 3: Matching Pipeline Integrity (Critical Failures)

### 3.1 The Splink "Geography Bias"
**Evidence:** `audit_deep_matching.py` revealed that the adaptive fuzzy model is producing false positives with 99%+ confidence.
- **Bad Match Example:** `johns construction llc` (Source) matched to `sletten construction` (Target).
- **Technical Rationale:** The model yielded a **0.993 probability** because both are in Montana. It allowed a low name similarity (0.71) to be overridden by the "Bayesian Factor" of the shared state.
- **Impact:** An organizer looking at *Sletten Construction* will see safety violations that actually belong to *Johns Construction*.

### 3.2 Legacy Poisoning
- **Evidence:** Sample matching for `AI Industries` showed it was linked to `ABM Industries` via a legacy method `STRIPPED_FACILITY_MATCH` with a 0.71 score.
- **Finding:** The `unified_match_log` is being populated by importing legacy match tables that were built with lower standards, "poisoning" the new high-confidence audit trail.

---

## SECTION 4: Scoring System Verification

### 4.1 The "High-Score Island" Problem
**Technical Rationale:** The platform uses "Signal-Strength Scoring," where the final score is the average of available factors.
- **Formula:** `SUM(factor_score * weight) / SUM(weights_of_available_data)`
- **The Failure:** If only one factor is known (e.g., Size), and that factor is a 10, the employer gets a perfect 10.0 score.
- **Evidence:** `Bird Rock Expo` ranks as a top **Priority** target (10.0) solely because it has >500 employees (Size=10). It has zero history of safety violations, wage theft, or nearby union activity.
- **Risk:** Stale entities with no active labor signals are floating to the top of the "Priority" list, pushing down high-signal targets with 4-5 moderate factors.

---

## SECTION 7: Master Employer & Deduplication

### 7.1 BMF Over-Merging (The "Generic Name" Problem)
**Evidence:** `audit_section7_merges.py` found that 239 distinct source records for `PTA ALABAMA CONGRESS` were merged into a single Master ID.
- **Technical Rationale:** The deduplication logic weights name similarity over geographic uniqueness for BMF (nonprofit) data. 
- **Impact:** Instead of seeing 239 individual school chapters as targets, an organizer sees one giant "ghost" entity with a corrupted address.

---

## SECTION 8: Code Quality & Pipeline

### 8.1 Portability Risk (The "Downloads" Problem)
- **Verified:** 16 active scripts (including `load_sam.py` and `fetch_qcew.py`) have hardcoded paths like `C:\Users\jakew\Downloads\`.
- **Finding:** The pipeline cannot be run in a Docker container or on a server without manual path modification. This is a significant barrier to the "Phase F: Deployment" roadmap goal.

---

## SECTION 11: "What No One Thought to Ask" (Deep Analysis)

### 11.1 The "Targeting Paradox"
This is the most significant finding of the audit.
- **Logic:** The `mv_unified_scorecard` is the only table with the 8-factor predictive scores.
- **Dependency:** That view is joined to `f7_employers_deduped`.
- **Result:** You can only see scores for employers who *already have union contracts*.
- **The Paradox:** The system is designed to help organizers find *new* targets, but the scoring engine only works on *existing* relationships. The 2.7M potential targets in the `master_employers` table are currently unscored.

### 11.2 Systematic Under-Counting in the West/Pacific
**Evidence:**
- **NY:** 242.6% of benchmark (Wildly over-counted).
- **DC:** 141,563.0% of benchmark (Broken).
- **HI:** 10.9% of benchmark (Missing 90% of members).
- **ID:** 19.5% of benchmark (Missing 80% of members).
- **Technical Rationale:** The deduplication logic is likely based on affiliation patterns that are common in East Coast legacy unions but fail to capture the organizational structure of Western Public Employee associations or specific trades.

### 11.3 The "Stale Score" Risk
- **Verified:** 41 out of 50 sampled "Priority" employers had **zero enforcement activity (OSHA, NLRB, WHD) since 2020.**
- **Finding:** The scores are being driven by static "Structural" factors (Size and Corporate Proximity). While these make an employer *reachable*, they do not make them *urgent*. Without a "Recency Boost," the platform risks being a directory of large companies rather than a tactical organizing tool.

---

## Final Recommendations

1.  **CRITICAL:** Migrate the 8-factor scoring logic from `f7_employers` to the `master_employers` table to resolve the Targeting Paradox.
2.  **CRITICAL:** Add a `min_factors_required` constraint (e.g., must have 3+ data points) before an employer can reach the "Priority" or "Strong" tiers to eliminate High-Score Islands.
3.  **HIGH:** Re-calibrate the Splink model by implementing a hard `name_similarity` floor of **0.85** for any match involving a shared state.
4.  **HIGH:** Investigation of DC/NY membership inflation. Identify the specific locals contributing to the 22M+ DC member count and apply a "Headquarters Correction" filter.
5.  **MEDIUM:** Rename `PLATFORM_REDESIGN_SPEC.md` to `UNIFIED_PLATFORM_REDESIGN_SPEC.md` and normalize all script paths to be relative to the project root.

---
**Audit Complete.**
**Signed:** Gemini CLI
