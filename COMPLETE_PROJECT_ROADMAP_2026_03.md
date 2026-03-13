# COMPLETE PROJECT ROADMAP
## Based on Round 4 Three-Audit Synthesis — March 2026

---

## HOW THIS ROADMAP WORKS

This document turns every finding from all three Round 4 audits (Claude Code, Codex, Gemini) plus the synthesis into a concrete, ordered plan. It's organized into phases from "do this today" to "do this in 6 months."

Every task has:
- **What to do** — in plain English
- **Why it matters** — what breaks or improves
- **How long it takes** — rough estimate
- **What skills are needed** — so we know which AI or person handles it
- **How to verify it worked** — a specific check
- **Dependencies** — what needs to happen first

Every phase also has **Open Questions** — things we need to investigate or decide before proceeding. Some of these are questions the audits asked but nobody fully answered.

**Important note on "skills needed":** When a task says "SQL" or "Python," that means it requires writing or running database queries or code. Tasks marked "Manual Research" mean a human needs to look things up on websites. Tasks marked "Decision" mean someone needs to make a judgment call about what the platform should do.

---

## PHASE 0: EMERGENCY FIXES (Do Immediately — Hours)

These are things that are either actively dangerous (security) or actively misleading users (broken features that look like they work). Drop everything and do these first.

---

### TASK 0-1: Rotate All Exposed Credentials
**Source:** All three auditors confirmed

**What to do:** The database password, the login security key, and the Google Maps key are all sitting in a readable file (``.env``) on the server. Anyone who gets access to this file can control the entire platform — they could read all the data, change scores, or delete everything.

Three specific credentials need to be changed:
1. The database password (currently a simple word+number pattern)
2. The JWT secret (this is what proves a logged-in user is really who they claim to be)
3. The Google API key (used for maps and location features)

**Steps:**
1. Generate a new random database password (20+ characters, mix of letters/numbers/symbols)
2. Generate a new random JWT secret (at least 64 characters)
3. Go to the Google Cloud Console and create a new API key, then delete the old one
4. Update the ``.env`` file with all three new values
5. Restart the application so it picks up the new credentials
6. Test that login works, the database connects, and maps load

**Why it matters:** If anyone ever saw the old credentials (even briefly), they could access the entire system. The database password is especially weak — it's a dictionary word with a number.

**How long:** 1-2 hours
**Skills needed:** System administration (someone comfortable with server settings)
**Dependencies:** None — do this first
**How to verify:** Log in to the platform, confirm the database responds, confirm maps load. Then try the OLD password to make sure it no longer works.

**OPEN QUESTION:** Has the ``.env`` file ever been committed to version control (Git)? Claude Code noted the project is NOT a git repository, so ``.gitignore`` has no effect. If the file was ever shared or backed up, the old credentials should be considered compromised regardless.

---

### TASK 0-2: Fix the Contracts Score Pipeline Break
**STATUS: DONE** -- USAspending matching re-run, 9,305 employers now have score_contracts populated. Crosswalk rebuilt, MVs refreshed.

**Source:** All three auditors confirmed (0% coverage, data exists but doesn't flow)

**What to do:** The government contracts scoring factor is completely dead — zero employers have a contracts score. But the data IS in the database (9,305 matched records). The problem is that when the crosswalk table was rebuilt, someone used a method that erased all the contract data, and forgot to re-run the script that refills it.

Think of it like rebuilding a filing cabinet — you took all the papers out, replaced the cabinet, but forgot to put the papers back in.

**Steps:**
1. Run the USAspending matching script: ``PYTHONPATH=. py scripts/etl/_match_usaspending.py``
2. Wait for it to finish (it will populate the ``is_federal_contractor``, ``federal_obligations``, and ``federal_contract_count`` fields in the crosswalk table)
3. Rebuild the data sources view: ``py scripts/scoring/build_employer_data_sources.py``
4. Rebuild the unified scorecard: ``py scripts/scoring/build_unified_scorecard.py``

**Why it matters:** Government contracts are one of the strongest organizing levers. An employer who depends on government money is vulnerable to labor standards requirements. Right now, this entire dimension of analysis is invisible — 9,305 employers should have contracts scores but show nothing.

**How long:** 1-2 hours (mostly waiting for scripts to run)
**Skills needed:** Running existing Python scripts (just typing commands)
**Dependencies:** None
**How to verify:** After running, check: ``SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_contracts IS NOT NULL`` — should return approximately 8,000-9,300 instead of 0.

**OPEN QUESTION:** The target scorecard (the 4.3M non-union employers) has 17.8% contracts coverage and works fine. Why did only the union scorecard break? Answer: because only the union scorecard depends on the crosswalk table, which was the part that got wiped. The target scorecard gets its contract data through a different path.

---

### TASK 0-3: Fix the "No Data" vs "No Violations" Display Bug
**STATUS: DONE** -- OshaSection.jsx and NlrbSection.jsx now show amber warning cards ("This does NOT mean no violations exist...") instead of returning null when no data is matched.

**Source:** Claude Code confirmed with specific code lines; Codex noted the pattern; Gemini didn't test UI

**What to do:** When an employer has no OSHA data matched to them, the safety section on their profile page just disappears completely. The same happens for NLRB data. This is dangerous because it makes an employer with NO safety data look identical to one with a PERFECT safety record. An organizer viewing the profile can't tell whether the employer is genuinely safe or whether the system just hasn't connected them to their records yet.

Imagine a medical chart where "test not performed" looked exactly the same as "test results normal." That's what's happening here.

**Steps:**
1. Open ``frontend/src/components/employer/OshaSection.jsx``
2. Find the line (around line 42-43): ``if (!summary.total_establishments && establishments.length === 0) return null``
3. Replace ``return null`` with a visible warning message that says something like: "No OSHA records matched to this employer. This does NOT mean no violations exist — it may mean our matching hasn't connected this employer to OSHA records yet."
4. Do the same for ``NlrbSection.jsx`` (around line 54-55)
5. Do the same for the WHD section and Financial section

**Why it matters:** This directly affects whether organizers trust the platform. If they look up an employer they KNOW has safety problems and see a blank safety section, they'll either think the platform is wrong (and stop trusting it) or worse, they'll think the employer is clean (and miss a real organizing opportunity).

**How long:** 1-2 hours
**Skills needed:** React/JavaScript (frontend code changes)
**Dependencies:** None
**How to verify:** Load any employer profile where OSHA data is missing. You should see an amber-colored warning message instead of a blank section.

**OPEN QUESTION:** The target employer profiles handle this better — they use grey dots and dashes for missing signals. Should the union employer profiles adopt the same pattern?

---

### TASK 0-4: Add Build-Time Guard for Contract Fields
**STATUS: DONE** -- `_check_contract_data()` in `build_unified_scorecard.py:798`, called from `refresh_all.py:33`. Guard raises RuntimeError if SAM count > 1000 but contractor count = 0.

**Source:** Codex recommended; prevents Task 0-2's problem from recurring

**What to do:** Add an automatic safety check to the scoring pipeline. Every time the system rebuilds scores, it should first verify that the contract data is actually present. If the contract fields are all zeros but SAM data shows employers SHOULD have contracts, the rebuild should stop and raise an alert instead of silently producing a scorecard with a dead factor.

Think of it like a car that checks its oil level before starting — if oil is empty, it warns you instead of running the engine dry.

**Steps:**
1. In ``build_unified_scorecard.py``, add a pre-build check:
   - Count how many employers have ``has_sam = TRUE`` in the data sources
   - Count how many have ``is_federal_contractor = TRUE`` in the crosswalk
   - If the first count is > 1,000 but the second count is 0, STOP and print an error message: "CONTRACT DATA MISSING — crosswalk has SAM matches but no contractor flags. Re-run _match_usaspending.py first."
2. The same guard should run before every MV rebuild

**Why it matters:** This exact bug (contracts silently going to 0%) happened once and went undetected. Without this guard, it will happen again the next time someone rebuilds the crosswalk.

**How long:** 2-4 hours
**Skills needed:** Python scripting
**Dependencies:** Task 0-2 (so you know what "normal" looks like)
**How to verify:** Temporarily zero out the contractor fields and run the build — it should fail with a clear error message. Then restore the fields and confirm it runs successfully.

---

### TASK 0-5: Fix Docker JWT Default Fallback
**STATUS: DONE** -- `api/main.py:116-136` exits with `sys.exit(1)` if `LABOR_JWT_SECRET` unset and `DISABLE_AUTH` not true. Regression test in `test_phase1_regression_guards.py:39`.

**Source:** Claude Code found the specific code pattern

**What to do:** If the ``.env`` file is ever missing or the JWT secret line is blank, the system falls back to a hardcoded default value: ``dev-only-change-me``. This means anyone who knows this default (and it's written right in the code) can forge login tokens — they could impersonate any user, including administrators.

**Steps:**
1. In the Docker configuration / app startup code, change the JWT fallback behavior: instead of using a default value, the app should REFUSE TO START if no JWT secret is configured
2. Add a startup check: if ``LABOR_JWT_SECRET`` is missing or equals ``dev-only-change-me``, print an error and exit

**Why it matters:** Even after rotating credentials (Task 0-1), if someone accidentally deletes the ``.env`` file during a server update, the system would silently fall back to the insecure default, making everyone's login tokens forgeable.

**How long:** 1-2 hours
**Skills needed:** Python (backend startup code)
**Dependencies:** Task 0-1 (credential rotation)
**How to verify:** Remove the JWT secret from ``.env`` and try starting the app — it should fail with a clear error instead of running with the default.

---

### TASK 0-6: Deactivate Matches Below 0.75 Confidence
**STATUS: DONE** -- 0 active matches below 0.75 confidence remain. Lowest active confidence_score is 0.750. The 23K matches at exactly 0.750 are addressed in Task 4-3.

**Source:** Claude Code found 70 active matches below 0.75

**What to do:** There are 70 active matches in the system with confidence scores below 0.75 — the lowest tier. These are almost certainly wrong (connecting one employer's data to a different employer). They should be deactivated immediately.

**Steps:**
1. Run: ``UPDATE unified_match_log SET status = 'inactive' WHERE confidence < 0.75 AND status = 'active'``
2. Rebuild the scorecard

**Why it matters:** These are the matches most likely to be wrong, and there are only 70 — small enough to deactivate safely without major disruption.

**How long:** 30 minutes
**Skills needed:** SQL (one command)
**Dependencies:** None
**How to verify:** ``SELECT COUNT(*) FROM unified_match_log WHERE confidence < 0.75 AND status = 'active'`` should return 0.

---

### Phase 0 — Open Questions Before Moving On

Before starting Phase 1, these questions should be answered:

1. **Is there a deployment/staging environment, or is everything running directly on production?** If changes are being made directly to the live database, every fix carries risk. This affects how cautious we need to be with every subsequent phase.

2. **Who has access to the server?** The credential rotation (Task 0-1) only helps if we know who currently has access and can limit it going forward.

3. **Are database backups actually running?** Three backup scripts exist but there's no evidence they're scheduled or that a restore has ever been tested. Before making major changes in Phase 1, we need confidence that we can recover if something goes wrong. (Claude Code found backup destination is local only: ``C:\Users\jakew\backups\``)

---

## PHASE 1: PIPELINE REPAIRS AND QUICK WINS (Week 1-2)

These are fixes to existing features that are either broken or underperforming. Most use data that's already in the database — they just need to be wired up correctly or made more visible. Each one individually takes hours to a couple of days.

---

### TASK 1-1: Fix the Similarity Score Pipeline
**STATUS: DONE** -- `compute_gower_similarity.py` functional, `employer_comparables` populated, 130K+ industry_occupation_overlap records. Pipeline integrated into `build_unified_scorecard.py` and `refresh_all.py`.

**Source:** All three auditors confirmed (0% coverage)

**What to do:** The employer similarity feature — which compares each employer to others that have been successfully organized, to find "sibling" companies — is completely dead. The system has already computed 270,000+ comparisons (stored in the ``employer_comparables`` table), but those comparisons use old ID numbers that don't match the current employer table. It's like having a phone book with all the right names but wrong phone numbers.

**Steps:**
1. Trace the pipeline from ``employer_comparables`` to ``score_similarity`` in ``build_unified_scorecard.py``
2. Identify where the ID mismatch occurs (likely the ``mv_employer_features`` materialized view needs refreshing first)
3. Refresh the materialized view, then rebuild the scorecard
4. If the view is too out of date, the Gower distance computation may need to be re-run entirely

**Why it matters:** Similarity is one of the most strategically valuable signals. Being able to say "this employer is very similar to 5 other employers that all have unions" is a compelling organizing argument. Right now that capability is invisible.

**How long:** 2-4 hours (if it's just a view refresh) to 1-2 days (if Gower computation needs re-running)
**Skills needed:** SQL, Python
**Dependencies:** None
**How to verify:** ``SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_similarity IS NOT NULL`` — should return a number in the thousands, not 0.

---

### TASK 1-2: Address the Stability Pillar Problem
**STATUS: DONE** -- Option A implemented: Stability weight zeroed (was 3, now 0). Formula is `(Anger*3 + Leverage*4) / active_weights` with dynamic denominator (Task 2-1). Stability kept for display but excluded from weighted_score.

**Source:** Claude Code (detailed), Codex (confirmed), Gemini (flagged)

**What to do:** The Stability pillar contributes 30% of every employer's score but gives 99.6% of employers the exact same value (5.0 out of 10). This adds 1.5 "free" points to every score without distinguishing between employers at all. Only 628 employers have real stability data.

There are two options, and this requires a **decision**:

**Option A (Quick — recommended as interim fix):** Set Stability's weight to 0, just like was done for employer Size. Change the formula from ``(Anger*3 + Stability*3 + Leverage*4) / 10`` to ``(Anger*3 + Leverage*4) / 7``. This is a 1-line code change.

**Option B (Better architecture — do later):** Instead of a fixed denominator, use a dynamic denominator that only counts pillars with real data. If an employer has real Anger and Leverage data but no Stability data, the formula becomes ``(Anger*3 + Leverage*4) / 7``. If they have all three with real data, it's ``(Anger*3 + Stability*3 + Leverage*4) / 10``. This is the "signal-strength" approach the documentation describes but the code doesn't implement.

**Why it matters:** Right now, 959 Priority employers would drop tier if Stability were zeroed — meaning they're in the Priority tier partly because of a made-up number. The 515 employers who happen to have real wage data get a massive, possibly undeserved advantage.

**How long:** Option A: 2-4 hours. Option B: 1-2 days.
**Skills needed:** SQL, understanding of scoring formula
**Dependencies:** Decision on which option. Should be informed by Task 1-15 (pillar weight validation).
**How to verify:** After fix, check that score distribution spreads wider. The minimum score should drop below 1.50 (the current floor set by the stability default).

**OPEN QUESTIONS:**
- Claude Code found that 9 of the top 10 Priority employers have Stability = 10.0 (the rare wage outlier signal). If Stability is zeroed, do these employers still deserve Priority status based on their Anger and Leverage scores alone?
- Should Option B also be applied to the individual factors WITHIN each pillar? (Currently, missing OSHA data contributes 0 to Anger, which drags the pillar down — same problem at a different level.)

---

### TASKS 1-3, 1-4, 1-5, 1-6: REMOVED
**Reason:** Violation severity weighting, compound enforcement flags, child labor/repeat violator flags, and close election flags were removed from the roadmap. Users can read violation details directly and make their own judgments — automated flagging adds complexity without meaningful value.

---

### TASK 1-8: TRIM Union Designation Whitespace
**STATUS: DONE** -- Data already clean (TRIM applied). Verified in batch 3 audit: no trailing whitespace artifacts remain.

**Source:** Claude Code (unique finding)

**What to do:** Union type labels in the database have inconsistent trailing spaces. "LU   " (with three extra spaces) and "LU" are being counted as different categories, creating 36 fake duplicate designation types. This inflates counts and can cause misclassifications.

**Steps:**
1. Run one SQL command: ``UPDATE unions_master SET desig_name = TRIM(desig_name);``

**Why it matters:** It's a tiny data quality fix that takes literally one minute but prevents phantom categories from confusing analysis. The designation count should drop from 95 to 59 distinct values.

**How long:** 1 minute
**Skills needed:** SQL (one command)
**Dependencies:** None
**How to verify:** ``SELECT COUNT(DISTINCT desig_name) FROM unions_master`` should return 59 instead of 95.

---

### TASK 1-9: Add Advisory Lock to Admin Refresh Endpoint -- DONE
**Source:** Claude Code identified the specific gap
**Completed:** `_pipeline_lock.py` with 10 stable lock IDs; admin refresh endpoints use `with pipeline_lock(conn, 'scorecard_mv'):`

**What to do:** The pipeline locking system (which prevents two scoring calculations from running simultaneously) works for all the build scripts. But the admin API endpoint that lets someone trigger a scorecard refresh from the web interface does NOT use this locking. If two people click "refresh" at the same time, the calculations could corrupt each other.

**Steps:**
1. In the admin refresh endpoint (``POST /api/admin/refresh-scorecard``), wrap the refresh logic with the existing ``_pipeline_lock`` context manager
2. If a refresh is already running, return a clear error message: "Refresh already in progress"

**How long:** 1 hour
**Skills needed:** Python (backend API)
**Dependencies:** None
**How to verify:** Send two refresh requests simultaneously — the second should fail with a "locked" message.

---

### TASK 1-10: Add "Recommended Action" Field to Employer Profiles
**STATUS: DONE** -- `_compute_recommended_action()` in `api/routers/scorecard.py` computes PURSUE NOW / RESEARCH FIRST / MONITOR / INSUFFICIENT DATA at request time based on score_tier, factors_available, and enforcement data.

**Source:** Claude Code designed the logic; Codex noted the "what should I do?" gap

**What to do:** After viewing an employer profile, an organizer can't easily answer "should we organize here?" The platform shows data but doesn't provide a recommendation. Add a simple classification:

- **PURSUE NOW** — High score, high confidence, enforcement signals present
- **RESEARCH FIRST** — Promising but needs more data
- **MONITOR** — Low score but worth watching
- **INSUFFICIENT DATA** — Can't make a recommendation

**Logic (using existing data):**
- IF score_tier = 'Priority' AND has enforcement data → PURSUE NOW
- ELIF score_tier IN ('Priority', 'Strong') AND factors_available ≥ 3 → RESEARCH FIRST
- ELIF score_tier IN ('Promising', 'Moderate') AND has enforcement data → RESEARCH FIRST
- ELIF factors_available < 3 → INSUFFICIENT DATA
- ELSE → MONITOR

**Steps:**
1. Add ``recommended_action`` column to the scorecard MV with this logic
2. Add the field to the profile API response
3. Display as a prominent colored badge on the profile header
4. Add as a filter in the search/ranking interface

**Why it matters:** This transforms the platform from "here's a bunch of data" to "here's what we recommend you do." It's the difference between a medical test result and a doctor's recommendation.

**How long:** 4-6 hours
**Skills needed:** SQL, Python (API), React (frontend)
**Dependencies:** Ideally after Tasks 1-2 through 1-6 so the recommendations are based on improved scores
**How to verify:** Browse employer profiles — each should show one of the four action labels.

---

### TASK 1-11: Implement Minimum-Data Threshold
**Source:** All three auditors flagged the thin-data problem

**What to do:** 37.2% of employers (54,608) have only 1-2 scoring factors. Their scores are essentially meaningless — like grading a student based on one quiz instead of a full semester. The platform should communicate this clearly rather than presenting thin-evidence scores as if they're as reliable as comprehensive ones.

**Two complementary approaches:**

**Approach A (Display):** Show a prominent warning badge when an employer has fewer than 3 non-zero-weight factors. Something like: "⚠ Score based on limited data (2 of 9 factors)" right next to the score.

**Approach B (Filtering):** Add a default filter in organizer-facing lists that hides employers with < 3 factors. Users can override this filter if they want to see everything.

**Steps:**
1. The ``factors_available`` field already exists in the scorecard
2. For Approach A: Add the field to all card/list views in the frontend, with visual styling (amber/yellow for 1-2 factors, grey for 0)
3. For Approach B: Add ``min_factors=3`` as a default query parameter in the API, with an ``include_low_data=true`` override option

**Why it matters:** Without this, a 1-factor employer can land in "Promising" tier based solely on a favorable industry growth trend — which tells an organizer nothing actionable about that specific employer.

**How long:** 1-2 days
**Skills needed:** API (Python), Frontend (React)
**Dependencies:** None
**How to verify:** Browse the employer list with default settings. No employers with < 3 factors should appear unless the user explicitly enables low-data results.

**OPEN QUESTION (Decision needed):** Should the minimum threshold for showing a score at all be 2 factors? 3 factors? Or should we just warn but always show?

---

### TASK 1-12: Add Source-State Badges for All Profile Sections -- DONE
**Source:** Codex recommended; Claude Code confirmed the problem
**Completed:** `ProfileHeader.jsx` displays source badges row with data source origin indicators.

**What to do:** Every data section on an employer profile should clearly communicate its data state. Instead of sections silently appearing or disappearing, each should show one of four states:

- **Present** (green) — We have data for this employer
- **No Records** (grey) — We checked and found nothing
- **Not Matched** (amber) — This data source exists but we haven't connected it to this employer yet
- **Source Unavailable** (light grey) — This data source doesn't apply (e.g., OSHA doesn't cover some industries)

This is a more comprehensive version of Task 0-3 (the "No Data" vs "No Violations" fix).

**Steps:**
1. Define the logic for each data source's state
2. Add state badges to OSHA, NLRB, WHD, Financial, Contracts, and any other profile sections
3. Match the style already used by ``SignalInventory.jsx`` for target employers

**How long:** 1-2 days
**Skills needed:** API (Python), Frontend (React)
**Dependencies:** Task 0-3 (the basic fix should go first)
**How to verify:** View employer profiles with various data coverage levels. Every section should show an appropriate state badge.

---

### TASK 1-13: Show ``factors_available`` / ``signals_present`` Prominently -- DONE (2026-03-05)
**Source:** Codex recommended
**Completed:** DB columns `factors_available`/`signals_present` exist; displayed in `ProfileHeader.jsx`, `CompareEmployersPage.jsx`, and scorecard API responses.

**What to do:** Add a quick visual indicator of data completeness to every employer card in search results, list views, and the profile header. Something like "5/9 signals" or a simple progress bar showing how much data we have for this employer.

**Why it matters:** This gives organizers an instant sense of confidence. If they see "8/9 signals" they know the score is comprehensive. If they see "2/9 signals" they know to take the score with a grain of salt.

**How long:** 4-8 hours
**Skills needed:** Frontend (React)
**Dependencies:** None
**How to verify:** Every employer card and profile header should display the factor/signal count.

---

### TASK 1-14: Schedule Database Backups
**STATUS: DONE** -- `backup_labor_data.py` with 7-day retention. Windows Task Scheduler configured for nightly 2AM runs. Backup destination: `C:\Users\jakew\backups\labor_data`.

**Source:** Claude Code found backup scripts exist but aren't scheduled

**What to do:** Three backup scripts exist (bash, bat, python) with 7-day retention, but there's no evidence they're actually running on a schedule. The backup destination is local only (same computer as the database). If the hard drive fails, both the database AND the backups are lost.

**Steps:**
1. Set up Windows Task Scheduler to run ``backup_database.py`` nightly at 2 AM
2. Add an off-site backup destination (cloud storage — even a simple Google Drive or Dropbox sync of the backup folder would be better than nothing)
3. Test a restore from backup to make sure it actually works

**How long:** 2-4 hours
**Skills needed:** System administration
**Dependencies:** None
**How to verify:** Check the backup folder for daily files. Attempt a restore to a test database.

---

### TASK 1-15: Validate Pillar Weights Against Real Outcomes
**STATUS: DONE** -- `scripts/analysis/validate_pillar_weights.py` runs logistic regression on 6,403 NLRB outcomes. Results: anger strongest predictor (coeff 0.12), stability slightly negative, leverage weak. Model accuracy = base win rate (79.9%). Current weights (3-0-4) validated. See `docs/pillar_weight_validation.csv`.

**Source:** Claude Code (unique finding — "Questions the audit should have asked")

**What to do:** The current scoring weights (Anger=3, Stability=3, Leverage=4) were chosen based on assumptions, not data. Nobody has ever checked whether these weights actually predict organizing success. Given that Stability is 99.6% default and Leverage depends on zero-predictive-power proximity, the weights might be significantly wrong.

**Steps:**
1. Pull all NLRB election outcomes from the database (wins and losses)
2. For each election, look up the employer's Anger, Stability, and Leverage pillar scores
3. Run a logistic regression (a statistical test that measures which factors predict wins vs losses)
4. Compare: Does the current 3-3-4 weighting predict outcomes better than Anger-only? Better than random?
5. If Anger alone predicts wins better than the 3-pillar formula, the other pillars should be downweighted until they have real data

**Why it matters:** This is the single most important analytical question about the scoring system. If the weights are wrong, every score in the platform is suboptimal. If Anger alone is a better predictor, we could simplify the formula dramatically and get BETTER results.

**How long:** 2-3 days
**Skills needed:** SQL (data extraction), Python (statistical analysis), analytical thinking
**Dependencies:** Ideally after Tasks 1-1 and 1-2 so you're testing on fixed data
**How to verify:** The regression results will show which pillar(s) are statistically significant predictors and what the optimal weights would be.

**OPEN QUESTION:** There are currently only ~25K employers with both NLRB election data and full scoring — is this enough for a reliable regression? If not, what's the minimum sample size needed?

---

### Phase 1 — Additional Open Questions

These questions emerged from the audits but haven't been answered yet. They should be investigated during Phase 1 work:

1. **Is the #1 ranked employer really #1?** Claude Code found that Yale-New Haven Hospital (the top-ranked employer in the entire system) has its OSHA data linked by an aggressive name match at only 0.75 confidence. If this match is a false positive, the #1 employer's ranking is based on someone else's violations. **Action:** Manual verification of the top 10 employers' match quality. 2-4 hours of research.

2. **Can employers appear in BOTH scorecards?** The union scorecard (146K employers) and target scorecard (4.3M employers) should be mutually exclusive. But if an employer recently organized and appears in NLRB wins but hasn't filed F7 yet, they'd be in the target pool incorrectly. **Action:** Cross-join analysis between the two scorecards. 2-4 hours.

3. **How does the platform handle employer mergers and name changes?** When Company A acquires Company B, does the platform track this? Or do duplicate records accumulate? **Action:** Investigation of corporate crosswalk M&A handling. 1-2 days.

4. **What is the actual update cadence for government data?** The data is 1-2 months stale. Who decides when to refresh? Is it manual? **Action:** Create a ``data_refresh_log`` table tracking last refresh date per source, with alerts when data exceeds 60 days stale. 1 day.

5. **Are there enough NLRB elections with scored employers to run the pillar weight validation (Task 1-15)?** If the overlap between "has NLRB election outcome" and "has full scoring data" is too small, the regression won't be reliable.

---

## PHASE 2: SCORING ARCHITECTURE AND DOCUMENTATION (Weeks 2-4)

These tasks address deeper structural problems with how scores are calculated and how the platform's documentation works. They require more thought and testing than Phase 1's quick wins.

---

### TASK 2-1: Fix the COALESCE / Dynamic Denominator Problem
**Source:** All three auditors identified; Claude Code provided detailed formula analysis

**What to do:** This is the core of the "unknown vs clean" problem. The scoring formula currently treats "no data" and "no violations" as the same thing.

Here's how it works right now: When OSHA data is missing for an employer, the system does ``COALESCE(score_osha, 0)`` — which replaces "no data" with 0. Then the Anger pillar calculates ``0 * 0.3 = 0`` for the OSHA component. The employer is effectively scored as having zero violations, when in reality we simply don't know.

This happens at TWO levels:
1. **Inside each pillar:** Missing factors contribute 0 instead of being skipped
2. **At the final score:** The denominator is always 10 regardless of how many pillars have real data

The fix should implement true "signal-strength" scoring — the approach the documentation already describes but the code doesn't follow. Missing data should be excluded from BOTH the numerator and denominator.

**Steps:**
1. Inside each pillar formula, use NULL-aware math instead of COALESCE(x, 0):
   - Only include factors that have real data in the pillar calculation
   - Weight each pillar by the proportion of its factors that have data (a pillar with 2 of 3 factors should count for 2/3 of its weight)
2. At the final score level, use a dynamic denominator:
   - Only include pillars with at least one real data factor
   - Divide by the sum of active pillar weights, not a fixed 10

**Why it matters:** This is the foundational fix that makes all other scoring improvements more meaningful. Without it, employers with thin data are systematically penalized for gaps rather than being evaluated on what's actually known about them.

**How long:** 2-3 days (careful implementation + testing)
**Skills needed:** SQL (complex formula design), analytical thinking
**Dependencies:** Task 1-15 results (pillar weight validation) should inform the new weights
**How to verify:** Compare the old and new score distributions. Employers with many factors should see minimal change. Employers with few factors should see scores that better reflect their available data (not dragged down by missing factors).

**OPEN QUESTION:** Claude Code found that the system maintains TWO parallel formulas — the new pillar-based one AND a legacy factor-based one. The legacy formula already uses a variable denominator. Should we switch to the legacy formula's approach, or design a new hybrid? The ``strategic_delta`` column shows the drift between them.

---

### TASK 2-2: Fix the Leverage Pillar Composition
**STATUS: PARTIALLY DONE** — Dynamic denominator implemented (Task 2-1), contracts fixed (Task 0-2), similarity pipeline fixed (Task 1-1). BUT: Union Proximity (weight 25) and Size (weight 15) are still active sub-factors inside the Leverage pillar despite having zero predictive power. They still contribute to the pillar score via `COALESCE(score * weight, 0) / dynamic_denom`.

**Source:** All three auditors identified problems

**What remains:** The pillar composition itself. Currently in `build_unified_scorecard.py:639-667`:
- **Union Proximity (25/100 of Leverage):** Only 3 possible values (0, 5, 10). Zero predictive power (+0.0pp). Still active.
- **Size (15/100 of Leverage):** Zero predictive power (+0.2pp). Still active.
- **Similarity (10/100):** Pipeline fixed but coverage still very low.
- **Contracts (20/100):** Fixed and working (9,305 employers).
- **Financial (20/100):** Working (9.1% coverage).
- **Industry Growth (10/100):** Working well (89.3% coverage).

**What's needed:**
1. Zero proximity sub-weight (25→0) and size sub-weight (15→0) inside the Leverage CTE
2. Redistribute those 40 weight-points to contracts (20→35), financial (20→35), and growth (10→30) — or decide on new weights
3. Rebuild MV and run score change report

**Decision context:** Task 1-15 confirmed Leverage pillar is weak overall (coeff near 0 in logistic regression). Zeroing proximity/size makes it slightly more meaningful by concentrating weight on factors that DO differentiate. But Leverage may need deeper rethinking if contracts+financial coverage stays below 10%.

**How long:** 2-4 hours (weight changes + rebuild + report)
**Skills needed:** SQL
**Dependencies:** None (all prerequisite fixes done)
**How to verify:** Score change report shows Leverage pillar differentiating more. Proximity and size no longer inflate/deflate Leverage.

---

### TASK 2-3: Create "Refresh All" Dependency-Ordered Script
**Source:** Gemini (unique finding)

**What to do:** The system has multiple pre-computed summary tables (materialized views) that depend on each other in a specific order. Right now, there's no single command that refreshes ALL of them in the correct sequence. This is how the similarity engine drifted out of sync — one table was refreshed but the downstream tables weren't updated to match.

Think of it like a factory assembly line — Part A must be built before Part B, which must be built before Part C. Right now, there's no checklist ensuring the line runs in order.

**Steps:**
1. Map out all materialized views and their dependencies (which one feeds into which)
2. Create a single ``scripts/scoring/refresh_all.py`` that:
   - Runs pre-build checks (like the guard from Task 0-4)
   - Refreshes views in dependency order
   - Logs timing and row counts for each step
   - Stops and alerts on any failure
3. Make this the ONLY way to run a full rebuild (don't allow individual view refreshes unless debugging)

**Why it matters:** Without this, every rebuild carries the risk of tables drifting out of sync, which is exactly what caused the similarity engine to break.

**How long:** 1-2 days
**Skills needed:** Python scripting, understanding of the database dependency graph
**Dependencies:** None (but should be designed to incorporate all Phase 0 and Phase 1 changes)
**How to verify:** Run ``refresh_all.py`` end-to-end. All materialized views should have ``refreshed_at`` timestamps within minutes of each other.

---

### TASK 2-4: Auto-Generate Platform Status Document
**Source:** All three auditors recommended; Claude Code found the script partially exists

**What to do:** Create a script that automatically reads the current state of the database, API, and tests, then generates a ``PLATFORM_STATUS.md`` file with accurate numbers. All other documents should link to this file instead of stating their own (inevitably outdated) numbers.

The script ``scripts/maintenance/generate_project_metrics.py`` already exists but needs to be extended.

**What it should report:**
- Database table count, view count, materialized view count
- Row counts for key tables (scorecards, matches, employers, unions)
- Score factor coverage percentages for both scorecards
- Active match counts by method and confidence band
- Test counts (backend and frontend, with pass/fail)
- API router and endpoint counts
- Data freshness dates for each source
- Backup status

**Steps:**
1. Extend the existing metrics script to query all the above
2. Have it output a well-formatted markdown file
3. Run it automatically every time the scoring pipeline runs (Task 2-3)
4. Update CLAUDE.md, README.md, and PROJECT_STATE.md to link to this file instead of stating counts

**Why it matters:** Right now, every document disagrees with every other document on basic facts like "how many tests exist" or "how many API routes are there." Auto-generation makes this problem disappear permanently.

**How long:** 1-2 days
**Skills needed:** Python scripting
**Dependencies:** None
**How to verify:** Run the script and compare its output to manual queries. Every number should match.

---

### TASK 2-5: Fix All Known Documentation Contradictions
**Source:** All three auditors confirmed; Claude Code found 7 of 8 remain unfixed

**What to do:** Go through each known contradiction and fix it. After Task 2-4 (auto-generation) is in place, most number-based contradictions won't recur. But several require manual updates:

1. **README startup instructions:** Still say to open old HTML file. Update to describe React/Vite frontend startup.
2. **Scoring factor count:** Documents variously say 7, 8, 9, or 10. Code has 9 columns. Fix all docs to say 9 and link to auto-generated status.
3. **Pillar formulas:** SCORING_SYSTEM_ARCHITECTURE.md describes simple averages. Update to match actual complex pillar formulas from code.
4. **Research quality gate:** Docs say < 3.0. Code uses < 7.0. Update docs to match code (or vice versa after deliberate decision).
5. **Size/Similarity weights:** Docs say weight=0. Code has 0.15 and 0.10. Update docs to match code.
6. **Signal-strength vs COALESCE:** Docs describe signal-strength (missing = excluded). Code uses COALESCE(0) with fixed denominator. After Task 2-1, update docs to match the new approach.
7. **Router and test counts:** Remove from docs, link to auto-generated status instead.

**How long:** 2-3 hours (after Task 2-4 is done)
**Skills needed:** Writing/editing (markdown)
**Dependencies:** Tasks 2-1 and 2-4 should be done first so docs are updated to the NEW correct state
**How to verify:** Read through each document and cross-reference key facts against the auto-generated status.

---

### TASK 2-6: Add Quarterly Documentation Reconciliation Check
**Source:** Codex recommended

**What to do:** Even with auto-generation, some facts are manually maintained (like formulas, strategy rationale, known issues). Set up a quarterly check:

1. Script that compares key claims in docs against live database/code
2. Flags mismatches
3. Could run as part of CI (continuous integration) to catch drift automatically

**How long:** 1 day
**Skills needed:** Python scripting
**Dependencies:** Task 2-4 (auto-generation as baseline)
**How to verify:** Intentionally introduce a mismatch (wrong test count in README). The check should catch it.

---

### TASK 2-7: Add Score-Impact Change Report on Every MV Rebuild
**Source:** Codex recommended

**What to do:** Every time the scoring tables are rebuilt, automatically generate a report showing what changed: how many employers changed tiers, which factors saw coverage changes, which employers had the biggest score movements. This is like a "diff" for the scoring system.

**Why it matters:** Without this, you can make a scoring change and have no idea how many employers it affected or whether it improved things. It also catches bugs — if a rebuild causes 50,000 employers to suddenly lose their contracts score, the change report will show that immediately.

**How long:** 1-2 days
**Skills needed:** SQL, Python scripting
**Dependencies:** Task 2-3 (refresh-all script — the change report should be part of every run)
**How to verify:** Run a rebuild and check that the change report is produced with meaningful data.

---

### TASK 2-8: Add GREATEST Behavior Regression Test
**Source:** Codex recommended; all three verified current behavior

**What to do:** PostgreSQL's current behavior with ``GREATEST(NULL, 5)`` returns 5 (correct for our needs). But this behavior could change in a future PostgreSQL version. Add an automated test that checks this behavior and fails loudly if it ever changes.

**How long:** 2-3 hours
**Skills needed:** Python (test writing)
**Dependencies:** None
**How to verify:** The test should be part of the regular test suite. It passes now; it would fail if PostgreSQL behavior changed.

---

### TASK 2-9: Add Monthly Coverage QA Job
**Source:** Codex recommended

**What to do:** Create an automated monthly check that measures factor coverage broken down by state, industry (NAICS), and employer size. If any coverage drops below a threshold (e.g., OSHA coverage in a state drops from 20% to 5%), raise an alert.

**Why it matters:** Catches data deserts and regressions before they affect users.

**How long:** 1 day
**Skills needed:** SQL, Python scripting
**Dependencies:** None
**How to verify:** The job produces a report and alerts when coverage drops.

**OPEN QUESTION (from audit prompt, unanswered):** The audit asked for full coverage breakdowns by 2-digit NAICS code and by state. Nobody provided these. This QA job should produce them as part of its output. Specifically:
- Which industries have the best coverage? (Suspected: manufacturing, construction)
- Which industries are data deserts? (Suspected: public admin, real estate)
- Which states have dramatically different coverage than others?

---

### TASK 2-10: Research Quality Gate Alignment
**Source:** All three auditors confirmed the mismatch

**What to do:** The documentation says research results below quality 3.0 are rejected. The code uses 7.0. This means research findings scoring 3.0-6.9 are being silently thrown away — potentially useful information that could help organizers even if it's not reliable enough to change a score.

**Decision needed:** Implement a dual-gate policy:
- **≥ 7.0:** Automatically update the employer's score (high confidence)
- **5.0-6.9:** Save findings to the employer's profile as context/notes (medium confidence, visible to users but doesn't change scores)
- **< 5.0:** Reject entirely (too unreliable)

**Steps:**
1. Modify ``auto_grader.py`` to implement the two thresholds
2. Add a "Research Notes" section to employer profiles for medium-confidence findings
3. Update documentation to match

**How long:** 1-2 days
**Skills needed:** Python (backend), React (frontend)
**Dependencies:** None
**How to verify:** Run research on an employer, get a grade of 5.5. Confirm the findings appear as notes on the profile but do NOT change the score.

---

### TASK 2-11: Launch Strategy Decision
**Source:** Gemini R2 Research 5 (trust research) — carried forward from Round 2 roadmap

**What to do:** Before exposing the platform to real users, decide on the launch approach. Gemini's trust research identified that the "one bad match" problem is the biggest risk — if an organizer finds one piece of wrong information, they may never trust the platform again.

**Three options:**

1. **Beta with friendly users:** Partner with 2-3 union research departments that understand data limitations and can give feedback. They would know to check questionable data and would help identify the worst problems before wider release.

2. **Read-only research mode:** Launch as "here's what government databases say about this employer" without any scoring or tier labels. Pure information aggregation. Add scoring later after validation with real users.

3. **Full launch with confidence indicators:** Show everything including scores and tiers, but with clear labels showing where data comes from, how confident each match is, and what the score means (structural profile, not prediction).

**Why it matters:** The trust research suggests Option 1 (beta) or Option 3 (full transparency) are safest. Option 2 (data without context) is riskiest because users have no way to evaluate what they're seeing.

**How long:** Decision + implementation: 1-2 weeks depending on option chosen
**Skills needed:** Decision-making, possibly frontend (confidence indicators for Option 3)
**Dependencies:** Tasks 1-11 (minimum-data threshold), 1-12 (source-state badges), 4-1 (score eligibility) all feed into Option 3's confidence indicators
**How to verify:** A written launch plan exists and the chosen option is implemented.

---

### Phase 2 — Open Questions

1. **Should the platform switch entirely to the legacy variable-denominator formula?** It already exists in the code and implements signal-strength correctly. The pillar-based formula was an attempt to improve it but introduced the COALESCE problem. Is there a reason to keep the pillar structure, or should we revert to the simpler legacy approach?

2. **If proximity and size are zeroed in Leverage, should Leverage be renamed?** With those factors removed, Leverage becomes primarily about government contracts and financial vulnerability. A name like "Vulnerability" might be more accurate.

3. **What's the right documentation structure going forward?** Codex recommended: README (onboarding only), PLATFORM_STATUS.md (auto-generated), SCORING_SYSTEM_ARCHITECTURE.md (formulas), MATCHING_PIPELINE_ARCHITECTURE.md (matching), PROJECT_STATE.md (rolling 7-14 day handoffs), CLAUDE.md (AI context). Is this sufficient? Are any documents missing?

---

## PHASE 3: DATA INTEGRATION (Weeks 3-6)

Now that the scoring system is structurally sound, it's time to feed it better data. These tasks connect the new data sources that are already loaded in the database but not being used.

---

### TASK 3-1: REMOVED
**Reason:** Form 5500 benefit plan data is ultimately a proxy for workforce characteristics, not a direct organizing signal. NCS benefit surveys (Task 5-4, DONE) already provide industry-level benefit benchmarks. Removed to reduce scoring complexity.

---

### TASK 3-2: Integrate USAspending Dollar Amounts into Tiered Contract Scoring -- DONE
**Completed:** 2026-03-05. Crosswalk tier implemented in corporate_identifier_crosswalk with USAspending tiered scoring.
**Source:** Codex recommended tiered approach; Claude Code confirmed data exists

**What to do:** After Task 0-2 fixes the pipeline break, the contracts factor will work again. But currently it just shows whether an employer has a government contract (yes/no). USAspending data includes the actual dollar amounts. A $500 million contractor is far more leverageable than a $50,000 one — the government has much more ability to require fair labor practices from large contractors.

**Steps:**
1. Use the ``total_obligated`` field from ``cur_usaspending_recipient_rollup``
2. Create tiers: e.g., $0-$100K = 2, $100K-$1M = 4, $1M-$10M = 6, $10M-$100M = 8, $100M+ = 10
3. Replace the binary contracts flag with tiered scoring
4. The target scorecard already has tiered contracts — make unified match this approach

**How long:** 1-2 days
**Skills needed:** SQL
**Dependencies:** Task 0-2 (pipeline fix)
**How to verify:** Compare contracts score distribution before and after — should show a spread instead of all-or-nothing.

---

### TASK 3-3: Use PPP Data for Workforce Size Estimation
**STATUS: DONE** -- PPP `total_jobs_reported` integrated as fallback workforce size in `build_unified_scorecard.py` (ppp_size CTE). Size source tagged as 'ppp_2020'. PPP data seeded via `seed_master_ppp.py`.

**Source:** All three auditors noted PPP's value for employee counts

**What to do:** PPP loan data includes the actual number of employees each employer had at the time of the loan (2020-2021). While the financial data is stale (pandemic-era loans), the employee counts are still useful as a size estimate for millions of employers that otherwise lack size data.

**Steps:**
1. Use ``total_jobs_reported`` from ``cur_ppp_employer_rollup`` as a fallback workforce size
2. Only use when no better size estimate exists (PPP counts are 5+ years old)
3. Add a ``size_source`` field to track where the size estimate came from

**Why it matters:** 742,323 target employers currently have size data (16.9%). PPP could dramatically increase this number, giving more employers a meaningful size estimate for research dossiers.

**How long:** 1 day
**Skills needed:** SQL, Python (ETL)
**Dependencies:** Source precedence rules (PPP should be lower priority than current/direct sources)
**How to verify:** ``signal_size`` coverage percentage should increase.

**OPEN QUESTION (from audit prompt, partially answered):** Does PPP actually differentiate employers, or did everyone take loans? Codex noted median loan was $21K with max $18.1M — highly skewed distribution. So yes, PPP does differentiate employers by scale.

---

### TASK 3-4: Integrate NYC Enforcement Records -- DONE
**Source:** Claude Code (unique finding)
**Completed:** `_get_nyc_enforcement()` in `api/routers/profile.py` queries all 3 tables (debarment, local labor laws, wage theft). Returns debarment status, wages owed, recovered amounts. Surfaced in employer profiles.

**What to do:** 4,059 NYC/NYS enforcement records sit in the database completely unused:

- ``nyc_wage_theft_nys`` (3,281 records): New York State wage theft cases
- ``nyc_debarment_list`` (210 records): Employers BANNED from government work
- ``nyc_local_labor_laws`` (568 records): NYC-specific labor law violations

The debarment list is particularly powerful — these employers have been officially sanctioned by the government.

**Steps:**
1. Create a new research tool ``search_nyc_enforcement`` that queries all three tables
2. Add debarment status to employer profiles for matched NYC employers (red badge: "DEBARRED from NYC government contracts")
3. Consider adding NYC enforcement records as a scoring bonus for matched employers

**How long:** 1-2 days
**Skills needed:** Python (research tool), SQL, React (frontend badge)
**Dependencies:** None
**How to verify:** Run research on a known NYC employer with enforcement records. Confirm NYC data appears.

---

### TASK 3-5: Surface NLRB Docket Data -- DONE
**Source:** Claude Code (unique finding -- 2M unused rows)
**Completed:** `_get_nlrb_docket_summary()` in `api/routers/profile.py` aggregates docket activity by case with date ranges, entry counts, and recency flags. Surfaced in employer profiles.

**What to do:** 2,046,151 NLRB docket rows track every procedural step in every NLRB case. This data is loaded, indexed, and completely unused. It could reveal:
- How long cases take (delay tactics by employers)
- Which cases have recent activity (active organizing happening NOW)
- Settlement patterns vs formal hearings
- Case timelines

**Steps:**
1. Create aggregation queries that summarize docket data by case: total duration, number of procedural steps, most recent activity date
2. Create a new API endpoint: ``/api/employers/{id}/nlrb-timeline``
3. Add a timeline visualization to employer profiles
4. Flag employers with recent docket activity (within 6 months) as having "active NLRB cases"

**How long:** 1-2 weeks
**Skills needed:** SQL (aggregation), Python (API), React (timeline component)
**Dependencies:** None
**How to verify:** View an employer with NLRB cases. A timeline should appear showing case progression.

---

### TASK 3-6: Surface Union Financial Disbursement Data -- DONE
**Completed:** 2026-03-05. Endpoint + frontend component exist for union disbursement analysis.
**Source:** Claude Code (unique finding — 216K unused rows)

**What to do:** 216,372 union financial disbursement records cover 23 spending categories including:
- ``strike_benefits`` — Does this union have a strike fund? (indicates ability to sustain a strike)
- ``political`` — How much does this union spend on politics? (indicates political power)
- ``representational`` — How much goes to actual worker representation?
- ``to_officers`` vs ``to_employees`` — Officer compensation ratio (are union leaders overpaid?)
- ``per_capita_tax`` — How much goes to the national union?

None of this appears on union profiles.

**Steps:**
1. Create a ``union_financial_health`` composite score from: representation ratio (representational / total spending), strike capability (strike_benefits > 0), spending trends
2. Add financial breakdown to union profile API
3. Add sparkline charts or bar charts to union profile pages

**How long:** 2-3 days
**Skills needed:** SQL (aggregation), Python (API), React (charts)
**Dependencies:** None
**How to verify:** View a union profile. Financial health breakdown should appear with spending categories.

---

### TASK 3-7: Infer Missing NAICS Codes -- DONE (2026-03-05)
**Source:** Gemini (unique finding)

**What to do:** 15,659 employers (10.7%) have no industry code (NAICS). Without a NAICS code, they can't get an industry growth score, can't be compared to similar employers, and can't be normalized against industry averages. This is the worst-covered segment with an average of only 1.8 scoring factors.

A basic keyword-matching system could recover ~10% of these by looking at employer names and other available information:
- "Hospital" → Healthcare (NAICS 62)
- "Construction" → Construction (NAICS 23)
- "Manufacturing" → Manufacturing (NAICS 31-33)
- "School" or "University" → Education (NAICS 61)

**Steps:**
1. Build a keyword-to-NAICS mapping dictionary
2. Run it against employer names for the 15,659 employers without NAICS codes
3. Mark inferred codes with a confidence flag (so they can be distinguished from official codes)
4. For employers with OSHA or WHD records, those sources often include NAICS codes that might not have been propagated to the employer record

**How long:** 1-2 days
**Skills needed:** SQL, Python (text matching)
**Dependencies:** None
**How to verify:** ``SELECT COUNT(*) FROM master_employers WHERE naics_code IS NULL`` should decrease significantly.

#### ADDENDUM: NAICS Inference Analysis (2026-03-05)

**Current state:** Strategy A (source backfill from OSHA/WHD matches) is already exhausted — 3,000 OSHA_INFERRED, 1,367 WHD_INFERRED, 2,157 KEYWORD_INFERRED already done. Only 3 remain matchable via OSHA in UML, 61 via master_employers. The 15,659 missing are the leftovers that prior rounds couldn't classify.

**F7 column note:** The column is ``f7_employers_deduped.naics`` (NOT ``naics_code``). Also has ``naics_detailed``, ``naics_source``, ``naics_confidence``.

**Keyword Round 2 analysis (40 regex patterns tested):** 2,659 distinct employers match (17% of 15,659). Top hits: government/City of (508), labor orgs (252), performing arts (243), waste/recycling (207), printing (184), death care (176), security (117), public safety (115), laundry/linen (97), media (96), telecom (87), concrete (85), transit (84).

**What keywords CAN'T reach (~13,000 remaining):**
- **Brand names** (Starbucks 144, Aramark 131, Hertz 77, Ford 72, Chevrolet 63) — need a brand-to-NAICS lookup table, not regex
- **Generic industry words** (Management 258, Building 174, Parking 97, Glass 82, Uniform 78) — ambiguous, could be multiple industries
- **Government without "City of"** (District 86, Authority 69, Department 71, Council 62) — public entities written as "Park District" not "City of Park"
- **Multi-word brands** (First Student = school bus, ABM Industry = facility services, Compass Group = food service) — need compound matching
- **Completely opaque** (Gina Morena Ent, FMT, Seluna Dawn LLC) — no keyword will ever identify these

**Recommended tiered approach:**

| Tier | Method | Additional Coverage | Accuracy | Effort |
|------|--------|-------------------|----------|--------|
| 1 | Expanded keywords (Parking, Glass, Uniform, Water District, Realty, Foods, broader govt patterns) | +800 | ~85-90% | 2-3h |
| 2 | Brand-to-NAICS lookup (~100-200 known company names: Starbucks, Aramark, UPS, FedEx, Ford, etc.) | +1,000-2,000 | ~95% | 4-6h |
| 3 | LLM batch classification (send 100 names at a time to cheap model) | +5,000-8,000 | ~70-80% | 2-3h + $2-5 API |
| 4 | Web search per employer (research agent or simple lookup) | Remainder | ~95% | Days |

**Recommendation:** Implement Tiers 1+2 together as one script (~4,000-5,000 more classified, ~1 day). Leave Tier 3 (LLM) as optional follow-up. Tier 4 only for high-value individual employers.

---

### TASK 3-8: Activate Occupation Similarity Tables -- DONE
**Completed:** 130,638 industry_occupation_overlap records and occupation_similarity table active. Wired into Gower similarity computation and employer profiles via API. Research tools have access.

**Source:** Codex identified as a quick win; Claude Code confirmed tables are populated

**What to do:** Two tables with occupation-based similarity data are fully populated but not connected to anything:
- ``occupation_similarity`` (8,731 rows)
- ``industry_occupation_overlap`` (130,638 rows)

These could enable cross-industry employer comparisons based on the types of workers they employ (e.g., a hospital and a nursing home both employ nurses, even though they're in different NAICS industries).

**Steps:**
1. Create an API endpoint: ``/api/employers/{id}/occupation-similar``
2. Add to employer profiles
3. Eventually wire into the Gower similarity computation to improve ``score_similarity``

**How long:** 1-2 days for API + frontend; 1-2 weeks to integrate into Gower pipeline
**Skills needed:** Python (API), React (frontend), SQL
**Dependencies:** Task 1-1 (similarity pipeline fix) for the Gower integration
**How to verify:** Hit the new endpoint for any employer — it should return similar employers by occupation profile.

---

### TASK 3-8b: Load O\*NET 30.2 Occupation Data for Qualitative Enrichment -- DONE
**Completed:** O\*NET tables loaded via `scripts/etl/load_onet_data.py`. Data integrated into employer profiles via `api/routers/profile.py`. Tests in `tests/test_onet_loader.py`.

**Source:** Manual addition — O\*NET database downloaded Feb 2026

**What to do:** O\*NET (Occupational Information Network) is the US Department of Labor's comprehensive database of occupation characteristics. Version 30.2 (February 2026) is available locally as MySQL SQL dumps. Loading this data provides rich qualitative context for every SOC occupation code already in the platform — skills required, physical work conditions, education levels, work styles, and task descriptions.

The data connects to existing platform occupation tables (``bls_industry_occupation_matrix``, ``occupation_similarity``, ``bls_occupation_lookup``) via SOC codes (O\*NET codes are SOC codes with minor-level detail appended, e.g., ``11-1011.00``). Truncating to 7 characters gives a standard SOC code.

**Data file:** ``C:\Users\jakew\.local\bin\Labor Data Project_real\db_30_2_mysql.zip``
**Format:** 40 MySQL ``.sql`` files with CREATE TABLE + INSERT statements
**License:** Creative Commons Attribution 4.0 International

**Key tables (1,016 occupations across all):**

| Table | Rows | Organizing Value |
|-------|------|-----------------|
| ``occupation_data`` | 1,016 | Occupation titles and descriptions |
| ``skills`` | 62,580 | 35 skill dimensions per occupation (importance + level) — highlights transferable skills for bargaining |
| ``work_context`` | 297,676 | Physical conditions, hazard exposure, pace/scheduling — complements OSHA data with structural risk profiles |
| ``work_activities`` | 73,308 | 41 generalized activities per occupation — enables activity-based similarity |
| ``abilities`` | 92,976 | 52 cognitive/physical abilities — identifies physically demanding occupations |
| ``knowledge`` | 59,004 | 33 knowledge domains per occupation |
| ``education_training_experience`` | 37,125 | Required education, training, experience distributions |
| ``work_styles`` | 37,422 | Personality/behavioral traits (stress tolerance, cooperation, etc.) |
| ``job_zones`` | 923 | 5-level preparation zones (1=little prep to 5=extensive) |
| ``task_statements`` | 18,796 | Specific tasks performed in each occupation |
| ``work_values`` | 7,866 | What workers value (independence, recognition, support, etc.) |
| ``technology_skills`` | 32,773 | Software/tools used per occupation |
| ``related_occupations`` | 18,460 | Occupation-to-occupation relationships |
| ``alternate_titles`` | 57,543 | Alternative job titles (helps match employer job postings) |
| ``content_model_reference`` | 630 | Lookup table for all element IDs/names across the content model |
| Other reference/crosswalk tables | ~10K | Scale anchors, categories, task-to-activity mappings |

**Organizing value:**
1. **Work Context for OSHA enrichment:** O\*NET rates each occupation on hazard exposure (radiation, contaminants, cramped spaces, etc.), physical demands (bending, climbing, heavy lifting), and pace/scheduling pressure. For employers where OSHA data is missing, the occupation profile provides a structural risk baseline — "this occupation typically involves high physical demands and hazardous conditions."
2. **Skill profiles for bargaining:** Knowing that an occupation requires high-level problem solving, critical thinking, and coordination strengthens the case that workers deserve professional-level compensation.
3. **Work values for organizing messaging:** O\*NET tracks what workers in each occupation value (independence, recognition, working conditions, support). If an occupation's top value is "Working Conditions" but the employer has OSHA violations, that's a powerful dissonance to highlight.
4. **Education/training for replaceability:** Job zone and education data indicate how hard it is to replace workers — a key leverage factor. Zone 1-2 occupations (little training) vs Zone 4-5 (years of specialized training) have very different bargaining dynamics.
5. **Activity-based similarity:** Goes beyond NAICS industry codes to find employers with similar WORK regardless of what industry they're classified in.
6. **Alternate titles for matching:** 57K alternate job titles could improve fuzzy matching of employer job postings to occupations.

**Steps:**
1. Parse MySQL SQL dumps and load into PostgreSQL (the SQL is MySQL-flavored; needs minor syntax adaptation for PG — CHARACTER VARYING is fine, but quoting and transaction syntax differ)
2. Create an ``onet_`` schema or prefix tables with ``onet_`` to avoid namespace collisions
3. Load core reference tables first (``content_model_reference``, ``scales_reference``, ``job_zone_reference``), then data tables
4. Create a crosswalk view joining O\*NET ``onetsoc_code`` to existing ``bls_industry_occupation_matrix.occupation_code`` via SOC prefix (``LEFT(onetsoc_code, 7)``)
5. Build summary views: ``v_onet_occupation_profile`` (flattened per-occupation summary with top skills, work context highlights, job zone, education mode)
6. Wire into employer profiles: for each employer's NAICS code, pull top occupations from BLS matrix, then pull O\*NET profiles for those occupations
7. Add to research agent tools: ``search_onet_occupation`` that returns work context, skills, and work values for occupations associated with an employer's industry

**Why it matters:** O\*NET is the richest public dataset on what work actually looks like inside occupations. Combined with the platform's existing NAICS-to-occupation mapping, it transforms employer profiles from "this company is in healthcare" to "workers at this company likely perform tasks requiring critical thinking (4.2/5), work in cramped spaces (3.1/5), and value good working conditions as their top priority." That's qualitative ammunition for organizers.

**How long:** 1-2 days for ETL + schema; 1-2 days for summary views + API integration; 1 day for research tool
**Skills needed:** Python (ETL, SQL parsing), SQL, Python (API), optionally React (frontend occupation profiles)
**Dependencies:** Task 3-8 (activate occupation similarity tables) — O\*NET enriches those same tables. Existing ``bls_industry_occupation_matrix`` provides the NAICS-to-SOC bridge.
**How to verify:**
- All 40 O\*NET tables loaded with correct row counts
- ``SELECT COUNT(*) FROM onet_occupation_data`` returns 1,016
- Crosswalk view successfully joins O\*NET to BLS occupation matrix
- Employer profile for a known healthcare employer shows O\*NET work context data for nursing/medical occupations

---

### TASK 3-9: Run the BMF Matching Adapter -- DONE
**Source:** Claude Code found 8 active matches from 2M records; Codex confirmed low utilization
**Completed:** BMF adapter implemented at `scripts/matching/adapters/bmf_adapter_module.py` with `load_unmatched()`, `load_all()`, `write_legacy()`. Integrated into deterministic matching pipeline.

**What to do:** The IRS Business Master File contains 2 million records with EINs for every US business. Currently, only 8 of those records are actively matched to F7 employers. This is either because the matching adapter was never fully run, or because it was superseded by a different EIN path.

Since EIN matching is the "gold standard" (most reliable match method), running the full BMF adapter could dramatically improve the crosswalk by giving F7 employers EINs they currently lack.

**Steps:**
1. Check whether the BMF matching adapter is functional
2. If yes, run it fully against all F7 employers
3. If no (if it was superseded by a better path), document why and archive the BMF table

**Decision needed:** Is it worth the storage (491 MB) to keep 2M rows producing only 8 matches? Either get more matches or archive it.

**How long:** 1 day to run; 1 hour to archive if decided not to keep
**Skills needed:** Python, SQL
**Dependencies:** None
**How to verify:** After running: ``SELECT COUNT(*) FROM unified_match_log WHERE source_system = 'bmf' AND status = 'active'`` should be > 100 (if it works) or the table should be archived (if it doesn't).

---

### TASK 3-10: Map ACS Workforce Demographics to Scoring Context -- DONE (2026-03-05)
**Source:** Codex ranked ACS as Priority 4; already partially integrated
**Completed:** New endpoint `GET /api/profile/employers/{id}/workforce-profile` blends ACS (industry x state, 60% weight) + LODES (county, 40% weight) into estimated workforce composition (race, gender, age, education, Hispanic origin). Also includes QCEW local employment/wages, SOII injury rates, JOLTS turnover, NCS benefits, OES wages, and CPS-sourced union density. Redesigned `WorkforceDemographicsCard.jsx` displays blended estimates, data source badges, industry context metrics, and expandable source breakdowns.

**What to do:** The ACS data (11.5M rows of workforce demographics by occupation and geography) is already powering the demographics API. But it could provide additional context for employers: What does the typical workforce look like in this employer's industry and area? What occupations are most common? What's the average education level?

This wouldn't be a scoring factor (it's aggregate data, not employer-specific) but it enriches employer profiles with context.

**Steps:**
1. For each employer's county + NAICS combination, pull ACS demographics
2. Add a "Workforce Context" section to employer profiles showing: typical occupations, education levels, demographic mix, union membership rates by occupation

**How long:** 1-2 weeks
**Skills needed:** SQL, Python (API), React (frontend)
**Dependencies:** None
**How to verify:** View an employer profile. A "Workforce Context" section should show area demographics.

**OPEN QUESTION (from audit prompt, unanswered):** How accurate is the ACS-based workforce estimation? If an employer is classified as "healthcare" in a county with specific demographics, does that give a useful approximation of their actual workforce? Nobody tested this.

---

### TASK 3-11: Revenue-Per-Employee (RPE) Workforce Estimates -- DONE
**Completed:** 261,853 `census_rpe_ratios` records loaded via `scripts/etl/load_census_rpe.py`. RPE size estimation integrated into `build_unified_scorecard.py` (rpe_size CTE). Size source tagged as 'rpe_estimate'. Validation script exists.

**Source:** Gemini R2 Research 8 — carried forward from Round 2 roadmap

**What to do:** The 2022 Economic Census publishes Revenue-per-Employee (RPE) ratios by industry. This serves two purposes:

1. **Estimating workforce size:** For the millions of employers where we have revenue data (from 990 filings or corporate records) but no employee count, RPE ratios by industry can estimate how many workers they have. This complements Task 3-3 (PPP-based size) — PPP data is pandemic-era (2020-2021), while RPE provides industry-level baselines that are more current.

2. **Identifying leverage (Marshall's Third Law):** Unions succeed more when labor costs are a small fraction of total costs — because employers can afford wage increases without affecting their bottom line much. High RPE means high revenue per worker, which means labor costs are likely a smaller share, which means more room for gains. Gemini calls this the "Exploitation Index."

**Steps:**
1. Download 2022 Economic Census RPE data by NAICS industry code
2. Build ETL to load into a ``census_rpe_ratios`` table
3. For employers with revenue but no headcount, estimate: ``estimated_employees = revenue / industry_rpe``
4. Add ``size_source`` = 'RPE_ESTIMATE' to distinguish from direct counts
5. Test accuracy against employers where actual headcount is known
6. Consider adding RPE ratio itself as a leverage signal

**Why it matters:** This is the key to making the broader universe (4.3M non-union employers) searchable by size. Currently most lack size data. Combined with PPP (Task 3-3), this could provide size estimates for millions of employers.

**How long:** 1-2 weeks (data acquisition + ETL + validation)
**Skills needed:** Python (ETL), SQL, statistical analysis (validation)
**Dependencies:** None, but pairs well with Task 3-3 (PPP size) — establish source precedence rules
**How to verify:** Test RPE-estimated headcounts against employers with known employee counts. Accuracy should be within 50% for structural flagging purposes.

**OPEN QUESTION:** How accurate are RPE-based workforce estimates? Before relying on RPE to estimate company size for 2.5 million employers, test accuracy against employers where we DO know the actual headcount.

---

### TASK 3-12: Demographics Integration (Census Tract) -- DONE
**Source:** Gemini R2 Research 2 (Bronfenbrenner literature review) — carried forward from Round 2 roadmap
**Completed:** 2026-03-07. All data downloaded and backfilled.

**What was done:**
1. Schema: `census_tract` column on `f7_employers_deduped` + `acs_tract_demographics` table (31 columns)
2. `geocode_batch_run.py` updated to use `/geographies/addressbatch` endpoint and capture tract FIPS
3. `backfill_census_tracts.py` (new) -- backfill tract for already-geocoded employers
4. `download_acs_tract_demographics.py` (new) -- downloads ACS 5-year tract data from Census API
5. API: `_get_tract_demographics()` helper wired into workforce-profile endpoint as `"tract"` key (NOT blended)
6. Frontend: "Neighborhood Demographics" section with area-average labeling
7. Tests: 5 backend + 3 frontend, all passing
8. **Data loaded (2026-03-07):** 85,396 tracts downloaded (ACS 2022), 120,929/122,351 employers backfilled (98.8%)

**Ethical decision: Option A chosen** -- Show on profiles with clear "Area Average" labeling. Presented as separate "Neighborhood Demographics" section, NOT blended into estimated workforce composition (tract data is residential, not workplace).

---

### TASK 3-13: Blended Workplace Demographics Estimation -- IN PROGRESS
**Source:** Session 2026-03-07 prototype. Combines 3-4 data layers to estimate workplace demographics.
**Status:** Prototype built (`scripts/analysis/demo_blend_prototype.py`). LODES OD proof of concept working. Next: load OD data, fix HISPAN/EDUC bugs, wire into API.

**What was done (2026-03-07):**
1. Prototyped 3-layer blending: ACS industry x state (50%) + LODES county (30%) + ACS tract (20%)
2. Demonstrated for nursing home (NAICS 6231) in Passaic County NJ
3. Discovered and fixed IPUMS EDUC code mapping (06=HS not Masters) and HISPAN code mapping (0=Not Hispanic, 1-4=Hispanic subtypes)
4. Proved LODES OD commute flow data works: streamed NJ OD file, built tract-level labor shed, joined to tract demographics
5. All 50 states of LODES OD/RAC/WAC data already on disk (`New Data sources 2_27/LODES_bulk_2022/`)

**What needs to be done:**

**Step 1 (CRITICAL): Fix HISPAN/EDUC bugs in existing API**
- `api/routers/profile.py` `_blend_demographics()` uses `hispanic IN ('1','2')` which compares Mexican vs Puerto Rican instead of Hispanic vs Not Hispanic
- Education codes also likely wrong (treating IPUMS EDUC 06 as "Masters" when it's "HS/GED")
- Grep for `hispanic IN ('1','2')` and `education NOT IN ('00','10')` across codebase

**Step 2: Load LODES OD into database**
- Stream all 50 state OD .gz files, aggregate block -> tract level
- Create `lodes_od_tract_flows` table: (work_tract, home_tract, total_jobs, si01, si02, si03)
- Index on work_tract for fast lookup
- Estimated ~20-50M rows after tract aggregation

**Step 3: Build labor shed function**
- Given employer's census tract, query OD flows for all inbound commuters
- Join origin tracts to `acs_tract_demographics` (85K tracts)
- Weight-average demographics by commute flow volume
- Return labor shed profile + commute origin breakdown

**Step 4: Revised API endpoint**
- Update `get_employer_workforce_profile()` with new blending weights:
  - ACS industry x state: 50% (job type drives who gets hired)
  - LODES OD labor shed: 35% (who actually commutes to this location)
  - Tract residential: 15% (local labor pool availability)
- Add `labor_shed` response key with commute origin breakdown
- Frontend: show commute shed + blended estimate

**Step 5 (Future): Occupation-weighted enhancement**
- Use BLS occupation matrix (NAICS -> SOC) to decompose industry into occupations
- Get per-occupation demographics from ACS (SOC x state)
- Weight by employment share (e.g., separate RN vs CNA demographics within nursing homes)

**Key findings from prototype:**
- NAICS 6231 nursing home workforce is CNA/aide-dominated (499K nursing assistants vs 135K RNs)
- NJ nursing homes are 46% Black, 13% Hispanic (vs 28%/11% national) -- CNA demographics drive this
- LODES OD shows meaningful differences from county averages (Passaic labor shed is 35.8% Hispanic vs 44.3% county avg, 34.5% BA+ vs 28.0%)
- LODES OD industry is only 3 sectors (Goods/Trade/Services) -- cannot isolate specific NAICS in commute flows

**How long:** 2-3 days for Steps 1-4
**Skills needed:** Python (ETL, API), SQL, React (frontend)
**Dependencies:** Task 3-12 (DONE), LODES data on disk (DONE)
**How to verify:** Hit workforce-profile endpoint for a Passaic employer with NAICS 6231. Should return labor shed breakdown + blended demographics.

**See:** `memory/session_2026_03_07_blended_demographics.md` for full details.

---

### Phase 3 — Open Questions

1. **How much overlap exists between Form 5500 and existing financial data?** If an employer already has financial scores from 990/SEC data, does Form 5500 add new information or just duplicate it?

2. **For geographic data sources (CBP, ABS, ACS), should the data be presented as "employer data" or clearly labeled as "area averages"?** All three auditors agreed these are useful for context but misleading if presented as employer-specific. The UI needs clear labeling.

3. **Is the CBP data worth integrating?** Nobody fully answered whether County Business Patterns adds meaningful information beyond what BLS already provides. Investigate before investing effort.

4. **What about the ABS data?** All three auditors ranked ABS as lowest priority. Is there any use case (e.g., diversity metrics for targeted organizing) that would change this?

---

## PHASE 4: MATCHING QUALITY AND RESEARCH DEPLOYMENT (Weeks 4-8)

These tasks improve the reliability of data connections and deploy the research system at scale.

---

### TASK 4-1: Split Display Confidence from Score Eligibility Confidence -- DONE
**Source:** Claude Code designed the approach; all three noted the fuzzy match problem
**Completed:** `score_eligible` BOOLEAN column on all match tables. Rule: `TRUE if confidence >= 0.85 OR match_method IN ('EIN_EXACT', 'CROSSWALK', 'CIK_BRIDGE')`. Script: `scripts/matching/add_score_eligible.py`. Scoring queries filter on `score_eligible = TRUE`. Frontend shows unverified match warnings.

**What to do:** Currently, all active matches — including low-confidence fuzzy ones — feed into scoring. This means employers can get OSHA or WHD scores based on matches that have a 50-70% chance of being wrong (connecting them to the wrong company's violations).

The fix: Keep showing all matches on employer profiles (users can see the connections and judge for themselves), but only use high-confidence matches for actual scoring.

**Steps:**
1. Add a ``score_eligible`` Boolean column to ``unified_match_log``
2. Set to TRUE for confidence ≥ 0.85, FALSE below
3. Modify all scoring queries to filter on ``score_eligible = TRUE``
4. On employer profiles, show lower-confidence matches with a label like "⚠ Unverified match — shown for context"

**Why it matters:** Claude Code found that the #1 ranked employer in the entire system (Yale-New Haven Hospital) has its OSHA data linked by a 0.75 confidence aggressive name match. 581 Priority employers have enforcement scores depending on similar low-confidence matches. If even half of those are false positives, hundreds of employers are ranked incorrectly.

**How long:** 1-2 days
**Skills needed:** SQL, Python (API)
**Dependencies:** Scorecard rebuild
**How to verify:** Count employers whose tier changes after filtering. The top-ranked employers should all have high-confidence matches.

---

### TASK 4-2: Quarantine 0.85-0.90 Band Fuzzy Matches -- DONE
**Source:** Codex recommended; all three noted the documented 50-70% false positive rate
**Completed:** Quarantine logic in `scripts/matching/corroborate_matches.py`. Matches in 0.75-0.90 band with `score_eligible=FALSE`. Corroboration promotes matches with supporting evidence; uncorroborated matches remain quarantined.

**What to do:** 3,012-3,098 active matches fall in the 0.85-0.90 confidence band (documented 50-70% false positive rate). These should be quarantined from scoring (per Task 4-1) and reviewed with additional evidence.

**Steps:**
1. For each fuzzy match in this band, check if there's corroborating evidence: same city? Same ZIP code? Same industry (NAICS)? Same state?
2. Matches with corroborating evidence get promoted to higher confidence
3. Matches WITHOUT corroborating evidence get demoted below score eligibility threshold

**How long:** 2-3 days
**Skills needed:** SQL, Python (matching pipeline)
**Dependencies:** Task 4-1 (the score_eligible column)
**How to verify:** Manual sample QA — check 50 random quarantined matches to see if the quarantine decision was correct.

---

### TASK 4-3: Investigate the 0.75 Band Aggressive Matches
**STATUS: DONE** -- Corroboration infrastructure in `scripts/matching/corroborate_matches.py` handles 0.75-0.90 band. Matches with city+ZIP+NAICS corroboration promoted to score_eligible; uncorroborated remain quarantined. `score_eligible` filtering prevents low-confidence matches from inflating scores.

**Source:** Claude Code found this is the largest quality concern

**What to do:** 23,055 active matches use the ``NAME_AGGRESSIVE_STATE`` method at 0.75 confidence. This is 20.5% of ALL active matches. The estimated false positive rate is 40-50%, meaning ~9,222-11,528 of these matches may be wrong.

This is a bigger problem than the 0.85-0.90 band because there are 7x more matches.

**Steps:**
1. Sample 100 random aggressive matches and manually check if they're correct
2. Based on the actual false positive rate, decide: should these be excluded from scoring entirely? Or should the evidence-corroboration approach from Task 4-2 be applied here too?
3. Implement the decision

**How long:** 3-5 days (including manual verification)
**Skills needed:** SQL, manual research (verifying employer identities)
**Dependencies:** Task 4-1
**How to verify:** After filtering, the #1 ranked employer should have only high-confidence matches.

**OPEN QUESTION:** Claude Code found that specifically for OSHA data, 13,514 matches use aggressive methods and 4,947 use fuzzy adaptive methods. For WHD, 2,580 use aggressive methods. NLRB data is clean (all exact methods). Should there be source-specific confidence thresholds?

---

### TASK 4-4: Fix Match Method Naming Inconsistency -- DONE (2026-03-05)
**Source:** Codex (unique finding)

**What to do:** ``NAME_STATE_EXACT`` (14,989 matches) and ``name_state_exact`` (4,891 matches) appear to be the same method with different capitalization, written by different software versions. This doesn't corrupt data but makes analysis harder.

**Steps:**
1. Standardize method names: ``UPDATE unified_match_log SET match_method = UPPER(match_method) WHERE ...``
2. Add a normalization step to the matching pipeline so new matches always use consistent naming

**How long:** 2-4 hours
**Skills needed:** SQL
**Dependencies:** None
**How to verify:** ``SELECT match_method, COUNT(*) FROM unified_match_log GROUP BY match_method`` should show no case-variant duplicates.

---

### TASK 4-5: Deploy Research System on High-Priority Targets at Scale -- DONE
**Source:** All three auditors recommended; Claude Code provided detailed deployment plan
**Completed:** `scripts/research/batch_research.py` (~375 lines) with resume, backfill-only, and dry-run modes. Usage: `py scripts/research/batch_research.py --type non_union --limit 50`. Queues tasks with pending status.

**What to do:** The research system has been tested on only 41 employers. It should be run on the ~1,450 highest-value targets (Priority tier employers with recent enforcement violations). The system architecture supports batch processing — it just hasn't been used at scale.

**Steps:**
1. Generate the target list: Priority tier + enforcement data + recent violations (within 2 years)
2. Use the batch research API: ``POST /api/research/batch`` with employer IDs
3. Run 3-5 parallel agents (limited by API rate limits)
4. Monitor quality grades as runs complete
5. Apply enhancements from runs scoring ≥ 7.0
6. Save medium-quality findings (5.0-6.9) as profile notes (per Task 2-10)

**Why it matters:** The research system works well (average quality 7.88 out of 10, 93% pass rate) — it's just negligibly deployed. This is the highest-ROI use of the research infrastructure.

**How long:** 20-33 hours of compute time (97 hours single-threaded, parallelized 3-5x)
**Skills needed:** API calls (running the batch), monitoring
**Dependencies:** Task 2-10 (dual quality gate)
**How to verify:** ``SELECT COUNT(*) FROM mv_unified_scorecard WHERE has_research = TRUE`` should grow from 41 to ~1,000+.

**OPEN QUESTION:** Claude Code found the research system has a self-reinforcing loop — it targets high-scoring employers and can only raise scores. Should research be redirected to mid-tier employers (Strong/Promising) where enhancement could change tier assignments? These employers arguably benefit more from research than employers who are already Priority.

---

### TASK 4-6: Add Research Cross-Validation Against Database Records -- DONE
**Source:** Claude Code identified the gap
**Completed:** `cross_validation_rate` and `cross_validation_discrepancies` columns (NUMERIC/JSONB) on research records. Auto-grader in `scripts/research/auto_grader.py` compares findings against DB records and logs validation metrics.

**What to do:** When the research agent discovers information (e.g., "Employer X has 3 OSHA violations"), it doesn't check whether this matches what's already in the OSHA database. If research says 3 violations but the database has 0, that's either new information or a research error — and there's no way to tell.

**Steps:**
1. After each research run, compare findings against existing database records
2. Flag discrepancies: "Research found 3 OSHA violations but database has 0 — needs verification"
3. Use consistency between research and database as a quality signal (consistent = higher confidence)

**How long:** 1-2 days
**Skills needed:** Python (research pipeline modification)
**Dependencies:** None
**How to verify:** Run research on an employer with known OSHA violations. The system should note whether research findings match database records.

---

### TASK 4-7: Add Employer Linkage Retry for Unlinked Research Runs -- DONE
**Source:** Codex found 40 of 118 runs are unlinked
**Completed:** Batch system supports `--resume` for retry. `scripts/research/employer_lookup.py` handles multi-attempt employer searches with fuzzy matching.

**What to do:** 40 research runs (34%) couldn't be linked back to a specific employer in the database. This means the research was done but the findings can't be connected to any employer's profile or score. Add a retry step that uses fuzzy matching to connect unlinked runs.

**How long:** 1-2 days
**Skills needed:** Python (matching logic)
**Dependencies:** None
**How to verify:** Run the retry process. The linked-run rate should increase from 66% toward 90%+.

---

### TASK 4-8: Add Tool Effectiveness Monitoring and Pruning ✅ DONE (2026-03-05, Codex)
**Source:** Codex recommended; Claude Code noted some tools have very low hit rates

**What to do:** Some research tools are slow and rarely find useful information (e.g., ``search_mergent`` has only a 26% hit rate and some web tools take 10-17 seconds average). Monitor each tool's performance and automatically skip tools that consistently fail or are too slow.

**Resolution:** Codex implemented `scripts/analysis/tool_effectiveness.py` -- analyzes research_runs JSONB for per-tool hit rates, latency, and data quality. Includes tests.

**How long:** 1 day
**Skills needed:** Python (backend monitoring)
**Dependencies:** None
**How to verify:** After pruning, median research run time should decrease without quality loss.

---

### TASK 4-9: Research Accuracy Benchmark (20 Known Employers)
**Source:** Audit prompt requested; nobody did it

**What to do:** Pick 20 employers where we KNOW the correct answers from government databases (specific OSHA violation counts, exact employee numbers, known NLRB cases). Run the research agent on all 20. Compare research findings to ground truth. Calculate accuracy rate.

This is the empirical test of whether the research system is actually reliable.

**How long:** 2-3 days (selecting employers, running research, comparing results)
**Skills needed:** SQL (data extraction), research agent operation, analytical comparison
**Dependencies:** None (should be done before scaling to 1,450 targets in Task 4-5)
**How to verify:** Produce a report showing: for each of 20 employers, what research found vs. what's true, with overall accuracy percentage.

---

### Phase 4 — Open Questions

1. **After implementing score_eligible filtering (Task 4-1), how many employers change tiers?** This needs to be measured to understand the magnitude of the match quality problem.

2. **For the 581 Priority employers with fuzzy-only enforcement data, how many would lose Priority status entirely if fuzzy matches were excluded?** This determines how urgently the matching needs to be improved.

3. **Is the research agent's 26% hit rate on Mergent data a Mergent problem or a matching problem?** If Mergent data quality is low, the tool should be deprioritized. If it's a matching problem (searching for the wrong employer name), the tool logic should be improved.

4. **How much compute budget is available for batch research?** Running 1,450 research targets requires significant API calls. What's the cost estimate?

---

## PHASE R3: RESEARCH DOSSIER GOLD STANDARD (Weeks 4-6)

**Source:** Gap analysis against organizer-defined "questions a gold standard research report must answer" (2026-03-03). Compared the 12-question gold standard checklist to the current 30-tool research agent and identified coverage gaps, missing dossier sections, and a UX problem with failed tool display.

The gold standard questions are: (1) company name + alt names, (2) parent company + siblings + investors, (3) NAICS drill-down, (4) address + other locations + email, (5) company type, (6) CEO + leadership, (7) union presence + NLRB + similar workplaces, (8) headcount + worker comments + job postings + worker types + demographics + wages, (9) revenue + assets + liabilities, (10) industry + occupation growth + union density by geography, (11) fed/state/local contracts + PPP + 5500 + OSHA + labor violations, (12) latest news.

**Current coverage:** Questions 1, 3, 5, 7, 8a-b, 8d-f, 10 (partial), 11 (federal only), 12 are well covered. Gaps are in corporate structure (Q2), multi-location (Q4a), leadership (Q6), geographic union density (Q10b), and state/local enforcement (Q11a/d). The frontend also has a UX problem: failed tool calls consume as much visual space as successful ones, making the action log mostly noise.

---

### TASK R3-1: Collapse Failed/Empty Tool Calls in Action Log
**Source:** UX observation — gold standard gap analysis (2026-03-03)

**What to do:** The ActionLog component currently shows every tool call as an equal-weight table row. A typical run calls 25-30 tools and 10-15 return nothing ("No SEC filings found," "No 990 data," etc.). This creates a wall of grey X marks that visually overwhelms the useful results. "Not found" (expected, not an error) should be treated differently from "errored" (unexpected failure).

**Steps:**
1. Separate tool results into three categories: found data, not found (expected), errored (unexpected)
2. Show full rows only for tools that found data or had actual errors
3. Collapse "not found" tools into a single summary line: "12 tools returned no data: search_sec, search_990, search_contracts..." with an expandable detail
4. Add a quick summary bar at the top: "18/30 tools found data | 2 errors | 45s total"
5. Update frontend tests for the new layout

**Why it matters:** The research page is the primary output users see. When half the action log is "nothing found" rows, users lose confidence in the tool and miss the important results. This is the highest-ROI UX fix for research.

**How long:** 4-6 hours
**Skills needed:** React (frontend component refactor)
**Dependencies:** None
**How to verify:** Run research on any employer. The action log should show found-data tools prominently, errors visibly, and "not found" tools collapsed into a single summary.

---

### TASK R3-2: Add Corporate Structure Research Tool -- DONE (2026-03-05)
**Source:** Gold standard Q2 — "What is the parent company? What companies are also owned by that company? Who are the investors?"

**What to do:** The current ``search_gleif_ownership`` tool has thin coverage (GLEIF only covers entities with LEIs). There's no tool that systematically builds a corporate family tree. Add a ``search_corporate_structure`` tool that combines multiple sources:
- GLEIF parent/subsidiary data (existing)
- SEC filings (10-K Exhibit 21 lists subsidiaries)
- CorpWatch corporate hierarchy
- Mergent parent/subsidiary fields
- Web search fallback for investor/PE/VC ownership

The tool should output: parent company name, parent type (public/private/PE), list of known subsidiaries, and investor names if available.

**Steps:**
1. Create ``search_corporate_structure`` in ``scripts/research/tools.py``
2. Query ``corporate_identifier_crosswalk`` for SEC/GLEIF/Mergent/CorpWatch links
3. For SEC-linked companies, extract subsidiary list from 10-K filings if available
4. Fall back to web search for private companies ("who owns [company name]")
5. Structure output as ``{parent: {name, type, ticker}, subsidiaries: [...], investors: [...]}``
6. Add to Gemini tool definitions in ``agent.py``

**Why it matters:** Organizers need to know who really controls a workplace. A facility owned by a PE firm with 50 portfolio companies is a very different organizing target than a family-owned business. This is the single biggest content gap in the dossier.

**How long:** 1-2 days
**Skills needed:** Python (research tool), SQL (crosswalk queries)
**Dependencies:** None (uses existing crosswalk)
**How to verify:** Run research on a known subsidiary (e.g., a hospital owned by a health system). The dossier should identify the parent company and list sibling facilities.

---

### TASK R3-3: Add Multi-Location Discovery Tool -- DONE (2026-03-05)
**Source:** Gold standard Q4a — "Does it have other locations in the zip, MSA, state, country?"

**What to do:** Organizers need to know if a target employer has other locations — sister facilities are natural organizing expansion targets. Currently no tool systematically discovers this. Add ``search_employer_locations`` that combines:
- OSHA establishment addresses (same employer name, different site addresses)
- SAM entity physical addresses
- Mergent location data
- SOS filings (registered addresses by state)
- Web scrape of "locations" / "about" pages

**Steps:**
1. Create ``search_employer_locations`` in ``scripts/research/tools.py``
2. Query OSHA establishments matching the employer name across all states
3. Query SAM entities for matching UEIs or name+state
4. Parse web scrape results for location pages
5. Deduplicate and cluster by city/state
6. Output: ``{locations: [{address, city, state, zip, source, establishment_count}], total_locations: N}``

**Why it matters:** Multi-location employers represent cascade organizing opportunities. Finding all locations helps organizers plan campaigns across a corporate footprint.

**How long:** 1-2 days
**Skills needed:** Python (research tool), SQL
**Dependencies:** None
**How to verify:** Run research on a known multi-location employer (e.g., a national chain). The dossier should list multiple locations with addresses.

---

### TASK R3-4: Add Leadership/Management Extraction Tool -- DONE (2026-03-05)
**Source:** Gold standard Q6 — "Who is the CEO of the parent company? Who are the leadership team of the location?"

**What to do:** Organizers need to know who runs the target workplace. Currently ``search_sos_filings`` captures registered agents and corporate officers (typically legal/compliance roles), but there's no tool focused on operational leadership (CEO, COO, local GM/plant manager). Add ``search_leadership`` that extracts management names from:
- SOS filings (existing — officers, directors)
- SEC proxy statements (executive compensation disclosures — public companies)
- Web scrape of "leadership" / "about us" / "team" pages
- Web search fallback ("[company name] CEO" / "[company name] [city] manager")

**Steps:**
1. Create ``search_leadership`` in ``scripts/research/tools.py``
2. For public companies: parse SEC proxy/DEF14A for named executive officers
3. For all companies: scrape "about us" / "leadership" / "team" pages via ``scrape_employer_website`` with targeted URL patterns
4. Combine with SOS officer data
5. Output: ``{parent_ceo: {name, title}, executives: [...], local_leadership: [...], source: "..."}``

**Why it matters:** Knowing who runs the workplace helps organizers personalize outreach, understand management style, and research individual decision-makers' track records.

**How long:** 1-2 days
**Skills needed:** Python (research tool, web scraping)
**Dependencies:** None
**How to verify:** Run research on a public company. The dossier should name the CEO and at least some C-suite executives.

---

### TASK R3-5: Add NAICS Drill-Down Narrative to Dossier -- DONE (2026-03-05)
**Source:** Gold standard Q3 — "What is the NAICS code? What do we infer the code down to 3, 4, 5, 6?"

**What to do:** When the dossier reports a NAICS code (e.g., 622110), it should explain what each level means in plain English:
- 62 = Health Care and Social Assistance
- 622 = Hospitals
- 6221 = General Medical and Surgical Hospitals
- 62211 = General Medical and Surgical Hospitals
- 622110 = General Medical and Surgical Hospitals

This helps organizers who aren't familiar with NAICS understand exactly what industry the employer is in and how it relates to broader sectors. The ``get_industry_profile`` tool already has some of this data but doesn't present the hierarchy.

**Steps:**
1. Load NAICS hierarchy data (2-through-6-digit titles) — available from Census Bureau
2. Enhance ``get_industry_profile`` tool to include hierarchical breakdown
3. Add the hierarchy to the identity section of the dossier output
4. Update ``DossierSection`` KEY_LABELS to render the hierarchy clearly

**Why it matters:** NAICS codes are opaque to non-specialists. Showing the full hierarchy helps organizers understand the industry context and find comparable employers.

**How long:** 4-6 hours
**Skills needed:** Python (tool enhancement), data loading
**Dependencies:** None
**How to verify:** Run research on any employer with a known NAICS code. The identity section should show the full 2-through-6-digit hierarchy with descriptions.

---

### TASK R3-6: Add New Dossier Sections (Corporate Structure, Locations, Leadership) ✅ DONE (2026-03-05, Codex)
**Source:** Gold standard gap analysis — current 7 sections don't cover Q2, Q4a, Q6

**What to do:** The dossier currently has 7 sections: identity, labor, workforce, workplace, financial, assessment, sources. Add three new sections to match the gold standard:

1. **Corporate Structure** — parent company, subsidiaries, investors, corporate family tree. Populated by R3-2 tool.
2. **Locations** — all known employer locations with addresses and establishment counts. Populated by R3-3 tool.
3. **Leadership** — CEO, executives, local management. Populated by R3-4 tool.

**Steps:**
1. Update ``agent.py`` system prompt to include the new sections in the dossier template
2. Add section metadata to ``DossierSection.jsx`` SECTION_META (icons, labels, default open state)
3. Add KEY_LABELS for new fields (parent_company, subsidiaries, investors, locations, ceo, executives, etc.)
4. Update SECTION_ORDER in ``ResearchResultPage.jsx``
5. Update the auto-grader's coverage dimension to include the new sections
6. Update frontend tests

**Why it matters:** Organizers expect a complete picture. Missing corporate structure and leadership info makes the dossier feel incomplete compared to what a manual researcher would produce.

**How long:** 1 day
**Skills needed:** Python (agent prompt), React (frontend sections)
**Dependencies:** Tasks R3-2, R3-3, R3-4 (tools that populate the sections)
**How to verify:** Run research on an employer. The dossier should show 10 sections instead of 7, with the new sections populated when data is available.

---

### TASK R3-7: Add Geographic Union Density Breakdown -- DONE (2026-03-05)
**Source:** Gold standard Q10b — "Are there many unions in the industry nationally, state, county, zip?"

**What to do:** The current ``get_industry_profile`` provides national-level union density from BLS. But organizers need to know union presence at the local level — "Are there other unions in this industry in this county?" Add geographic granularity to the union density tool.

**Steps:**
1. Create ``search_local_union_density`` tool or enhance ``get_industry_profile``
2. Query F7 data: count distinct unions and bargaining units by NAICS prefix + state, county, zip
3. Query NLRB elections by industry + geography for recent organizing activity
4. Output: ``{national_density: X%, state_unions: N, state_bus: N, county_unions: N, county_bus: N, recent_elections_nearby: [...]}``

**Why it matters:** Local union density is a key indicator of organizing infrastructure — existing unions nearby mean experienced organizers, established labor councils, and community support. National density alone misses the local picture.

**How long:** 4-6 hours
**Skills needed:** Python (research tool), SQL
**Dependencies:** None
**How to verify:** Run research on an employer in a heavily unionized area. The dossier should show state/county-level union counts and nearby elections.

---

### TASK R3-8: Improve State/Local Enforcement and Contract Coverage -- DONE (2026-03-05)
**Source:** Gold standard Q11a/d — "Does the employer receive state or municipal contracts?" and "Do they have state or local labor violations?"

**What to do:** The current research tools cover federal enforcement (OSHA, WHD, SAM) and NYC-specific enforcement, but miss state/local data. This is a data acquisition problem — most states don't publish procurement or labor violations in machine-readable format. Where data IS available, add tools:

**Steps:**
1. Audit which states publish procurement data in downloadable format (start with NY, CA, IL, MA — largest labor markets)
2. For states with available data, build ``search_state_contracts`` tool
3. Extend ``search_nyc_enforcement`` pattern to other cities/states that publish enforcement data
4. For states without data, enhance web search queries to include state-specific enforcement ("OSHA [state]" / "[company] labor violations [state]")
5. Add state/local contract and violation counts to the workplace and financial dossier sections

**Why it matters:** State and local contracts are significant leverage — many cities have labor peace/neutrality requirements for contractors. State labor violations (wage theft, misclassification) often differ from federal findings.

**How long:** 1-2 weeks (research-intensive — data availability varies by state)
**Skills needed:** Python (ETL, research tools), manual research (data source identification)
**Dependencies:** None (can start immediately, but full coverage is a long-term project)
**How to verify:** Run research on an employer in NY or CA. State-level contract and enforcement data should appear when available.

---

### TASK R3-9: Wire BLS Datasets (OES/SOII/JOLTS/NCS) into Research Tools -- DONE
**Completed:** 2026-03-05. OES/SOII/JOLTS/NCS wired into get_industry_profile() in tools.py.
**Source:** Gap analysis (2026-03-05) — 4 BLS datasets loaded but unused by research tools

**What to do:** `get_industry_profile()` in `scripts/research/tools.py` only queries occupation matrix, projections, and density. It should also pull from the 4 BLS datasets loaded on 2026-03-04:

1. **OES area wages** — `mv_oes_area_wages` (224K rows). Add area-specific wage percentiles (10th/25th/median/75th/90th) by occupation. Currently only national wages from `bls_occupation_projections`.
2. **SOII injury rates** — `mv_soii_industry_rates` (45K rows). Add industry-level injury/illness rates and trends. Complements OSHA violation data with statistical benchmarks.
3. **JOLTS turnover** — `mv_jolts_industry_rates` (63K rows). Add quit rates, job openings, hires by industry. Quit rates signal labor instability — a key organizing indicator.
4. **NCS benefits** — `mv_ncs_benefits_access` (593K rows). Add healthcare, retirement, paid leave access/participation rates. Benefits gaps are organizing signals.

Also consider: wire O*NET data (currently API-only in `api/routers/profile.py`) into research tools for occupation-level skill/knowledge analysis.

**How long:** 2-4 hours
**Skills needed:** Python, SQL (research tools)
**Dependencies:** BLS data already loaded (2026-03-04)
**How to verify:** Run `get_industry_profile('TEST', naics='622110', state='NY')`. Should return SOII injury rates, JOLTS quit rates, NCS benefits access, and OES area wages in addition to existing data.

---

### Phase R3 — Open Questions

1. **Email address extraction (Q4b) — worth the effort?** Extracting employer email addresses from web scrapes and contact pages is technically possible but has dubious value for labor organizing. Organizers typically need worker contacts, not corporate email. Consider deprioritizing.

2. **Asset/liability data for private companies (Q9a-b) — any viable source?** SEC covers public companies. For private companies, the only sources are Mergent (spotty), D&B (expensive), or Form 990 (nonprofits only). Is there a cost-effective way to get private company financial detail?

3. **Occupation-level growth projections (Q10a) — which data source?** BLS Occupational Employment and Wage Statistics (OEWS) or Occupational Outlook Handbook (OOH) could provide occupation growth forecasts. Is this worth loading as a new data source, or is industry-level growth sufficient?

4. **How should the dossier present "Verified None" vs "Not Searched"?** When a tool finds no data, should the dossier say "No OSHA violations found" (which might mislead) or "OSHA data: not matched to this employer" (more honest but verbose)?

5. **Should the new dossier sections affect the auto-grading formula?** Adding 3 sections means the coverage dimension denominator changes. A run that fills 7/10 sections scores lower than the same run would have at 7/7. Adjust grading to account for new sections incrementally?

---

## PHASE 5: NEW DATA SOURCES AND PUBLIC SECTOR (Months 2-4)

These tasks bring in entirely new data that doesn't exist in the platform yet. They require more effort because they involve external data acquisition, not just internal pipeline fixes.

---

### TASK 5-1: NLRB API Daily Sync -- DONE
**Source:** Claude Code recommended as easiest new data source
**Completed:** `scripts/etl/sync_nlrb_sqlite.py` (~832 lines) -- 10-phase diff-based sync from SQLite to PostgreSQL. Handles filings, elections, voting units, participants, docket, allegations, tallies, and more. Usage: `py scripts/etl/sync_nlrb_sqlite.py path.db --commit [--phase X]`

**What to do:** The NLRB has a public API (``api.nlrb.gov``) that provides free JSON access to cases, elections, and decisions. The platform's NLRB data is currently 1-2 months stale. A daily or weekly sync would keep it current.

**Steps:**
1. Build an ETL script that pulls new cases/elections from the NLRB API
2. Deduplicate against existing records
3. Schedule to run daily

**How long:** 1 week
**Skills needed:** Python (ETL scripting, API integration)
**Dependencies:** None
**How to verify:** After one week, the latest NLRB case date should be within 1 day of current.

---

### TASK 5-2: REMOVED
**Reason:** WARN Act data is a lagging indicator (layoffs already happened) with limited organizing value. Deprioritized in favor of forward-looking signals.

---

### TASK 5-3: State PERB Pilot (NY + CA + OH)
**Source:** All three auditors recommended; most detailed analysis by Claude Code

**What to do:** Public sector workers make up roughly half of all union members, but the platform's data comes almost entirely from federal databases that only cover the private sector. State Public Employee Relations Boards (PERBs) maintain records of public sector bargaining units. Starting with three states would unlock massive new coverage.

**Pilot states (primary — largest coverage impact):**
- **New York PERB:** Online case search, web-scrapable, thousands of cases
- **California PERB:** Online case tracker, partially searchable, structured scraping feasible
- **Ohio SERB:** Published contract settlements, some structured data

**Alternative easy-start states (from Round 2 audit — most accessible data):**
- **Minnesota BMS:** Structured web tables with unit size — easiest to ingest
- **Washington PERC:** Searchable online database — medium difficulty

**Steps:**
1. Research each state's data format, availability, and content in detail
2. Build web scrapers for each state
3. Create ETL pipelines to load into existing ``ps_*`` tables
4. Match public sector employers to the platform's existing records (or create new employer records)
5. Design public sector scoring factors (PERB election history, state labor law compliance, contract status)

**Why it matters:** 5.4 million union members are in primarily public sector unions (NEA, AFT, AFSCME) that are essentially invisible on the platform. For a tool used by public sector unions, this is a critical gap.

**How long:** 4-6 weeks for 3-state pilot (approximately 2 weeks per state)
**Skills needed:** Python (web scraping, ETL), SQL, data modeling
**Dependencies:** None (can start anytime)
**How to verify:** ``ps_bargaining_units`` should grow from 438 to thousands.

**OPEN QUESTIONS (from audit prompt, mostly unanswered):**

These should be investigated as part of the Task 5-3 planning:

1. **For each of the 10 states listed in the audit prompt** (CA, NY, IL, MA, NJ, OH, PA, MI, CT, MN), what format is the PERB data in? CSV, PDF, database, website scrape? This was asked but not fully answered for all 10.

2. **For each state with accessible data:** Does it include employer name, union name, bargaining unit size, recognition date, contract expiration? Can it be bulk-downloaded or does each record need individual scraping?

3. **How would public sector data change the scoring system?** NLRB-based signals don't apply to public sector (PERB/FLRA instead). What replaces them? Need to design a parallel scoring framework.

4. **The Census of Governments** lists ~90,000 government entities. Could this serve as a crosswalk to match PERB data to government employers? Claude Code estimated "low match confidence" — but has this been tested?

5. **Can LM filings identify public sector locals?** Text analysis of the jurisdiction description field (e.g., "City of Boston employees") could identify which of the 5,511 unions in ``ar_membership`` are public sector. Claude Code estimated 70% accuracy. How many are there? This should be tested before the PERB pilot.

6. **What about FLRA for federal employees?** The ``flra_olms_union_map`` table has only 40 rows. Federal employees represent ~700K union members. Should FLRA data acquisition happen in parallel with PERB?

7. **Draft a FOIA request template** for states without online data. The audit prompt specifically asked for this but nobody wrote one.

---

### TASK 5-4: BLS Benefit Surveys -- DONE
**Completed:** 2026-03-05. NCS data loaded (768K rows) and surfaced in workforce profile endpoint.
**Source:** Audit prompt listed; Claude Code recommended as easy to obtain

**What to do:** BLS publishes industry benefit averages (what benefits are typical for each industry). This provides the benchmark needed for the ``score_benefits`` factor from Task 3-1 — you can't say "this employer's benefits are below average" without knowing what average is.

**How long:** 3-5 days (public download CSVs, simple ETL)
**Skills needed:** Python (ETL)
**Dependencies:** Task 3-1 (Form 5500 integration) benefits from this context
**How to verify:** Industry benefit averages available for comparison in employer profiles.

---

### TASK 5-5: Integrate Public Sector Tables into Platform
**Source:** Codex found these tables are one-time loaded; Claude Code confirmed they're unused

**What to do:** The platform already has:
- ``ps_parent_unions`` (24 rows)
- ``ps_union_locals`` (1,520 rows)
- ``ps_employers`` (7,987 rows)
- ``ps_bargaining_units`` (438 rows)

These need to be connected to research tools, scoring factors, and API endpoints. Currently, no part of the platform uses them.

**Steps:**
1. Add public sector employers to the research tool's searchable scope
2. Create API endpoints for public sector employer profiles
3. Set up a recurring ingestion schedule (currently one-time January 2026 load)
4. Connect to new PERB data as it arrives from Task 5-3

**How long:** 1-2 weeks
**Skills needed:** Python (API), SQL
**Dependencies:** Task 5-3 provides the data flow
**How to verify:** Public sector employers appear in search results and have profiles.

---

### TASK 5-6: State OSHA Plan Data
**Source:** Audit prompt listed

**What to do:** 22 states run their own OSHA programs (called "state plan states"). Their data may not be in the federal OSHA database. Getting state OSHA data could roughly double OSHA coverage.

**Steps:**
1. Research which state OSHA programs publish their data
2. Start with the 5 largest state-plan states
3. Build ETL pipelines to integrate

**How long:** 2-4 weeks per state
**Skills needed:** Python (ETL, possible web scraping), SQL
**Dependencies:** None
**How to verify:** OSHA coverage percentage increases in state-plan states.

**OPEN QUESTION:** Which 5 state-plan states would give us the most additional data? The audit prompt asked this but nobody provided state-level record count estimates.

---

### TASK 5-7: State Wage Theft Agencies
**Source:** Audit prompt listed

**What to do:** Similar to state OSHA — some states have their own wage theft enforcement beyond the federal WHD. Integrating these would increase WHD-equivalent coverage.

**How long:** 2-4 weeks per state
**Skills needed:** Python (ETL, possible web scraping), SQL
**Dependencies:** None
**How to verify:** WHD-equivalent coverage percentage increases.

---

### Phase 5 — Open Questions

1. **What's the legal landscape for web scraping PERB data?** Is it clearly public record that can be scraped freely, or are there terms of service restrictions?

2. **How sustainable is web scraping for ongoing updates?** Sites change their structure. Would FOIA requests be more reliable for long-term data access, even if slower?

3. **For the 17 unions with zero F7 coverage** (NEA 2.84M, AFT 1.80M, AFSCME 1.31M, etc.), could the research agent systematically scrape their national websites to build employer-level detail? Claude Code found the AFSCME prototype worked (295 profiles, 160 employers, 73 matched). Is this scalable?

4. **Is Glassdoor/Indeed data worth the legal risk?** The audit prompt listed it as "HIGH value, HIGH risk." All three auditors avoided making a recommendation. Does the value justify potential legal challenges?

---

## PHASE 6: UX FEATURES AND EXPORTS (Weeks 6-10, can overlap with Phase 5)

These tasks improve what users can DO with the platform, not just what data it contains.

---

### TASK 6-1: Enhanced CSV Export -- DONE
**Source:** Claude Code found current export is rudimentary (11 fields)

**What to do:** The current CSV export includes only basic fields. It should include enforcement details, NLRB election history, corporate hierarchy, research findings, and all scoring factors.

**How long:** 1-2 days
**Skills needed:** Python (API endpoint), SQL
**Dependencies:** None
**How to verify:** Download CSV. Verify it contains OSHA details, NLRB elections, etc.

---

### TASK 6-2: PDF/Print Employer Profiles -- DONE
**Source:** Claude Code recommended; neither other auditor addressed

**What to do:** Organizers need to bring information to committee meetings. There's no way to print or export a clean employer profile. Options:
- Add print-friendly CSS (simplest)
- Add a PDF generation library
- Both

**How long:** 2-3 days
**Skills needed:** React (CSS), optional PDF library
**Dependencies:** None
**How to verify:** Print an employer profile. It should be readable on paper.

---

### TASK 6-3: Employer Comparison View ✅ DONE (2026-03-05, Codex)
**Source:** Audit prompt requested; Claude Code designed it

**What to do:** Let users compare 2-3 employers side by side with radar charts showing all scoring factors. This is a basic workflow for organizers choosing between potential targets.

**Resolution:** Codex implemented `CompareEmployersPage.jsx` at `/compare` route with side-by-side factor comparison, radar charts, and employer selection. Includes frontend tests.

**How long:** 1 week
**Skills needed:** React (frontend development, charting library)
**Dependencies:** Scorecard API
**How to verify:** Select two employers. See a side-by-side comparison page.

---

### TASK 6-4: Fix Frontend Signal Count Mismatch -- DONE (2026-03-05)
**Source:** Gemini (unique finding)

**What to do:** The UI shows "Signals Detected" out of 8, but there are actually 9+ factors in the data. Update the total to match reality.

**How long:** 1-2 hours
**Skills needed:** React (frontend)
**Dependencies:** None
**How to verify:** Check the signals display for any employer. The total should show the correct number.

**Resolution:** Changed "/8" to "/9" in ProfileHeader.jsx, TargetsPage.jsx, and TargetsTable.jsx. Backend counts 9 signals (osha, whd, nlrb, contracts, financial, industry_growth, union_density, size, similarity).

---

### TASK 6-5: Fix Research Enhancement Badge Logic -- DONE (2026-03-05)
**Source:** Gemini (unique finding)

**What to do:** The "R" badge (indicating research has enhanced a score) only shows when the enhanced score is strictly GREATER than the database score. If research CONFIRMS a high database score (same number), no badge appears. There should be a "Verified" badge for confirmed scores.

**How long:** 2-4 hours
**Skills needed:** React (frontend)
**Dependencies:** None
**How to verify:** Find an employer where research confirmed the existing score. A "Verified" badge should appear.

**Resolution:** Added `isVerified()` function in ScorecardSection.jsx that detects `has_research && enh === base`. Shows blue "V" badge (#3a6b8c) alongside existing green "R" badge for enhanced scores.

---

### TASK 6-6: Build Outcome Feedback Loop ✅ DONE (2026-03-05, Codex)
**Source:** Claude Code (unique finding — "Questions the audit should have asked")

**What to do:** The platform recommends organizing targets but never learns whether those recommendations were good. Add a simple "Campaign Outcome" field to flagged employers: Won / Lost / Abandoned / In Progress. Over time, this data validates (or invalidates) the scoring system.

**Resolution:** Codex implemented `scripts/etl/create_campaign_outcomes.py` (table creation), `api/campaigns.py` (CRUD API router), `CampaignOutcomeCard.jsx` (frontend modal). Table needs to be created by running `py scripts/etl/create_campaign_outcomes.py`.

**Steps:**
1. Create a ``campaign_outcomes`` table
2. Add a simple modal to the "Flag as Target" workflow asking for status updates
3. Eventually use outcomes to validate scoring weights (feedback into Task 1-15)

**How long:** 1-2 days
**Skills needed:** SQL, Python (API), React (frontend modal)
**Dependencies:** None
**How to verify:** Flag an employer, enter a campaign outcome. Data appears in the outcomes table.

---

### TASK 6-7: Surface Research Quality in Frontend Profiles -- DONE
**Source:** Research agent investigation (Feb 27) -- carried forward from Round 2 roadmap
**Completed:** `ResearchInsightsCard.jsx` displays research quality score, contradictions, dossier link, and freshness. Wired into employer profile page. `research_quality` field returned in API profile payload.

**What to do:** When an employer has research data, the profile page should display it prominently. The frontend components already exist (``DossierSection``, ``ActionLog``) but aren't wired into employer profile pages. This builds on Tasks 1-12 (source-state badges) and 4-5 (research deployment) — once research runs at scale, profiles need to show the results.

**What to display:**
- Research quality score (0-10) with a visual indicator (ScoreGauge or colored badge)
- Key contradictions between DB and web sources (e.g., "DB shows 0 OSHA violations, web mentions safety incidents")
- Data freshness indicator (when was research last run?)
- Link to full dossier with 7 collapsible sections (Company Overview, Labor Relations, Financial, Workforce, Industry, Compliance, Strategic Assessment)
- Score delta: how much did research change this employer's score?

**Steps:**
1. Wire ``DossierSection`` component into the employer profile page (conditionally rendered when ``has_research = TRUE``)
2. Add a "Research Intelligence" section between the scoring section and enforcement details
3. Show research quality badge in the profile hero/header area
4. Display contradiction count with expandable detail
5. Add "Last Researched: X days ago" freshness indicator
6. Link "View Full Dossier" to the research result detail page

**How long:** 4-6 hours
**Skills needed:** React (frontend component wiring)
**Dependencies:** Task 4-5 (research deployment — needs research data to display)
**How to verify:** View an employer profile that has research data. The research section should appear with quality score, contradictions, and dossier link.

---

### Phase 6 — Open Questions

1. **What export formats do organizers actually need?** PDF? Word? PowerPoint slides? A "board report" format? Ask actual users before building.

2. **Should there be a "My Targets" dashboard?** A place where an organizer can save employers they're watching, track campaign status, and see score changes over time?

---

## PHASE 7: UNION DATA QUALITY (Weeks 6-10, can overlap with Phases 5-6)

---

### TASK 7-1: Fix Union Hierarchy — Name Parsing for Intermediate Bodies -- DONE (2026-03-03)
**Source:** Claude Code tested IBEW and Teamsters specifically; all three flagged the problem

**What to do:** Union hierarchy is flat — only 2 levels (national → local). Real unions have 3-5 levels (national → district → council → local). IBEW has 11 districts that are completely missing. Teamsters have 25+ joint councils that are missing.

**Approach: Name-parsing (recommended as quickest):**
1. Parse union names for hierarchy clues: "IBEW District 3" → level=DISTRICT, parent=IBEW International
2. "Teamsters Joint Council 16" → level=JOINT_COUNCIL, parent=Teamsters International
3. A regex-based classifier could handle ~80% of cases
4. Update ``parent_fnum`` in ``union_hierarchy`` for classified intermediates

**How long:** 2-3 days
**Skills needed:** Python (regex/text parsing), SQL
**Dependencies:** Task 1-8 (TRIM whitespace first)
**How to verify:** Expand IBEW in the Union Explorer. You should see 11 districts between the international and 838 locals, not a flat list.

**Resolution:** (1) `desig_name` classification in `_classify_union_level()` maps NHQ/FED=national, DC/JC/CONF/D/C/SC/SA/BCTC=intermediate, LU/BR/etc=local. (2) `parent_fnum` links locals to intermediates. (3) `AffiliationTree.jsx` renders 3-level hierarchy (national > intermediate > local) with state grouping for orphan locals. (4) Local numbers now displayed in tree nodes and profile headers (2026-03-06). (5) Hierarchy API endpoint returns `local_number` for all locals.

---

### TASK 7-2: Resolve CWA District 7 / File Number 12590
**Source:** Claude Code investigated in detail (Addendum C)

**What to do:** CWA District 7 covers 42 employer relationships with 22,650 workers across 19 states. The district split into 5 successor locals. Each employer relationship needs to be assigned to the correct successor local.

**Key finding:** AT&T Mobility LLC (Birmingham, AL) accounts for 93.3% of the workers (21,126). One manual lookup for this single employer would resolve the vast majority of the problem.

**Steps:**
1. Research which CWA local now covers AT&T Mobility Birmingham → Update that one record
2. For the remaining 41 employers (averaging 37 workers each), research which successor local covers each
3. Validate the 5 crosswalk entries (currently at 0.70 confidence)

**How long:** 2-4 hours of manual research
**Skills needed:** Manual research (OLMS lookup, union website research)
**Dependencies:** None
**How to verify:** File 12590 should resolve to specific successor locals with no orphaned relationships.

---

### TASK 7-3: Resolve Remaining 138 Missing Union File Numbers
**Source:** Claude Code found 138 remain (down from 195)

**What to do:** 138 file numbers in the union-employer relationship table don't match any known union. These cover thousands of workers. Each one is either: (a) a merged union that needs remapping, (b) a dissolved union that should be marked historical, (c) a data entry error, or (d) unknown.

**Steps:**
1. Sort by worker count (largest impact first)
2. For the top 20, look up the file number on the OLMS public disclosure system (``https://olms.dol.gov``)
3. Determine status and remap or mark as appropriate
4. For the remaining 118, batch-process where possible using affiliation patterns

**How long:** 1-2 days (manual research on top 20, batch processing for remainder)
**Skills needed:** Manual research, SQL
**Dependencies:** None
**How to verify:** Missing file number count drops from 138 toward 0.

---

### TASK 7-4: Filter or Flag Stale Union Records -- DONE (2026-03-03)
**Source:** Claude Code found ~20% have yr_covered before 2020

**What to do:** About 20% of unions in the database haven't filed an annual report in 3+ years. These are likely dissolved or merged. The API search wisely filters them out by default (``yr_covered >= 2022``), but they inflate aggregate counts and clutter the hierarchy tree.

**Steps:**
1. Count how many unions have ``yr_covered`` before 2020
2. Add a ``is_likely_inactive`` flag based on filing recency
3. Exclude from hierarchy trees and aggregate statistics unless explicitly requested
4. Show inactive unions with a grey "Inactive" label if they appear in search results

**How long:** 4-6 hours
**Skills needed:** SQL, API, Frontend
**Dependencies:** None
**How to verify:** Union counts should drop to reflect only active organizations. Hierarchy trees should be cleaner.

**Resolution:** (1) `is_likely_inactive` flag added to `unions_master`. (2) Hierarchy endpoint filters inactive by default (`include_inactive=false`). (3) Inactive badge shown in AffiliationTree. (4) `union_hierarchy.count_members` prevents double-counting; `deduplicated_members` field in national endpoint (2026-03-06: fixed stale __pycache__ that was hiding this field, total dropped from ~70M to ~13.9M).

---

### TASK 7-5: Add Union Health Composite Indicators -- DONE
**Source:** Audit prompt requested; Claude Code mapped data availability
**Completed:** 4-part composite health grade in `api/routers/unions.py` (`_compute_health()`). Displayed in `UnionProfilePage.jsx` with `UnionProfileHeader` showing health grade. Sub-indicators: membership trend, election win rate, financial stability, organizing activity.

**What to do:** Add composite health indicators for each union local:
- **Membership trend:** Growing or shrinking (data in ``lm_data``)
- **Election win rate:** How often does this local win NLRB elections? (data in ``nlrb_elections`` + ``nlrb_participants``)
- **Financial stability:** Assets vs liabilities, spending patterns (data in ``ar_assets_investments`` + ``ar_disbursements_total``)
- **Organizing activity:** Is this local actively filing NLRB cases? (data in NLRB filings)

Claude Code found: 24,776 unions have 3+ years of filing data. 45.7% are growing membership, 51.9% declining, 2.3% flat.

**Steps:**
1. For each indicator, write the SQL aggregation query
2. Create a ``union_health_score`` composite
3. Add to union profile API
4. Display as trend sparklines or health badges on union profiles

**How long:** 2-3 days
**Skills needed:** SQL, Python (API), React (frontend visualization)
**Dependencies:** Task 3-6 (disbursement analysis) provides financial health data
**How to verify:** View a union profile. Health indicators should appear with trend data.

---

### TASK 7-6: Clarify F7 "Covered Workers" vs LM "Members" Display -- DONE (2026-03-05)
**Source:** Claude Code found the distinction is not explained to users

**What to do:** F7 data counts "covered workers" (everyone the union covers in bargaining), while LM data counts dues-paying members. Building trades show 10-30x more covered workers than members (USW: 588K covered workers vs 18K members). This is structurally correct but confusing if not explained.

**Steps:**
1. Add tooltips or info icons explaining the difference
2. Show both numbers when available (covered workers from F7, members from LM)
3. Flag extreme ratios (>10x) with an explanation

**How long:** 4-8 hours
**Skills needed:** React (frontend), API (if LM data not yet in union endpoint)
**Dependencies:** None
**How to verify:** View a building trades union. Both numbers should appear with clear labels.

**Resolution:** (1) Fixed bug: `union.total_workers` was wrong key (always `--`), corrected to `union.f7_total_workers`. (2) Hero now shows both "Members (LM)" and "Covered Workers (F-7)" side by side. (3) MiniStat relabeled to "Covered Workers (F-7)". (4) Extreme ratio (>10x) shows explanatory note. (5) Tooltips added to Members headers in UnionResultsTable, AffiliationTree, SisterLocalsSection, UnionFinancialsSection. (6) Results table "Workers" column renamed to "Covered" with tooltip.

---

### TASK 7-7: Union Explorer Page Cleanup

**Status:** OPEN
**Added:** 2026-03-07
**Priority:** High — this is one of the first pages a user sees

**Problem:** The union explorer page has multiple data quality and UX issues that need systematic cleanup:

1. **Membership numbers still inconsistent across views** — Tree view now uses NHQ membership (MAX per affiliation) but profile pages, search results, and sub-nodes (intermediates, locals) may still show stale or incorrect counts. Need end-to-end audit of where `members` is sourced.
2. **Schedule 13 (LM filing) is authoritative for active membership** — Ensure all membership displays consistently use the NHQ's LM filing membership, not sums of locals.
3. **Profile page content audit** — Each section (membership history, organizing capacity, employers, elections, financials, disbursements, sister locals, expansion targets, health) needs review for data accuracy and completeness.
4. **Tree view UX for large unions** — Expanding SEIU/IBEW/Teamsters may produce unusably long lists. Consider pagination, virtual scrolling, or collapsed state summaries.
5. **Search results table** — Verify member counts, covered workers, and other columns are accurate and sourced consistently.
6. **National summary cards** — AFL-CIO/CTW/Independent grouping logic is naive (string matching on aff_abbr). Needs proper affiliation group mapping.
7. **Intermediate body display** — Some intermediates show 0 members or 0 locals. Verify hierarchy classification and member aggregation.
8. **Inactive union handling** — Inactive unions appear in tree but may confuse users. Consider visual distinction or filtering options.

**How long:** 2-4 sessions
**Skills needed:** React (frontend), FastAPI (backend), SQL (data queries)
**Dependencies:** None
**How to verify:** Manual walkthrough of 5+ large affiliations (SEIU, IBEW, AFSCME, Teamsters, UFCW). Each should show correct NHQ membership, usable hierarchy, and accurate profile data.

---

### Phase 7 — Open Questions

1. **How many intermediate bodies actually exist in the database?** List the 20 largest by membership. Where do they sit in the hierarchy currently?

2. **For the Teamsters test case:** Does the hierarchy show all 4 levels correctly (International → Area Conferences → Joint Councils → Locals)? Or is it flat?

3. **Are there duplicate unions in the database?** Two records for the same local under slightly different names? Claude Code said no true duplicates found, but Codex didn't verify this independently.

4. **The union explorer page is described as "one of the first things a user sees." How does it actually look?** Does expanding a large union (SEIU, IBEW, Teamsters) give a usable experience? Nobody tested the actual UI with screenshots.

---

## PHASE 8: LONG-TERM PROJECTS (Months 4-6+)

These are larger efforts that build on everything above. They should only start after the foundation is solid.

---

### TASK 8-1: SEC EDGAR Deep Integration + Mergent Full Load
**PRIORITY: NEXT UP** — This is one of the next major tasks.
**Source:** Codex found only metadata loaded; Claude Code confirmed no deep parsing

**What to do:** Two complementary data enrichment efforts for public/large company coverage:

**Part A — SEC EDGAR XBRL Parsing:**
SEC filings contain employee counts, human capital disclosures, executive compensation, and subsidiary information. Currently only a metadata table exists (517K companies). Full XBRL parsing of 10-K filings would provide:
- Employee counts (for large public companies)
- CEO-to-worker pay ratio (powerful organizing argument)
- Human capital risk disclosures
- Subsidiary structures (Exhibit 21)

**Part B — Mergent Full Load (~1.75M records):**
Currently only 56,426 Mergent records loaded (partial load via `load_mergent_al_fl.py`). The full Mergent dataset contains ~1.75 million US business records with DUNS numbers, employee counts, revenue, NAICS codes, and addresses. Loading the full dataset would:
- Dramatically increase employer-level size data coverage (employee counts for 1.75M employers)
- Provide revenue data for RPE validation and financial scoring
- Add NAICS codes for hundreds of thousands of employers currently missing industry classification
- Enable crosswalk expansion via DUNS→EIN linkage

**This task should get its own detailed roadmap** given the scope — SEC XBRL parsing and Mergent bulk loading are independent workstreams that can run in parallel.

**How long:** 3-4 weeks total (SEC XBRL: 2-3 weeks, Mergent full load: 1-2 weeks)
**Skills needed:** Python (XBRL parsing, edgartools library, ETL), SQL, data modeling
**Dependencies:** None
**How to verify:** ``sec_companies`` table gains ``employee_count``, ``ceo_pay`` columns with data. ``mergent_employers`` grows from 56K to ~1.75M rows.

---

### TASK 8-2: CBA Database Scaling
**Source:** Claude Code found pipeline built but only 4 contracts loaded

**What to do:** The Collective Bargaining Agreement (CBA) analysis pipeline exists end-to-end (extract, parse, tag, review) but only has 4 contracts. Scaling to thousands requires sourcing contracts at scale, likely from PDF collections.

**How long:** 3-6 months to reach 5,000 contracts
**Skills needed:** PDF processing, NLP, data engineering
**Dependencies:** Contract sourcing strategy

---

### TASK 8-3: Expand Union Web Scraper
**Source:** Claude Code found AFSCME prototype works; Codex confirmed partial build

**What to do:** The AFSCME web scraper prototype (295 profiles, 160 employers, 73 matched) proved the concept works. Expand to other large unions: SEIU, Teamsters, UFCW, IBEW.

**How long:** 4-6 weeks per union
**Skills needed:** Python (web scraping, Crawl4AI), data matching
**Dependencies:** Task 7-1 (hierarchy should be fixed first so scraped data can be placed correctly)

---

### TASK 8-4: Build Employer Website Scraper
**Source:** Claude Code found research agent has single-employer tool but no systematic pipeline

**What to do:** Build a systematic crawling pipeline that scrapes employer websites for: employee counts, office locations, job postings, benefits information, corporate statements. Currently, the research agent's ``scrape_employer_website`` tool works for individual employers but there's no batch infrastructure.

**How long:** 3-4 weeks
**Skills needed:** Python (web scraping, NLP), infrastructure
**Dependencies:** None

---

### TASK 8-5: CPS Microdata for Custom Density Calculations
**Source:** Claude Code listed as not started

**What to do:** Current Population Survey microdata from IPUMS would enable custom union density calculations by detailed occupation, industry, and geography combinations — more granular than existing BLS aggregates.

**How long:** 2-3 weeks
**Skills needed:** Data science, SQL
**Dependencies:** None

---

### TASK 8-6: News Monitoring Pipeline
**Source:** Claude Code listed as not started

**What to do:** Monitor news sources for: strikes, organizing campaigns, major layoffs, workplace safety incidents, wage theft scandals. Automatically flag employers in the platform when they appear in labor news.

**How long:** 2-3 weeks initial build; ongoing maintenance
**Skills needed:** Python (news API integration, NLP), infrastructure
**Dependencies:** News API subscription

---

### TASK 8-7: REMOVED
**Reason:** Historical density trends are informational but don't drive organizing decisions. State×industry density estimates already built via `create_state_industry_estimates.py`. CPS occupation demographics loaded via `load_cps_table11.py`. Remaining EPI data is nice-to-have, not actionable.

---

### TASK 8-8: Archive Low-Value Data Sources
**Source:** Codex identified specific candidates

**What to do:** Three data sources consume significant storage with minimal return:
1. **IRS BMF** — 2M rows, 491 MB, 8 active matches (unless Task 3-9 improves this)
2. **CorpWatch** — 1.4M rows, 3 GB, 3,177 active matches (keep for crosswalk, archive raw tables)
3. **Mergent** — 70K rows, 462 active matches (keep if research tool uses it, archive otherwise)

**Decision needed:** For each, either improve utilization or move to cold storage.

**How long:** 2-3 days
**Skills needed:** Database administration
**Dependencies:** Task 3-9 (BMF matching decision)

---

## MASTER OPEN QUESTIONS LIST

These are all unanswered questions from the audits, organized by topic. They should be investigated at the appropriate phase but are collected here for reference.

### Scoring & Architecture
1. Should the platform switch to the legacy variable-denominator formula entirely?
2. What are the empirically optimal pillar weights based on NLRB election outcomes?
3. Should "Leverage" be renamed if proximity and size are removed?
4. Is there a feedback loop between score improvements and user behavior?

### Data Quality
5. Full factor coverage breakdown by 2-digit NAICS code — which industries are best/worst covered?
6. Full factor coverage breakdown by state — which states are data deserts?
7. How accurate is ACS-based workforce estimation for individual employers?
8. Does CBP add meaningful information beyond what BLS already provides?
9. What about ABS — any use case for diversity metrics?

### Matching
10. What is the actual false positive rate for NAME_AGGRESSIVE_STATE matches? (Need empirical test, not documented estimate)
11. Is the Yale-New Haven Hospital #1 ranking legitimate, or based on a false positive match?
12. Can employers appear in both the union and target scorecards simultaneously?
13. How does the platform handle employer name changes, mergers, acquisitions?

### Research System
14. What's the actual accuracy of the research system against 20 known employers? (Benchmark test needed)
15. Should research target mid-tier employers instead of top-tier for maximum tier-change impact?
16. How much compute budget is available for batch research on 1,450 targets?
17a. Should new dossier sections (corporate structure, locations, leadership) affect the auto-grading coverage formula?
17b. Is email address extraction worth building, or is it low-value for labor organizing?
17c. What state/local procurement databases are available in machine-readable format? (NY, CA, IL, MA priority)
17d. Is there a viable source for private company assets/liabilities beyond Mergent and 990s?

### Union Data
17. How many intermediate bodies exist in the database? List the 20 largest.
18. How many of the 5,511 unions in ar_membership are identifiable as public sector?
19. Does the Union Explorer page actually provide a usable experience for large unions?

### Public Sector
20. Which of the 10 listed states have downloadable PERB data in what formats?
21. Can LM filings reliably identify public sector locals via text analysis? What accuracy?
22. Is FLRA data accessible for bulk download?
23. How many government entities are in the Census of Governments, and could it serve as a crosswalk?
24. Draft a FOIA request template for states without online PERB data.

### Platform Operations
25. Is there a deployment/staging environment, or is everything on production?
26. Who has server access?
27. What's the data refresh cadence? Who triggers it? Is it manual?
28. Has a backup restore ever been tested?

### Strategic & User Research (from Round 2 audits)
29. Does the "research briefing tool" framing match what organizers actually need? The two-layer model is based on published sources, not direct interviews. Show the platform to 2-3 real organizing directors and ask: "Is this useful? What's missing?"
30. Is there a third use case beyond "deep profiles" and "structural flags"? Organizers might also want: monitoring (track changes at employers on my watchlist), industry intelligence (what's happening across all hospitals in NJ?), or campaign tracking (where is organizing activity increasing?).
31. How do organizers currently do employer research, and how long does it take? If the current process takes 2 weeks of manual searching and the platform does it in 30 seconds, that's compelling even with imperfect data.
32. Should Industry Growth weight increase from 2x to 3x? (Decision D5) It's the second-strongest predictor at +9.6 pp, nearly as strong as NLRB. Increasing to 3x would concentrate scoring power in 3 factors at 3x weight.
33. Should Union Proximity weight decrease from 3x? (Decision D12) Zero predictive power (+0.0 pp), but may have strategic value (institutional support, experienced organizers nearby) that doesn't show up in win/loss statistics.
34. Can Indeed MCP connector provide employer-level job posting data for turnover flagging? Or is it limited to job search functionality?
35. Can Glassdoor/Indeed review data be accessed programmatically for "friction signals" (spike in 1-star reviews)? What are the terms of service?
36. Are H-1B/LCA filings useful as a hiring intent signal? DOL Foreign Labor Certification data is machine-readable. Sudden stop in filings + WARN notice could indicate major disruption. Skews toward tech/healthcare.

---

*Roadmap compiled from: ROUND_4_AUDIT_REPORT_CLAUDE_CODE.md, ROUND_4_AUDIT_REPORT_CODEX.md, ROUND_4_AUDIT_REPORT_GEMINI.md, ROUND_4_THREE_AUDIT_SYNTHESIS.md, plus merged items from UNIFIED_ROADMAP_FINAL_2026_02_26.md (Round 2 audits)*

*Last updated: 2026-03-11. Tasks 3-1, 5-2, 8-7 REMOVED (not actionable). Tasks 6-1, 6-2 marked DONE. ~50 of 59 tasks now complete.*
*Total tasks: 59 (3 removed) | Total open questions: 34 | Estimated timeline: 6+ months end-to-end*
