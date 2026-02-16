# Performance Profile

## Matching Throughput

- Exact pass sample: 5000 records, 9 matches, 0.529s (9450.39 rec/s)
- Fuzzy pass sample: 1500 records, 422 matches, 33.297s (45.05 rec/s)

## Query Timings

- Employer lookup: 0.045 ms
- Match log query: 0.551 ms
- Top occupations view: 2.632 ms

## Bottlenecks

- Slowest profiled query: Top occupations view (2.632 ms)
- Fuzzy tier costs more than exact tiers; batch size and trigram selectivity are primary levers.

## Recommendations

- Add/verify index on unified_match_log(source_system, status, created_at) for frequent filtered scans.
- Keep deterministic batch sizes between 1,000 and 5,000 records for stable throughput.
- For fuzzy tiers, test trigram thresholds 0.45-0.55 to trade recall for speed.
