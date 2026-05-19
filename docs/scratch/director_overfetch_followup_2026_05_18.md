# Director endpoint over-fetch: deferred follow-up

Date: 2026-05-18
Branch: `ship/2026-05-18-drop-director-overfetch` (no-op + this note)
Decision: **DEFER**

## Background

Round 4 of today's 20-agent sweep flagged the `limit * 3` over-fetch in two
endpoints as potentially wasted work, on the theory that SQL/Python parity
holds after the BoardCard fix:

- `api/routers/directors.py:200` — `params["row_limit"] = limit * 3`
- `api/routers/director_network.py:127` — implicit (no LIMIT on the 1-hop
  query, but the Python `one_hop_clean` comprehension on line 127 drops
  rows the SQL clause already missed)

The claim was that, because `api/services/director_name_filter.py` now
mirrors the Python predicate rule-for-rule in SQL, the Python residue
filter at the response boundary catches nothing and the over-fetch is
fetching rows the SQL clause already excludes.

## Investigation

The premise is true on `ship/2026-05-18-boardcard-filter-fix` (tip
`75a015e`) — there the SQL clause was extended to include the year-regex
guard (`director_name !~ '[[:<:]](19|20)[0-9]{2}[[:>:]]'`) and the
punctuation-stripped numeric first-token guard
(`RTRIM(SPLIT_PART(TRIM(director_name), ' ', 1), '.,;:') !~ '^[0-9]+$'`).

But on master (`86ca1ed`), neither guard is in SQL. Compare
`api/services/director_name_filter.py:119-128` (master) versus the same
file at `75a015e:119-145`. Master SQL only has: NOT NULL + length +
token-count >= 2 + bad_first_words + bad_subs. The Python predicate
(`is_likely_real_director_name`) adds, on top of that:

1. `re.search(r"\b(19|20)\d{2}\b", s)` — rejects names containing a
   4-digit year. Catches proxy-statement page-header leakage like
   `"2026 Proxy Statement 15"`, `"All directors and"`-after-`"2026"`,
   etc.
2. `first_word.isdigit()` — rejects names whose first whitespace-token
   is purely numeric (catches `"12 2026 Proxy Statement"`-style after
   the year regex would also catch it; both layered for defense).

These are exactly the residue classes the `limit * 3` comment refers to:
`small over-fetch for the year-regex residue`.

So on master, removing the over-fetch would cause two concrete failure
modes:

- `/api/directors?limit=25` against a population where the top SQL-survivors
  contain year-bearing garbage (e.g. a master whose DEF14A parser admitted
  multiple "2026 Proxy Statement N" rows above the real-director threshold)
  would return fewer than 25 entries even though >=25 real directors exist
  past the LIMIT cutoff. `len(out)` could be 22 instead of 25 if 3 of the
  top 25 SQL-survivors are year-bearing residue.
- `director_network` would silently undercount 1-hop neighbors whose only
  shared director is a year-bearing name. (Less likely than (1) but the
  same class.)

## Why "land it anyway" is risky

The task prompt's worst-case framing was: "until boardcard merges, the
response array might be very slightly under-filled for masters with heavy
year-regex residue." That's accurate but understates the scope: today's
`load_def14a_filings.py` pipeline has demonstrated affinity for this
class of false-positive (root cause that triggered the original SQL
fix). Until parity holds in SQL, the over-fetch is doing real work.

The fix is also one-line trivial to land *after* the boardcard branch
merges. There's no carry cost to deferring.

## When to land this fix

When `ship/2026-05-18-boardcard-filter-fix` (currently tip `75a015e`)
lands on master, re-open this branch and:

1. Change `api/routers/directors.py:200`
   from `params["row_limit"] = limit * 3`
   to   `params["row_limit"] = limit`.
2. Drop the `if len(out) >= limit: break` guard at line 228-229 (still
   harmless but no longer load-bearing; can stay or go).
3. Audit `api/routers/director_network.py` for similar 3x patterns; the
   one-hop block at line 127 uses a Python comprehension to filter and
   has no LIMIT in SQL, so there's nothing to change there — it just
   becomes a no-op pass.
4. Add the regression test from this PR's stub (see
   `tests/api/test_directors_no_overfetch.py` — does NOT exist yet
   because that test would fail today on master).

## What this PR does

Documents the deferral and creates the branch so the work item is
tracked. No code change. The branch ships as evidence of the audit
trail, not as a behavioral change.

## Boeing / Walmart sanity check (informational, no code change required)

Per the task prompt, here is what a before/after on master would look
like:

- Before (today, on master with `limit * 3`): SQL fetches 75 rows for
  `?limit=25`; Python filters out year-bearing residue (call it
  `R = residue_count` for that master); response returns
  `min(25, 75 - R)` entries. For most masters `R = 0`, so 25 of 75.
- Hypothetical-after (today, with this branch merged ahead of boardcard
  fix): SQL fetches 25 rows; Python returns `25 - R`. For masters with
  any year-bearing residue, response is short.

Concrete Boeing pre-boardcard-merge state: BoardCard's `directors[]`
returned 0 elements vs `director_count=8`. That's the exact divergence
class — all 8 SQL-survivors were year-bearing parser garbage. With this
branch merged but not the boardcard fix, `/api/directors?limit=25` on a
similar master would return 0-3 entries instead of 25.

## Cross-reference

- Boardcard branch: `ship/2026-05-18-boardcard-filter-fix` (tip
  `75a015e`, in-flight PR per MEMORY.md `session_2026_05_18_18_agent_sweep_7_ship_branches`).
- Originating master 4238837 (Pfizer master canonical name corruption)
  is unrelated; this is a different finding from the same audit pass.
