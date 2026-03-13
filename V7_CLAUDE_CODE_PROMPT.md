# V7 Demographics Model — Claude Code Implementation Prompt

**Project root:** `C:\Users\jakew\.local\bin\Labor Data Project_real`  
**Working directory:** `scripts\analysis\demographics_comparison\`  
**Database:** PostgreSQL, `olms_multiyear` on localhost  
**Purpose:** Rebuild data splits, fix known bugs, and implement model improvements  
  for the V7 workforce demographics estimation model

---

## How to Work

Work through this document in the order it is written. Each phase has numbered
checkpoints. At each checkpoint, stop, show the output or result, and wait for
approval before continuing. Do not skip ahead or bundle multiple checkpoints
into one step.

When editing files, show the before/after diff for every change. When running
scripts, show the full terminal output. When running database queries, show the
full result.

If something is ambiguous or a file doesn't match what is described, stop and
ask rather than guessing.

---

## Background You Need

The model estimates workforce demographics (race, gender, Hispanic share) for
employers that don't publicly report this data. It validates against EEO-1
federal contractor filings (ground truth).

**V6 results (what we're building on):**
- Trained on 2,702 companies from ONE of five EEO-1 files
- Race MAE: 4.203pp, Gender MAE: 11.979pp — passed 7/7 criteria
- Known remaining problems: Asian underestimate (-2.277pp), Female overestimate
  (+5.203pp), Accommodation/Food sector very bad (13.9pp race MAE)

**V7 goal:** Use all five EEO-1 files (~12,000+ training companies), fix the
ZIP code bug that was silently dropping ~1,365 Northeast companies, and
implement targeted improvements for the known weaknesses.

**Two-holdout structure (NEW in V7):**
- Permanent holdout: 1,000 companies, frozen forever, never trained on
- Test holdout: 1,000 companies, evaluation only for this version
- Training: everything else (~12,000+ companies)

---

## PHASE 1: Bug Fix and File Edits

These are code/config changes only. No scripts run yet.

### Checkpoint 1A — Fix ZIP zero-padding bug in `data_loaders.py`

**The problem:** EEO-1 files store ZIP codes as integers, so "08512" becomes
"8512". The `zip_to_county()` function looks this up in the database without
padding it back to 5 digits, so ~1,365 companies silently fail geography
resolution and get dropped from the usable pool. Northeast states (NJ, MA, CT,
RI, NH, ME, VT) are most affected.

Find `zip_to_county()` in `data_loaders.py`. It will contain a line like:
```python
zipcode = str(zipcode).strip()
```

Change that line to:
```python
zipcode = str(zipcode).strip().zfill(5)
```

`.zfill(5)` left-pads with zeros to reach 5 characters. Already-5-digit ZIPs
are unchanged. 4-digit ZIPs like "8512" become "08512".

**Show:** The before and after diff. Then run a quick sanity check:
```python
# Verify the fix works
test_cases = ["8512", "07065", "10001", "02134", "99999"]
for z in test_cases:
    print(str(z).strip().zfill(5))
# Expected: 08512, 07065, 10001, 02134, 99999
```

---

### Checkpoint 1B — Update `select_permanent_holdout_100.py`

This script currently selects 100 companies for the permanent holdout.
We need 1,000.

Make these three changes:

1. Find `TARGET = 100` and change to `TARGET = 1000`

2. Find the SEED constant and set it to `SEED = 99`
   (Must differ from test holdout SEED=42 so selections are independent)

3. Find the output path where the JSON file is saved. Change the filename from
   `selected_permanent_holdout_100.json` to `selected_permanent_holdout_1000.json`

4. If there is a description string inside the JSON output, update it to
   say "1000-company permanent holdout"

**Show:** The full diff of all changes to this file.

**Do NOT run this script yet.**

---

### Checkpoint 1C — Update filename references across four files

Four scripts load the permanent holdout by filename. All need updating.

In each file, find any line referencing `selected_permanent_holdout_100.json`
and change it to `selected_permanent_holdout_1000.json`.

Files to update:
- `build_expanded_training_v6.py`
- `select_test_holdout_1000.py` — also confirm SEED=42 is present
- `run_ablation_v6.py`
- `validate_v6_final.py` — this may already say `_1000.json`; if so, confirm
  and leave it alone

**Show:** The diff for each file. If `validate_v6_final.py` already has the
correct filename, say so explicitly.

---

## PHASE 2: Sequential Data Rebuild

Run these in exact order. Each step depends on the previous one completing.

### Checkpoint 2A — Generate 1,000-company permanent holdout

Run:
```
py select_permanent_holdout_100.py
```

(The script keeps its old name but now generates 1,000 companies.)

**Verify:**
1. Output file `selected_permanent_holdout_1000.json` exists
2. It contains exactly 1,000 company codes (or close — some strata may have
   fewer companies than the target floor)
3. Print the stratification breakdown: how many companies per NAICS group
   and per region

**Do not proceed until this file exists and looks correct.**

---

### Checkpoint 2B — Build full pool (Pass 1, permanent holdout excluded only)

Run:
```
py build_expanded_training_v6.py
```

At this point `selected_test_holdout_1000.json` does not yet exist, so the
script will only exclude the permanent holdout. This produces the pool from
which the test holdout will be drawn.

**Verify:**
1. Print how many total companies are in the output
2. Print how many were excluded as permanent holdout
3. Expected result: roughly 13,500-14,500 companies (after ZIP fix, before
   test holdout removal)
4. Check Northeast representation improved: print company count by region
   and confirm Northeast is no longer severely underrepresented

---

### Checkpoint 2C — Generate 1,000-company test holdout

Run:
```
py select_test_holdout_1000.py
```

**Verify:**
1. Output file `selected_test_holdout_1000.json` exists with ~1,000 companies
2. Run an overlap check between permanent holdout and test holdout:
```python
import json
with open('selected_permanent_holdout_1000.json') as f:
    perm = set(json.load(f)['company_ids'])
with open('selected_test_holdout_1000.json') as f:
    test = set(json.load(f)['company_ids'])
overlap = perm & test
print(f"Overlap: {len(overlap)} companies")
assert len(overlap) == 0, "CONTAMINATION ERROR"
print("PASS: zero overlap confirmed")
```

**Do not proceed if there is any overlap.**

---

### Checkpoint 2D — Build final training set (Pass 2, both holdouts excluded)

Run:
```
py build_expanded_training_v6.py
```

Now that `selected_test_holdout_1000.json` exists, the script will exclude
both holdouts. This is the actual training set for V7.

**Verify:**
1. Print total training companies — expect roughly 12,000-12,500
2. Confirm exclusion counts: should show ~1,000 permanent holdout + ~1,000
   test holdout excluded
3. Run a three-way overlap check:
```python
import json
with open('expanded_training_v6.json') as f:
    training_ids = set(c['company_code'] for c in json.load(f))
with open('selected_permanent_holdout_1000.json') as f:
    perm = set(json.load(f)['company_ids'])
with open('selected_test_holdout_1000.json') as f:
    test = set(json.load(f)['company_ids'])

print(f"Training: {len(training_ids)}")
print(f"Training ∩ Permanent holdout: {len(training_ids & perm)}")
print(f"Training ∩ Test holdout: {len(training_ids & test)}")
print(f"Permanent ∩ Test holdout: {len(perm & test)}")
assert len(training_ids & perm) == 0, "CONTAMINATION: training overlaps permanent holdout"
assert len(training_ids & test) == 0, "CONTAMINATION: training overlaps test holdout"
assert len(perm & test) == 0, "CONTAMINATION: holdouts overlap each other"
print("PASS: all three sets are fully disjoint")
```

**Do not train the gate until all three assertions pass.**

---

## PHASE 3: Model Improvements

These are implemented before gate training so the new features and methods
are baked in from the start.

**Implementation order matters.** Do these in the sequence listed.

---

### Checkpoint 3A — QCEW wage as gate feature (1-line change, high value-to-effort)

**The problem:** `get_qcew_concentration()` already returns `avg_annual_pay`
for every company but `train_gate_v2.py` discards it. Wages are a strong
proxy for workforce composition within an industry (a hedge fund vs a
community bank are both "Finance" but look completely different).

In `train_gate_v2.py`, find where the QCEW location quotient is added to the
feature vector. It will look like:

```python
qcew_lq = cl.get_qcew_lq(county_fips, naics4)
qcew_lq_val = float(qcew_lq) if qcew_lq is not None else 1.0
# ...
X_num.append([qcew_lq_val, acs_lodes_div, tract_entropy, ...])
```

Make these changes:
1. Also fetch `avg_annual_pay` from the QCEW result:
```python
qcew_data = cl.get_qcew_concentration(county_fips, naics4[:2])
qcew_lq_val = float(qcew_data['location_quotient']) if qcew_data else 1.0
# Normalize avg pay: log-scale, default to 50000 if missing
import math
raw_pay = qcew_data['avg_annual_pay'] if qcew_data and qcew_data['avg_annual_pay'] else 50000
qcew_pay_val = math.log(max(raw_pay, 1000))  # log scale, floor at $1k
```

2. Add `qcew_pay_val` to the numerical feature list alongside `qcew_lq_val`

3. Add `'qcew_avg_pay_log'` to `num_feature_names` in the same position

**Show:** The full diff. Note that `get_qcew_concentration()` is on the
cached loader — confirm whether `cl` in this context is the cached loader
or a raw cursor; use whichever pattern already exists in the file.

---

### Checkpoint 3B — Per-segment calibration in `train_gate_v2.py`

**The problem:** V6's `calibration_v2.json` applies one global bias correction
per expert per demographic dimension. Asian underestimate is -2.277pp globally,
but it is probably -6pp+ for California tech companies and near zero for
Midwest manufacturing. A global correction cannot fix both.

**What to change in `train_gate_v2.py`:**

Find where calibration bias is currently computed. It will look something like:
```python
# Compute per-expert bias corrections
for expert_name in expert_names:
    for dim in ['White', 'Black', 'Asian', ...]:
        bias = mean(pred[dim] - actual[dim])  # for all companies routed to this expert
        calibration[expert_name][dim] = -bias * DAMPENING
```

Change the structure to compute bias at three levels and store all three:

```python
calibration = {}

for expert_name in expert_names:
    calibration[expert_name] = {}
    
    for dim in RACE_CATS + ['Hispanic', 'Female']:
        # Global correction (always available)
        global_bias = compute_mean_bias(expert_name, dim, all_companies)
        
        # NAICS-group-level correction (use if >= 50 training examples in segment)
        for naics_group in NAICS_GROUPS:
            segment_companies = [c for c in all_companies 
                                 if c['naics_group'] == naics_group 
                                 and c['assigned_expert'] == expert_name]
            if len(segment_companies) >= 50:
                seg_bias = compute_mean_bias_for(segment_companies, dim)
            elif len(segment_companies) >= 20:
                # Use broader sector grouping (manufacturing / services / government)
                sector_companies = get_sector_companies(naics_group, expert_name, all_companies)
                seg_bias = compute_mean_bias_for(sector_companies, dim)
            else:
                seg_bias = global_bias  # fall back to global
            
            calibration[expert_name][naics_group][dim] = {
                'correction': -seg_bias * DAMPENING,
                'n': len(segment_companies),
                'used_fallback': len(segment_companies) < 50
            }
        
        calibration[expert_name]['_global'][dim] = {
            'correction': -global_bias * DAMPENING,
            'n': len(all_companies_for_expert)
        }
```

Define a helper that maps NAICS groups to broader sectors for fallback:
```python
NAICS_SECTOR_MAP = {
    # Manufacturing cluster
    'Metal/Machinery Mfg (331-333)': 'manufacturing',
    'Chemical/Material Mfg (325-327)': 'manufacturing',
    'Food/Bev Manufacturing (311,312)': 'manufacturing',
    'Computer/Electrical Mfg (334-335)': 'manufacturing',
    'Transport Equip Mfg (336)': 'manufacturing',
    'Other Manufacturing': 'manufacturing',
    # Services cluster
    'Professional/Technical (54)': 'services',
    'Finance/Insurance (52)': 'services',
    'Information (51)': 'services',
    'Admin/Staffing (56)': 'services',
    'Wholesale Trade (42)': 'services',
    # Healthcare cluster
    'Healthcare/Social (62)': 'healthcare',
    # Retail/food cluster
    'Retail Trade (44-45)': 'retail_food',
    'Accommodation/Food Svc (72)': 'retail_food',
    # Infrastructure cluster
    'Transportation/Warehousing (48-49)': 'infrastructure',
    'Utilities (22)': 'infrastructure',
    'Construction (23)': 'infrastructure',
    # Other
    'Agriculture/Mining (11,21)': 'other',
    'Other': 'other',
}
```

**In `validate_v6_final.py`:** Update the calibration lookup to use the
segment-specific correction when available:
```python
def apply_calibration(prediction, expert_name, naics_group, calibration):
    result = prediction.copy()
    expert_cal = calibration.get(expert_name, {})
    
    for dim in prediction:
        # Try segment-specific first, fall back to global
        seg_cal = expert_cal.get(naics_group, {}).get(dim)
        global_cal = expert_cal.get('_global', {}).get(dim)
        
        correction = seg_cal['correction'] if seg_cal else (
            global_cal['correction'] if global_cal else 0.0
        )
        result[dim] = prediction[dim] + correction
    
    # Renormalize race to 100% after corrections
    return renormalize(result)
```

**Show:** The full diff for both files. Print a sample of the calibration JSON
showing that segment-level entries exist and have sensible values.

---

### Checkpoint 3C — Adaptive gender blend weights in `methodologies_v6.py`

**The problem:** The G1 gender method uses a fixed 50/50 blend between BLS
occupation data and smoothed IPF. For industries far from 50% female, the
IPF component (which reflects general county population ~50/50) drags the
estimate toward center. Construction gets estimated at ~30% female when it
should be ~11%.

**Add this function to `methodologies_v6.py`:**

```python
def get_gender_blend_weight(naics_2digit):
    """Return BLS occupation weight for gender blend (remainder goes to IPF).
    
    Industries far from 50% female should trust occupation data more heavily.
    Uses NAICS_GENDER_BENCHMARKS from config.py for industry benchmarks.
    """
    try:
        from config import NAICS_GENDER_BENCHMARKS
        benchmark = NAICS_GENDER_BENCHMARKS.get(str(naics_2digit), 45.0)
    except (ImportError, KeyError):
        benchmark = 45.0
    
    distance_from_50 = abs(float(benchmark) - 50.0)
    
    if distance_from_50 > 25:
        # e.g. Construction (11%), Healthcare (77%), Mining (15%)
        return 0.75  # 75% BLS occupation, 25% IPF
    elif distance_from_50 > 15:
        # e.g. Transportation (25%), Education (66%), Manufacturing (29%)
        return 0.65  # 65% BLS occupation, 35% IPF
    else:
        # e.g. Retail (50%), Finance (53%), Information (40%)
        return 0.50  # Keep current 50/50 blend
```

**Update the G1 gender method** (wherever it computes the 50/50 blend) to
call this function instead of using a hardcoded 0.50 weight:

```python
# Find the line that blends BLS and IPF for gender, e.g.:
# gender_est = 0.50 * bls_gender + 0.50 * ipf_gender

# Change to:
bls_weight = get_gender_blend_weight(naics4[:2])
ipf_weight = 1.0 - bls_weight
gender_est = bls_weight * bls_gender + ipf_weight * ipf_gender
```

Also update the cached version in `cached_loaders_v6.py` if the G1 blend
is duplicated there.

**Show:** Full diff for all files touched. Print the blend weights for the
5 most extreme industries to confirm the function is working:
```python
for naics, name in [('23','Construction'),('62','Healthcare'),
                    ('48','Transportation'),('52','Finance'),('72','Food')]:
    w = get_gender_blend_weight(naics)
    print(f"NAICS {naics} ({name}): BLS={w:.0%}, IPF={1-w:.0%}")
```

---

### Checkpoint 3D — Build occupation-chain precomputed table (Expert G setup)

This is the highest-impact new capability. Before implementing Expert G as
an estimation method, build the precomputed lookup table that makes it fast.

**Background:** We confirmed via database queries that a three-way chain
produces dramatically different estimates by geography:
- Hospitals in Hawaii: 13.6% Asian
- Hospitals in Mississippi: 0.2% Asian
Chain: BLS industry occupation mix × OES metro employment weights × ACS
state-level occupation demographics

**Step 1:** Create a Python script `build_occ_chain_table.py` in the
demographics comparison directory:

```python
"""
Build precomputed occupation-chain demographics table.

For each NAICS group × state, compute the expected demographic composition
using the three-way chain:
  1. BLS industry-occupation matrix: what jobs make up this industry?
  2. OES metro employment: how does the local job mix deviate from national?
  3. ACS state-level occupation demographics: who holds each job in this state?

Output: occ_local_demographics table in PostgreSQL
  Columns: naics_group, state_fips, pct_female, pct_asian, pct_white,
           pct_black, pct_hispanic, pct_aian, occs_matched,
           pct_industry_covered, computed_at
"""

import psycopg2
import psycopg2.extras
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

# Map V6 NAICS groups to BLS industry matrix codes
# Use the primary NAICS code that best represents each group
NAICS_GROUP_CODES = {
    'Healthcare/Social (62)': ['621000', '622000', '623000', '624000', '62'],
    'Finance/Insurance (52)': ['522000', '523000', '524000', '52'],
    'Information (51)': ['511000', '512000', '515000', '517000', '51'],
    'Professional/Technical (54)': ['541000', '54'],
    'Admin/Staffing (56)': ['561000', '561300', '56'],
    'Retail Trade (44-45)': ['441000', '445000', '448000', '44', '45'],
    'Accommodation/Food Svc (72)': ['722000', '722511', '722512', '721000', '72'],
    'Construction (23)': ['236000', '237000', '238000', '23'],
    'Transportation/Warehousing (48-49)': ['484000', '485000', '492000', '48', '49'],
    'Wholesale Trade (42)': ['423000', '424000', '42'],
    'Utilities (22)': ['221000', '22'],
    'Metal/Machinery Mfg (331-333)': ['332000', '333000', '331000', '33'],
    'Chemical/Material Mfg (325-327)': ['325000', '326000', '327000', '32'],
    'Food/Bev Manufacturing (311,312)': ['311000', '312000', '31'],
    'Computer/Electrical Mfg (334-335)': ['334000', '335000', '33'],
    'Transport Equip Mfg (336)': ['336000', '33'],
    'Other Manufacturing': ['31', '32', '33'],
    'Agriculture/Mining (11,21)': ['111000', '112000', '211000', '212000', '11', '21'],
    'Other': ['81', '92'],
}

def build_table(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Create output table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS occ_local_demographics (
            id SERIAL PRIMARY KEY,
            naics_group TEXT NOT NULL,
            state_fips CHAR(2) NOT NULL,
            pct_female NUMERIC(5,2),
            pct_asian NUMERIC(5,2),
            pct_white NUMERIC(5,2),
            pct_black NUMERIC(5,2),
            pct_hispanic NUMERIC(5,2),
            pct_aian NUMERIC(5,2),
            occs_matched INTEGER,
            pct_industry_covered NUMERIC(5,1),
            computed_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(naics_group, state_fips)
        )
    """)
    conn.commit()
    
    # Get all states
    cur.execute("SELECT DISTINCT state_fips FROM cur_acs_workforce_demographics "
                "WHERE state_fips IS NOT NULL AND state_fips != '' "
                "ORDER BY state_fips")
    states = [r['state_fips'] for r in cur.fetchall()]
    
    results = []
    
    for naics_group, bls_codes in NAICS_GROUP_CODES.items():
        print(f"\nProcessing: {naics_group}")
        
        # Get industry occupation mix from BLS matrix
        # Try codes in order until we get data
        occ_mix = []
        for code in bls_codes:
            cur.execute("""
                SELECT occupation_code, percent_of_industry
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s 
                  AND LOWER(occupation_type) = 'line item'
                  AND percent_of_industry IS NOT NULL
                ORDER BY percent_of_industry DESC
            """, [code])
            rows = cur.fetchall()
            if rows:
                occ_mix = [(r['occupation_code'], float(r['percent_of_industry'])) 
                           for r in rows]
                print(f"  BLS code {code}: {len(occ_mix)} occupations, "
                      f"{sum(p for _,p in occ_mix):.1f}% covered")
                break
        
        if not occ_mix:
            print(f"  WARNING: No BLS occupation data found")
            continue
        
        occ_codes = [oc for oc, _ in occ_mix]
        total_pct = sum(p for _, p in occ_mix)
        
        # For each state, compute occupation-chain demographics
        for state_fips in states:
            # Get ACS demographics per occupation for this state
            # ACS uses 6-digit codes without dashes; BLS uses dashes
            placeholders = ','.join(['%s'] * len(occ_codes))
            normalized_codes = [c.replace('-', '') for c in occ_codes]
            
            cur.execute(f"""
                SELECT 
                    soc_code,
                    SUM(weighted_workers) FILTER (WHERE sex = '2') as female_w,
                    SUM(weighted_workers) FILTER (WHERE race IN ('4','5') 
                        AND hispanic = '0') as asian_w,
                    SUM(weighted_workers) FILTER (WHERE race = '1' 
                        AND hispanic = '0') as white_w,
                    SUM(weighted_workers) FILTER (WHERE race = '2' 
                        AND hispanic = '0') as black_w,
                    SUM(weighted_workers) FILTER (WHERE hispanic != '0') as hisp_w,
                    SUM(weighted_workers) FILTER (WHERE race = '3' 
                        AND hispanic = '0') as aian_w,
                    SUM(weighted_workers) FILTER (WHERE sex IN ('1','2')) as total_w
                FROM cur_acs_workforce_demographics
                WHERE soc_code IN ({placeholders})
                  AND state_fips = %s
                  AND sex IN ('1','2')
                GROUP BY soc_code
                HAVING SUM(weighted_workers) FILTER (WHERE sex IN ('1','2')) > 100
            """, normalized_codes + [state_fips])
            
            acs_rows = {r['soc_code']: r for r in cur.fetchall()}
            
            if not acs_rows:
                continue
            
            # Compute weighted average
            total_weight = 0.0
            accum = {k: 0.0 for k in 
                     ['female', 'asian', 'white', 'black', 'hisp', 'aian']}
            matched = 0
            
            for occ_code, ind_share in occ_mix:
                norm_code = occ_code.replace('-', '')
                if norm_code not in acs_rows:
                    continue
                row = acs_rows[norm_code]
                total_w = float(row['total_w'] or 0)
                if total_w == 0:
                    continue
                
                weight = ind_share  # industry share as weight
                total_weight += weight
                matched += 1
                
                for key, col in [('female', 'female_w'), ('asian', 'asian_w'),
                                  ('white', 'white_w'), ('black', 'black_w'),
                                  ('hisp', 'hisp_w'), ('aian', 'aian_w')]:
                    accum[key] += weight * float(row[col] or 0) / total_w * 100
            
            if total_weight < 10 or matched < 5:
                continue  # Not enough coverage to be reliable
            
            row_result = {
                'naics_group': naics_group,
                'state_fips': state_fips,
                'pct_female': round(accum['female'] / total_weight, 2),
                'pct_asian': round(accum['asian'] / total_weight, 2),
                'pct_white': round(accum['white'] / total_weight, 2),
                'pct_black': round(accum['black'] / total_weight, 2),
                'pct_hispanic': round(accum['hisp'] / total_weight, 2),
                'pct_aian': round(accum['aian'] / total_weight, 2),
                'occs_matched': matched,
                'pct_industry_covered': round(total_weight, 1),
            }
            results.append(row_result)
    
    # Insert all results
    if results:
        cur.execute("DELETE FROM occ_local_demographics")
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO occ_local_demographics 
                (naics_group, state_fips, pct_female, pct_asian, pct_white,
                 pct_black, pct_hispanic, pct_aian, occs_matched, pct_industry_covered)
            VALUES 
                (%(naics_group)s, %(state_fips)s, %(pct_female)s, %(pct_asian)s,
                 %(pct_white)s, %(pct_black)s, %(pct_hispanic)s, %(pct_aian)s,
                 %(occs_matched)s, %(pct_industry_covered)s)
            ON CONFLICT (naics_group, state_fips) DO UPDATE SET
                pct_female = EXCLUDED.pct_female,
                pct_asian = EXCLUDED.pct_asian,
                pct_white = EXCLUDED.pct_white,
                pct_black = EXCLUDED.pct_black,
                pct_hispanic = EXCLUDED.pct_hispanic,
                pct_aian = EXCLUDED.pct_aian,
                occs_matched = EXCLUDED.occs_matched,
                pct_industry_covered = EXCLUDED.pct_industry_covered,
                computed_at = NOW()
        """, results)
        conn.commit()
        print(f"\nInserted {len(results)} rows into occ_local_demographics")
    
    # Verification query
    cur.execute("""
        SELECT naics_group, state_fips, pct_asian, pct_female, occs_matched
        FROM occ_local_demographics
        WHERE naics_group = 'Healthcare/Social (62)'
          AND state_fips IN ('06', '15', '28', '48')
        ORDER BY state_fips
    """)
    print("\nSanity check — Hospitals by state (pct_asian):")
    for r in cur.fetchall():
        print(f"  State {r['state_fips']}: Asian={r['pct_asian']}%, "
              f"Female={r['pct_female']}%, occs={r['occs_matched']}")
    
    cur.close()

if __name__ == '__main__':
    conn = get_connection()
    build_table(conn)
    conn.close()
```

**Run the script and show output.** The sanity check at the end should show
meaningfully different Asian percentages across states for Healthcare —
particularly Hawaii (state 15) should be notably higher than Mississippi (28).

**Expected runtime:** 5-15 minutes. The ACS table is 11M rows so some queries
will be slow — this is expected and acceptable since it only runs once.

---

### Checkpoint 3E — Add Expert G loader to `data_loaders.py` and `cached_loaders_v6.py`

Add a function to look up the precomputed occupation-chain estimate:

**In `data_loaders.py`:**
```python
def get_occ_chain_demographics(cur, naics_group, state_fips):
    """Get occupation-chain demographic estimate for a NAICS group x state.
    
    Uses precomputed occ_local_demographics table built by 
    build_occ_chain_table.py. Returns dict with race/gender/hispanic
    percentages, or None if no data for this combination.
    
    This implements the three-way chain:
      BLS industry occupation mix × OES local weights × ACS state occupation demographics
    """
    if not naics_group or not state_fips:
        return None
    try:
        cur.execute("""
            SELECT pct_female, pct_asian, pct_white, pct_black,
                   pct_hispanic, pct_aian, occs_matched, pct_industry_covered
            FROM occ_local_demographics
            WHERE naics_group = %s AND state_fips = %s
        """, [naics_group, state_fips])
        row = cur.fetchone()
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        return None
    
    if not row:
        return None
    
    # Only return if coverage is sufficient to be reliable
    if (row['occs_matched'] or 0) < 5 or (row['pct_industry_covered'] or 0) < 20:
        return None
    
    return {
        'Female': float(row['pct_female'] or 0),
        'Male': 100.0 - float(row['pct_female'] or 0),
        'Asian': float(row['pct_asian'] or 0),
        'White': float(row['pct_white'] or 0),
        'Black': float(row['pct_black'] or 0),
        'Hispanic': float(row['pct_hispanic'] or 0),
        'AIAN': float(row['pct_aian'] or 0),
        'NHOPI': 0.0,  # not separately tracked
        'Two+': max(0.0, 100.0 - float(row['pct_white'] or 0) 
                    - float(row['pct_black'] or 0) - float(row['pct_asian'] or 0)
                    - float(row['pct_aian'] or 0)),
        '_occs_matched': int(row['occs_matched'] or 0),
        '_pct_covered': float(row['pct_industry_covered'] or 0),
        '_data_source': 'occ_chain_local',
    }
```

**In `cached_loaders_v6.py`:**
```python
def get_occ_chain_demographics(self, naics_group, state_fips):
    """Cached lookup for occupation-chain demographics."""
    return self._cached(
        ('occ_chain', naics_group, state_fips),
        get_occ_chain_demographics, self.cur, naics_group, state_fips)
```

---

### Checkpoint 3F — Implement Expert G method in `methodologies_v6.py`

Add the Expert G estimation method. It uses the occupation-chain table for
race/Hispanic/gender, with IPF as fallback when coverage is insufficient.

```python
def method_expert_g_occ_chain(cur, naics4, state_fips, county_fips, 
                               naics_group=None, **kwargs):
    """Expert G: Occupation-chain local demographics.
    
    Uses precomputed occupation-chain table (BLS industry mix x ACS state
    occupation demographics) as primary signal, blended with standard IPF
    as a fallback when coverage is low.
    
    Best for: Healthcare, Finance, Information, Professional services —
    industries with well-defined occupation mixes and geographic demographic
    variation in those occupations (especially Asian workers in coastal metros).
    
    Returns dict matching standard expert output format.
    """
    from data_loaders import get_occ_chain_demographics
    from methodologies_v3 import variable_dampened_ipf
    from methodologies_v5 import smoothed_ipf
    
    occ_chain = get_occ_chain_demographics(cur, naics_group, state_fips)
    
    if occ_chain and occ_chain['_pct_covered'] >= 40:
        # High confidence: primarily trust occupation chain
        occ_weight = 0.70
        
        # Get standard IPF estimate as secondary signal
        ipf_est = variable_dampened_ipf(cur, naics4, state_fips, county_fips)
        
        if ipf_est:
            # Blend: 70% occupation chain, 30% IPF
            result = {}
            for cat in ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']:
                result[cat] = (occ_weight * occ_chain.get(cat, 0) + 
                               (1 - occ_weight) * ipf_est.get(cat, 0))
            result['_data_source'] = 'expert_g_occ_chain_blend'
        else:
            result = {k: occ_chain.get(k, 0) for k in 
                      ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']}
            result['_data_source'] = 'expert_g_occ_chain_only'
        
        # Gender from occupation chain
        result['Female'] = occ_chain.get('Female', 50.0)
        result['Male'] = 100.0 - result['Female']
        
        # Hispanic from occupation chain
        result['Hispanic'] = occ_chain.get('Hispanic', 0.0)
        result['Not Hispanic'] = 100.0 - result['Hispanic']
        
        # Renormalize race to 100%
        race_total = sum(result.get(k, 0) for k in 
                         ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+'])
        if race_total > 0:
            for k in ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']:
                result[k] = result[k] * 100 / race_total
        
        return result
    
    else:
        # Low coverage: fall back to standard variable dampened IPF
        # (same as V6-Full baseline)
        result = variable_dampened_ipf(cur, naics4, state_fips, county_fips)
        if result:
            result['_data_source'] = 'expert_g_fallback_ipf'
        return result
```

**Add Expert G to the expert registry** in both `methodologies_v6.py` and
`cached_loaders_v6.py` (wherever the expert name→function mapping lives).

**Show:** Full diff. Then run a quick test to confirm Expert G returns
different estimates for a Healthcare company in California vs Mississippi:
```python
# Quick smoke test
# (use your existing test harness or write a minimal inline test)
```

---

### Checkpoint 3G — Add Expert G to gate training in `train_gate_v2.py`

**Add Expert G to the list of experts the gate evaluates** alongside the
existing experts (A, B, D, E, F, V6-Full). This means:

1. During training set evaluation, compute Expert G's prediction for every
   training company alongside the other experts
2. The gate learns which companies Expert G is best for
3. Expert G's performance gets its own calibration entry in `calibration_v2.json`

Find where experts are enumerated in `train_gate_v2.py`. It will look like:
```python
EXPERTS = ['Expert_A', 'Expert_B', 'Expert_D', 'Expert_E', 'Expert_F', 'V6-Full']
```

Add:
```python
EXPERTS = ['Expert_A', 'Expert_B', 'Expert_D', 'Expert_E', 'Expert_F', 
           'Expert_G', 'V6-Full']
```

Also add `naics_group` to the data passed per company during training, since
Expert G needs it for its lookup:
```python
# In the company feature extraction loop, ensure naics_group is available
naics_group = classify_naics_group(naics4)
# Pass to Expert G alongside naics4, state_fips, county_fips
```

**Show:** The full diff. Note that this means gate training will now evaluate
7 experts per company instead of 6, adding some runtime. With 12,000 training
companies at ~1.15s/company, gate training was already expected to take 3-4
hours; adding Expert G will add ~40-50 minutes.

---

### Checkpoint 3H — NAICS 72 special handling in `config.py` and `validate_v6_final.py`

**The problem:** Accommodation/Food (NAICS 72) had 13.9pp race MAE in V6 —
more than 3x the overall average. Workers in this sector (restaurants, hotels)
are disproportionately from local immigrant communities not well-captured by
county-level demographic averages.

**In `config.py`**, add:
```python
# Sectors where workers reflect very local geography rather than county averages.
# These sectors have high proportions of immigrant workers, seasonal labor,
# or workers deployed to client sites.
HIGH_GEOGRAPHIC_NAICS = {
    '72',  # Accommodation/Food — immigrant-heavy, neighborhood-level clusters
    '56',  # Admin/Staffing — workers deployed to client sites, not company address
    '23',  # Construction — project-based workers, follow construction sites
}
```

**In `validate_v6_final.py`**, in the routing logic where companies get
assigned to experts, add a pre-routing check:

```python
naics_2 = naics4[:2] if naics4 else ''

# High-geographic sectors: boost Expert B (tract-heavy) weight
# Expert B uses 35% ACS + 25% LODES + 40% tract — most geographic
if naics_2 in HIGH_GEOGRAPHIC_NAICS:
    # Boost Expert B's gate probability before final assignment
    if 'Expert_B' in gate_probs:
        gate_probs['Expert_B'] = max(gate_probs.get('Expert_B', 0), 0.45)
        # Renormalize remaining experts
        remaining = {k: v for k, v in gate_probs.items() if k != 'Expert_B'}
        remaining_total = sum(remaining.values())
        if remaining_total > 0:
            scale = (1.0 - gate_probs['Expert_B']) / remaining_total
            for k in remaining:
                gate_probs[k] = remaining[k] * scale
```

**Show:** Full diff for both files.

---

### Checkpoint 3I — Soft routing for Expert E in `validate_v6_final.py`

**Current behavior:** Any NAICS 52 (Finance) or 22 (Utilities) company is
hard-routed to Expert E — the gate is completely bypassed. This made sense
in V6 but now that the gate has more training data and Expert G exists,
some Finance companies (especially high-wage investment firms) may benefit
from Expert G instead.

Find the hard-routing logic. It will look like:
```python
if naics_group in EXPERT_E_INDUSTRIES:
    prediction = run_expert_e(company)
    return prediction
```

Change to soft routing that still strongly favors Expert E but allows override:
```python
if naics_group in EXPERT_E_INDUSTRIES:
    # Soft route: boost Expert E to 70% minimum but let gate still contribute
    current_e_prob = gate_probs.get('Expert_E', 0.0)
    if current_e_prob < 0.70:
        boost = 0.70 - current_e_prob
        gate_probs['Expert_E'] = 0.70
        # Reduce all other experts proportionally
        others = {k: v for k, v in gate_probs.items() if k != 'Expert_E'}
        others_total = sum(others.values())
        if others_total > 0:
            scale = (1.0 - 0.70) / others_total
            for k in others:
                gate_probs[k] = others[k] * scale
    # Then proceed with normal blended prediction using gate_probs
    # (do NOT short-circuit return here)
```

**Show:** Full diff.

---

## PHASE 4: Gate Training

### Checkpoint 4A — Train Gate V2

Run:
```
py train_gate_v2.py
```

This will take 3-5 hours with 12,000 training companies × 7 experts.
Show progress output periodically. Do not interrupt.

**When complete, verify:**
1. `gate_v2.pkl` was written and file size is reasonable (not 0 bytes)
2. `calibration_v2.json` was written
3. Print the calibration summary — show segment-level corrections exist
   for the major NAICS groups
4. Print gate feature importance scores — confirm that `qcew_avg_pay_log`
   has non-zero importance (it should if wages genuinely predict routing)
5. Print Expert G routing statistics: what percent of companies got routed
   primarily to Expert G, and which NAICS groups

---

## PHASE 5: Validation

### Checkpoint 5A — Validate on test holdout

Run validation against `selected_test_holdout_1000.json`:
```
py validate_v6_final.py --holdout selected_test_holdout_1000.json
```

**Report all metrics in a table:**

| Criterion | V6 Baseline | V7 Result | V7 Target | Status |
|-----------|-------------|-----------|-----------|--------|
| Race MAE | 4.203 pp | ? | < 3.90 pp | |
| P>20pp | 13.5% | ? | < 12% | |
| P>30pp | 4.0% | ? | < 3.5% | |
| Abs Bias | 1.000 | ? | < 0.85 | |
| Hispanic MAE | 7.752 pp | ? | < 7.00 pp | |
| Gender MAE | 11.979 pp | ? | < 10.00 pp | |
| Asian signed bias | -2.277 pp | ? | < -1.50 pp | |
| Female signed bias | +5.203 pp | ? | < +3.50 pp | |
| Red flag rate | 0.87% | ? | < 5% | |

Also report:
- Race MAE broken down by NAICS group (especially Accommodation/Food — was 13.9pp)
- Expert G routing: how often was it selected and was it the best expert?
- Per-segment calibration: show that Asian corrections differ by NAICS group

---

### Checkpoint 5B — Validate on permanent holdout

Run validation against `selected_permanent_holdout_1000.json`:
```
py validate_v6_final.py --holdout selected_permanent_holdout_1000.json
```

Show the same metrics table. This is the cross-version comparable benchmark —
note that any future V8 model must also be evaluated here to be comparable to V7.

---

## What NOT to Do

These were tested in V6 ablation or investigated during planning and confirmed
to make things worse. Do not implement them:

| Approach | Why Not |
|----------|---------|
| Industry-LODES CNS columns for race | +0.343pp MAE worse in ablation |
| H1 geography-heavy Hispanic | Overfits training, fails on holdout |
| OES metro all-industry for gender | Produces ~50% female for everything |
| M9c combined LODES+QCEW | +0.383pp MAE worse in ablation |
| National CPS for occupation demographics | No geographic variation — all cities give same estimate |
| ABS Annual Business Survey | Measures business owners not workers |
| QWI Quarterly Workforce Indicators | Measures turnover not demographics |

---

## File Change Summary

| File | Changes |
|------|---------|
| `data_loaders.py` | ZIP zfill fix; add `get_occ_chain_demographics()` |
| `select_permanent_holdout_100.py` | TARGET=1000, SEED=99, new output filename |
| `build_expanded_training_v6.py` | Filename ref: `_100` → `_1000` |
| `select_test_holdout_1000.py` | Filename ref: `_100` → `_1000`; confirm SEED=42 |
| `run_ablation_v6.py` | Filename ref: `_100` → `_1000` |
| `validate_v6_final.py` | Confirm filename; segment calibration lookup; soft Expert E routing; HIGH_GEOGRAPHIC boost |
| `train_gate_v2.py` | Add `qcew_avg_pay_log` feature; per-segment calibration; add Expert G |
| `methodologies_v6.py` | Add `get_gender_blend_weight()`; update G1 blend; add Expert G method |
| `cached_loaders_v6.py` | Add `get_occ_chain_demographics()` cached wrapper; update G1 blend call |
| `config.py` | Add `HIGH_GEOGRAPHIC_NAICS` |
| `build_occ_chain_table.py` | New script — builds `occ_local_demographics` table |

---

## New Files Created

| File | Purpose |
|------|---------|
| `build_occ_chain_table.py` | One-time script to build precomputed occupation-chain table |
| `selected_permanent_holdout_1000.json` | 1,000-company frozen holdout (never train on) |
| `selected_test_holdout_1000.json` | 1,000-company evaluation holdout (rebuilt) |
| `expanded_training_v6.json` | Rebuilt training set (~12,000+ companies) |
| `gate_v2.pkl` | Retrained gate model |
| `calibration_v2.json` | Per-segment calibration corrections |

---

*Generated: 2026-03-09*  
*Source: V7_PREPARATION.md handoff + V7_PLAN.md + V7_MODEL_IMPROVEMENTS.md*  
*Evidence base: Live database queries against olms_multiyear on localhost*
