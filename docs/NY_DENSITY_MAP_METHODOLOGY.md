# NY Union Density Map - Methodology Report

**Last Updated:** February 2026
**Author:** Labor Relations Research Platform
**Status:** Production

---

## 1. Executive Summary

The NY Union Density Map provides estimated union density at four geographic levels for New York State: county (62), ZIP code (1,826), census tract (5,411), and congressional district (26). The map combines American Community Survey workforce composition data with Bureau of Labor Statistics industry-specific union density rates, calibrated against Current Population Survey statewide benchmarks.

The core methodology treats private and public sector density as fundamentally different phenomena. Private sector density is estimated via industry-weighted BLS rates with an auto-calibrated "climate multiplier." Public sector density is decomposed by government level (federal, state, local), each with its own union density rate derived from CPS data. The two sectors are then combined using class-of-worker shares to produce a total density estimate.

**Key Results:**

| Level | Records | Avg Total | Avg Private | Range (Total) |
|-------|---------|-----------|-------------|---------------|
| County | 62 | 20.2% | 12.4% | 12.2% - 26.5% |
| ZIP | 1,826 | 18.7% | 11.5% | 0% - 63.7% |
| Tract | 5,411 | 18.6% | 11.7% | 0% - 48.2% |
| Congress. District | 26 | ~19% | ~12% | varies |

---

## 2. Data Sources

### Primary Sources

| Source | Vintage | What It Provides | Resolution |
|--------|---------|------------------|------------|
| **American Community Survey (ACS)** | 2025 5-year est. | Industry composition (13 industries), class-of-worker shares (7 categories) | County, ZIP (ZCTA), Tract |
| **Bureau of Labor Statistics** | 2024 | Union membership rates by industry (Table 3, 12 industries) | National |
| **Current Population Survey (CPS)** | 2025 | Statewide private & public sector union density | State |
| **unionstats.com (Hirsch/Macpherson)** | 2025 | State-level sector density (private, public, total) | State |
| **Census TIGER/Line** | 2022 | Census tract polygon boundaries (cb_2022_36_tract_500k) | Tract |
| **NYS GIS Clearinghouse** | 2023 | Congressional district boundaries | District |
| **new-york-zip-codes.kml** | Current | ZIP code polygon boundaries for NY | ZIP |

### ACS Workforce Data Fields

The ACS provides two key variable groups per geography:

**Industry Composition (13 categories):**
- Agriculture, forestry, fishing, hunting, and mining
- Construction
- Manufacturing
- Wholesale trade
- Retail trade
- Transportation and warehousing, and utilities
- Information
- Finance and insurance, and real estate, and rental and leasing
- Professional, scientific, management, administrative, and waste management
- Educational services, and health care and social assistance
- Arts, entertainment, recreation, accommodation, and food services
- Other services, except public administration
- Public administration

**Class of Worker (7 categories):**
- Private for-profit wage and salary workers
- Private not-for-profit wage and salary workers
- Local government workers
- State government workers
- Federal government workers
- Self-employed in own not-incorporated business
- Unpaid family workers

---

## 3. Private Sector Density Methodology

### Overview

Private sector density is estimated using a three-step process:

1. Compute an **industry-weighted expected density** from 10 BLS industry rates
2. Apply an **auto-calibrated climate multiplier** to match the CPS statewide benchmark
3. Weight by the geography's **private class-of-worker share**

### Step 1: Industry-Weighted Expected Density

For each geography, we compute the expected private density based on its industry composition using 10 of the 12 BLS industries:

| Industry | BLS 2024 Density | Included? |
|----------|-----------------|-----------|
| Transportation & Utilities | 16.2% | Yes |
| Construction | 10.3% | Yes |
| Manufacturing | 7.8% | Yes |
| Information | 6.6% | Yes |
| Wholesale Trade | 4.6% | Yes |
| Agriculture & Mining | 4.0% | Yes |
| Retail Trade | 4.0% | Yes |
| Leisure & Hospitality | 3.0% | Yes |
| Other Services | 2.7% | Yes |
| Professional & Business Services | 2.0% | Yes |
| Finance | 1.3% | Yes |
| **Education & Health Services** | **8.1%** | **No** |
| **Public Administration** | **N/A** | **No** |

### Why Education/Health and Public Admin Are Excluded

**Education & Health (8.1% BLS rate):** A large share of education and healthcare workers in New York are public employees (e.g., SUNY faculty, public school teachers, municipal hospital staff). Including them in the private sector calculation would double-count workers already captured in the public sector density estimate. The BLS 8.1% rate blends private and public workers in these fields, making it unreliable for a purely private sector estimate.

**Public Administration:** By definition, public administration workers are government employees. They are handled entirely by the public sector decomposition (Section 4).

**Hybrid Approach Rejected:** A hybrid methodology was tested where the 10 private industries used industry weighting while education/health used the state CPS private rate directly. Results across 3,144 national counties showed only a -0.07% average difference from the simpler exclusion approach. The hybrid was rejected in favor of simplicity.

| Metric | Exclusion (Current) | Hybrid | Difference |
|--------|---------------------|--------|------------|
| National Avg | 5.26% | 5.19% | -0.07% |
| High Edu/Health Counties (>30%) | Lower | +0.5% to +0.8% | Minimal |
| Low Edu/Health Counties (<15%) | Higher | -1% to -2% | Minimal |

### Step 2: Renormalization

Since we exclude education/health and public admin, the remaining 10 industry shares no longer sum to 1.0. We renormalize them:

```
For each industry i in {10 private industries}:
    normalized_share_i = raw_share_i / sum(all 10 raw shares)
```

The expected density is then:

```
Expected_Private = SUM( normalized_share_i * BLS_rate_i ) for i in 10 industries
```

### Step 3: Auto-Calibrated Climate Multiplier

The raw expected density reflects only industry composition. It does not account for New York's strong union culture - the legal environment, collective bargaining traditions, and organizing history that cause NY's actual density to exceed what industry mix alone predicts.

The **climate multiplier** corrects for this:

```
Multiplier = CPS_Target / Avg_County_Expected
           = 12.4% / 5.48%
           = 2.2618x
```

Where:
- **CPS_Target** = 12.4% (NY statewide private sector density from CPS 2025)
- **Avg_County_Expected** = simple average of expected density across all 62 NY counties

The multiplier is derived automatically at runtime from the county data, not hardcoded. If the source data changes, the multiplier self-adjusts to maintain calibration to the CPS benchmark.

**Final private density for a geography:**

```
Private_Density = Expected_Private * Climate_Multiplier
```

---

## 4. Public Sector Density Methodology

### Two-Stage Calculation

Public sector density uses a fundamentally different approach from private sector. Rather than industry weighting, it decomposes the government workforce by level and applies level-specific union rates.

### Stage 1: Contribution to Total Density (load_ny_density.py)

In the density estimation script, public density is calculated as a **contribution** to the total population density:

```
Federal_Contribution = federal_worker_share * NY_Federal_Rate
State_Contribution   = state_worker_share   * NY_State_Rate
Local_Contribution   = local_worker_share   * NY_Local_Rate

Public_Contribution  = Federal + State + Local
```

The rates used in `load_ny_density.py` (the estimation script):
- Federal: 42.2%
- State: 46.3%
- Local: 63.7%

These are CPS-derived rates representing the fraction of workers at each government level who are union members.

### Stage 2: Within-Sector Rate Override (build_density_map.py)

For the map display, we want to show the **within-sector** public density (i.e., "of all government workers in this area, what percentage are unionized?"). The map build script recalculates this using the `state_govt_level_density` table:

```python
# From build_density_map.py
NY_FED_RATE   = 48.57%
NY_STATE_RATE = 53.37%
NY_LOCAL_RATE = 73.33%

Public_Density = (fed_share * FED_RATE + state_share * STATE_RATE + local_share * LOCAL_RATE)
                 / govt_class_total
```

This division by `govt_class_total` converts from "contribution to total workforce" to "rate among government workers only."

### Rate Difference Explanation

The two sets of rates serve different purposes:

| Rate Set | Federal | State | Local | Source | Purpose |
|----------|---------|-------|-------|--------|---------|
| load_ny_density.py | 42.2% | 46.3% | 63.7% | CPS direct | Contribution to total density |
| build_density_map.py | 48.57% | 53.37% | 73.33% | state_govt_level_density table | Within-sector display rate |

The `state_govt_level_density` rates may differ from raw CPS rates due to estimation methodology for government-level decomposition (the CPS reports combined public sector density; federal/state/local breakdown is estimated from workforce shares and national baselines).

---

## 5. Total Density Calculation

Total density combines private and public contributions, weighted by class-of-worker shares:

```
Total_Density = (Private_Class_Total * Private_Density) + Public_Contribution
```

Where:
- `Private_Class_Total` = for-profit share + nonprofit share (from ACS class-of-worker)
- `Private_Density` = industry-weighted, multiplier-adjusted rate (Section 3)
- `Public_Contribution` = sum of federal/state/local contributions (Section 4, Stage 1)

**Workers contributing 0% density:**
- Self-employed (in own not-incorporated business)
- Unpaid family workers

These workers are excluded from both private and public density calculations because they cannot form or join unions by law.

---

## 6. Auto-Calibration

### Why Calibration Is Needed

Without calibration, the industry-weighted expected density for NY counties averages ~5.48%. The actual CPS-measured private sector density for New York is 12.4%. This gap exists because:

1. BLS rates are **national averages** - they don't reflect NY's stronger union environment
2. NY has favorable collective bargaining laws (Taylor Law, etc.)
3. Historical union density and organizing culture amplify actual rates above industry expectations

### Calibration Process

```
1. Load county workforce data from ACS Excel files
2. For each of 62 counties, compute Expected_Private (10-industry weighted, multiplier=1.0)
3. Take simple (unweighted) average across all counties
4. Multiplier = 12.4% / average_expected
5. Apply multiplier to all geographies (counties, ZIPs, tracts)
```

The calibration is performed once using county data, then the same multiplier is applied uniformly to ZIP and tract calculations. This ensures consistency across geographic levels.

### Validation

After calibration:
- County average private density = 12.4% (matches CPS target exactly)
- The spread of private density across counties reflects genuine industry-mix variation, scaled to the correct statewide level

---

## 7. Geographic Levels

### County (62 records)

- **Source:** `data/ny_county_workforce.xlsx`
- **FIPS format:** 5-digit (e.g., `36061` for Manhattan)
- **Key use:** Calibration base, county choropleth, congressional district aggregation

| Metric | Value |
|--------|-------|
| Mean Total Density | 20.2% |
| Mean Private Density | 12.4% |
| Min Total | 12.2% (Manhattan) |
| Max Total | 26.5% (Hamilton) |

**NYC Borough Comparison:**

| Borough | Total | Private | Public |
|---------|-------|---------|--------|
| Staten Island | 22.4% | 12.7% | 13.1% |
| Bronx | 19.4% | 13.1% | 9.0% |
| Queens | 18.0% | 12.6% | 8.0% |
| Brooklyn | 17.1% | 11.2% | 8.1% |
| Manhattan | 12.2% | 8.3% | 5.3% |

**Top 5 Counties by Total Density:**

1. Hamilton (26.5%) - Rural, high government employment share
2. Lewis (23.4%) - High public sector share
3. Schoharie (22.9%) - Rural government employment
4. St. Lawrence (22.9%) - University town (SUNY Canton, Clarkson)
5. Franklin (22.4%) - Rural government employment

### ZIP Code (1,826 records)

- **Source:** `data/ny_zip_workforce.xlsx`
- **FIPS format:** 5-digit ZIP (e.g., `10001`)
- **Geometry:** KML file (`new-york-zip-codes.kml`)

| Metric | Value |
|--------|-------|
| Mean Total Density | 18.7% |
| Mean Private Density | 11.5% |
| Min Total | 0% |
| Max Total | 63.7% |

Note: Extreme values (0%, 63.7%) occur in ZIPs with very small populations or institutional populations (e.g., military bases, prisons) where government worker shares approach 100%.

### Census Tract (5,411 records)

- **Source:** `data/ny_tract_workforce.xlsx`
- **FIPS format:** 11-digit (e.g., `36061000100`)
- **Geometry:** Census TIGER/Line shapefile (`cb_2022_36_tract_500k.zip`)

| Metric | Value |
|--------|-------|
| Mean Total Density | 18.6% |
| Mean Private Density | 11.7% |
| Min Total | 0% |
| Max Total | 48.2% |

Tracts with 0% density are typically institutional tracts (no civilian workforce) or tracts with suppressed ACS data.

### Congressional District (26 records)

- **Source:** Derived from tract-level data via point-in-polygon assignment
- **Geometry:** NYS GIS Clearinghouse district boundaries

Congressional district density is not directly estimated. Instead, it is aggregated from census tract estimates (see Section 8).

---

## 8. Congressional District Overlay

### Methodology

Congressional districts do not align with county or ZIP boundaries, making direct calculation impossible. Instead, we use a tract-centroid approach:

1. **Compute tract centroids** from the Census TIGER shapefile bounding boxes
2. **Simplify district polygons** using Douglas-Peucker algorithm (tolerance = 0.003 degrees)
3. **Filter tiny island polygons** (area < 0.001 square degrees) from MultiPolygon districts
4. **Bounding box pre-filter** - skip point-in-polygon test if centroid is outside district bbox
5. **Ray-casting point-in-polygon** test to assign each tract centroid to a district
6. **Simple average** of all assigned tract densities produces the district estimate

### Implementation Details

```
For each tract:
    centroid = center_of_bounding_box(tract_geometry)
    For each congressional district:
        if centroid NOT in district.bbox: skip
        if point_in_polygon(centroid, district.geometry):
            district.tracts.append(tract_density)
            break

For each district:
    avg_total  = mean(tract.total  for tract in district.tracts)
    avg_private = mean(tract.private for tract in district.tracts)
    avg_public  = mean(tract.public  for tract in district.tracts)
```

### Limitations

- **Centroid assignment** is an approximation. A tract whose centroid falls in District A may straddle the boundary with District B. This is acceptable at the 5,411-tract resolution where boundary effects average out.
- **Simple averaging** treats all tracts equally regardless of population. A population-weighted average would be more accurate but requires ACS population counts not currently loaded.
- **Coverage:** Not all tracts may be assigned (some centroids may fall outside all district polygons due to water features or boundary precision). The build script reports the assignment rate.

---

## 9. Map Build Pipeline

### Data Flow

```
ACS Excel Files                Census TIGER        KML File         NYS GIS
(county/ZIP/tract)             (tract shapefile)   (ZIP boundaries) (congressional)
       |                             |                   |                |
       v                             |                   |                |
load_ny_density.py                   |                   |                |
  - Auto-calibrate multiplier        |                   |                |
  - Calculate density estimates      |                   |                |
  - Export CSVs to data/             |                   |                |
  - Store in PostgreSQL              |                   |                |
       |                             |                   |                |
       v                             v                   v                v
  ny_county_density.csv    cb_2022_36_tract_500k  new-york-zip-   Congressional
  ny_zip_density.csv                .zip          codes.kml       Districts.geojson
  ny_tract_density.csv               |                   |                |
       |                             |                   |                |
       +-----------------------------+-------------------+----------------+
                                     |
                                     v
                          build_density_map.py
                            - Parse KML -> ZIP GeoJSON
                            - Parse Shapefile -> Tract GeoJSON
                            - Build county data array
                            - Override public density rates
                            - Build congressional districts
                            - Simplify geometries
                            - Round coordinates
                            - Inject into HTML
                                     |
                                     v
                          ny_density_map.html
                            (self-contained, ~25-30 MB)
```

### Build Steps

| Step | Script | Action |
|------|--------|--------|
| 0 | `build_density_map.py` | Read CSVs, build county/ZIP/tract data arrays |
| 1 | `build_density_map.py` | Parse ZIP KML into GeoJSON FeatureCollection |
| 2 | `build_density_map.py` | Download & parse Census tract shapefile into GeoJSON |
| 2B | `build_density_map.py` | Build congressional district data from tract centroids |
| 3 | `build_density_map.py` | Inject all data into HTML via regex replacement |

### Running the Build

```cmd
cd C:\Users\jakew\Downloads\labor-data-project

# Step 1: Calculate density estimates (writes CSVs + database)
py scripts/load_ny_density.py

# Step 2: Build map (reads CSVs, writes HTML)
py scripts/build_density_map.py
```

---

## 10. Validation & Results

### Statewide Benchmark Comparison

| Metric | Map Estimate | CPS/EPI Benchmark | Match |
|--------|-------------|-------------------|-------|
| Private Density (county avg) | 12.4% | 12.4% (CPS) | Exact (by calibration) |
| Public Density (statewide) | ~55-60% | 63.5% (EPI) | Reasonable |
| Total Density (statewide) | ~20% | 22.0% (CPS) | Close |

Note: The county simple average (~20.2%) is not the same as a population-weighted statewide estimate. NYC's large workforce share would pull the weighted average toward Manhattan/Brooklyn's lower densities.

### Cross-Level Consistency

| Check | Result |
|-------|--------|
| County avg private == CPS target | 12.4% == 12.4% (exact) |
| ZIP avg private close to county avg | 11.5% vs 12.4% (reasonable - population weighting differs) |
| Tract avg private close to county avg | 11.7% vs 12.4% (reasonable) |
| Rural counties higher total density | Confirmed (Hamilton 26.5%, Lewis 23.4%) |
| Urban counties driven by private | Confirmed (Manhattan low govt share = low total) |

### Known Edge Cases

| Geography | Density | Explanation |
|-----------|---------|-------------|
| ZIPs with 0% | No civilian workforce (institutional, PO box only) |
| ZIPs with >50% | Military bases, prison towns (near-100% govt workers) |
| Tracts with 0% | Institutional tracts, suppressed ACS data |
| Manhattan (12.2% total) | Lowest county - high finance/professional share, low govt share |
| Hamilton (26.5% total) | Highest county - very small, high govt employment share |

---

## 11. Key Methodological Decisions

### Decision 1: Exclude Education/Health from Private Sector

**Rationale:** In New York, a large fraction of education and healthcare workers are public employees (public school teachers, SUNY faculty, municipal hospital staff). The BLS 8.1% rate blends private and public workers. Including it in the private calculation, then multiplying by the 2.26x climate multiplier, inflates private density estimates. These workers are better captured in the public sector decomposition.

**Impact:** Removing education/health lowered the average county private density from ~13.7% to 12.4% (matching CPS). The climate multiplier also adjusted from a hardcoded 2.40x to the auto-derived 2.26x.

### Decision 2: Auto-Calibrate Rather Than Hardcode Multiplier

**Rationale:** The multiplier depends on the average expected density, which changes if ACS data is updated or if BLS rates change. Auto-calibration ensures the output always matches the CPS benchmark without manual intervention.

**Formula:** `Multiplier = CPS_Target / mean(expected_density across 62 counties)`

### Decision 3: Simple Average for Congressional Districts

**Rationale:** Population-weighted averaging would require additional ACS population data. Simple averaging of tract densities is adequate for the intended use case (broad district comparison) and avoids additional data pipeline complexity.

### Decision 4: Coordinate Precision of 4 Decimal Places

**Rationale:** 4 decimal places in longitude/latitude provides ~11 meter accuracy, which is more than sufficient for choropleth polygon boundaries. Reducing from full precision (15+ digits) significantly shrinks the HTML file size without visible quality loss.

### Decision 5: Douglas-Peucker Simplification at 0.003 Degree Tolerance

**Rationale:** Congressional district boundaries have very high vertex counts from the source GeoJSON. A tolerance of 0.003 degrees (~333 meters) reduces vertex count substantially while maintaining visually accurate boundaries at the zoom levels used in the map.

### Decision 6: Two-Rate Public Sector System

**Rationale:** The density estimation script (`load_ny_density.py`) and the map build script (`build_density_map.py`) use different public sector rate sets. This is intentional:

- **Estimation script** needs rates that represent contributions to total workforce density (used in the `Total_Density = Private_Part + Public_Part` formula)
- **Map build script** needs within-sector rates for the map's "Public Density" display column (answering "what % of government workers are unionized?")

The map build script's `calc_public_density()` function divides the contribution by `govt_class_total` to convert between these two representations.

---

## 12. API Integration

The density data is served through the following API endpoints (localhost:8001):

### NY-Specific Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/density/ny/summary` | Summary statistics at all geographic levels |
| `GET /api/density/ny/counties` | All 62 county density estimates |
| `GET /api/density/ny/county/{fips}` | Single county detail with tract statistics |
| `GET /api/density/ny/zips` | ZIP code density (1,826 ZIPs, paginated) |
| `GET /api/density/ny/zip/{zip_code}` | Single ZIP detail |
| `GET /api/density/ny/tracts` | Census tract density (5,411 tracts, paginated) |
| `GET /api/density/ny/tract/{tract_fips}` | Single tract detail |

### Supporting Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/density/industry-rates` | BLS 2024 industry union density rates (12 industries) |
| `GET /api/density/state-industry-comparison` | Expected vs actual density by state with climate multiplier |
| `GET /api/density/state-industry-comparison/{state}` | Single state industry breakdown |
| `GET /api/density/by-county/{fips}/industry` | County industry breakdown and density calculation |

### Database Tables

| Table | Records | Key Columns |
|-------|---------|-------------|
| `ny_county_density_estimates` | 62 | county_fips, estimated_total_density, estimated_private_density, estimated_public_density |
| `ny_zip_density_estimates` | 1,826 | zip_code, estimated_total_density, estimated_private_density |
| `ny_tract_density_estimates` | 5,411 | tract_fips, county_fips, estimated_total_density |
| `bls_industry_density` | 12 | industry_code, union_density_pct |
| `state_industry_density_comparison` | 51 | state, expected_private_density, actual_private_density, climate_multiplier |

---

## 13. Technical Details

### File Sizes

| File | Approximate Size | Contents |
|------|-----------------|----------|
| `ny_density_map.html` | 25-30 MB | Self-contained map with all GeoJSON + data |
| ZIP GeoJSON | ~8-10 MB | 1,800+ ZIP polygons |
| Tract GeoJSON | ~15-18 MB | 5,411 tract polygons |
| Congressional GeoJSON | ~100-200 KB | 26 simplified district polygons |
| County data | ~10 KB | 62 county records (no geometry - uses Leaflet built-in) |

### Coordinate Precision

Coordinates are rounded to 4 decimal places (`COORD_PRECISION = 4`):

| Decimal Places | Accuracy | Use Case |
|----------------|----------|----------|
| 4 | ~11 meters | Choropleth boundaries (current) |
| 5 | ~1.1 meters | Street-level mapping |
| 6 | ~0.11 meters | Surveying precision |

The 4-place precision reduces file size by ~30-40% compared to full precision with no visible quality impact at map zoom levels.

### Geometry Simplification

Congressional district boundaries use Douglas-Peucker line simplification:

- **Tolerance:** 0.003 degrees (~333 meters)
- **Island filtering:** MultiPolygon parts with area < 0.001 square degrees are removed
- **Ring closure:** Simplified rings are guaranteed to remain closed (first point == last point)
- **Recursion limit:** Automatically raised for large polygons (`len(ring) * 2`)

### Build Script Dependencies

```
pyshp          - Reading Census TIGER shapefiles
requests       - Downloading tract shapefile from Census Bureau
xml.etree      - Parsing KML (standard library)
csv            - Reading density CSVs (standard library)
json           - GeoJSON output (standard library)
zipfile        - Extracting shapefile from ZIP (standard library)
```

### Data Processing Notes

- **NPO share handling:** County and ZIP ACS files provide nonprofit worker counts (not percentages). The script calculates the percentage as the remainder: `npo_share = 1.0 - sum(other_shares)`.
- **Tract files** already provide all values as percentages.
- **FIPS padding:** County and ZIP FIPS are zero-padded to 5 digits; tract FIPS to 11 digits.
- **Missing data:** Geographies with no civilian workforce (all shares = 0) get 0% density. These are typically institutional areas.

---

## Appendix A: Formula Reference

### Private Sector Density

```
Let S_i = ACS industry share for industry i (10 private industries)
Let R_i = BLS union density rate for industry i
Let M   = auto-calibrated climate multiplier

Normalized_S_i = S_i / SUM(S_j for j in 10 industries)

Expected_Private = SUM(Normalized_S_i * R_i)
Private_Density  = Expected_Private * M
```

### Public Sector Density (Contribution)

```
Let F = federal worker share, S = state worker share, L = local worker share
Let RF = federal union rate, RS = state union rate, RL = local union rate

Public_Contribution = F * RF + S * RS + L * RL
```

### Public Sector Density (Within-Sector, for display)

```
Public_Within_Sector = Public_Contribution / (F + S + L)
```

### Total Density

```
Let P = private class total (for-profit + nonprofit shares)

Total_Density = P * Private_Density + Public_Contribution
```

### Climate Multiplier Derivation

```
M = CPS_Target / AVG(Expected_Private_i for i in 62 counties)
  = 12.4% / 5.48%
  = 2.2618
```

---

## Appendix B: Revision History

| Date | Change | Impact |
|------|--------|--------|
| 2026-02-05 | Initial density estimates with class-of-worker adjustment | Created 62 county, 1,826 ZIP, 5,411 tract estimates |
| 2026-02-05 | Removed edu/health from private calculation | County avg private dropped from 13.7% to 12.4% |
| 2026-02-05 | Added auto-calibration (was hardcoded 2.40x) | Multiplier now self-adjusts to 2.2618x |
| 2026-02-05 | Added congressional district overlay | 26 districts with tract-averaged density |
| 2026-02-05 | Map build pipeline created | Self-contained HTML with injected GeoJSON |
