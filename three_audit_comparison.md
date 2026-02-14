# Three-Audit Comparison: Claude vs Gemini vs Codex
## Labor Relations Research Platform — February 14, 2026

---

## How to Read This Document

Three different AI systems (Claude Code, Gemini, and OpenAI Codex) each did a "blind" audit of the platform — meaning none of them saw each other's work. This document compares what they found. Think of it like getting three independent inspectors to look at a house: where they all agree, you can be very confident those issues are real. Where only one noticed something, it might be a unique insight — or it might be a stretch.

**Quick definitions for this document:**
- **"Orphaned rows"** = Data that points to records that no longer exist (like an address book entry for a building that got demolished — your note still says "go here" but there's nothing there)
- **"CORS"** = A security setting that controls which websites can talk to your system. Wide open = anyone on the internet can access it.
- **"Auth"** = Authentication — requiring people to log in before they can use the system
- **"Match rate"** = The percentage of records from one database that could be successfully linked to records in another database

---

## Part 1: Where All Three Agree (High Confidence These Are Real)

These are the issues that every single auditor independently flagged. When three separate reviewers find the same problems without talking to each other, you can trust these are genuine.

### 🔴 Security: The Platform Is Not Safe for Shared Use

**What's wrong:** The system currently lets anyone access it without logging in. There's a login system built in, but it's turned off by default. On top of that, any website anywhere in the world could potentially pull data from your system because the security gate (CORS) is wide open.

**Why all three flagged it:** This isn't a matter of opinion — it's a factual observation. All three looked at the same code and saw the same thing: authentication disabled, CORS unrestricted.

**What it means for you:** Right now, this only matters if you deploy the platform to a server. Since it runs on your local machine, no one else can reach it anyway. But the moment you want other organizers to use it, this becomes the first thing to fix.

| Auditor | How They Described It |
|---------|----------------------|
| **Claude** | Ranked it #5 and #6 on the priority list. Called it a "deployment blocker." |
| **Gemini** | Made it their #1 immediate priority. "Enable API Authentication immediately." |
| **Codex** | Made it their #1 critical issue. "Fail startup if no JWT secret in production." |

**Bottom line:** All three say: lock this down before anyone besides you uses it.

---

### 🔴 Password Exposed in Code

**What's wrong:** The database password (`Juniordog33!`) appears directly in at least one script file. Even though most of the system correctly reads the password from a secure configuration file, this one script has the actual password written out in the code.

**Why it matters (in plain terms):** Imagine you have a safe with a combination lock on it, and you've been careful to not share the combo — except you accidentally wrote it on a sticky note on page 47 of a notebook. If anyone ever sees that notebook, they know the combo. In code, this is even worse because version-tracking systems (like Git) remember every change forever. Even if you delete the password tomorrow, it's still in the history.

| Auditor | What They Found |
|---------|----------------|
| **Claude** | Found it in `nlrb_win_rates.py` line 9 AND in the audit prompt document itself. Ranked it Critical #2. Also noted ~259 scripts historically had broken password patterns. |
| **Gemini** | Did not specifically call out the exact file, but flagged the overall credential management pattern. |
| **Codex** | Found it in the same file plus noted 31+ scripts with questionable credential patterns. Listed the `.env` file exposure. |

**Bottom line:** Rotate (change) the password, remove it from the code, and set up a system so passwords are never stored in code files again.

---

### 🔴 The 50% Orphaned Data Problem

**What's wrong:** When the system links unions to employers, about half of those links (60,373 out of ~120,000) point to employer records that no longer exist. This happened because the system went through a cleanup process (deduplication — combining duplicate employer records into single clean records) but the links weren't updated to point to the new clean records.

**Why it matters (in plain terms):** Imagine you have a phone directory with 120,000 entries, but 60,000 of the phone numbers have been changed and no one updated the directory. If someone looks up a union and asks "which employers do they bargain with?", the system silently skips half the answers. It doesn't show an error — it just gives you an incomplete list. Every search, every score, every analysis is working with only half the real information.

| Auditor | How They Characterized It |
|---------|--------------------------|
| **Claude** | Called it "the single most damaging data quality issue." Ranked it #1 overall. Said it "immediately doubles effective coverage" once fixed. Estimated 4-6 hours to fix. |
| **Gemini** | Did NOT explicitly flag this specific issue in their findings. This is a significant miss. |
| **Codex** | Flagged it clearly: "50.38% orphan rate" and ranked it High priority (#2 in High tier). Suggested splitting the data into "current" and "historical" tables. Estimated 3-5 days. |

**Important disagreement:** Claude and Codex both caught this, but Gemini missed it entirely. Claude ranked it as THE top priority (#1), while Codex ranked it a tier below (High, not Critical). Claude's argument is that this corrupts every single data output the platform produces. Codex treated it more as a structural design issue. Claude's reasoning is stronger here — this should probably be the first thing to fix.

---

### 🟡 The Frontend Is a Maintenance Nightmare

**What's wrong:** The entire user interface — everything you see when you use the platform — lives in a single file that's nearly 10,000 lines long. That's like having an entire book with no chapters, no table of contents, and no page numbers. Any change to one part risks accidentally breaking something in another part.

| Auditor | Their Take |
|---------|-----------|
| **Claude** | 10,506 lines. 25+ global variables. 40+ silent error handlers. Ranked it Medium (#14). Called it "unmaintainable." |
| **Gemini** | Called it the "weakest part of the codebase" and "spaghetti code." Recommended a full rewrite in React. |
| **Codex** | 9,972 lines. Flagged hardcoded localhost URL, inline event handlers, accessibility gaps. Ranked it Medium (#1). |

**Bottom line:** All agree this needs to be broken up, but opinions differ on urgency. Claude and Codex say it works for now (Medium priority), while Gemini was more alarmed and wanted a quicker React migration. The practical reality: it works, but adding new features or fixing bugs in it is slow and risky.

---

### 🟡 Low Match Rates Are Limiting the Platform's Power

**What's wrong:** When the platform tries to link OSHA safety records to employer records, it only succeeds about 14% of the time. For wage theft cases (WHD), it's about 7%. For IRS nonprofit data, about 2.4%.

**Why it matters (in plain terms):** The platform's strength is connecting information from different sources. If you can look up an employer and see their safety violations, wage theft history, union elections, AND government contracts all in one place — that's incredibly powerful. But if 86% of OSHA records can't be matched to an employer, you're missing most of the picture.

**Important context all three noted:** These rates are actually much BETTER than they were a few days earlier (OSHA went from 7.9% to 13.7% — a 74% improvement). And the low rates are partly structural — OSHA tracks over a million workplaces, but only about 61,000 are unionized employers. You'll never get to 100%.

| Auditor | Their Stance |
|---------|-------------|
| **Claude** | Noted improvement but said 86% unmatched is still a problem. Recommended quality gates and human review workflows. |
| **Gemini** | Most optimistic. Called the improvement "fantastic" and recommended continuing current strategies plus elevating the use of Splink (a statistical matching tool). Suggested targeting 25% OSHA match rate. |
| **Codex** | Most measured. Noted the rates are real improvements. Focused on making confidence levels visible to users rather than just raising rates. |

---

### 🟡 No Tests for the Most Important Code

**What's wrong:** The system has 47 automated tests that check whether things work, which is good. But there are zero tests for the matching pipeline (the code that links records across databases) and zero tests for the scoring system (the code that rates employers as organizing targets). These are arguably the two most important pieces of the whole platform.

| Auditor | Their Take |
|---------|-----------|
| **Claude** | Called it a major gap. "The platform's core value (entity matching) has zero automated tests." |
| **Gemini** | Same assessment. "The core matching logic is not unit-tested." |
| **Codex** | Same finding. "Limited unit-level safeguards for match precision/recall regressions." |

**What this means practically:** If someone makes a change to the matching code and accidentally introduces a bug, there's nothing to catch it automatically. The bad matches would silently flow into the rest of the system.

---

### 🟡 README Has the Wrong Startup Command

**What's wrong:** The README file (the first thing any new person reads) tells you to start the system using a command that doesn't work. The file it references doesn't exist anymore.

| Auditor | Priority |
|---------|---------|
| **Claude** | Critical #4 (easy fix, first-impression killer) |
| **Gemini** | Not explicitly called out as a standalone finding |
| **Codex** | Noted under project organization risks |

**Bottom line:** A 5-minute fix that everyone noticed.

---

## Part 2: Where They Disagree

### Priority Ranking Philosophy

The three auditors structured their priorities quite differently, and this matters because it tells you which lens they were looking through:

**Claude's approach: "Fix what hurts the data first"**
- Made the orphaned data problem #1 because it affects every output
- Ranked security issues #2-4 because no one else currently uses the system
- Most detailed and specific (32 ranked items with time estimates)

**Gemini's approach: "Get ready for real users"**
- Made security and deployment readiness #1 because they were thinking about the next phase
- Focused heavily on long-term architecture decisions (React, Redis, Terraform, MLOps)
- Most forward-looking and strategic

**Codex's approach: "Reduce risk systematically"**
- Led with security but also emphasized the "silent analytical errors" from orphaned data
- Most focused on the category of "things that can go wrong quietly without anyone noticing"
- Unique focus on dynamic SQL construction risks across many files

### The SQL Safety Debate

This is an interesting area where the auditors had genuinely different assessments:

| Auditor | Assessment |
|---------|-----------|
| **Claude** | "SQL injection is effectively mitigated. 99%+ of queries use parameterized statements." Said the current approach is safe. |
| **Gemini** | Called the current f-string SQL approach "safe-but-fragile" and "a code smell." Recommended switching to SQLAlchemy Core. |
| **Codex** | Most concerned. Listed "dynamic SQL assembly" as their #1 High priority. Found interpolated SQL fragments across many router files. Called it "fragile and hard to audit." |

**What this means in plain terms:** Think of it like a kitchen knife. Claude says "the knife is being used safely right now." Gemini says "it works, but you should switch to a safer tool eventually." Codex says "there are a lot of knives lying around in places where someone could get hurt, and you should clean this up soon."

The truth is probably in the middle — the system isn't actively vulnerable right now (Claude's point), but the coding pattern makes it easy for a future developer to accidentally create a vulnerability (Codex's point).

### Frontend Strategy

| Auditor | Recommendation |
|---------|---------------|
| **Claude** | Break it up into components (React or Vue). 2-3 weeks. Medium priority. |
| **Gemini** | Full React rewrite with Material-UI component library, Redux state management, and the "Strangler Fig" gradual migration pattern. Most ambitious recommendation. |
| **Codex** | Split into modules first, keep it as generated HTML output. Most pragmatic / least disruptive. |

**What this means for you:** Gemini is recommending a major rebuild with lots of new technologies. Claude suggests a moderate overhaul. Codex says just organize what you have better. Given that you're a one-person team and the frontend works, Codex's approach is probably the most realistic short-term, with Claude's approach as the medium-term target.

---

## Part 3: Unique Catches (Only One Auditor Found It)

### Only Claude Found:

1. **`LIMIT 500` pre-filter bug in scoring** — When the system calculates organizing scores, it first grabs 500 employers from the database (sorted by violations), then scores those 500. But an employer with a mediocre violation count but excellent scores on other factors (union presence, industry density, etc.) would never get evaluated. The system is essentially looking at the "top 500 by one measure" instead of "top 500 overall." This is a significant analytical flaw that could cause organizers to miss good targets.

2. **Rate limiter memory leak** — The system tracks which internet addresses have made requests, but never cleans up old entries. Over days or weeks of running, this list grows forever and slowly eats up memory.

3. **Building trades over-count by 10-32x** — F7 reports count "covered workers" (everyone working under a union contract on a project), while LM2 reports count dues-paying members. This makes building trade numbers wildly inflated. USW shows 32x, Pipe Fitters 29x, IATSE 27x. The platform displays these numbers without explaining this huge caveat.

4. **GLEIF data ROI problem** — One dataset (GLEIF, which tracks global corporate identities) takes up 10.6 GB — over HALF the entire database — but only produced 605 matches. That's an enormous amount of storage for very little value.

5. **Scorecard ceiling for unmatched employers** — 86% of OSHA establishments can't be linked to union data, so they automatically lose points on several scoring factors. This means most scores get squeezed into a narrow range (0-50 out of 100), making the scoring tiers less meaningful.

6. **Two separate scoring systems that aren't unified** — There's an OSHA scorecard (0-100) and a Mergent sector scorecard (0-62). An organizer seeing a score of "45" has no way to know which system generated it.

### Only Gemini Found:

1. **FMCS Contract Expiration Data as highest priority new data source** — Gemini specifically identified the Federal Mediation and Conciliation Service data (which tracks when union contracts expire) as the single most valuable data source not yet in the platform. When a contract is about to expire, that's a critical moment for organizing campaigns.

2. **OpenSecrets.org API as alternative to raw FEC data** — Instead of processing raw federal election contribution data (which is messy), Gemini suggested using the pre-cleaned OpenSecrets.org API.

3. **News and media monitoring elevated in priority** — Gemini thought real-time news alerts about strikes, layoffs, etc. should be moved up from the "post-launch" wish list to a medium-term priority.

4. **MLOps practices for predictive modeling** — Gemini was the only auditor to discuss experiment tracking (MLflow), model registries, and model monitoring — the infrastructure you'd need to run machine learning models in a serious way.

5. **Splink as central matching strategy** — Gemini specifically recommended making Splink (a statistical matching library already partially used) the primary matching approach for ALL data sources, rather than the current tier-based system.

6. **Database migration tool (Alembic/Flyway)** — Gemini noted that there's no system for managing database structure changes over time. When you add a new table or column, there's no record of what changed and no way to reproduce those changes on another copy of the database.

### Only Codex Found:

1. **6 foreign keys without supporting indexes** — Codex identified specific database columns that have relationship constraints but no indexes to make lookups fast. As the database grows, these will cause slowdowns. (Think of it like a library book that's catalogued but the catalog isn't organized — you know the book exists but finding it takes forever.)

2. **Frontend hardcoded to localhost** — The web interface has `http://localhost:8001/api` written directly in the code. This means if you ever deploy the system to a server, you'd have to manually change this. Codex recommended making this configurable.

3. **Score model versioning** — Codex was the only one to recommend storing a "version number" with each scoring run, so you could track how scores change as the methodology evolves. This is important for trust — if an organizer sees a score change, they need to know whether it's because the data changed or because the formula changed.

4. **Orphan solution: split into current vs. historical** — While Claude recommended fixing the orphaned data by re-linking it, Codex suggested a different structural approach: splitting the union-employer relationship table into "current relationships" and "historical relationships" so that queries always know which era of data they're looking at.

5. **"Evidence packet" export concept** — Codex specifically described an organizer workflow feature where you could generate a printable bundle of all the evidence about a target employer (safety record, wage theft history, election results, comparable employers) as a single downloadable package for campaign use.

---

## Part 4: Methodology Comparison

How each auditor did their work reveals something about the reliability of their findings:

| Aspect | Claude | Gemini | Codex |
|--------|--------|--------|-------|
| **Approach** | Launched 5 parallel specialized agents + read critical files directly | Sequential document review → code → database | Systematic file-by-file inventory with targeted deep dives |
| **Database validation** | Ran live SQL queries. Verified orphan counts, index usage, table sizes. | Tried `psql`, failed, wrote a custom Python script instead. Verified match rates. | Ran live SQL queries. Verified counts, orphans, FK indexes, constraints. |
| **Time** | ~53 minutes | Not reported | Not reported |
| **Total findings** | 32 ranked items | ~25 recommendations across 12 sections | ~20 findings in 4 priority tiers |
| **Live verification** | Yes — ran queries to verify orphan counts, index stats | Yes — wrote scripts to verify match rates | Yes — ran pytest (47 passed), ran multiple DB queries |
| **Strengths** | Most specific and detailed. Caught subtle analytical bugs (LIMIT 500, scoring ceiling). Strongest union-use perspective. | Best strategic/architectural vision. Most forward-looking. Best on new data sources and ML infrastructure. | Most security-focused. Best on systematic risk reduction. Most concise and actionable format. |
| **Weaknesses** | May over-weight technical debt relative to working features | Missed the orphaned data problem entirely. Some recommendations assume a larger team/budget. | Fewer unique analytical insights. Less detail on union usability. |

---

## Part 5: Unified Priority List

Combining all three audits into a single action plan, weighting issues by how many auditors flagged them and the severity of the impact:

### 🔴 CRITICAL — Do These First

| # | Issue | Flagged By | Why First | Estimated Effort |
|---|-------|-----------|-----------|-----------------|
| 1 | **Fix the 60,373 orphaned union-employer links** | Claude ✅ Codex ✅ | Every query, score, and search is working at 50% capacity. This is the highest-impact single fix possible. | 4-6 hours (Claude) to 3-5 days (Codex, if restructuring) |
| 2 | **Rotate database password and remove from code** | Claude ✅ Codex ✅ | The password is permanently in the code history. Must be changed. | 2 hours |
| 3 | **Enable authentication before any shared deployment** | Claude ✅ Gemini ✅ Codex ✅ | All three agree: the system is wide open. Non-negotiable before anyone else uses it. | 1-2 days |
| 4 | **Restrict CORS to specific domains** | Claude ✅ Gemini ✅ Codex ✅ | All three agree: this is a basic security gate that's currently missing. | 30 minutes |
| 5 | **Fix README startup command** | Claude ✅ Codex ✅ | 5-minute fix. First thing that breaks for any new person. | 5 minutes |

### 🟠 HIGH — Do Before Anyone Else Uses It

| # | Issue | Flagged By | Why Important | Estimated Effort |
|---|-------|-----------|--------------|-----------------|
| 6 | **Create requirements.txt** (list of software dependencies) | Claude ✅ | Without this, nobody else can set up the system. It's like having a recipe without an ingredients list. | 1 hour |
| 7 | **Fix the LIMIT 500 scoring pre-filter** | Claude ✅ | Organizers are potentially missing good targets because the system evaluates the wrong 500 employers. | 4 hours |
| 8 | **Cache scorecard results** (stop recalculating from scratch every time) | Claude ✅ | The system currently reloads 138,000 records into memory every time someone views a scorecard. Slow and wasteful. | 4-8 hours |
| 9 | **Fix 4 broken corporate endpoints** | Claude ✅ | These API pages return errors because they reference tables that don't exist. | 1-2 hours |
| 10 | **Sanitize error messages in auth system** | Claude ✅ Codex ✅ | Currently leaks internal technical details to anyone who sends a bad login request. | 15 minutes |
| 11 | **Externalize frontend API URL** | Codex ✅ | The web interface is hardcoded to `localhost` — must be configurable for deployment. | Less than 1 day |
| 12 | **Add missing database indexes for foreign keys** | Codex ✅ | 6 relationship columns without supporting indexes. Will slow down as data grows. | Less than 1 day |
| 13 | **Address dynamic SQL patterns across routers** | Codex ✅ Gemini ✅ | Multiple files construct database queries in a way that's technically safe today but fragile for the future. | 4-7 days |

### 🟡 MEDIUM — Plan for Next Development Cycle

| # | Issue | Flagged By | What It Improves | Estimated Effort |
|---|-------|-----------|-----------------|-----------------|
| 14 | **Add geocoding to OSHA establishments** | Claude ✅ | The map feature is essentially empty without location coordinates. This makes territory mode actually useful. | 2-3 days |
| 15 | **Break up the frontend file** | Claude ✅ Gemini ✅ Codex ✅ | All three agree it needs to be split up. Disagreement is on how aggressively. | 1-3 weeks |
| 16 | **Add data freshness tracking** | Claude ✅ | Show when each data source was last updated. Organizers need to know if they're looking at data from 2025 or 2018. | 2 hours |
| 17 | **Add unit tests for matching pipeline** | Claude ✅ Gemini ✅ Codex ✅ | All three agree: the most important code in the system has zero automated tests. | 1-2 days |
| 18 | **Add unit tests for scoring engine** | Claude ✅ Gemini ✅ Codex ✅ | Same issue as above — the scoring logic has no tests. | 1 day |
| 19 | **Add score model versioning** | Codex ✅ | Track which version of the scoring formula produced each score, so changes can be audited. | 3-5 days |
| 20 | **Integrate FMCS contract expiration data** | Gemini ✅ | The single most valuable new data source identified. When contracts expire, that's a key organizing moment. | Not estimated |
| 21 | **Integrate ULP (Unfair Labor Practice) data** | Claude ✅ | Every organizer needs to know which employers retaliate against organizing. This is the #1 missing dataset for field use. | 3-5 days |
| 22 | **Add plain-language score explanations** | Claude ✅ | Don't just show "42/100" — explain WHY. "High safety violations, growing industry, similar employers organized successfully." | 1-2 days |
| 23 | **Document the F7 public-sector blind spot in the UI** | Claude ✅ | 5.4 million union members (teachers, postal workers, etc.) are invisible to the platform. Organizers should know this. | 1 hour |
| 24 | **Drop unused database indexes** | Claude ✅ | 319 indexes are never used. They waste 2.6 GB of space and slow down data updates. | 2-4 hours |
| 25 | **Clean up 785 scripts** | Claude ✅ Codex ✅ | Organize scripts into active/legacy/archive so new people can find what matters. | 2-3 days |

### 🟢 LOW — When Time Allows

| # | Issue | Flagged By | Notes |
|---|-------|-----------|-------|
| 26 | Accessibility compliance (WCAG) | Claude ✅ Codex ✅ | No screen reader support, no keyboard navigation. |
| 27 | Mobile responsive design | Claude ✅ Gemini ✅ Codex ✅ | Organizers are on phones in the field. |
| 28 | Archive or remove GLEIF data (10.6 GB for 605 matches) | Claude ✅ | Half the database for almost no value. |
| 29 | Set up CI/CD pipeline (automated testing) | Claude ✅ Gemini ✅ | Run tests automatically whenever code changes. |
| 30 | Create Docker deployment setup | Claude ✅ Gemini ✅ | Needed for deploying to any server. |
| 31 | Temporal scoring decay (recent violations weighted more) | Claude ✅ | A violation from 2010 should matter less than one from 2025. |
| 32 | API versioning | Claude ✅ Gemini ✅ | Prevents breaking changes from affecting all users at once. |
| 33 | Replace in-memory rate limiter with Redis-based one | Gemini ✅ Codex ✅ | Current approach won't work if multiple copies of the system are running. |
| 34 | Database migration tooling (Alembic) | Gemini ✅ | Track and reproduce database structure changes over time. |
| 35 | Predictive model development (replace heuristic scoring) | Gemini ✅ | Long-term: use machine learning to identify targets instead of hand-tuned rules. |

---

## Part 6: Key Takeaways

### The Three Auditors Paint a Consistent Picture

Despite different methodologies and perspectives, they broadly agree:

1. **The data foundation is impressive and real.** 14.5 million deduplicated union members, validated within 1.4% of federal benchmarks. This is not a toy project — it's a genuinely novel research capability.

2. **The platform is a working prototype, not a production system.** It works well for a single researcher on a local machine. It is NOT ready for multiple users on a shared server.

3. **The single highest-impact fix is the orphaned data problem.** Fixing those 60,373 broken links would immediately improve every output the platform produces. (Gemini missed this, which is notable.)

4. **Security must be addressed before sharing.** All three agree: enable login, restrict access, change the password.

5. **The matching pipeline and scoring system need automated tests.** These are the intellectual core of the platform and they have zero safety nets.

6. **The frontend works but is fragile.** Breaking it up is important but not urgent.

### Where to Spend Your Time

If you had one week of focused work, based on all three audits combined:

- **Day 1:** Fix orphaned relations, rotate password, fix README (Critical items 1, 2, 5)
- **Day 2:** Enable auth, restrict CORS, create requirements.txt (Critical items 3, 4, 6)
- **Day 3:** Fix LIMIT 500 scoring bug, cache scorecard results (High items 7, 8)
- **Day 4:** Add data freshness tracking, fix broken endpoints, externalize frontend URL (items 9, 11, 16)
- **Day 5:** Start writing tests for matching pipeline and scoring engine (items 17, 18)

That one week would resolve every Critical and most High items identified across all three audits.
