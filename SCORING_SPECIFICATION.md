# Scoring Specification — The Organizer Platform
## Decided in Platform Redesign Interview | February 20, 2026

---

## Overview

Every employer gets a score from 0 to 10 that answers: **"How promising does this employer look as an organizing target?"**

The score is built from 8 separate factors. Each factor gives its own 0-10 rating. If a factor has no data for an employer, it gets skipped entirely — it doesn't count as zero. This is the "signal-strength" approach.

The final score is a **weighted average** of all factors that have data, with weights reflecting organizing strategy priorities.

---

## The 8 Factors

### Factor 1: OSHA Safety Violations (Weight: 1x)

| Element | Decision |
|---------|----------|
| **Method** | Industry-normalized violation count (compared to peers in same sector) |
| **Time Decay** | 5-year half-life — a violation loses half its weight every 5 years |
| **Severity Bonus** | +1 point for willful or repeat violations (capped at 10) |
| **No Data** | Factor skipped entirely |

**Rationale:** Workers at dangerous workplaces have a concrete, personal reason to want a union. Safety is one of the strongest motivators — but it's ranked lower in weight because grievances alone don't make campaigns winnable.

---

### Factor 2: NLRB Activity (Weight: 3x)

| Element | Decision |
|---------|----------|
| **Split** | 70% nearby momentum / 30% own history |
| **Nearby Definition** | Within 25 miles AND similar industry |
| **Wins** | Score positive |
| **Losses** | Score NEGATIVE (penalty — a recent loss is a red flag) |
| **Time Decay** | 7-year half-life on all election data |
| **Latest Election** | Most recent election at the same employer dominates |
| **No Data** | Factor skipped entirely |

**Rationale:** What's happening around an employer — nearby wins at similar workplaces — is a better predictor of future success than the employer's own history. Own history is as likely to be negative (losses = cold shop) as positive. The "hot shop effect" is the main signal.

---

### Factor 3: WHD Wage Theft (Weight: 1x)

| Cases | Score |
|-------|-------|
| 0 cases | 0 |
| 1 case | 5 |
| 2-3 cases | 7 |
| 4+ cases | 10 |

| Element | Decision |
|---------|----------|
| **Dollar Amounts** | Displayed on profile for context but do NOT affect the score |
| **Time Decay** | 5-year half-life (same as OSHA) |
| **No Data** | Factor skipped entirely (~84% of employers have no WHD data) |

**Rationale:** Wage theft is near-binary — the signal is "they got caught" vs "no record." Repeat violations are the strongest signal. Dollar amounts are unreliable for comparison across industries.

---

### Factor 4: Government Contracts (Weight: 2x)

| Contract Levels | Score |
|----------------|-------|
| No contracts | 0 |
| Federal only | 4 |
| State only | 6 |
| City/local only | 7 |
| Any two levels | 8 |
| All three levels | 10 |

| Element | Decision |
|---------|----------|
| **Dollar Value** | Tiebreaker within tiers only (bigger contracts nudge up slightly, can't jump tiers) |
| **Time Decay** | None — a current contract is a current contract |
| **Data Sources** | USASpending (federal) + SAM.gov (federal registry) + NY Open Book (state) + NYC Open Data (city) |
| **No Data** | Factor skipped entirely |

**Rationale:** Government contracts give unions political leverage. State and local contracts weighted higher than federal because state/city officials are more responsive to labor pressure under current political conditions.

---

### Factor 5: Union Proximity (Weight: 3x)

| Relationship | Score |
|-------------|-------|
| 2+ unionized siblings (same parent company) | 10 |
| 1 unionized sibling OR corporate family connection | 5 |
| No relationship | 0 |

| Element | Decision |
|---------|----------|
| **No gradations** | Purely structural — either the connection exists or it doesn't |
| **Corporate family** | Related through ownership chain but not same company; treated same as 1 sibling |
| **No Data** | Factor skipped entirely |

**Rationale:** The most powerful organizing signal. Sibling unions mean proven templates, known playbooks, existing worker connections, and institutional knowledge. This is ranked #1 in importance.

---

### Factor 6: Industry Growth (Weight: 2x)

| Element | Decision |
|---------|----------|
| **Method** | Linear mapping from BLS 10-year industry projections onto 0-10 |
| **Scale** | Fastest growing industry in dataset = 10, fastest shrinking = 0, everything else proportional |
| **Data Level** | Industry-level only (not individual employer financials) |
| **Future** | Blend in employer-specific revenue/employee data when estimation tool is built |
| **No NAICS Code** | Factor skipped entirely (~15% of employers) |

**Rationale:** Strategic resource allocation. Organizing in a growing industry means a growing membership base for years. A dying industry means a shrinking local even after a win.

---

### Factor 7: Employer Size (Weight: 3x)

| Employees | Score |
|-----------|-------|
| Under 15 | 0 |
| 15 → 500 | Ramps linearly from 0 to 10 |
| 500+ | 10 (plateaus) |

| Element | Decision |
|---------|----------|
| **Shape** | Ramp up only — bigger is never worse |
| **Under 15** | Scored at 0 — not realistic targets |
| **No Data** | Factor skipped entirely |

**Rationale:** Size determines viability. Under 15 isn't worth the campaign cost. The sweet spot starts around 50 but bigger employers are never a downgrade — they represent larger potential membership gains.

---

### Factor 8: Statistical Similarity — NEW (Weight: 2x)

| Element | Decision |
|---------|----------|
| **Method** | Combination of how many comparable unionized employers are found AND how close the best matches are |
| **Scope** | Only applies to employers with NO corporate/sibling union connection (otherwise Factor 5 covers them) |
| **Engine** | Uses existing Gower distance comparables engine |
| **No Data** | Factor skipped entirely |

**Rationale:** Even without corporate connections, patterns matter. If every nursing home that looks like this one has a union, that's useful intelligence. Separated from Factor 5 because it's inference rather than known structural relationships.

---

## Factor Weights

| Tier | Weight | Factors |
|------|--------|---------|
| **Top (3x)** | 3x | Union Proximity, Employer Size, NLRB Activity |
| **Middle (2x)** | 2x | Gov Contracts, Industry Growth, Statistical Similarity |
| **Bottom (1x)** | 1x | OSHA Safety, WHD Wage Theft |

Top tier controls ~53% of the final score. Middle tier ~35%. Bottom tier ~12%.

**Admin-configurable:** All weights can be changed through the admin settings panel. No guardrails — full flexibility.

---

## How the Final Score is Calculated

1. Calculate each factor's 0-10 score
2. Skip any factor with no data (signal-strength approach)
3. Multiply each score by its weight (1x, 2x, or 3x)
4. Sum all weighted scores
5. Divide by total weight of factors that had data
6. Result: weighted average from 0-10

**Example:** An employer has data for OSHA (score 6, weight 1x), NLRB (score 8, weight 3x), Gov Contracts (score 7, weight 2x), and Employer Size (score 10, weight 3x).

- Weighted scores: (6×1) + (8×3) + (7×2) + (10×3) = 6 + 24 + 14 + 30 = 74
- Total weight: 1 + 3 + 2 + 3 = 9
- Final score: 74 ÷ 9 = **8.2**

---

## Tier Labels (Percentile-Based)

| Tier | Percentile | Approx Count (of 146,863) |
|------|-----------|---------------------------|
| **Priority** | Top 3% | ~4,400 |
| **Strong** | Next 12% | ~17,600 |
| **Promising** | Next 25% | ~36,700 |
| **Moderate** | Next 35% | ~51,400 |
| **Low** | Bottom 25% | ~36,700 |

- Percentile-based: tiers recalculate on every data refresh
- No user notifications when tiers shift due to other employers' scores changing
- "Priority" is exclusive by design — only ~4,400 employers earn it

---

## Design Philosophy

The weight ranking reflects how experienced organizers actually prioritize:

1. **Strategic positioning** (Is this a smart target?) — Union Proximity, Employer Size, NLRB Activity
2. **Leverage** (Can we apply pressure?) — Gov Contracts, Industry Growth, Statistical Similarity
3. **Worker grievances** (Are workers motivated?) — OSHA Safety, WHD Wage Theft

Grievances make workers angry. Strategy makes campaigns winnable. The scoring system reflects that distinction.
