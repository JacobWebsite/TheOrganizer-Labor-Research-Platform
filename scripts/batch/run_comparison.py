import os
"""Run all 9 scenarios with limit 200 and report results."""
import psycopg2
import sys
import time

sys.path.insert(0, r'C:\Users\jakew\Downloads\labor-data-project')
from scripts.matching.pipeline import MatchPipeline
from scripts.matching.config import list_scenarios

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))

results = []
for scenario_name in list_scenarios():
    print(f"Running {scenario_name}...", end=" ", flush=True)
    start = time.time()
    try:
        pipeline = MatchPipeline(conn, scenario=scenario_name, skip_fuzzy=True)
        stats = pipeline.run_scenario(limit=200)
        elapsed = time.time() - start
        tier_breakdown = {v: stats.by_method.get(v, 0) for v in ['EIN', 'NORMALIZED', 'ADDRESS', 'AGGRESSIVE']}
        results.append({
            'scenario': scenario_name,
            'status': 'OK',
            'source': stats.total_source,
            'matched': stats.total_matched,
            'rate': stats.match_rate,
            'tiers': tier_breakdown,
            'time': elapsed,
        })
        print(f"{stats.total_matched}/{stats.total_source} ({stats.match_rate:.1f}%) in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start
        results.append({
            'scenario': scenario_name,
            'status': f'FAIL: {e}',
            'source': 200,
            'matched': 0,
            'rate': 0,
            'tiers': {},
            'time': elapsed,
        })
        print(f"FAIL: {e}")
        conn.rollback()

print("\n" + "=" * 90)
print(f"{'Scenario':<25} {'Status':<6} {'Src':>5} {'Match':>5} {'Rate':>7} {'EIN':>5} {'NORM':>5} {'ADDR':>5} {'AGGR':>5} {'Time':>6}")
print("-" * 90)
for r in results:
    t = r['tiers']
    print(f"{r['scenario']:<25} {r['status']:<6} {r['source']:>5} {r['matched']:>5} {r['rate']:>6.1f}% {t.get('EIN',0):>5} {t.get('NORMALIZED',0):>5} {t.get('ADDRESS',0):>5} {t.get('AGGRESSIVE',0):>5} {r['time']:>5.1f}s")

total_matched = sum(r['matched'] for r in results)
total_source = sum(r['source'] for r in results)
ok_count = sum(1 for r in results if r['status'] == 'OK')
print("-" * 90)
print(f"{'TOTAL':<25} {ok_count}/9   {total_source:>5} {total_matched:>5} {total_matched/total_source*100:>6.1f}%")

conn.close()
