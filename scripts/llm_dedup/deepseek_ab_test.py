"""
DeepSeek V4 vs Haiku 4.5 A/B test on dedup-judge labels.

Purpose
-------
Validate whether DeepSeek V4-Flash (or V4-Pro) produces the same labels Haiku
gave on our existing 39,127-pair validation batch. If agreement is >=92% we
can commit to running the full national dedup sweep on V4 at ~70-90% lower
cost (per the 2026-05-02 cost analysis; see vault session note).

Inputs
------
- validation_judge_prompt.SYSTEM_PROMPT   -- same v2 prompt Haiku saw
- anthropic_validation_batch_results.jsonl -- Haiku ground truth (raw model JSON)
- anthropic_validation_batch_manifest.json -- pair_type / source / state lookup
- validation_sample_45k.json              -- full pair input data
- DEEPSEEK_API_KEY env var (or `DeepSeek API=...` line in .env)

Outputs
-------
- deepseek_ab_results_<timestamp>.jsonl   -- per-pair raw model output
- deepseek_ab_summary_<timestamp>.json    -- agreement matrix + costs

Usage
-----
  py scripts/llm_dedup/deepseek_ab_test.py --model deepseek-v4-flash --n 200
  py scripts/llm_dedup/deepseek_ab_test.py --model deepseek-v4-pro --n 200
  py scripts/llm_dedup/deepseek_ab_test.py --smoke   # 1 pair only

Caching note
------------
DeepSeek caching is AUTOMATIC on prefix match (no cache_control flag needed).
The system prompt is ~3,945 tokens which exceeds the cache unit, so once the
first request writes it, all subsequent requests in the same call session
should hit the cache. Verify via `usage.prompt_cache_hit_tokens` field.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(DIR, "..", ".."))

from validation_judge_prompt import (  # noqa: E402
    SYSTEM_PROMPT,
    build_user_message,
)

# ---------------------------------------------------------------------------
# Pricing tables (USD per 1M tokens)
# ---------------------------------------------------------------------------
PRICING = {
    "deepseek-v4-flash": {
        # Standard pricing (no promo applies)
        "input_cache_miss": 0.14,
        "input_cache_hit":  0.0028,
        "output":           0.28,
    },
    "deepseek-v4-pro": {
        # 75% promo through 2026-05-31 15:59 UTC
        "input_cache_miss": 0.435,    # regular $1.74
        "input_cache_hit":  0.003625, # regular $0.0145
        "output":           0.87,     # regular $3.48
    },
    "deepseek-v4-pro-regular": {
        "input_cache_miss": 1.74,
        "input_cache_hit":  0.0145,
        "output":           3.48,
    },
    # Reference: Haiku 4.5 batch (50% off) with 90% cache discount on reads.
    "haiku-4-5-batch": {
        "input_cache_miss": 0.50,   # $1 base * 50% batch
        "input_cache_hit":  0.05,   # $0.10 cache read * 50% batch
        "output":           2.50,   # $5 base * 50% batch
    },
}

# ---------------------------------------------------------------------------
# Env loading (handles malformed `.env` lines like `DeepSeek API=...`)
# ---------------------------------------------------------------------------

def load_deepseek_key() -> str:
    # Try standard env vars first
    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_API", "DeepSeek_API"):
        if os.environ.get(var):
            return os.environ[var]

    # Fall back to regex scan of .env (handles `DeepSeek API=sk-...`)
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        raise RuntimeError(f".env not found at {env_path}")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if "deepseek" in line.lower():
                m = re.search(r"(sk-[A-Za-z0-9_-]+)", line)
                if m:
                    return m.group(1)
    raise RuntimeError(
        "DeepSeek API key not found. Add DEEPSEEK_API_KEY=sk-... to .env "
        "or rename the existing 'DeepSeek API=...' line."
    )

# ---------------------------------------------------------------------------
# Sample selection
# ---------------------------------------------------------------------------

# Stratified target: cover both pair_types AND all 6 labels.
# Total = 200. Over-samples rare classes (PARENT_CHILD, BROKEN) so the A/B
# has statistical power on them, then reweights when reporting if needed.
STRATA_QUOTAS = {
    ("dedup",     "DUPLICATE"):    30,
    ("dedup",     "UNRELATED"):    30,
    ("dedup",     "SIBLING"):      20,
    ("dedup",     "RELATED"):      20,
    ("dedup",     "PARENT_CHILD"): 10,
    ("dedup",     "BROKEN"):        2,
    ("hierarchy", "DUPLICATE"):    25,
    ("hierarchy", "UNRELATED"):    15,
    ("hierarchy", "SIBLING"):      25,
    ("hierarchy", "RELATED"):      15,
    ("hierarchy", "PARENT_CHILD"):  5,
    ("hierarchy", "BROKEN"):        3,
}


def parse_haiku_label(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        # Defensive: malformed single-line fences (```{...}```) have no newline
        # to split on; codex flagged that the prior version raised IndexError
        # outside the API-call try, killing the run. Use try/except.
        try:
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        except IndexError:
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:
        return None


def load_haiku_labels() -> dict:
    """Returns {custom_id: {label, confidence, primary_signal, raw_text}}."""
    path = os.path.join(DIR, "anthropic_validation_batch_results.jsonl")
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            cid = d.get("custom_id")
            r = d.get("result", {})
            if r.get("type") != "succeeded":
                continue
            msg = r.get("message", {})
            content = msg.get("content", [])
            text = "".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            )
            obj = parse_haiku_label(text)
            if obj and cid:
                out[cid] = {
                    "label": obj.get("label"),
                    "confidence": obj.get("confidence"),
                    "primary_signal": obj.get("primary_signal"),
                    "raw_text": text.strip(),
                }
    return out


def load_manifest() -> dict:
    path = os.path.join(DIR, "anthropic_validation_batch_manifest.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["pair_lookup"]


def load_sample() -> dict:
    """Returns {(id1, id2): pair_dict} from validation_sample_45k.json."""
    path = os.path.join(DIR, "validation_sample_45k.json")
    with open(path, "r", encoding="utf-8") as f:
        sample = json.load(f)
    return {(p["id1"], p["id2"]): p for p in sample}


def stratified_sample(haiku: dict, manifest: dict, sample_idx: dict, n: int,
                      seed: int) -> list:
    """Pick `n` (cid, pair_data, haiku_record) using STRATA_QUOTAS scaled
    proportionally if n != 200."""
    rng = random.Random(seed)
    # Scale quotas if n != 200. Floor at 1 per stratum so every label/pair_type
    # is represented; that means n must be >= len(STRATA_QUOTAS) (= 12) or the
    # adjust loop has nothing to subtract from. Bail out fast in that case.
    n_strata = len(STRATA_QUOTAS)
    if n < n_strata:
        # Codex flagged that the original adjust loop hangs forever when every
        # quota is at the floor of 1 and `diff` is still negative. Skip the
        # adjustment entirely and just take 1 per stratum (or 0 if n=0).
        scaled = {k: (1 if i < n else 0) for i, k in enumerate(STRATA_QUOTAS)}
    else:
        scale = n / 200.0
        scaled = {k: max(1, int(round(v * scale))) for k, v in STRATA_QUOTAS.items()}
        diff = n - sum(scaled.values())
        keys = list(scaled.keys())
        # Cap iterations to prevent infinite loop on edge cases.
        max_iters = 10 * abs(diff) + 100
        iters = 0
        while diff != 0 and iters < max_iters:
            iters += 1
            k = rng.choice(keys)
            if diff > 0:
                scaled[k] += 1; diff -= 1
            elif scaled[k] > 1:
                scaled[k] -= 1; diff += 1
        if diff != 0:
            print(f"WARNING: stratum quota adjust hit iter cap; off by {diff}")

    # Build candidate pool keyed by (pair_type, label)
    pool = defaultdict(list)
    for cid, h in haiku.items():
        meta = manifest.get(cid, {})
        pt = meta.get("pair_type")
        lbl = h["label"]
        pool[(pt, lbl)].append(cid)

    chosen = []
    missing = []
    for stratum, quota in scaled.items():
        cands = pool.get(stratum, [])
        if len(cands) < quota:
            missing.append((stratum, len(cands), quota))
            quota = len(cands)
        rng.shuffle(cands)
        for cid in cands[:quota]:
            meta = manifest[cid]
            id1 = meta["id1"]
            id2 = meta["id2"]
            try:
                id1n = int(id1) if id1 else id1
                id2n = int(id2) if id2 else id2
            except (TypeError, ValueError):
                id1n, id2n = id1, id2
            pair_data = (
                sample_idx.get((id1n, id2n))
                or sample_idx.get((id1, id2))
                or sample_idx.get((str(id1), str(id2)))
            )
            if pair_data is None:
                # Reconstruct minimal pair from manifest if sample missed it
                pair_data = {
                    "id1": id1, "id2": id2,
                    "display_name_1": meta.get("name1"),
                    "display_name_2": meta.get("name2"),
                    "source_1": meta.get("src1"),
                    "source_2": meta.get("src2"),
                    "pair_type": meta.get("pair_type"),
                }
            chosen.append({
                "custom_id": cid,
                "pair_data": pair_data,
                "haiku": haiku[cid],
                "stratum": stratum,
            })
    if missing:
        print("WARNING: undersized strata (took all available):")
        for s, have, want in missing:
            print(f"  {s}: have {have}, wanted {want}")
    return chosen

# ---------------------------------------------------------------------------
# DeepSeek call
# ---------------------------------------------------------------------------

def call_deepseek(client, model: str, pair_data: dict, max_tokens: int = 3000):
    # NB: DeepSeek V4 has thinking-mode enabled by default; reasoning tokens
    # consume the completion budget BEFORE the final JSON. Smoke testing showed
    # 60-300 reasoning tokens per call. 3000 leaves ample headroom.
    user_msg = build_user_message(pair_data)
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    elapsed = time.time() - t0

    text = resp.choices[0].message.content or ""
    usage = resp.usage
    cache_hit = getattr(usage, "prompt_cache_hit_tokens", None)
    cache_miss = getattr(usage, "prompt_cache_miss_tokens", None)
    if cache_hit is None and hasattr(usage, "model_extra"):
        # OpenAI SDK puts non-standard fields in model_extra
        ex = usage.model_extra or {}
        cache_hit = ex.get("prompt_cache_hit_tokens")
        cache_miss = ex.get("prompt_cache_miss_tokens")
    # Codex flagged: original fallback set miss=prompt_tokens when miss was
    # missing but hit was present, double-counting cached tokens. Compute miss
    # as prompt_tokens - hit (clamped to >=0) when API only returns hit.
    cache_hit_safe = cache_hit or 0
    if cache_miss is None:
        cache_miss_safe = max(usage.prompt_tokens - cache_hit_safe, 0)
    else:
        cache_miss_safe = cache_miss
    return {
        "text": text,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cache_hit_tokens": cache_hit_safe,
        "cache_miss_tokens": cache_miss_safe,
        "elapsed_s": elapsed,
    }

# ---------------------------------------------------------------------------
# Cost calc
# ---------------------------------------------------------------------------

def compute_cost(model: str, prompt_cache_hit: int, prompt_cache_miss: int,
                 output_tokens: int) -> float:
    p = PRICING[model]
    return (
        prompt_cache_hit  * p["input_cache_hit"]  / 1_000_000 +
        prompt_cache_miss * p["input_cache_miss"] / 1_000_000 +
        output_tokens     * p["output"]           / 1_000_000
    )

# ---------------------------------------------------------------------------
# Agreement analysis
# ---------------------------------------------------------------------------

# When comparing labels, treat MERGE-vs-NO-MERGE as the operationally critical
# signal. SIBLING/RELATED/PARENT_CHILD all collapse to "no merge but related."
LABEL_GROUPS = {
    "DUPLICATE":    "MERGE",
    "UNRELATED":    "DROP",
    "BROKEN":       "DROP",
    "SIBLING":      "RELATED",
    "RELATED":      "RELATED",
    "PARENT_CHILD": "RELATED",
}


def analyze(rows: list) -> dict:
    n = len(rows)
    exact = sum(1 for r in rows if r["deepseek_label"] == r["haiku_label"])
    grouped = sum(
        1 for r in rows
        if LABEL_GROUPS.get(r["deepseek_label"]) == LABEL_GROUPS.get(r["haiku_label"])
    )
    parse_fail = sum(1 for r in rows if r["deepseek_label"] is None)

    # Confusion matrix
    cm = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cm[r["haiku_label"]][r["deepseek_label"] or "_PARSE_FAIL"] += 1

    # Per-label agreement
    per_label = {}
    for haiku_lbl, ds_dist in cm.items():
        total = sum(ds_dist.values())
        ex = ds_dist.get(haiku_lbl, 0)
        per_label[haiku_lbl] = {
            "n": total,
            "exact_match": ex,
            "exact_pct": round(100*ex/total, 1) if total else 0,
            "ds_distribution": dict(ds_dist),
        }

    return {
        "n": n,
        "exact_agreement_pct":   round(100 * exact   / n, 2) if n else 0,
        "grouped_agreement_pct": round(100 * grouped / n, 2) if n else 0,
        "parse_fail_count":      parse_fail,
        "confusion_matrix": {
            haiku_lbl: dict(ds_dist) for haiku_lbl, ds_dist in cm.items()
        },
        "per_label": per_label,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    # Only the API-callable model names are valid CLI choices.
    # `deepseek-v4-pro-regular` is a pricing-comparison row in PRICING, NOT a
    # real model name — passing it to the API would fail every request.
    _api_models = [m for m in PRICING.keys()
                   if not m.endswith("-regular") and not m.startswith("haiku")]
    ap.add_argument("--model", default="deepseek-v4-flash", choices=_api_models)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true",
                    help="Run a single pair to verify auth + schema, then exit.")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="Seconds to sleep between requests (avoid rate limits)")
    args = ap.parse_args()

    print("[load] Haiku ground truth...")
    haiku = load_haiku_labels()
    print(f"  {len(haiku):,} parseable Haiku verdicts")
    manifest = load_manifest()
    print(f"  {len(manifest):,} pairs in manifest")
    sample_idx = load_sample()
    print(f"  {len(sample_idx):,} pairs in validation sample")

    print(f"\n[sample] stratified n={args.n} (seed={args.seed})")
    chosen = stratified_sample(haiku, manifest, sample_idx, args.n, args.seed)
    strata_counts = Counter(c["stratum"] for c in chosen)
    print("  actual strata sizes:")
    for s, c in sorted(strata_counts.items()):
        print(f"    {s[0]:11s} {s[1]:14s} {c:>3}")

    if args.smoke:
        chosen = chosen[:1]
        print("\n[smoke] running 1 pair only")

    # Bootstrap OpenAI client pointed at DeepSeek
    from openai import OpenAI
    api_key = load_deepseek_key()
    print(f"\n[auth] DeepSeek key loaded: {api_key[:6]}...{api_key[-4:]}")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # System prompt size sanity (DeepSeek caches automatically; no threshold doc'd
    # but the prompt is ~3.9K tokens which beats any plausible minimum)
    sys_chars = len(SYSTEM_PROMPT)
    print(f"[prompt] system_prompt_chars={sys_chars:,}  ~tokens={sys_chars//4:,}")
    print(f"[model]  {args.model}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = os.path.join(DIR, f"deepseek_ab_results_{ts}.jsonl")
    summary_path = os.path.join(DIR, f"deepseek_ab_summary_{ts}.json")

    rows = []
    total_cache_hit = 0
    total_cache_miss = 0
    total_output = 0
    total_cost = 0.0
    total_elapsed = 0.0

    print(f"\n[run] calling DeepSeek on {len(chosen)} pairs...")
    with open(results_path, "w", encoding="utf-8") as fout:
        for i, item in enumerate(chosen):
            cid = item["custom_id"]
            try:
                ds = call_deepseek(client, args.model, item["pair_data"])
            except Exception as e:
                print(f"  [{i+1:3d}/{len(chosen)}] {cid}  ERROR: {e}")
                row = {
                    "custom_id": cid,
                    "stratum": list(item["stratum"]),
                    "haiku_label": item["haiku"]["label"],
                    "haiku_confidence": item["haiku"]["confidence"],
                    "deepseek_label": None,
                    "deepseek_confidence": None,
                    "deepseek_primary_signal": None,
                    "deepseek_raw_text": None,
                    "error": str(e)[:200],
                }
                rows.append(row)
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                continue

            obj = parse_haiku_label(ds["text"]) or {}
            ds_label = obj.get("label")
            ds_conf = obj.get("confidence")
            ds_signal = obj.get("primary_signal")

            cost = compute_cost(
                args.model,
                ds["cache_hit_tokens"],
                ds["cache_miss_tokens"],
                ds["completion_tokens"],
            )
            total_cache_hit += ds["cache_hit_tokens"]
            total_cache_miss += ds["cache_miss_tokens"]
            total_output += ds["completion_tokens"]
            total_cost += cost
            total_elapsed += ds["elapsed_s"]

            agree = "MATCH" if ds_label == item["haiku"]["label"] else "DIFF"
            print(f"  [{i+1:3d}/{len(chosen)}] {cid:30s} "
                  f"haiku={item['haiku']['label']:13s} "
                  f"ds={str(ds_label):13s} {agree}  "
                  f"in={ds['prompt_tokens']:>5} (hit={ds['cache_hit_tokens']:>5}) "
                  f"out={ds['completion_tokens']:>3}  "
                  f"${cost:.5f}  {ds['elapsed_s']:.1f}s")

            row = {
                "custom_id": cid,
                "stratum": list(item["stratum"]),
                "haiku_label": item["haiku"]["label"],
                "haiku_confidence": item["haiku"]["confidence"],
                "haiku_primary_signal": item["haiku"]["primary_signal"],
                "deepseek_label": ds_label,
                "deepseek_confidence": ds_conf,
                "deepseek_primary_signal": ds_signal,
                "deepseek_raw_text": ds["text"],
                "prompt_tokens": ds["prompt_tokens"],
                "completion_tokens": ds["completion_tokens"],
                "cache_hit_tokens": ds["cache_hit_tokens"],
                "cache_miss_tokens": ds["cache_miss_tokens"],
                "elapsed_s": ds["elapsed_s"],
                "cost_usd": cost,
            }
            rows.append(row)
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            if args.sleep > 0:
                time.sleep(args.sleep)

    # Analyze
    successful = [r for r in rows if r.get("deepseek_label") is not None]
    analysis = analyze(rows)

    cache_hit_pct = (
        100 * total_cache_hit / max(1, total_cache_hit + total_cache_miss)
    )

    summary = {
        "model": args.model,
        "n_requested": args.n,
        "n_run": len(rows),
        "n_successful": len(successful),
        "seed": args.seed,
        "timestamp": ts,
        "agreement": analysis,
        "cost": {
            "total_usd": round(total_cost, 6),
            "per_pair_usd": round(total_cost / max(1, len(rows)), 6),
            "total_cache_hit_tokens": total_cache_hit,
            "total_cache_miss_tokens": total_cache_miss,
            "total_output_tokens": total_output,
            "cache_hit_pct": round(cache_hit_pct, 2),
        },
        "latency": {
            "total_s": round(total_elapsed, 2),
            "mean_s": round(total_elapsed / max(1, len(rows)), 2),
        },
        "extrapolation_to_5M_pairs": {
            "model": args.model,
            "tokens_per_pair_estimate": (
                total_cache_miss + total_cache_hit + total_output
            ) // max(1, len(rows)),
            "cost_5M_pairs_usd": round(
                total_cost / max(1, len(rows)) * 5_000_000, 0
            ),
        },
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # ---- Print human report ----
    print("\n" + "=" * 70)
    print(f"DEEPSEEK A/B SUMMARY  ({args.model})")
    print("=" * 70)
    print(f"Pairs run        : {len(rows)}")
    print(f"Parse failures   : {analysis['parse_fail_count']}")
    print(f"Exact agreement  : {analysis['exact_agreement_pct']}%")
    print(f"Grouped agreement: {analysis['grouped_agreement_pct']}%  "
          f"(MERGE/RELATED/DROP buckets)")
    print()
    print("Per-Haiku-label agreement:")
    for lbl, info in sorted(analysis["per_label"].items()):
        print(f"  haiku={lbl:13s} n={info['n']:>3}  "
              f"exact={info['exact_match']:>3} ({info['exact_pct']}%)")
        for ds_lbl, count in sorted(info["ds_distribution"].items(),
                                     key=lambda x: -x[1]):
            if ds_lbl != lbl:
                print(f"      -> deepseek={ds_lbl:14s} {count:>3}")
    print()
    print(f"Cache hit rate   : {cache_hit_pct:.1f}%  "
          f"(hit={total_cache_hit:,}, miss={total_cache_miss:,})")
    print(f"Output tokens    : {total_output:,}")
    print(f"Total cost       : ${total_cost:.4f}")
    print(f"Per-pair cost    : ${total_cost/max(1,len(rows)):.6f}")
    print(f"Wall time        : {total_elapsed:.1f}s "
          f"({total_elapsed/max(1,len(rows)):.2f}s/pair)")
    print()
    print("Extrapolation to 5M pair national sweep:")
    print(f"  Estimated cost : ${summary['extrapolation_to_5M_pairs']['cost_5M_pairs_usd']:,.0f}")
    print()
    print(f"Results JSONL    : {results_path}")
    print(f"Summary JSON     : {summary_path}")


if __name__ == "__main__":
    sys.exit(main())
