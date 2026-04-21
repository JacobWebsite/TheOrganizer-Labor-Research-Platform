"""
Submit anthropic_batch_input.jsonl to Anthropic's Message Batches API,
poll for completion, and download results.

Three subcommands:
  submit   -- upload the .jsonl, get back a batch_id, save it to state file.
  status   -- poll the existing batch_id and print progress + ETA.
  fetch    -- once status is "ended", download results.jsonl and parse into
              a CSV joined with the prep manifest.

Usage:
  py scripts/llm_dedup/submit_anthropic_batch.py submit
  py scripts/llm_dedup/submit_anthropic_batch.py status
  py scripts/llm_dedup/submit_anthropic_batch.py fetch

Requires ANTHROPIC_API_KEY in env or .env.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DIR, '..', '..', '.env'), override=True)
except ImportError:
    pass

import anthropic

BATCH_INPUT    = os.path.join(DIR, 'anthropic_batch_input.jsonl')
MANIFEST_PATH  = os.path.join(DIR, 'anthropic_batch_manifest.json')
STATE_PATH     = os.path.join(DIR, 'anthropic_batch_state.json')
RESULTS_JSONL  = os.path.join(DIR, 'anthropic_batch_results.jsonl')
RESULTS_CSV    = os.path.join(DIR, 'anthropic_batch_results.csv')


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------

def cmd_submit(args):
    if not os.path.exists(BATCH_INPUT):
        print(f'ERROR: {BATCH_INPUT} not found. Run prep_anthropic_batch.py first.')
        return 1

    # Quick request count + size
    n = sum(1 for _ in open(BATCH_INPUT, 'r', encoding='utf-8'))
    size_mb = os.path.getsize(BATCH_INPUT) / 1024 / 1024
    print(f'Batch input: {n:,} requests, {size_mb:.1f} MB')

    if not args.yes:
        print('\nThis will submit a billable batch to Anthropic.')
        confirm = input('Type "submit" to proceed: ').strip()
        if confirm != 'submit':
            print('Aborted.')
            return 1

    # The SDK accepts an iterable of request dicts. Stream from the JSONL file.
    def request_iter():
        with open(BATCH_INPUT, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                yield {
                    'custom_id': obj['custom_id'],
                    'params': obj['params'],
                }

    # Split into chunks if requested (--chunk-size N submits N batches sequentially).
    requests = list(request_iter())
    if args.skip_first:
        print(f'  --skip-first {args.skip_first:,} -> skipping already-submitted requests')
        requests = requests[args.skip_first:]
    chunk_size = args.chunk_size or len(requests)
    chunks = [requests[i:i+chunk_size] for i in range(0, len(requests), chunk_size)]
    print(f'\nSubmitting {len(chunks)} batch(es), '
          f'{chunk_size:,} request(s) each (last may be smaller)...')

    # Resume from existing state if any
    existing = load_state()
    batch_ids = list(existing.get('batch_ids', []))
    if batch_ids:
        print(f'  (resuming with {len(batch_ids)} pre-existing batch_id(s))')

    t0 = time.time()
    for i, chunk in enumerate(chunks, 1):
        print(f'  [{i}/{len(chunks)}] uploading {len(chunk):,} requests...')
        # Fresh client per chunk -- reusing the connection pool after a 40MB POST
        # was triggering WinError 10054 connection resets on Windows.
        last_err = None
        for attempt in range(1, 4):
            client = anthropic.Anthropic(timeout=1800.0, max_retries=0)
            try:
                b = client.messages.batches.create(requests=chunk)
                batch_ids.append(b.id)
                print(f'    -> batch_id: {b.id}  status: {b.processing_status}')
                # Save state immediately so a subsequent failure doesn't lose this id
                save_state({
                    'batch_ids': batch_ids,
                    'batch_id': batch_ids[0],
                    'submitted_at': time.time(),
                    'request_count': n,
                    'partial_progress': f'{i}/{len(chunks)} chunks',
                })
                break
            except Exception as e:
                last_err = e
                print(f'    attempt {attempt}/3 failed: {type(e).__name__}: {str(e)[:120]}')
                if attempt < 3:
                    sleep_s = 10 * attempt
                    print(f'    sleeping {sleep_s}s before retry...')
                    time.sleep(sleep_s)
        else:
            print(f'    ALL ATTEMPTS FAILED for chunk {i}. Aborting; resume with '
                  f'--skip-first {(args.skip_first or 0) + i*chunk_size}')
            return 1
        # Brief pause between chunks to be gentle on the network
        time.sleep(3)
    elapsed = time.time() - t0

    state = {
        'batch_ids': batch_ids,
        'batch_id': batch_ids[0],  # backwards compat for status/fetch (pre-split)
        'submitted_at': time.time(),
        'request_count': n,
        'submit_elapsed_sec': round(elapsed, 1),
    }
    save_state(state)
    print('\n--- Submitted ---')
    for bid in batch_ids:
        print(f'  batch_id: {bid}')
    print(f'(submit took {elapsed:.1f}s)')
    print(f'\nState saved: {STATE_PATH}')
    print('Next: py scripts/llm_dedup/submit_anthropic_batch.py status')
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def cmd_status(args):
    state = load_state()
    batch_ids = state.get('batch_ids') or ([state['batch_id']] if state.get('batch_id') else [])
    if not batch_ids:
        print('No batch_ids in state. Run submit first.')
        return 1

    client = anthropic.Anthropic()
    if args.watch:
        prev = None
        while True:
            statuses = [client.messages.batches.retrieve(bid) for bid in batch_ids]
            agg = {'processing': 0, 'succeeded': 0, 'errored': 0, 'canceled': 0, 'expired': 0}
            all_ended = True
            for b in statuses:
                c = b.request_counts
                for k in agg:
                    agg[k] += getattr(c, k, 0)
                if b.processing_status != 'ended':
                    all_ended = False
            line = (f'[{time.strftime("%H:%M:%S")}] '
                    f'{"ALL ENDED" if all_ended else "in_progress":12s}  '
                    f'processing={agg["processing"]} succeeded={agg["succeeded"]} '
                    f'errored={agg["errored"]} canceled={agg["canceled"]} '
                    f'expired={agg["expired"]}')
            if line != prev:
                print(line)
                prev = line
            if all_ended:
                print('\nAll batches ended. Run fetch.')
                state['ended_at'] = time.time()
                save_state(state)
                return 0
            time.sleep(args.interval)
    else:
        for bid in batch_ids:
            b = client.messages.batches.retrieve(bid)
            c = b.request_counts
            print(f'batch_id: {b.id}')
            print(f'  status: {b.processing_status}  ended_at: {b.ended_at}')
            print(f'  counts: processing={c.processing} succeeded={c.succeeded} '
                  f'errored={c.errored} canceled={c.canceled} expired={c.expired}')
        return 0


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def cmd_fetch(args):
    state = load_state()
    batch_ids = state.get('batch_ids') or ([state['batch_id']] if state.get('batch_id') else [])
    if not batch_ids:
        print('No batch_ids in state. Run submit first.')
        return 1

    client = anthropic.Anthropic()
    for bid in batch_ids:
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != 'ended':
            print(f'Batch {bid} is {b.processing_status}, not ended yet.')
            return 1

    print(f'Downloading results streams for {len(batch_ids)} batch(es)...')
    n = 0
    succeeded = 0
    errored = 0
    parse_fail = 0
    verdict_counts = Counter()
    confidence_counts = Counter()

    # Load manifest for join keys
    manifest = {}
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f).get('pair_lookup', {})

    with open(RESULTS_JSONL, 'w', encoding='utf-8') as out_jsonl, \
         open(RESULTS_CSV, 'w', encoding='utf-8') as out_csv:
        out_csv.write('custom_id,id1,id2,classification,composite,src1,src2,'
                      'name1,name2,verdict,confidence,reason\n')

        all_entries = []
        for bid in batch_ids:
            for entry in client.messages.batches.results(bid):
                all_entries.append(entry)
        for entry in all_entries:
            n += 1
            custom_id = entry.custom_id
            d = entry.model_dump() if hasattr(entry, 'model_dump') else dict(entry)
            out_jsonl.write(json.dumps(d, default=str) + '\n')

            # Result type: succeeded | errored | canceled | expired
            r = entry.result
            rtype = getattr(r, 'type', None) or (r.get('type') if isinstance(r, dict) else None)
            if rtype != 'succeeded':
                errored += 1
                continue
            succeeded += 1

            # Pull message text
            msg = getattr(r, 'message', None) or (r.get('message') if isinstance(r, dict) else None)
            content = getattr(msg, 'content', None) or (msg.get('content') if isinstance(msg, dict) else [])
            text = ''
            for block in content:
                btype = getattr(block, 'type', None) or (block.get('type') if isinstance(block, dict) else None)
                if btype == 'text':
                    text += getattr(block, 'text', None) or (block.get('text') if isinstance(block, dict) else '')
            text = text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()

            try:
                verdict_obj = json.loads(text)
            except Exception:
                parse_fail += 1
                continue

            v = verdict_obj.get('verdict', 'UNKNOWN')
            c = verdict_obj.get('confidence', 'UNKNOWN')
            verdict_counts[v] += 1
            confidence_counts[c] += 1

            meta = manifest.get(custom_id, {})
            def _csv(s):
                if s is None:
                    return ''
                s = str(s).replace('"', "'").replace('\n', ' ').replace(',', ';')
                return f'"{s}"'

            out_csv.write(','.join([
                custom_id,
                str(meta.get('id1', '')), str(meta.get('id2', '')),
                meta.get('classification', ''),
                f'{meta.get("composite", 0):.4f}' if meta.get('composite') is not None else '',
                _csv(meta.get('src1')), _csv(meta.get('src2')),
                _csv(meta.get('name1')), _csv(meta.get('name2')),
                v, c, _csv(verdict_obj.get('reason', '')),
            ]) + '\n')

    print(f'\nFetched {n:,} entries')
    print(f'  succeeded: {succeeded:,}')
    print(f'  errored:   {errored:,}')
    print(f'  parse_fail (succeeded but bad JSON): {parse_fail:,}')
    print('\nVerdict distribution:')
    for k, v in verdict_counts.most_common():
        print(f'  {k:12s} {v:>6,}')
    print('\nConfidence distribution:')
    for k, v in confidence_counts.most_common():
        print(f'  {k:12s} {v:>6,}')
    print(f'\nWrote {RESULTS_JSONL} and {RESULTS_CSV}')
    return 0


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('submit')
    sp.add_argument('--yes', action='store_true', help='skip confirmation prompt')
    sp.add_argument('--chunk-size', type=int, default=None,
                    help='split into batches of this size (avoids 162MB single-POST issues)')
    sp.add_argument('--skip-first', type=int, default=0,
                    help='skip the first N requests (resume after a partial submit)')
    sp.set_defaults(func=cmd_submit)

    sp = sub.add_parser('status')
    sp.add_argument('--watch', action='store_true', help='poll until done')
    sp.add_argument('--interval', type=int, default=30, help='poll interval seconds')
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser('fetch')
    sp.set_defaults(func=cmd_fetch)

    args = ap.parse_args()

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ERROR: ANTHROPIC_API_KEY not set in env or .env', file=sys.stderr)
        return 1
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
