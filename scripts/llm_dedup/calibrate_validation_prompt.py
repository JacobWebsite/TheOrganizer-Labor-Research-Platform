"""
Live-API calibration for the v2 validation prompt. Runs N pairs via live
Messages API and reports:
  - Actual token usage (input cached/uncached + output)
  - Projected full-batch cost based on measured averages
  - Label / primary_signal distribution of returned verdicts
  - JSON parse failures (must be 0 before we submit the full batch)
  - 10 sample verdicts printed for visual inspection

Usage:
  py scripts/llm_dedup/calibrate_validation_prompt.py             # default 100 pairs
  py scripts/llm_dedup/calibrate_validation_prompt.py --n 50
  py scripts/llm_dedup/calibrate_validation_prompt.py --concurrency 8
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from validation_judge_prompt import (  # noqa: E402
    SYSTEM_PROMPT, JUDGE_MODEL, MAX_OUTPUT_TOKENS, PROMPT_VERSION,
    build_request_messages,
)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DIR, "..", "..", ".env"), override=True)
except ImportError:
    pass

import anthropic

SAMPLE_PATH = os.path.join(DIR, "validation_sample_45k.json")
OUT_PATH = os.path.join(DIR, "calibration_validation_results.json")


def judge_one(client, pair):
    messages = build_request_messages(pair)
    t0 = time.time()
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
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "cache_creation_input_tokens": getattr(
                resp.usage, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(
                resp.usage, "cache_read_input_tokens", 0),
            "output_tokens": resp.usage.output_tokens,
        }
        return {"ok": True, "text": text, "usage": usage,
                "latency_s": time.time() - t0}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "latency_s": time.time() - t0}


def parse_verdict(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json\n"):
            t = t[5:]
    try:
        return json.loads(t)
    except Exception:
        i = t.find("{")
        if i >= 0:
            for j in range(len(t), i, -1):
                try:
                    return json.loads(t[i:j])
                except Exception:
                    pass
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        pairs = json.load(f)
    # Stratified: take pairs from every bucket/type mix proportionally
    # For simplicity, interleave first N pairs which are already shuffled per state
    sample = pairs[:args.n]
    print(f"Calibrating on {len(sample)} pairs ({args.concurrency} concurrent)")
    print(f"Prompt version: {PROMPT_VERSION}  model: {JUDGE_MODEL}")
    print(f"System prompt chars: {len(SYSTEM_PROMPT):,}")
    print()

    client = anthropic.Anthropic()
    results = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        fut_map = {pool.submit(judge_one, client, p): p for p in sample}
        done = 0
        for fut in as_completed(fut_map):
            p = fut_map[fut]
            r = fut.result()
            r["pair_type"] = p.get("pair_type")
            r["tier_bucket"] = p.get("tier_bucket")
            r["state"] = p.get("state")
            r["id1"] = p.get("id1")
            r["id2"] = p.get("id2")
            r["name1"] = p.get("display_name_1")
            r["name2"] = p.get("display_name_2")
            results.append(r)
            done += 1
            if done % 20 == 0:
                elapsed = time.time() - t0
                print(f"  {done}/{len(sample)}  ({elapsed:.1f}s elapsed, "
                      f"{done/elapsed:.1f}/s)")

    elapsed = time.time() - t0
    print(f"\nTotal: {len(results)} results in {elapsed:.1f}s  "
          f"({len(results)/elapsed:.1f}/s)")

    # Token usage aggregation
    successes = [r for r in results if r["ok"]]
    parse_ok = 0
    parse_errs = []
    labels = Counter()
    signals = Counter()
    confidences = Counter()
    unknown_signals = Counter()

    from validation_judge_prompt import PRIMARY_SIGNAL_ENUM
    valid_signals = set(PRIMARY_SIGNAL_ENUM)

    total_input = 0
    total_cache_write = 0
    total_cache_read = 0
    total_output = 0
    for r in successes:
        u = r["usage"]
        total_input += u["input_tokens"]
        total_cache_write += u["cache_creation_input_tokens"] or 0
        total_cache_read += u["cache_read_input_tokens"] or 0
        total_output += u["output_tokens"]

        v = parse_verdict(r["text"])
        if v is None:
            parse_errs.append(r["text"][:200])
        else:
            parse_ok += 1
            labels[v.get("label", "?")] += 1
            confidences[v.get("confidence", "?")] += 1
            sig = v.get("primary_signal", "?")
            signals[sig] += 1
            if sig not in valid_signals and sig != "?":
                unknown_signals[sig] += 1

    errors = [r for r in results if not r["ok"]]
    print(f"\nAPI errors: {len(errors)}")
    for e in errors[:5]:
        print(f"  {e['error']}")

    print(f"\nParse successes: {parse_ok}/{len(successes)}  "
          f"({100*parse_ok/max(1,len(successes)):.1f}%)")
    print(f"Parse failures: {len(parse_errs)}")
    for t in parse_errs[:3]:
        print(f"  SAMPLE: {t!r}")

    print("\nLabel distribution:")
    for label, n in labels.most_common():
        print(f"  {label:15s} {n:>4} ({100*n/max(1,parse_ok):.1f}%)")

    print("\nConfidence distribution:")
    for c, n in confidences.most_common():
        print(f"  {c:10s} {n:>4} ({100*n/max(1,parse_ok):.1f}%)")

    print("\nTop 15 primary_signals:")
    for sig, n in signals.most_common(15):
        flag = "" if sig in valid_signals else "  ** UNKNOWN"
        print(f"  {sig:35s} {n:>4}{flag}")
    if unknown_signals:
        print(f"\n** {len(unknown_signals)} unknown signal values (not in enum): **")
        for sig, n in unknown_signals.most_common(10):
            print(f"   {sig}: {n}")

    # Token averages
    n_ok = len(successes)
    avg_input = total_input / n_ok
    avg_cache_read = total_cache_read / n_ok
    avg_cache_write = total_cache_write / n_ok
    avg_output = total_output / n_ok

    print("\n=== Token usage (per pair average) ===")
    print(f"  input_tokens (non-cached): {avg_input:,.0f}")
    print(f"  cache_creation_input:      {avg_cache_write:,.0f}")
    print(f"  cache_read_input:          {avg_cache_read:,.0f}")
    print(f"  output_tokens:             {avg_output:,.0f}")

    cache_hit_rate = total_cache_read / max(1, total_cache_read + total_cache_write)
    print(f"\nCache read vs write: {100*cache_hit_rate:.1f}% cache hit rate "
          f"(= {total_cache_read:,} read vs {total_cache_write:,} write)")

    # Cost estimate for full 45K batch
    # Haiku 4.5 pricing with Batch 50% discount:
    BATCH_DISCOUNT = 0.5
    INPUT_BASE = 1.00   # $/MTok
    CACHE_WRITE = 1.25  # $/MTok (first-time, 25% premium)
    CACHE_READ = 0.10   # $/MTok (90% off)
    OUTPUT = 5.00       # $/MTok

    FULL_N = 39_161  # actual sample size

    # Assume cache hit rate holds: 99%+ after the first request writes
    # Projected: every request incurs (non-cached input + output), plus
    # system-prompt reads from cache (once written).
    # Simpler: extrapolate total tokens * cost per token.
    proj_input = avg_input * FULL_N / 1_000_000 * INPUT_BASE * BATCH_DISCOUNT
    proj_cache_write = avg_cache_write * FULL_N / 1_000_000 * CACHE_WRITE * BATCH_DISCOUNT
    proj_cache_read = avg_cache_read * FULL_N / 1_000_000 * CACHE_READ * BATCH_DISCOUNT
    proj_output = avg_output * FULL_N / 1_000_000 * OUTPUT * BATCH_DISCOUNT

    total_cost = proj_input + proj_cache_write + proj_cache_read + proj_output

    print(f"\n=== Projected cost for {FULL_N:,}-pair batch (Haiku 4.5 Batch API) ===")
    print(f"  input (non-cached):   ${proj_input:.2f}")
    print(f"  cache creation:       ${proj_cache_write:.2f}")
    print(f"  cache reads:          ${proj_cache_read:.2f}")
    print(f"  output:               ${proj_output:.2f}")
    print(f"  TOTAL:                ${total_cost:.2f}")
    print(f"  +30% buffer:          ${total_cost * 1.3:.2f}")

    # Save full calibration log
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "n_requested": args.n,
            "n_ok": n_ok,
            "n_errors": len(errors),
            "n_parse_ok": parse_ok,
            "n_parse_fail": len(parse_errs),
            "avg_tokens": {
                "input_non_cached": avg_input,
                "cache_creation": avg_cache_write,
                "cache_read": avg_cache_read,
                "output": avg_output,
            },
            "total_tokens": {
                "input_non_cached": total_input,
                "cache_creation": total_cache_write,
                "cache_read": total_cache_read,
                "output": total_output,
            },
            "labels": dict(labels),
            "confidences": dict(confidences),
            "signals": dict(signals),
            "unknown_signals": dict(unknown_signals),
            "projected_batch_cost_usd": total_cost,
            "projected_batch_cost_with_buffer_usd": total_cost * 1.3,
        }, f, indent=2)
    print(f"\nSaved log -> {OUT_PATH}")

    # Print 10 sample verdicts for visual review
    print("\n=== 10 sample verdicts (for visual review) ===")
    for r in successes[:10]:
        v = parse_verdict(r["text"]) or {}
        print(f"\n  [{r.get('tier_bucket','?')}] {r['name1']!r:60} vs {r['name2']!r}")
        print(f"    -> {v.get('label','?')}/{v.get('confidence','?')}  "
              f"signal={v.get('primary_signal','?')}")
        print(f"       {v.get('reasoning','')[:200]}")


if __name__ == "__main__":
    sys.exit(main())
