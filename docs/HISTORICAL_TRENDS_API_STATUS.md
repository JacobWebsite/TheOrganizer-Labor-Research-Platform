# Historical Trends API - Status Summary

**Date:** January 29, 2026  
**Status:** ✅ COMPLETE - All endpoints implemented and tested

---

## Available Endpoints

### Membership Trends

| Endpoint | Description | Status |
|----------|-------------|--------|
| `GET /api/trends/national` | National membership by year (2010-2024) | ✅ |
| `GET /api/trends/affiliations/summary` | Top 30 affiliations with growth rates | ✅ |
| `GET /api/trends/by-affiliation/{aff_abbr}` | Yearly trends for specific union | ✅ |
| `GET /api/trends/states/summary` | All states with 2010 vs 2024 comparison | ✅ |
| `GET /api/trends/by-state/{state}` | Yearly trends for specific state | ✅ |

### Election Trends

| Endpoint | Description | Status |
|----------|-------------|--------|
| `GET /api/trends/elections` | NLRB elections by year (2007-2024) | ✅ |
| `GET /api/trends/elections/by-affiliation/{aff_abbr}` | Elections for specific union | ✅ |

### Sector Analysis

| Endpoint | Description | Status |
|----------|-------------|--------|
| `GET /api/trends/sectors` | Employers by NAICS sector | ✅ |

---

## Sample Responses

### National Trends
```
GET /api/trends/national

{
  "trends": [
    {"year": 2010, "union_count": 24063, "total_members_raw": 61622057},
    {"year": 2024, "union_count": 19536, "total_members_raw": 70114653}
  ]
}
```

### Affiliation Summary (Top 5)
```
GET /api/trends/affiliations/summary

AFL-CIO:  13.5M (2024), +14.8% from 2010
AFT:       7.3M (2024), +238.5% from 2010
SEIU:      4.9M (2024), +6.8% from 2010
NEA:       3.7M (2024), -15.5% from 2010
IBT:       3.6M (2024), +0.7% from 2010
```

### Election Trends (Key Years)
```
GET /api/trends/elections

2010: 2,068 elections, 60.2% win rate
2015: 1,923 elections, 73.0% win rate
2020: 1,030 elections, 68.6% win rate (COVID)
2024: 2,091 elections, 76.6% win rate
```

### Sector Distribution (Top 5)
```
GET /api/trends/sectors

Construction (23):     12,119 employers, 4.2M workers
Manufacturing (31):     9,402 employers, 1.3M workers
Healthcare (62):        7,173 employers, 2.1M workers
Transportation (48):    5,618 employers, 700K workers
Hospitality (72):       2,802 employers, 349K workers
```

---

## Data Coverage

- **OLMS Membership:** 15 years (2010-2024), ~20K unions/year
- **NLRB Elections:** 18 years (2007-2024), 1,000-2,100 elections/year
- **F-7 Employers:** 63,118 deduplicated employers with NAICS codes

---

## Notes

1. **Raw vs Reconciled Data:** National trends show raw OLMS totals (~60-70M) which include hierarchy double-counting. BLS benchmark is ~14-15M.

2. **HQ Location Effect:** DC shows highest membership due to national headquarters concentration. State-level analysis requires careful interpretation.

3. **Election Win Rate Trend:** Union win rates have increased from 53% (2007) to 77% (2024), reflecting changing organizing landscape.

---

## Next Steps (Optional Enhancements)

1. **Trends Visualization Tab** - Chart.js-based UI to display trends
2. **Reconciled Membership Trends** - Apply deduplication logic to historical data
3. **Industry Trends** - Track membership changes within NAICS sectors
4. **Geographic Heat Maps** - County/MSA level trend visualization
