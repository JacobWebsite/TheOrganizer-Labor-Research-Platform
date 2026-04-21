"""
Convert candidates_singletons_scored.json into an Anthropic Message Batches
input file (.jsonl). Each line is one batch request, custom_id = "pair_<id1>_<id2>".

Run after blocking, before submission. The submitter script reads this file and
posts it to /v1/messages/batches.

Usage:
  py scripts/llm_dedup/prep_anthropic_batch.py
  py scripts/llm_dedup/prep_anthropic_batch.py --limit 5000      # subset
  py scripts/llm_dedup/prep_anthropic_batch.py --classes ambiguous,auto_duplicate
"""
import argparse
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from dedup_judge_prompt import (
    SYSTEM_PROMPT, JUDGE_MODEL, MAX_OUTPUT_TOKENS, PROMPT_VERSION,
    build_request_messages,
)

CANDIDATES_PATH = os.path.join(DIR, 'candidates_singletons_scored.json')
BATCH_PATH      = os.path.join(DIR, 'anthropic_batch_input.jsonl')
MANIFEST_PATH   = os.path.join(DIR, 'anthropic_batch_manifest.json')

# Anthropic Batch API caps
MAX_REQUESTS_PER_BATCH = 100_000
MAX_BYTES_PER_BATCH    = 256 * 1024 * 1024  # 256 MB


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None,
                    help='cap total requests (for smaller pilot)')
    ap.add_argument('--classes', default='auto_duplicate,ambiguous,auto_different',
                    help='comma-separated heuristic classes to include')
    args = ap.parse_args()

    keep_classes = {c.strip() for c in args.classes.split(',') if c.strip()}

    with open(CANDIDATES_PATH) as f:
        all_pairs = json.load(f)

    selected = [p for p in all_pairs if p['classification'] in keep_classes]
    print(f'Loaded {len(all_pairs):,} pairs; {len(selected):,} match classes={sorted(keep_classes)}')

    if args.limit and args.limit < len(selected):
        selected = selected[:args.limit]
        print(f'Capped to first {len(selected):,} (--limit)')

    if len(selected) > MAX_REQUESTS_PER_BATCH:
        print(f'WARNING: {len(selected):,} > {MAX_REQUESTS_PER_BATCH:,} batch limit. '
              'You will need to split across multiple batches.')

    # Write JSONL
    seen_ids = set()
    bytes_written = 0
    with open(BATCH_PATH, 'w', encoding='utf-8') as out:
        for p in selected:
            cid = f'pair_{p["id1"]}_{p["id2"]}'
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            req = {
                'custom_id': cid,
                'params': {
                    'model': JUDGE_MODEL,
                    'max_tokens': MAX_OUTPUT_TOKENS,
                    'system': [{
                        'type': 'text',
                        'text': SYSTEM_PROMPT,
                        'cache_control': {'type': 'ephemeral'},
                    }],
                    'messages': build_request_messages(p),
                },
            }
            line = json.dumps(req, ensure_ascii=False) + '\n'
            bytes_written += len(line.encode('utf-8'))
            out.write(line)

    print(f'\nWrote {len(seen_ids):,} requests -> {BATCH_PATH}')
    print(f'File size: {bytes_written/1024/1024:.1f} MB '
          f'({100*bytes_written/MAX_BYTES_PER_BATCH:.1f}% of 256 MB cap)')

    # Manifest -- helpful when matching results back to original pair metadata
    manifest = {
        'prompt_version': PROMPT_VERSION,
        'model': JUDGE_MODEL,
        'classes_included': sorted(keep_classes),
        'request_count': len(seen_ids),
        'bytes': bytes_written,
        'pair_lookup': {  # custom_id -> minimal pair info for joining results
            f'pair_{p["id1"]}_{p["id2"]}': {
                'id1': p['id1'], 'id2': p['id2'],
                'classification': p['classification'],
                'composite': p['scores']['composite'],
                'name1': p.get('display_name_1'),
                'name2': p.get('display_name_2'),
                'src1': p.get('source_1'),
                'src2': p.get('source_2'),
            }
            for p in selected
        },
    }
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=1, default=str)
    print(f'Manifest: {MANIFEST_PATH}')

    # Cost estimate based on calibration prior
    PER_PAIR_LIVE  = 0.00065   # ballpark: ~$20 for 31K pairs with caching
    PER_PAIR_BATCH = PER_PAIR_LIVE / 2
    print('\nCost estimate (rough, refine with calibration script):')
    print(f'  Live API : ${len(seen_ids) * PER_PAIR_LIVE:.2f}')
    print(f'  Batch API: ${len(seen_ids) * PER_PAIR_BATCH:.2f}')


if __name__ == '__main__':
    sys.exit(main())
