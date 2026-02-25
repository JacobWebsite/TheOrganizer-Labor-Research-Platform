# I11 - Geocoding Gap by Score Tier

Generated: 2026-02-24 19:05

## Summary

Overall geocoding rate: **122,351** / **146,863** (83.3%). **24,512** employers lack coordinates.

## Geocoding Rate by Score Tier

| Score Tier | Total | Geocoded | % Geocoded |
|------------|------:|--------:|-----------:|
| Priority | 2,283 | 1,907 | 83.5% |
| Strong | 15,424 | 13,036 | 84.5% |
| Promising | 40,733 | 34,087 | 83.7% |
| Moderate | 51,698 | 43,181 | 83.5% |
| Low | 36,725 | 30,140 | 82.1% |

## Overall Rate

| Metric | Value |
|--------|------:|
| Total employers | 146,863 |
| Geocoded | 122,351 |
| Missing coordinates | 24,512 |
| Geocoding rate | 83.3% |

## Top 10 States with Geocoding Gaps

| State | Total | Missing | % Missing |
|-------|------:|--------:|----------:|
| NY | 16,138 | 2,055 | 12.7% |
| IL | 14,416 | 1,978 | 13.7% |
| CA | 17,351 | 1,798 | 10.4% |
| PA | 9,627 | 1,640 | 17.0% |
| NJ | 7,313 | 1,333 | 18.2% |
| OH | 6,997 | 759 | 10.8% |
| MI | 6,767 | 755 | 11.2% |
| MN | 6,080 | 738 | 12.1% |
| WA | 5,561 | 676 | 12.2% |
| MO | 5,324 | 640 | 12.0% |

## Implications

- Geocoding gaps affect geographic search, map visualizations, and metro-level analysis.
- If higher-priority tiers have lower geocoding rates, those employers are under-represented in location-based features.
- States with the largest absolute gaps should be prioritized for batch geocoding runs (Census Bureau batch geocoder, max 10K per batch).
- Consider geocoding Priority and Strong tiers first to maximize value from the geocoding pipeline.
