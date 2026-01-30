# MSA/Metro Geography Implementation - Progress

**Date Started:** January 30, 2026  
**Status:** ✅ COMPLETE  
**Total Time:** ~35 minutes

---

## Data Sources

| File | Records | Key Fields |
|------|---------|------------|
| list1_2023.xlsx (OMB CBSA) | 1,918 | CBSA Code, CBSA Title, County, State, FIPS |
| msa_2024.xlsx (EPI) | ~1,500 | FIPS code, Metro Area, Union Members/Density |

**Loaded Data:**
- 935 CBSA definitions (393 Metro + 542 Micro)
- 1,915 county-to-CBSA mappings
- 1,505 MSA union stats (303 metros × 5 sectors)
- 25,763 employers mapped to MSAs (40.8%)

---

## Checkpoints

### Database Schema (CP1-3)
- [x] **CP1:** Create cbsa_definitions table ✅
- [x] **CP2:** Create cbsa_counties lookup table ✅
- [x] **CP3:** Create msa_union_stats table (EPI data) ✅

### Data Loading (CP4-6)
- [x] **CP4:** Load OMB CBSA definitions ✅ (935 records)
- [x] **CP5:** Load county-to-CBSA mapping ✅ (1,915 records)
- [x] **CP6:** Load EPI MSA union stats ✅ (1,505 records)

### Employer MSA Mapping (CP7-9)
- [x] **CP7:** Add cbsa_code column to f7_employers_deduped ✅
- [x] **CP8:** Create city/state to CBSA lookup view ✅
- [x] **CP9:** Populate employer MSA codes ✅ (40.8% = 25,763 employers)

### API Endpoints (CP10-12)
- [x] **CP10:** GET /api/lookups/metros - List MSAs ✅
- [x] **CP11:** Add metro filter to employer search ✅
- [x] **CP12:** GET /api/metros/{cbsa}/stats - MSA details ✅

### Frontend (CP13-15)
- [x] **CP13:** Add Metro dropdown to employer filter ✅
- [x] **CP14:** Show MSA name in employer results ✅
- [x] **CP15:** Add MSA union density to dropdown ✅

---

## Progress Log

### CP1-3: Database Schema ✅
**Time:** 2 min | Tables created: cbsa_definitions, cbsa_counties, msa_union_stats

### CP4-6: Data Loading ✅
**Time:** 5 min | Loaded 935 CBSAs, 1,915 counties, 1,505 MSA stats

### CP7-9: Employer MSA Mapping ✅
**Time:** 10 min | Mapped 25,763 employers (40.8%) to CBSAs via city/state

### CP10-12: API Endpoints ✅
**Time:** 8 min | Added:
- `/api/lookups/metros` - Returns metros sorted by employer count
- `/api/metros/{cbsa}/stats` - Full metro details with union density by sector
- Metro filter in `/api/employers/search`

### CP13-15: Frontend ✅
**Time:** 10 min | Added:
- Metro dropdown in employer filters showing density %
- Metro name displayed in employer search results
- NY-Newark shows "20.2%" density in dropdown

---

## Top Metros by Employer Count

| Metro | Employers | Workers | Union Density |
|-------|-----------|---------|---------------|
| New York-Newark-Jersey City | 2,926 | 789K | 20.2% |
| Chicago-Naperville-Elgin | 1,932 | 230K | 13.2% |
| Los Angeles-Long Beach-Anaheim | 1,181 | 526K | 12.7% |
| San Francisco-Oakland-Fremont | 1,023 | 312K | 15.4% |
| Philadelphia-Camden-Wilmington | 749 | 91K | 11.3% |

---

## Files Modified

1. `api/labor_api_v6.py` - Added metro endpoints and filters
2. `frontend/labor_search_v6.html` - Metro dropdown and results display

## Test URLs

```
# List metros
http://localhost:8001/api/lookups/metros

# Metro stats
http://localhost:8001/api/metros/35620/stats

# Search by metro
http://localhost:8001/api/employers/search?metro=35620
```
