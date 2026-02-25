# I14 - Legacy Match Quality Audit (Non-SAM Sources)

Generated: 2026-02-24 19:05:13

## Summary

This audit samples active matches from the **oldest pipeline runs** for each source system to assess whether early matches contain false positives that have persisted uncorrected.

## Methodology

For each source system (`osha`, `whd`, `990`, `sec`, `bmf`):

1. Identify the 3 oldest `run_id` values with active matches
2. Sample 20 active matches from those runs (random, seed=42)
3. Look up the source record name from the source table
4. Compare source name vs F7 employer name using:
   - Evidence `name_similarity` if available (>=0.90 = CONFIRMED)
   - EIN-based match method = CONFIRMED
   - Token overlap >=0.70 = CONFIRMED, >=0.40 = PLAUSIBLE, else SUSPECT

## Per-Source Results

### OSHA

Oldest run_ids: `det-osha-20260218-171640-b3of4, det-osha-20260218-172746-b4of4, det-osha-20260223-111723-b1of4`

| Source_Name | F7_Name | Method | Confidence | Category |
| --- | --- | --- | --- | --- |
| (not found) | Trane Technologies | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Eagle Picher Technologies LLC | FUZZY_SPLINK_ADAPTIVE | 1.000 | CONFIRMED |
| (not found) | Bison Laboratories Inc. | NAME_STATE_EXACT | 0.900 | SUSPECT |
| (not found) | AOW Associates, Inc. | NAME_CITY_STATE_EXACT | 0.950 | SUSPECT |
| (not found) | Butler Architectural Woodworking | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Ahern Rentals Inc.  | NAME_CITY_STATE_EXACT | 0.950 | SUSPECT |
| (not found) | Walt Disney World | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | U.s. Axle Inc. | NAME_CITY_STATE_EXACT | 0.950 | SUSPECT |
| (not found) | Eagle Manufacturing Company | NAME_CITY_STATE_EXACT | 0.950 | SUSPECT |
| (not found) | AM&G Waterproofing LLC | NAME_STATE_EXACT | 0.900 | SUSPECT |
| (not found) | Fairmount Foundry Inc. | FUZZY_SPLINK_ADAPTIVE | 1.000 | SUSPECT |
| (not found) | Aramark Correctional Services | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Lineage Logistics, LLC | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Pixelle Specialty Solutions | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Economy Paving | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Groot Recycling & Waste Services, Inc. | NAME_STATE_EXACT | 0.900 | SUSPECT |
| (not found) | SCI | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Rhodes Crane & Rigging | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Henry County Administrator | FUZZY_SPLINK_ADAPTIVE | 1.000 | SUSPECT |
| (not found) | Douglas Parking | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |

**OSHA sample counts:** CONFIRMED=1, PLAUSIBLE=0, SUSPECT=19 (n=20)

### WHD

Oldest run_ids: `det-whd-20260220-015837`

| Source_Name | F7_Name | Method | Confidence | Category |
| --- | --- | --- | --- | --- |
| Papich Construction Company | Papich Construction dba Sierra Pacific M | NAME_AGGRESSIVE_STATE_CITY_RESOLVED | 0.750 | SUSPECT |
| Barnallen Technologies | Bradley Technologies, Inc. | FUZZY_SPLINK_ADAPTIVE | 1.000 | SUSPECT |
| DuPont | DuPont | NAME_CITY_STATE_EXACT | 0.950 | CONFIRMED |
| Professional Contract Service | Professional Contract Services, Inc. | NAME_AGGRESSIVE_STATE | 0.750 | PLAUSIBLE |
| Cassens Transport Company | Cassens Transport | NAME_AGGRESSIVE_STATE | 0.750 | PLAUSIBLE |
| WA, State of - Dept of Corrections | WA State Department of Corrections | NAME_AGGRESSIVE_STATE | 0.750 | PLAUSIBLE |
| AMF Electrical Contractors, Inc. | Electrical Contractors Inc | FUZZY_TRIGRAM | 0.871 | SUSPECT |
| Landmark Construction | The Lane Construction Corporation | FUZZY_SPLINK_ADAPTIVE | 0.775 | SUSPECT |
| New Rainbow Foods | Rainbow Foods | FUZZY_SPLINK_ADAPTIVE | 0.998 | PLAUSIBLE |
| Fenton Art Glass | Fenton Art Glass Company | NAME_AGGRESSIVE_STATE | 0.750 | CONFIRMED |
| Davidson Transit Organization | Davidson Transit Organization | NAME_CITY_STATE_EXACT | 0.950 | CONFIRMED |
| Physical Security, LLC | Physical Security | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| J & B Acoustical | J&B Acoustical | NAME_CITY_STATE_EXACT | 0.950 | SUSPECT |
| St. Clare Hospital | St Clare Hospital | NAME_CITY_STATE_EXACT | 0.950 | PLAUSIBLE |
| MV Transportation | MV Transportation | NAME_CITY_STATE_EXACT | 0.950 | CONFIRMED |
| Acme Markets | Acme Markets  | NAME_STATE_EXACT | 0.900 | CONFIRMED |
| Flight Club New York | Links Club of New York | FUZZY_SPLINK_ADAPTIVE | 1.000 | PLAUSIBLE |
| Ford Motor Company | Ford Motor Company | NAME_CITY_STATE_EXACT | 0.950 | CONFIRMED |
| Schneider Electric | Schneider Electric  | NAME_CITY_STATE_EXACT | 0.950 | CONFIRMED |
| Bayshore Residence and Rehabilitation Ce | Bayshore Residence and Rehabilitation Ce | NAME_CITY_STATE_EXACT | 0.950 | CONFIRMED |

**WHD sample counts:** CONFIRMED=8, PLAUSIBLE=6, SUSPECT=6 (n=20)

### 990

Oldest run_ids: `det-990-20260219-145700-b1of5, det-990-20260219-145734-b1of5, det-990-20260219-153217-b1of5`

| Source_Name | F7_Name | Method | Confidence | Category |
| --- | --- | --- | --- | --- |
| (not found) | AFSCME, DISTRICT COUNCIL 37 | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | CVS HEALTH | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Kaiser Los Angeles-Kaiser Permanente Med | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Bozeman Health | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Northwood University (Maint/Cust) | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Kentmere Rehabilitation & Skilled Care,  | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Chicago Reader | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | The Shield Institute | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Harper Creek Community Schools | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | LOUIS P CIMINELLI CONSTRUCTION CO INC | FUZZY_SPLINK_ADAPTIVE | 1.000 | SUSPECT |
| (not found) | Nation Union Of Healthcare Wor | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | International Brotherhood of Electrical  | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Madison County Housing Authority | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Master Builders Association of Western P | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Plumbers & Steamfitters Local 367 | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Jewish Voice for Peace | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Sheet Metal Workers Pension Fund SASMI | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | New York Foundation for Senior Citizens  | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Los Angeles Ballet | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Pioneer Towers | EIN_EXACT | 1.000 | SUSPECT |

**990 sample counts:** CONFIRMED=0, PLAUSIBLE=0, SUSPECT=20 (n=20)

### SEC

Oldest run_ids: `det-sec-20260219-084641-b1of5, det-sec-20260219-094928-b2of5, det-sec-20260219-104926-b3of5`

| Source_Name | F7_Name | Method | Confidence | Category |
| --- | --- | --- | --- | --- |
| (not found) | Ford Motor Company | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Aquarius Gaming, LLC | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | PENHALL COMPANY | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Aramark Business & Industry, LLC. | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Muzak | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Ford Motor Company | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | TPC Group, Inc. | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | TIDELANDS OIL PRODUCTION COMPANY | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | National Broadcasting Company | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Atrium Companies  | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | AppFolio | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Raycom Media | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Lanter Distributing | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Ford Motor Company | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Flint Hills | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | United Refining Company | NAME_AGGRESSIVE_STATE | 0.750 | SUSPECT |
| (not found) | Engility Corporation | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Weyerhaeuser  | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Dandelion Chocolate Inc. | NAME_STATE_EXACT | 0.900 | SUSPECT |
| (not found) | Kos Media LLC | EIN_EXACT | 1.000 | SUSPECT |

**SEC sample counts:** CONFIRMED=0, PLAUSIBLE=0, SUSPECT=20 (n=20)

### BMF

Oldest run_ids: `det-bmf-20260218-195316`

| Source_Name | F7_Name | Method | Confidence | Category |
| --- | --- | --- | --- | --- |
| (not found) | Kaiser Foundation Hospitals | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | ST. JOSEPH BON SECOURS MERCY HEALTH | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Kaiser Foundation Health Plan Inc. | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Trustees of the University of Pennsylvan | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Dignity Health | NAME_CITY_STATE_EXACT | 0.950 | SUSPECT |
| (not found) | New York University | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | Johns Hopkins University | EIN_EXACT | 1.000 | SUSPECT |
| (not found) | New York Presbyterian Hospital  | EIN_EXACT | 1.000 | SUSPECT |

**BMF sample counts:** CONFIRMED=0, PLAUSIBLE=0, SUSPECT=8 (n=8)

## Aggregate Quality

| Source | Sampled | Confirmed | Plausible | Suspect | Est. FP Rate |
| --- | --- | --- | --- | --- | --- |
| OSHA | 20 | 1 | 0 | 19 | 95.0% |
| WHD | 20 | 8 | 6 | 6 | 30.0% |
| 990 | 20 | 0 | 0 | 20 | 100.0% |
| SEC | 20 | 0 | 0 | 20 | 100.0% |
| BMF | 8 | 0 | 0 | 8 | 100.0% |
| **TOTAL** | 88 | 9 | 6 | 73 | 83.0% |

## Overall False Positive Estimate

Across all 88 sampled matches from oldest runs:

- **CONFIRMED:** 9 (10.2%)
- **PLAUSIBLE:** 6 (6.8%)
- **SUSPECT:** 73 (83.0%)

**WARNING:** High false-positive rate in legacy matches. Oldest runs may contain low-quality matches that were never cleaned up by subsequent pipeline improvements.

## Recommendations

1. **Review SUSPECT matches** -- Manually inspect flagged matches, especially from the oldest run_ids, to confirm or reject them.
2. **Re-run deterministic matcher** -- Use `--rematch-all` on source systems with high FP rates to supersede old matches with improved matching logic.
3. **Apply name similarity floor** -- Ensure all active matches meet minimum name similarity thresholds (0.75 for trigram, 0.80 for RapidFuzz).
4. **Version tracking** -- Compare match quality across run_ids to verify that newer runs produce fewer false positives.
5. **Automate periodic audits** -- Run this script after each major pipeline update to track quality trends over time.
