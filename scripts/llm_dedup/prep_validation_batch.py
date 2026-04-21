"""
Convert validation_sample_45k.json into an Anthropic Message Batches input file
(.jsonl) using the v2 validation prompt (validation_judge_prompt.py).

Each line is one batch request with custom_id = "pair_<id1>_<id2>".
The system prompt is marked for ephemeral caching (>=2048 tokens enables the
90% cache-read discount after the first hit).

Usage:
  py scripts/llm_dedup/prep_validation_batch.py
  py scripts/llm_dedup/prep_validation_batch.py --limit 500     # for calibration
  py scripts/llm_dedup/prep_validation_batch.py --limit 500 --out anthropic_batch_calibration.jsonl
"""
import argparse
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from validation_judge_prompt import (  # noqa: E402
    SYSTEM_PROMPT, JUDGE_MODEL, MAX_OUTPUT_TOKENS, PROMPT_VERSION,
    build_request_messages,
)

SAMPLE_PATH = os.path.join(DIR, "validation_sample_45k.json")
DEFAULT_OUT = os.path.join(DIR, "anthropic_validation_batch_input.jsonl")
MANIFEST_PATH = os.path.join(DIR, "anthropic_validation_batch_manifest.json")

# Batch API caps
MAX_REQUESTS_PER_BATCH = 100_000
MAX_BYTES_PER_BATCH = 256 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=SAMPLE_PATH,
                    help="Input sample JSON path")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Output JSONL path")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap total requests (e.g., for calibration)")
    args = ap.parse_args()

    with open(args.sample, "r", encoding="utf-8") as f:
        pairs = json.load(f)

    print(f"Loaded {len(pairs):,} pairs from {args.sample}")
    if args.limit and args.limit < len(pairs):
        # Use slice for reproducibility (sample was already randomized during build)
        pairs = pairs[:args.limit]
        print(f"Capped to first {len(pairs):,} via --limit")

    if len(pairs) > MAX_REQUESTS_PER_BATCH:
        print(f"WARNING: {len(pairs):,} > {MAX_REQUESTS_PER_BATCH:,} batch cap; "
              "you will need to split across batches.")

    seen_ids = set()
    bytes_written = 0
    manifest = {
        "prompt_version": PROMPT_VERSION,
        "model": JUDGE_MODEL,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "pair_lookup": {},
    }

    with open(args.out, "w", encoding="utf-8") as out:
        for p in pairs:
            id1 = p.get("id1") or ""
            id2 = p.get("id2") or ""
            cid = f"pair_{id1}_{id2}"
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            req = {
                "custom_id": cid,
                "params": {
                    "model": JUDGE_MODEL,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "system": [{
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    "messages": build_request_messages(p),
                },
            }
            line = json.dumps(req, ensure_ascii=False) + "\n"
            bytes_written += len(line.encode("utf-8"))
            out.write(line)

            # Keep minimal pair info in manifest for joining results later
            manifest["pair_lookup"][cid] = {
                "id1": id1, "id2": id2,
                "pair_type": p.get("pair_type"),
                "tier_bucket": p.get("tier_bucket"),
                "state": p.get("state"),
                "engine_rule": p.get("engine_rule"),
                "engine_tier": p.get("engine_tier"),
                "hier_rule": p.get("hier_rule"),
                "cluster_size": p.get("cluster_size"),
                "parent_candidate_name": p.get("parent_candidate_name"),
                "mostly_generic": p.get("mostly_generic"),
                "name1": p.get("display_name_1"),
                "name2": p.get("display_name_2"),
                "src1": p.get("source_1"),
                "src2": p.get("source_2"),
            }

    manifest["request_count"] = len(seen_ids)
    manifest["bytes"] = bytes_written

    print(f"\nWrote {len(seen_ids):,} requests -> {args.out}")
    print(f"File size: {bytes_written/1024/1024:.1f} MB "
          f"({100*bytes_written/MAX_BYTES_PER_BATCH:.1f}% of 256 MB cap)")

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, default=str)
    print(f"Manifest: {MANIFEST_PATH}")

    # Cost estimate (Haiku 4.5 Batch with caching)
    # Prices per 1M tokens:
    INPUT_CACHE_READ = 0.10   # $0.10/MTok for cached reads (90% off base $1)
    INPUT_CACHE_WRITE = 1.25  # $1.25/MTok first-time cache write (25% premium on base $1)
    INPUT_BASE = 1.00         # $1.00/MTok base input
    OUTPUT = 5.00             # $5.00/MTok base output
    BATCH_DISCOUNT = 0.5      # 50% off all Batch API

    system_tokens = len(SYSTEM_PROMPT) // 4  # ~3,445
    # First request writes the cache (1.25x), rest read it (0.10x)
    # Assume user message averages 300 tokens, output averages 200 tokens
    user_avg = 300
    output_avg = 200
    n = len(seen_ids)

    # Cache write (1 request) + cache reads (n-1)
    input_cost = (
        system_tokens * INPUT_CACHE_WRITE / 1_000_000 +
        system_tokens * (n - 1) * INPUT_CACHE_READ / 1_000_000 +
        user_avg * n * INPUT_BASE / 1_000_000
    ) * BATCH_DISCOUNT

    output_cost = output_avg * n * OUTPUT / 1_000_000 * BATCH_DISCOUNT

    print("\nCost estimate (Haiku 4.5 Batch + caching):")
    print(f"  Input:  ${input_cost:.2f}")
    print(f"  Output: ${output_cost:.2f}")
    print(f"  TOTAL:  ${input_cost + output_cost:.2f}")
    print("  (actual cost depends on realized token usage; calibration "
          "script gives better estimate after a 500-pair live run)")


if __name__ == "__main__":
    sys.exit(main())
