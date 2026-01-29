# F-7 Employer Geocoding Improvement Plan

**Date:** January 23, 2026  
**Current Rate:** 73.8% (110,996 / 150,388)  
**Target Rate:** 88-90%

---

## Root Cause Analysis

| Issue | Count | % of Failures |
|-------|-------|---------------|
| PO Box addresses | 8,725 | 24.7% |
| Multi-line addresses | 2,840 | 8.0% |
| Suite/Unit/# in address | 1,862 | 5.3% |
| Highway/Route formats | 1,980 | 5.6% |
| Formatting issues | 607 | 1.7% |
| Other (geocoder limits) | ~20,000 | 56.6% |

---

## Improvement Strategies

### 1. Address Preprocessing (Est. +4,000 records)
- Extract first line from multi-line addresses
- Strip suite/unit/apt designations
- Fix double spaces and formatting
- Standardize highway/route formats

### 2. PO Box → City Centroid (Est. +8,000 records)
- Geocode PO Box addresses to city center
- Flag as `geocode_quality = 'city_centroid'`
- Acceptable for regional analysis

### 3. Alternative Geocoders (Est. +10,000 records)
- **Nominatim (OSM):** Free, try first
- **Geocodio:** $0.50/1000, good US coverage
- **Google Maps API:** $5/1000, best parsing (fallback)

---

## Implementation Steps

| Step | Task | Est. Gain | Time |
|------|------|-----------|------|
| 1 | Clean multi-line addresses, retry Census | +2,000 | 1 hr |
| 2 | Strip suite/unit designations, retry | +1,500 | 1 hr |
| 3 | PO Box → city centroid geocoding | +8,000 | 1 hr |
| 4 | Nominatim batch for remaining failures | +5,000 | 2 hrs |
| 5 | Geocodio for stubborn failures (~$20) | +5,000 | 1 hr |

**Total estimated improvement:** +22,000 records → **88.5%**

---

## Schema Addition

```sql
ALTER TABLE f7_employers ADD COLUMN geocode_quality VARCHAR(20);
-- Values: 'rooftop', 'street', 'city_centroid', 'zip_centroid', 'manual'

ALTER TABLE f7_employers ADD COLUMN geocode_source VARCHAR(20);
-- Values: 'census', 'nominatim', 'geocodio', 'google', 'manual'
```

---

## Priority

**Medium** - Current 73.8% is adequate for most analysis. Improvement can be done incrementally alongside other integration work.
