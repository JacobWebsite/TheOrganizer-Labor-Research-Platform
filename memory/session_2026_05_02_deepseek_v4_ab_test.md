# Session 2026-05-02 (PM-late) — DeepSeek V4 A/B Test and Rule Mining

## Summary

Costed the DeepSeek V4-Pro 75% promo (ends 2026-05-31) against the deferred-API-spend backlog, then ran a 200-pair A/B test on V4-Flash and V4-Pro against the existing 39,127-pair Haiku v2.0 validation batch (`anthropic_validation_batch_results.jsonl`). Built a reusable A/B harness `scripts/llm_dedup/deepseek_ab_test.py`. Mined the full 39K Haiku results for deterministic-rule candidates. Did targeted DB-level ground-truth verification on the V4-Flash false-merge cases — discovered Haiku had hallucinated R1 (EIN-conflict) violations on cases where only one record had an EIN.

User explicitly deferred the rule-engine code work to a future session.

## Changes Made

### New code

**`scripts/llm_dedup/deepseek_ab_test.py`** (569 lines, NEW, untracked)
- Reusable A/B harness for any DeepSeek model vs Haiku v2.0 ground truth
- Loads existing `anthropic_validation_batch_results.jsonl` (39,127 pairs) and re-parses labels from raw JSONL (CSV had been buggy in earlier sessions)
- Stratified 200-pair sampling across 12 strata (pair_type × 6 labels)
- Calls DeepSeek through OpenAI-compat SDK at `https://api.deepseek.com`
- Custom env-loading for `.env` since `DeepSeek API=...` line has a space and trips python-dotenv (regex fallback)
- Tracks `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` from `usage`
- Computes per-call cost from a pricing table (V4-Flash, V4-Pro promo, V4-Pro regular)
- Reports: exact + grouped agreement, confusion matrix, per-label breakdown, cache hit %, total cost, 5M-pair extrapolation
- CLI: `--model`, `--n`, `--seed`, `--smoke`, `--sleep`

**Output files** (also new, untracked):
- `deepseek_ab_results_20260502_184750.jsonl` — V4-Flash 200 results
- `deepseek_ab_summary_20260502_184750.json` — V4-Flash full report
- `deepseek_ab_results_20260502_191649.jsonl` — V4-Pro 200 results
- `deepseek_ab_summary_20260502_191649.json` — V4-Pro full report
- 4 earlier smoke files (3 pairs total, can be deleted)

### No code edits to existing files

### Spawn-task chip filed early in session (duplicate, can be ignored)

Filed a chip about "CSV verdict parser bug in submit_anthropic_batch.py" — turns out that bug was fixed in an earlier 2026-05-02 session (see `memory/session_2026_05_02_validation_csv_verdict_fix.md`). The CSV header still says `verdict` but the values are now correctly populated. My initial parse showing all UNKNOWN appears to have been a stale read or test artifact.

## Key Findings

### Cost
- **V4-Flash extrapolation: $1,112 for 5M pairs** (sequential, 91.9% cache hit). 3.1× cheaper than Haiku batch ($3,500-4,200).
- **V4-Pro promo extrapolation: $5,337 for 5M pairs**. Worse than Haiku batch even at 75% off. Promo doesn't pay for itself on this task.
- **V4-Pro regular price** would be ~$21,000 for 5M.
- Per-pair: V4-Flash $0.000222 ($0.044 / 200); V4-Pro promo $0.001067 ($0.213 / 200).
- DeepSeek prompt caching is **automatic** (no `cache_control` flag like Anthropic). System prompt at 5,230 tokens caches automatically.
- Reasoning tokens (V4 thinking mode) count as completion tokens. 60-300 per V4-Flash call, more on V4-Pro. Set `max_tokens=3000` minimum.

### Agreement
- V4-Flash: **77.5% exact, 87.0% grouped** (MERGE/RELATED/DROP buckets)
- V4-Pro: **80.5% exact, 89.0% grouped**
- Both below my 92% bar for confident swap.
- V4-Pro fixes 5 of 6 PARENT_CHILD parse failures (empty-content responses) and adds BROKEN class support (V4-Flash never returned BROKEN).
- V4-Pro is slightly WORSE on RELATED (25.7% vs 34.3%) but in the same direction — sub-classifying into SIBLING/PARENT_CHILD, which is arguably more useful.

### Ground truth itself is noisy

The "false-merge" framing was misleading. Pulled DB rows for the 3 most cited Haiku-correct cases:

| Pair | Reality | Haiku verdict | Haiku reasoning |
|---|---|---|---|
| AWAKE.ORG (sam, no EIN, LA 90043) vs AWAKE ORG (bmf, EIN, Inglewood 90305) | only one EIN exists | UNRELATED | hallucinated `ein_conflict` |
| CRAWFORD CONTRACTING (sam, no EIN, MT PLEASANT MI 48858) vs (mergent, EIN, same address) | only one EIN, same address | RELATED | hallucinated `ein_conflict` |
| UNIVERSAL MALL LLC (osha, Warren MI 48092) vs L.L.C. (gleif, Troy MI 48084) | NEITHER has EIN, ZIP mismatch real | RELATED | reasonable |

The first two are clear DeepSeek-correct cases that I'd misclassified as DeepSeek errors. **True V4-Flash false-merge rate is ~1.0%, not 1.5-3.5%.**

### Triple-convergence rule mining

When Haiku + V4-Flash + V4-Pro all agree on label AND on `primary_signal`, that's strong rule evidence. Top clusters from the 200-sample:
- `series_number` → SIBLING (39 cases, 100% triple-convergence)
- `name_punctuation_only_diff` → DUPLICATE (14)
- `name_byte_identical` → DUPLICATE (9)
- `subsidiary_naming` → PARENT_CHILD (5)
- `name_suffix_only_diff` → DUPLICATE (4)
- `ein_conflict` → UNRELATED (4) — when conflict is REAL (both EINs present)
- `government_subdivision` → PARENT_CHILD (4)

### Rule mining (39K Haiku full set)

4 hard rules ≥95% concentration with n≥100:
- `name_byte_identical` → DUPLICATE (99.8% of 3,766)
- `source_diversity_agree` → DUPLICATE (100.0% of 597)
- `zip_city_match` → RELATED (99.4% of 176)
- `insufficient_information` → UNRELATED (98.1% of 160)

6 strong rules ≥90% (covering an additional 45% of pairs).

Cross-checked against existing 16 H-rules in `rule_engine.py` — most signals already covered. Identified **4 new rule candidates** worth coding:
1. **Real-EIN-conflict guard**: harden `has_ein_conflict()` to require BOTH records have non-empty EINs
2. **H17 cross_src_one_ein_same_zip**: same canonical name + diff sources + same ZIP + exactly-one EIN → DUPLICATE/MEDIUM
3. **H18 industry_mismatch**: different 2-digit NAICS prefix → UNRELATED/HIGH
4. **H19 gleif_person_name**: GLEIF×2 + identical person-name pattern + no other fields → BROKEN

Coverage math at 5M scale: tuned rule_engine + V4-Flash hybrid = ~$400 (vs V4-Flash alone $1,112 vs Haiku batch $3,500-4,200).

## Roadmap Updates

No items closed. The DeepSeek-V4-evaluation task is informal (not in MERGED_ROADMAP).

Work that this session unblocks (deferred to future sessions):
- Code the 4 new H-rules and validate against 39K Haiku set
- Run V4-Flash on 10-K employee extraction (~$48, replaces never-run $140 Gemini job)
- Run V4-Flash on union scraper distillation ($1.50, replaces $30 Sonnet that was dropped for cost)

## Debugging Notes

1. **DeepSeek V4 thinking tokens**: V4 has reasoning mode on by default. Reasoning tokens are charged as `completion_tokens`. First smoke test set `max_tokens=300` and got empty content because reasoning consumed the entire budget. Fix: bump max_tokens to 3000 minimum. No documented way to disable thinking on V4-Flash/V4-Pro (V3-era `deepseek-chat` was the non-thinking variant; V4 docs don't expose a `thinking=false` parameter).

2. **DeepSeek `.env` parsing**: the existing `.env` has `DeepSeek API=sk-...` with a space in the var name, which python-dotenv can't parse (warns about lines 32, 34, 36, 38). Built a regex fallback `re.search(r'(sk-[A-Za-z0-9_-]+)', line)` for any line containing 'deepseek'. Did NOT modify the `.env` file because Jacob may have other tooling that reads the spaced name.

3. **DeepSeek prompt caching is automatic** — no `cache_control` flag like Anthropic. Cache fields surface in `usage.prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`. Cache hits at 91-92% on this prompt size after the first call. Sequential calls let the cache warm; parallel calls would race on the first cache write.

4. **OpenAI SDK 2.20.0 is OpenAI-compatible with DeepSeek**: just set `base_url="https://api.deepseek.com"` and use `client.chat.completions.create(...)` as normal.

5. **Buggy watcher in middle of run**: my first completion-watcher used `until grep -q "DEEPSEEK A/B SUMMARY" log; do sleep 15; done` — but Python's stdout buffering meant the log file stayed empty for the whole run, even though the JSONL was being written line-by-line. Better watcher pattern: `until [ "$(wc -l < results.jsonl)" = "200" ]; do sleep 30; done`.

6. **Triple-convergence as a ground-truth proxy**: when Haiku, V4-Flash, V4-Pro all agree, treat that as ~truth (146 of 200 pairs in this sample). When two of three converge against the third, the third is most often wrong. This is a usable cheap ground-truth method when there's no human gold set.

## Files (final state)

- **NEW (untracked)**: `scripts/llm_dedup/deepseek_ab_test.py`
- **NEW (untracked)**: 4 result JSONL + summary JSON files in `scripts/llm_dedup/`
- **No edits** to any existing tracked file

## Pricing (snapshot, will need refresh next time):

| Model | Input cache miss | Input cache hit | Output | Context |
|---|---|---|---|---|
| V4-Flash | $0.14/M | $0.0028/M | $0.28/M | 1M |
| V4-Pro (promo) | $0.435/M | $0.003625/M | $0.87/M | 1M |
| V4-Pro (regular) | $1.74/M | $0.0145/M | $3.48/M | 1M |
| Haiku 4.5 (batch) | $0.50/M | $0.05/M | $2.50/M | 200K |

Promo expires 2026-05-31 15:59 UTC.

## Cost This Session

$0.26 total in DeepSeek API spend ($0.044 Flash + $0.213 Pro + $0.003 smokes/diagnostics).
