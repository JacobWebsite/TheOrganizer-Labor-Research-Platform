# Historical Trends API - Checkpoint Plan

**Date:** January 29, 2026  
**Goal:** Create API endpoints for historical membership and election trends

---

## Data Available

**OLMS Membership Data (2010-2024):**
- 15 full years of data (2025 partial)
- 2010: 24,095 unions, 61.6M members
- 2024: 19,554 unions, 70.1M members (raw, pre-dedup)
- Key trends: AFT +238%, IATSE +453%, NEA -15%, UFCW -22%

**NLRB Election Data (2007-2024):**
- ~33,000 elections with outcomes
- Win rate trend: 53% (2007) → 77% (2024)
- 2024: 2,091 elections, 76.6% win rate

---

## Checkpoint 1: National Membership Trends API ⏳

**Goal:** Endpoint for overall union membership by year

**Endpoint:** `GET /api/trends/national`

**Response:**
```json
{
  "trends": [
    {"year": 2010, "total_members": 14300000, "union_count": 24095},
    {"year": 2024, "total_members": 14500000, "union_count": 19554}
  ]
}
```

**Notes:** 
- Use reconciled data to avoid double-counting
- Exclude Canadian members, retirees, hierarchy duplicates

**Validation:**
- [ ] Returns 15 years of data (2010-2024)
- [ ] Totals align with BLS benchmarks (~14-15M)

---

## Checkpoint 2: Affiliation Trends API ⏳

**Goal:** Membership trends by national union affiliation

**Endpoint:** `GET /api/trends/by-affiliation?aff_abbr=SEIU`

**Response:**
```json
{
  "affiliation": "SEIU",
  "trends": [
    {"year": 2010, "members": 1800000, "union_count": 150},
    {"year": 2024, "members": 1950000, "union_count": 140}
  ]
}
```

**Also:** `GET /api/trends/affiliations/summary` - Top 20 affiliations with growth rates

**Validation:**
- [ ] Returns data for specified affiliation
- [ ] Summary shows growth/decline percentages

---

## Checkpoint 3: State Trends API ⏳

**Goal:** Membership trends by state

**Endpoint:** `GET /api/trends/by-state?state=CA`

**Response:**
```json
{
  "state": "CA",
  "trends": [
    {"year": 2010, "members": 2500000, "union_count": 3200},
    {"year": 2024, "members": 2400000, "union_count": 2800}
  ]
}
```

**Also:** `GET /api/trends/states/summary` - All states with current membership

**Validation:**
- [ ] Returns data for specified state
- [ ] Summary ranks states by membership

---

## Checkpoint 4: NLRB Election Trends API ⏳

**Goal:** Election outcomes by year

**Endpoint:** `GET /api/trends/elections`

**Response:**
```json
{
  "trends": [
    {"year": 2010, "elections": 2068, "union_wins": 1245, "win_rate": 60.2},
    {"year": 2024, "elections": 2091, "union_wins": 1602, "win_rate": 76.6}
  ]
}
```

**Also:** `GET /api/trends/elections/by-affiliation?aff_abbr=SEIU`

**Validation:**
- [ ] Returns election data 2007-2024
- [ ] Win rates match database calculations

---

## Checkpoint 5: Industry Sector Trends API ⏳

**Goal:** Trends by NAICS sector (from F-7 employer data)

**Endpoint:** `GET /api/trends/by-sector`

**Response:**
```json
{
  "sectors": [
    {"naics_2digit": "62", "sector_name": "Health Care", "employer_count": 15000, "avg_unit_size": 250},
    {"naics_2digit": "23", "sector_name": "Construction", "employer_count": 8000, "avg_unit_size": 500}
  ]
}
```

**Validation:**
- [ ] Returns top sectors by employer count
- [ ] Links to NAICS sector names

---

## Checkpoint 6: Test & Verify ⏳

**Test Cases:**

| Endpoint | Expected Result |
|----------|-----------------|
| /api/trends/national | 15 years, ~14-15M members |
| /api/trends/by-affiliation?aff_abbr=SEIU | SEIU growth ~7% |
| /api/trends/by-state?state=NY | NY trends |
| /api/trends/elections | Win rate 53%→77% |

---

## Files to Modify

1. `api/labor_api_v6.py` - Add all trend endpoints

---

## Estimated Time: 4-6 hours

---

*Ready to begin. Proceeding with Checkpoint 1.*
