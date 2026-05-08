"""Export V12 trained state to JSON files for API consumption.

V12's training pipeline in run_v12.py produces three stateful artifacts:
  1. Calibration offsets (dict of tuple keys -> (offset, count))
  2. Per-industry Hispanic weights (dict of naics_group -> weight dict)
  3. Per-tier Hispanic weights (dict of tier -> weight dict)

None of these are saved by run_v12.py. The API needs them at request time
without retraining (which takes several minutes).

This script runs the V12 training pipeline once and saves the three artifacts
to JSON files in api/data/ so the V12 API service can load them at startup.

Usage:
    py scripts/analysis/demographics_comparison/export_v12.py

Output files:
    api/data/v12_calibration.json      - calibration offsets
    api/data/v12_hispanic_weights.json - industry + tier Hispanic weights
"""
import os
import sys
import json
import time
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPT_DIR)

from db_config import get_connection
from psycopg2.extras import RealDictCursor

from cached_loaders_v6 import CachedLoadersV6
from run_v9_2 import (
    train_industry_weights, train_tier_weights,
    train_calibration_v92,
)
from run_v10 import build_v10_splits, build_records, load_json
from run_v12 import v12_scenario, V12_HISP_WEIGHTS, EXPERT_A_WEIGHT, QWI_GENDER_WEIGHT
from run_v12_qwi import QWICache

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'api', 'data')


def serialize_offset_key(k):
    """Turn a tuple calibration key into a pipe-delimited string.

    Original shape: (dim, cat, level_name, *levels)
      e.g. ('race', 'White', 'dt_reg_ind', 'Med-High', 'South', 'Healthcare/Social (62)')
      or   ('hisp', 'Hispanic', 'global')

    Serialized: 'race|White|dt_reg_ind|Med-High|South|Healthcare/Social (62)'

    Pipe is safe because it does not appear in naics_group labels, regions,
    diversity tiers, or the fixed dimension/category/level strings.
    """
    return '|'.join(str(p) for p in k)


def main():
    t0 = time.time()
    print('V12 EXPORT -- trained state to JSON')
    print('=' * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load QWI cache
    qwi = QWICache()

    # Load data splits
    splits = build_v10_splits()
    cp_path = os.path.join(SCRIPT_DIR, 'v9_best_of_ipf_prediction_checkpoint.json')
    cp = load_json(cp_path)
    rec_lookup = {r['company_code']: r for r in cp['all_records']}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print('\nBuilding records...')
    all_companies = (splits['train_companies']
                     + splits['perm_companies']
                     + splits['v10_companies'])
    all_records = build_records(all_companies, rec_lookup, cl)

    train_records = [r for r in all_records if r['company_code'] in splits['train_codes']]
    print('  train=%d' % len(train_records))

    # Train Hispanic weights
    print('\nTraining Hispanic weights...')
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    print('  industry_weights: %d groups' % len(industry_weights))
    print('  tier_best_weights: %d tiers' % len(tier_best_weights))

    # Add QWI Hispanic signal to all records
    for rec in all_records:
        qwi_hisp = qwi.get_hispanic(rec['county_fips'], rec['naics4'])
        rec['signals']['qwi_hisp'] = qwi_hisp

    # V12 scenario function (partially applied)
    def scenario_fn(rec):
        return v12_scenario(rec, qwi, industry_weights, tier_best_weights)

    # Train V12 calibration
    print('\nTraining V12 calibration...')
    cal = train_calibration_v92(train_records, scenario_fn, max_offset=20.0)
    print('  %d calibration buckets' % len(cal))

    level_counts = defaultdict(int)
    for k in cal:
        level_counts[k[2]] += 1
    for level in ['dt_reg_ind', 'dt_ind', 'reg_ind', 'ind', 'global']:
        print('    %-15s %4d buckets' % (level, level_counts.get(level, 0)))

    # Serialize calibration (tuple keys -> pipe-delimited strings)
    cal_serializable = {
        serialize_offset_key(k): {'offset': v[0], 'n': v[1]}
        for k, v in cal.items()
    }

    cal_out = {
        'description': 'V12 calibration offsets, trained 2026-04-14',
        'max_offset': 20.0,
        'levels': ['dt_reg_ind', 'dt_ind', 'reg_ind', 'ind', 'global'],
        'n_buckets': len(cal_serializable),
        'offsets': cal_serializable,
    }
    cal_path = os.path.join(OUTPUT_DIR, 'v12_calibration.json')
    with open(cal_path, 'w', encoding='utf-8') as f:
        json.dump(cal_out, f, indent=2)
    print('\nWrote %s (%d bytes)' % (cal_path, os.path.getsize(cal_path)))

    # Serialize Hispanic weights
    hw_out = {
        'description': 'V12 Hispanic blend weights, trained 2026-04-14',
        'default_v12_weights': V12_HISP_WEIGHTS,
        'expert_a_weight': EXPERT_A_WEIGHT,
        'qwi_gender_weight': QWI_GENDER_WEIGHT,
        'industry_weights': industry_weights,
        'tier_best_weights': tier_best_weights,
    }
    hw_path = os.path.join(OUTPUT_DIR, 'v12_hispanic_weights.json')
    with open(hw_path, 'w', encoding='utf-8') as f:
        json.dump(hw_out, f, indent=2)
    print('Wrote %s (%d bytes)' % (hw_path, os.path.getsize(hw_path)))

    cur.close()
    conn.close()

    print('\nTotal runtime: %.0fs' % (time.time() - t0))
    print('Done.')


if __name__ == '__main__':
    main()
