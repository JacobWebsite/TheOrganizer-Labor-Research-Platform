"""
Live-API calibration: send N candidate pairs to Claude Haiku, parse the
JSON verdicts, and print a summary so we can eyeball quality before paying
for a full Batch API run.

Defaults to a stratified mini-sample (some auto_duplicate, some ambiguous,
some auto_different) so we see how the prompt handles each tier.

Usage:
  py scripts/llm_dedup/calibrate_judge_live.py            # default 200 pairs
  py scripts/llm_dedup/calibrate_judge_live.py --n 50     # quick smoke
  py scripts/llm_dedup/calibrate_judge_live.py --concurrency 20

Requires ANTHROPIC_API_KEY in the environment (or in .env).
"""
import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from dedup_judge_prompt import (
    SYSTEM_PROMPT, JUDGE_MODEL, MAX_OUTPUT_TOKENS, PROMPT_VERSION,
    build_request_messages,
)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DIR, '..', '..', '.env'), override=True)
except ImportError:
    pass

import anthropic

CANDIDATES_PATH = os.path.join(DIR, 'candidates_singletons_scored.json')
RESULTS_PATH    = os.path.join(DIR, 'calibration_results.json')


def stratified_sample(pairs, n, seed=42):
    rng = random.Random(seed)
    by_class = {'auto_duplicate': [], 'ambiguous': [], 'auto_different': []}
    for p in pairs:
        by_class.setdefault(p['classification'], []).append(p)
    # Allocate proportional to overall mix but with floors
    mix = {
        'auto_duplicate':  max(20, n // 5),    # 20% or 20 floor
        'ambiguous':       max(20, (3 * n) // 5),  # 60%
        'auto_different':  max(20, n // 5),    # 20%
    }
    sample = []
    for cls, k in mix.items():
        bucket = by_class.get(cls, [])
        if not bucket:
            continue
        sample.extend(rng.sample(bucket, min(k, len(bucket))))
    rng.shuffle(sample)
    return sample[:max(n, len(sample))]


def judge_one(client, pair):
    messages = build_request_messages(pair)
    try:
        resp = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )
        text = "".join(block.text for block in resp.content if block.type == "text").strip()
        usage = {
            'input': resp.usage.input_tokens,
            'output': resp.usage.output_tokens,
            'cache_read': getattr(resp.usage, 'cache_read_input_tokens', 0) or 0,
            'cache_creation': getattr(resp.usage, 'cache_creation_input_tokens', 0) or 0,
        }
        # Strip optional code fences
        if text.startswith('```'):
            text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        try:
            verdict = json.loads(text)
        except Exception as e:
            return {'error': f'parse_fail: {e}', 'raw': text[:300], 'usage': usage}
        return {'verdict': verdict, 'usage': usage}
    except Exception as e:
        return {'error': f'api_fail: {type(e).__name__}: {str(e)[:200]}'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=200, help='target sample size')
    ap.add_argument('--concurrency', type=int, default=10, help='parallel workers')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ERROR: ANTHROPIC_API_KEY not set in env or .env', file=sys.stderr)
        return 1

    print(f'Prompt version: {PROMPT_VERSION}   Model: {JUDGE_MODEL}')
    with open(CANDIDATES_PATH) as f:
        all_pairs = json.load(f)
    sample = stratified_sample(all_pairs, args.n, seed=args.seed)
    print(f'Loaded {len(all_pairs):,} pairs; sampled {len(sample)} stratified.')

    client = anthropic.Anthropic()
    t0 = time.time()
    results = []
    totals = Counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {ex.submit(judge_one, client, p): p for p in sample}
        for i, fut in enumerate(as_completed(futures), 1):
            p = futures[fut]
            r = fut.result()
            results.append({'pair': p, 'response': r})
            if 'usage' in r:
                u = r['usage']
                totals['input']          += u.get('input', 0)
                totals['output']         += u.get('output', 0)
                totals['cache_read']     += u.get('cache_read', 0)
                totals['cache_creation'] += u.get('cache_creation', 0)
            if i % 25 == 0 or i == len(sample):
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0
                print(f'  {i}/{len(sample)} ({rate:.1f} req/s, {elapsed:.0f}s)')

    elapsed = time.time() - t0

    # Summary
    print('\n' + '=' * 60)
    print('CALIBRATION SUMMARY')
    print('=' * 60)
    print(f'Wall clock         : {elapsed:.1f}s')
    print(f'Throughput         : {len(sample)/elapsed:.1f} req/s')
    print(f'Total input tokens : {totals["input"]:,}')
    print(f'Cache read tokens  : {totals["cache_read"]:,}')
    print(f'Cache create tokens: {totals["cache_creation"]:,}')
    print(f'Total output tokens: {totals["output"]:,}')

    # Cost estimate (Haiku 4.5 pricing)
    INPUT_COST    = 1.00 / 1_000_000
    CACHE_READ    = 0.10 / 1_000_000
    CACHE_WRITE   = 1.25 / 1_000_000
    OUTPUT_COST   = 5.00 / 1_000_000
    cost = (totals['input']  * INPUT_COST
            + totals['cache_read']     * CACHE_READ
            + totals['cache_creation'] * CACHE_WRITE
            + totals['output'] * OUTPUT_COST)
    per_pair = cost / max(1, len(sample))
    print(f'Calibration cost   : ${cost:.4f}  (${per_pair*1000:.3f} per 1000 pairs)')
    print(f'Projected 31,532   : ${per_pair * 31532:.2f} live API')
    print(f'Projected via Batch: ${per_pair * 31532 / 2:.2f} (Batch API = 50% off)')

    # Verdict distribution
    verdicts = Counter()
    confidences = Counter()
    parse_fails = 0
    api_fails = 0
    by_heuristic = {}
    for r in results:
        resp = r['response']
        h = r['pair']['classification']
        if 'verdict' in resp:
            v = resp['verdict'].get('verdict', 'UNKNOWN')
            c = resp['verdict'].get('confidence', 'UNKNOWN')
            verdicts[v] += 1
            confidences[c] += 1
            by_heuristic.setdefault(h, Counter())[v] += 1
        elif 'error' in resp:
            if resp['error'].startswith('parse'):
                parse_fails += 1
            else:
                api_fails += 1

    print('\nVerdict distribution:')
    for k, v in verdicts.most_common():
        print(f'  {k:12s} {v}')
    print('\nConfidence distribution:')
    for k, v in confidences.most_common():
        print(f'  {k:12s} {v}')
    print('\nVerdict by heuristic class (cross-tab):')
    for h, vc in by_heuristic.items():
        print(f'  {h}:')
        for v, n in vc.most_common():
            print(f'    -> {v:12s} {n}')
    if parse_fails or api_fails:
        print(f'\nFailures: {parse_fails} parse, {api_fails} API')

    # Save raw
    with open(RESULTS_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            'prompt_version': PROMPT_VERSION,
            'model': JUDGE_MODEL,
            'sample_size': len(sample),
            'totals': dict(totals),
            'cost_estimate': round(cost, 4),
            'projected_full_run_live': round(per_pair * 31532, 2),
            'projected_full_run_batch': round(per_pair * 31532 / 2, 2),
            'results': results,
        }, f, indent=1, default=str)
    print(f'\nDetailed results: {RESULTS_PATH}')

    # Print 10 examples for spot-check
    print('\n--- 10 sample verdicts (eyeball these) ---')
    for r in results[:10]:
        p = r['pair']
        resp = r['response']
        n1 = (p.get('display_name_1') or '')[:45]
        n2 = (p.get('display_name_2') or '')[:45]
        if 'verdict' in resp:
            v = resp['verdict']
            print(f'  [{p["classification"]:14s}] -> {v.get("verdict","?"):10s} ({v.get("confidence","?"):6s})')
            print(f'     A: {n1}')
            print(f'     B: {n2}')
            print(f'     reason: {v.get("reason","")[:120]}')
        else:
            print(f'  [{p["classification"]:14s}] -> ERROR: {resp.get("error","")[:120]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
