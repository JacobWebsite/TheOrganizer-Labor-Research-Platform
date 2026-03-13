# Analysis Results & Data Operations (2026-03)

## RPE Dual Validation (2026-03-03)
- **Script:** `scripts/analysis/validate_rpe_estimates.py` (rewritten for dual ground truths)
- **Methodology doc:** `docs/rpe_methodology_summary.md`
- **SUSB data:** 261,853 rows (2,055 national + 84,354 state + 175,444 county)
- **Supervisor multiplier:** Built from `bls_industry_occupation_matrix` (355 NAICS prefixes, SOC 11-xxxx + first-line supervisors, default 1.15, median 1.134)
- **Ground Truth A (NLRB whole-company elections):**
  - 2,002 raw -> 625 after whole-company filter (known_emp<200, eligible_voters/known_emp>=0.5) -> 530 with RPE match
  - actual_emp = eligible_voters * supervisor_multiplier
  - Results: National Med.Err=95.2%, W50%=18.1% | State W50%=15.8% | County W50%=16.4%
- **Ground Truth B (990 self-reported employees):**
  - 8,759 raw -> 7,793 with RPE match
  - Results: National Med.Err=58.8%, W50%=49.1% | State W50%=48.0% | County W50%=47.2%
- **Cross-validation verdict: Geographic RPE does NOT help.** Both GTs agree state/county are 1-2pp *worse* than national.
  - State W50% delta: GT-A -2.3pp, GT-B -1.0pp
  - County W50% delta: GT-A -1.7pp, GT-B -1.8pp
- **Sector highlights (GT-B):** Healthcare best (50% err, 57% W50%), Construction worst (64% err, 41% W50%), Information worst (76% err, 25% W50%)
- **Size effect:** Larger employers more accurate (500+: 37% err, 70% W50% vs <25: 65% err, 46% W50%)
- **Recommendation:** Use national RPE only; drop geographic cascade from scoring CTEs
- **Remaining tuning directions:**
  1. Filter out holding companies / pass-through entities before applying RPE
  2. Sector-specific bias corrections (wholesale, construction)
  3. Add Mergent Sales column for private-sector validation
- **MV NOT rebuilt** -- national-only simplification justified but not yet applied

## Mergent Bulk Import (2026-03-02)
- **Universe:** 1,744,929 companies from Mergent/D&B, pulled 2,000 at a time
- **Loaded so far:** 254,000 rows (14.56%) from 127 xlsx files (.csv extension)
- **Remaining:** 1,490,929 (745 batches of 2k)
- **Import script:** `import_mergent.py` (supports `--dir`, `--file`, `--status`)
- **Tracking table:** `mergent_import_progress` (per-file, idempotent)
- **Dedup after import:** `py scripts/etl/dedup_master_employers.py --phase 1` then `--phase 2` then `--phase 3 --min-name-sim 0.85` (fresh, no --resume), then `--phase 4 --resume` + targeted rescore of enriched records
- **Key insight:** `--resume` for phases 1-3 skips new records (cursor past them). Must run fresh. Phase 4 resume works but misses enriched older records -- do targeted rescore after.
- **Results:** 254k imported -> 4,546,912 master_employers total
- **Data dirs:** `all companies mergent/` (1-36), `all companies 37_63/` (37-63), `all companies 64_88/` (64-88), `all companies 89_125/` (89-125)
- **Known gap:** `import_mergent.py` does NOT create `master_employer_source_ids` rows for new inserts. Needs fix.
- **Cross-source enrichment:** Each batch enriches ~9-10k non-mergent records (mostly SAM) with emp count + NAICS

## Quality Score Tier Redesign (2026-03-02)
- **Old formula:** `source_count * 20 + EIN(10) + emp_count(10)` -- measured cross-source linkage only
- **New formula (implemented):** Gate-based on structural completeness + source count
  - **0-20 Sparse:** Missing location OR (emp AND naics) -- not analytically useful
  - **21-40 Structurally useful:** Has location + (emp OR naics) -- enough for structural analysis
  - **41-60 Multi-source:** 3+ sources, OR 2 sources + structurally useful
  - **61-80 Rich:** 4+ sources, OR 3 sources + fully complete (emp+naics+location)
  - **81-100 Premium:** 5+ sources, OR 4 sources + fully complete
- **Changed in:** `scripts/etl/dedup_master_employers.py` run_phase4() function
- **Current distribution:** 0-20: 2,773,851 | 21-40: 1,585,269 | 41-60: 151,752 | 61-80: 25,844 | 81-100: 10,196
- **Key benefit:** Every record in 21-40+ is guaranteed analyzable. Mergent records land in 21-40 on arrival (95% emp, 100% NAICS)
- **Projection (all 1.74M mergent loaded):** Analyzable share grows from ~39% to ~42%

## Multi-Union Industry Regression (2026-03-02)
- **Original:** `cwa_panel_regression.py` -- CWA-only, 5 sub-sectors x 21 years (2006-2026), hardcoded membership + BEA/BLS data
- **Generalized:** `union_industry_regression.py` -- 17 unions x 15 years (2010-2024), membership from DB
- **Scripts/output at:** `C:\Users\jakew\.local\bin\` (not in Labor Data Project_real)
- **Output files:** `union_industry_panel_data.csv`, `union_industry_regression_grid.png`, `union_divergence_summary.png`
- **Key innovation: Active-only membership from Schedule 13**
  - `ar_membership` table (216K rows) has LM-2 Schedule 13 category breakdowns
  - Per-union classification rules in `ACTIVE_CATEGORY_RULES` dict separate active from retired/honorary/agency fee
  - `nhq_reconciled_membership` table (132 rows) has pre-reconciled latest-year data with retired/canadian deductions
  - Biggest corrections: CWA 682K->367K (46% retired), IAM 548K->362K (34%), AFT 1.83M->1.24M (27%)
- **Union HQ f_nums:** NEA=342, SEIU=137, AFT=12, IBT=93, UFCW=56, AFSCME=289, IBEW=116, LIUNA=131, IAM=107, USW=94, CJA=85, UAW=149, NFOP=411, UNITE HERE=511, CWA=188, NNU=544309, SMART=73
- **Regression results (active-only, FE panel):**
  - Coefficient: 0.119, p=0.003 (within FE); p=0.025 (PanelOLS clustered SE) -- both significant
  - Interpretation: 1% increase in lagged active membership -> 0.12% increase in industry VA
  - Productivity dominates growth model (coeff 1.41, p<0.001); membership growth near zero in growth spec
- **Cyclicality:** Counter-cyclical: IAM, LIUNA, SEIU, USW. Acyclical: the other 13.
- **Biggest decliners (active):** CWA -28%, NEA -14%, AFSCME -13%, USW -13%, IAM -11%
- **Biggest growers (active):** NNU +65%, SMART +48%, AFT +39%, UNITE HERE +24%, NFOP +16%
- **Every industry grew** +10% to +68% regardless of membership trajectory
- **BEA/BLS data:** Hardcoded in script (not from API). Sectors: education, healthcare, transport_warehouse, retail, public_admin, utilities_construction, construction, manufacturing, motor_vehicles, accommodation_food, information, hospitals
- **Caveats:** Single-sector mapping per union is a simplification; AFT/SMART have 2013 merger artifacts; COVID 2020 outliers; short panel (T=15)
