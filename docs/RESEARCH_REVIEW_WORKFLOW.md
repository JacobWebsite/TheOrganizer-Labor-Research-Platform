# Research Dossier Review Workflow

**Status:** Active (manual end-of-week pass)
**Last updated:** 2026-05-12
**Related open problem:** `Open Problems/Research Agent Human Review Near Zero.md`

## Why this document exists

The research agent has produced 192 completed runs holding 6,348 extracted facts, but as of 2026-05-12 only **1 fact has been human-reviewed**. The technical infrastructure for review is fully in place (DB columns, 24+ review API endpoints, frontend components). The gap is purely workflow: there is no defined cadence for who reviews what, when, or how reviews influence the next batch.

This document defines that workflow. It is intentionally lightweight so it can survive a launch crunch.

## Background: what review actually does

When a reviewer confirms or rejects a fact, the system propagates that verdict through three layers:

1. **`research_facts.human_verdict`** is set to `confirmed`, `rejected`, `irrelevant`, or `flagged`. A `reviewed_at` timestamp and `review_source` tag are recorded.
2. **`research_actions.data_quality`** is updated for the action that produced the fact, raising or lowering the tool's track record.
3. **`research_strategies.avg_quality`** is recomputed when enough reviews land for that (industry, company_type, size) bucket. This shifts the recommended tool order on the *next* research run, so good tools get tried earlier and weak ones are dropped.

In short: the closed loop only closes when a human says "this is right" or "this is wrong." Without that, the auto-grader is grading itself.

## The weekly review cadence (target)

Once per week (proposed: end of day Friday), one reviewer spends about 30 minutes doing the following:

1. Generate this week's review queue by running:
   ```powershell
   py scripts/research/list_dossiers_needing_review.py `
     --priority highest_quality `
     --limit 20 `
     --out files/review_queue_$(Get-Date -Format yyyy_MM_dd).csv
   ```
2. Open the CSV in Excel or paste it into a Google Sheet.
3. Pick **5 dossiers** from the top of the list (highest-quality unreviewed runs).
4. For each dossier, open the URL in `frontend_review_url`. Use the **Priority Review card** to look at the 5 facts most worth checking (contradicted, low-confidence, web-sourced numeric, low-tool-accuracy). Confirm or reject each. Optional: add a note.
5. After the 5 dossiers, set the **run-level usefulness verdict** (thumbs up / down) for each. This single signal triggers the strategy-quality update and is the most efficient feedback the reviewer can give.
6. Commit the CSV to `files/` so future audits can see what was reviewed when.

**Total: 5 dossiers x 5 facts = 25 reviews per week.** At that pace it takes about 6 months to chip through all 6,348 facts, but in practice the strategy-quality updates kick in long before that and the auto-grader-vs-human agreement rate can be measured after 50-100 reviews, at which point the cadence can be cut back to spot checks.

## The review queue script

`scripts/research/list_dossiers_needing_review.py` emits a CSV of unreviewed runs sorted by priority. Key flags:

| Flag | What it does |
|------|--------------|
| `--min-quality 6.0` | Lowest quality score to include (default 6.0 = dual-gate cutoff) |
| `--priority highest_quality` | Sort mode: `highest_quality` (default), `contradictions`, `gold_standard`, `most_facts`, `recent` |
| `--limit 20` | Max rows to emit (default 20) |
| `--gold-only` | Only include `is_gold_standard = TRUE` runs (for calibration passes) |
| `--out path.csv` | Write to file instead of stdout |
| `--tsv` | Tab-separated for paste into spreadsheets |

Each row carries the run identifier, the master employer it links to, the auto-grade score, fact rollup counts (contradictions, low-confidence, web-numeric), and a deep link straight to the review page in the frontend. Reviewers do not need to write SQL.

### Priority modes

- **highest_quality** — runs where confirmation has the most upside (these runs are already strong and review unlocks score enhancement).
- **contradictions** — runs flagged as internally inconsistent; review here unlocks consistency-score deductions.
- **gold_standard** — runs marked as calibration anchors; review here measures auto-grader accuracy.
- **most_facts** — runs with the most extracted facts but lowest review coverage (best for bulk reviewers).
- **recent** — most recent completions first (good for catching agent regressions early).

## Per-fact decision rules (short version)

A reviewer should mark a fact as:

- **`confirmed`** — the fact is supported by an authoritative source (government DB, primary corporate document, well-known reporter) and matches the value seen.
- **`rejected`** — the fact is contradicted by an authoritative source, or the agent hallucinated a value not present in the cited source.
- **`irrelevant`** — the fact is technically true but does not belong in the dossier (e.g., personal trivia about an executive, off-topic compliance issue from a different subsidiary).
- **`flagged`** — the reviewer is unsure. The flag-only button in the UI is the shorthand for "this needs a second look from someone with more context."

For the manual workflow, the **flag-only** route is the lowest-friction path. A reviewer who is short on time should flag uncertain facts and skip them rather than guessing — the auto-confirm endpoint (`POST /maintenance/auto-confirm`) will mark the unflagged facts as confirmed once the run-level usefulness is set, so flagging is conservative-correct.

## Auto-grader-vs-human agreement measurement

After ~50 reviews are in, run:

```sql
WITH agreement AS (
  SELECT
    f.id,
    f.human_verdict,
    f.confidence,
    CASE
      WHEN f.human_verdict IN ('confirmed', 'irrelevant') AND f.confidence >= 0.7 THEN 1
      WHEN f.human_verdict = 'rejected' AND f.confidence < 0.5 THEN 1
      WHEN f.human_verdict = 'flagged' THEN NULL
      ELSE 0
    END AS agrees
  FROM research_facts f
  WHERE f.human_verdict IS NOT NULL
)
SELECT
  COUNT(*) FILTER (WHERE agrees = 1) AS agreed,
  COUNT(*) FILTER (WHERE agrees = 0) AS disagreed,
  COUNT(*) FILTER (WHERE agrees IS NULL) AS flagged,
  ROUND(100.0 * COUNT(*) FILTER (WHERE agrees = 1) / NULLIF(COUNT(*) FILTER (WHERE agrees IS NOT NULL), 0), 1) AS agreement_pct
FROM agreement;
```

If agreement is >90%, drop the weekly cadence to spot-checking 10 facts per new batch run. If agreement is <70%, the auto-grader's confidence thresholds need to be retuned before any score enhancements are trusted.

## What this workflow does NOT cover

- **High-volume batch review.** If the agent ever produces hundreds of new runs per week, this manual cadence will not scale. The frontend UI already supports section-level approve/reject, bulk operations, and A/B comparison; once volume picks up, switch to that.
- **Calibration of the auto-grader rubric.** The grader uses fixed weights and thresholds defined in `scripts/research/auto_grader.py`. Adjusting those is a separate exercise that should follow ~200 reviewed facts, not precede it.
- **Reviewing the dossier prose itself.** The review surface is per-fact, not per-paragraph. The Gemini-generated narrative in each section is graded only for coverage and length; if a sentence is misleading but no specific fact backs it, the reviewer can leave a note on the run but cannot mark "this sentence is wrong" structurally. A future enhancement could add section-level prose flags.

## Files referenced

- `scripts/research/list_dossiers_needing_review.py` — review queue CSV generator.
- `api/routers/research.py` — review API (28 endpoints including per-fact verdict, section bulk, run usefulness, A/B compare, priority facts, gold standard toggle).
- `scripts/research/auto_grader.py` — `apply_human_fact_review()`, `apply_run_usefulness()`, `update_strategy_quality()` propagate verdicts into strategy quality.
- `frontend/src/features/research/` — review UI components (PriorityReviewCard, DossierHeader usefulness chips, section-level approve/reject).
- `Open Problems/Research Agent Human Review Near Zero.md` — vault note that motivated this workflow.

## Future automation (post-launch)

When time permits, the manual CSV pass can be replaced with:

1. A scheduled task (Friday 4 PM) that emits the CSV and posts it to a designated review channel.
2. A `/api/research/review/digest` endpoint that returns the same data as JSON for embedding in a dashboard.
3. An optional Slack/email digest that includes per-run thumbnails and direct review URLs.

None of these change the workflow described above — they just remove the manual `py scripts/research/list_dossiers_needing_review.py` step.
