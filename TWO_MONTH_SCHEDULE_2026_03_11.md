# Two-Month Improvement Schedule
## March 11 - May 11, 2026

**Created:** 2026-03-11
**Supersedes:** Nothing — this is a scheduling layer on top of `COMPLETE_PROJECT_ROADMAP_2026_03.md`

---

## How This Schedule Works

- **8 weeks**, organized into 4 two-week sprints
- Tasks are categorized: **Session work** (things done in Claude Code sessions), **Parallel tracks** (long-running projects with their own roadmaps), **Decisions** (things that need investigation then a call), and **One-time events** (audits, reviews)
- Open questions from the master roadmap are matched to the tasks they belong to
- Items marked with `[ROADMAP NEEDED]` require a dedicated planning document before execution begins

---

## Sprint 1: Foundations (March 11 - March 24)

### Session Work
| Task | Est. | Notes |
|------|------|-------|
| **Task 2-5: Fix Documentation Contradictions** | 1-2 sessions | Do in the next couple sessions. 7 of 8 contradictions remain. |
| **Task R3-1: Collapse Failed/Empty Tool Calls** | 1 session | High-ROI UX fix for research page. Quick win. |
| **Task 3-13: Finish Blended Demographics** | ~1 week remaining | Fix HISPAN/EDUC bugs, load LODES OD, build labor shed function, wire API. |
| **Task 2-6: Set Up Weekly Doc Reconciliation** | 1 session (after 2-5) | Once 2-5 is done, run `check_doc_consistency.py` weekly. This IS the quarterly check — just run it weekly instead. |

### Decisions to Make
| Decision | Context |
|----------|---------|
| **Task 8-4: Employer Website Scraper usefulness** | Is this going in the research agent? What are the actual use cases? Decide before building anything. |
| **Task 8-5: CPS Microdata importance** | Why is this important? Might be useful, might not. Quick investigation to decide keep/cut. |

### Planning Work
| Item | Output |
|------|--------|
| **Task 4-9: Gold Standard Dossier Roadmap** | Create a plan to build 20 known-employer gold standard dossiers. Select the 20 employers, define ground truth sources, design the benchmark scoring methodology. `[ROADMAP NEEDED]` |

### Open Questions (Sprint 1)
- OQ #7: How accurate is ACS-based workforce estimation? *(answers inform Task 3-13)*
- OQ #8: Does CBP add meaningful info beyond BLS? *(investigate during 3-13 work)*
- OQ R3-4: How should the dossier present "Verified None" vs "Not Searched"? *(decide during R3-1)*

---

## Sprint 2: Research Quality + Parallel Track Kickoff (March 25 - April 7)

### Session Work
| Task | Est. | Notes |
|------|------|-------|
| **Task 4-9: Begin Gold Standard Dossiers** | 2-3 sessions | Execute the roadmap from Sprint 1. Run research agent on 20 employers, compare to ground truth. Essential before finishing the research agent. |
| **Task 7-3: Investigate Missing 138 File Numbers** | 1 session | Sort by worker count, look up top 20 on OLMS. Decide if remainder is fixable or should be marked historical. |
| **Task 7-7: Union Explorer Cleanup (Phase 1)** | 2-3 sessions | Membership dedup audit, ensure NHQ membership is authoritative source everywhere. Manual checks on 5 large affiliations. |

### Parallel Tracks Launched
| Track | Deliverable |
|-------|-------------|
| **Task 8-1: SEC EDGAR + Mergent Full Load** | Write the full roadmap. Two independent workstreams: (A) SEC XBRL parsing for employee counts, pay ratios, subsidiaries; (B) Mergent full load from 56K to 1.75M rows. `[ROADMAP NEEDED]` |
| **Task 8-2: CBA Database Scaling** | Write the full roadmap. This is nearly a separate project — contract sourcing, PDF extraction at scale, provision taxonomy expansion. Runs in parallel with everything else. `[ROADMAP NEEDED]` |
| **Mergent Intellect Continued Pull** | Continue pulling remaining ~1.32M records (400K of 1.72M done). Provides DUNS, EIN, hierarchy, depth for targets. Long-running background task. |

### Reviews
| Item | Purpose |
|------|---------|
| **Task 8-3: Review Union Scraper Roadmap** | `UNION_SCRAPER_UPGRADE_ROADMAP.md` exists. Review it, assess how useful the tiered extraction upgrade actually is, decide whether to proceed or cut. |

### Decisions to Make
| Decision | Context |
|----------|---------|
| **Task 7-3 verdict** | After investigating: are the 138 missing file numbers fixable, or mark them historical? |
| **Task 8-3 verdict** | Keep, modify, or shelve the union scraper upgrade? |
| **Task 8-4 verdict** | Based on Sprint 1 analysis: build it, shelve it, or fold into research agent? |
| **Task 8-5 verdict** | Keep or cut CPS microdata task? |

### Open Questions (Sprint 2)
- OQ #14: What's the actual research agent accuracy against 20 known employers? *(Task 4-9 answers this directly)*
- OQ #15: Should research target mid-tier employers? *(informs 4-9 employer selection)*
- OQ #17a-d: Research system open questions *(all inform 4-9 design)*
- OQ #17-19 (Union Data): intermediate body count, public sector identification, Explorer UX *(Task 7-7)*
- OQ #3: Are there duplicate unions? *(Task 7-7 dedup audit)*

---

## Sprint 3: State/Local Expansion + Deep Integration (April 8 - April 21)

### Session Work
| Task | Est. | Notes |
|------|------|-------|
| **Task 4-9: Complete Gold Standard Benchmark** | Wrap up | Finalize accuracy report. Feed results back into research agent improvements. |
| **Task 7-2: Resolve CWA District 7** | 1 session | Manual research: which CWA local covers AT&T Mobility Birmingham? Then the other 41 employers. |
| **Task 7-7: Union Explorer Cleanup (Phase 2)** | 1-2 sessions | Tree UX for large unions, search results accuracy, national summary card logic. |
| **Task 8-8: Archive Low-Value Data Sources** | 1 session | Decide on BMF (2M rows, 8 matches), CorpWatch (1.4M rows), Mergent partial (70K rows). Archive or improve. |

### Major Planning
| Item | Output |
|------|--------|
| **Phase 5: State & Local Data Expansion Roadmap** | This is bigger than any single task. Create a full roadmap covering: (1) State and local government contracts collection — which states, what formats, how to ingest; (2) PERB feasibility — research the 10 listed states for data format/accessibility, make go/no-go decision; (3) State OSHA plan data (Task 5-6); (4) State wage theft agencies (Task 5-7); (5) Integration of existing ps_* tables (Task 5-5). `[ROADMAP NEEDED]` |

### One-Time Event
| Event | Scope |
|-------|-------|
| **Multi-AI Full Code Audit** | Full audit of: codebase functions, all documents, document index completeness, test coverage gaps, dead code, stale references. Use Claude Code + Codex + Gemini. Produce consolidated findings report. Schedule across multiple sessions. |

### Parallel Tracks (Continuing)
- **Task 8-1** execution begins (per its roadmap)
- **Task 8-2** execution begins (per its roadmap, separate project)
- **Mergent Intellect** pull continues

### Open Questions (Sprint 3)
- OQ #20-24 (Public Sector): PERB data formats, FLRA access, Census of Governments, FOIA templates *(all feed Phase 5 roadmap)*
- OQ #5-6: Coverage breakdown by NAICS and state *(multi-AI audit should produce these)*
- OQ #25-28 (Platform Ops): deployment env, access control, refresh cadence, backup testing *(audit scope)*
- OQ #10: Actual FP rate for aggressive matches *(audit scope — matching quality)*
- OQ #11: Is Yale-New Haven #1 legitimate? *(audit scope)*
- OQ #12: Can employers appear in both scorecards? *(audit scope)*
- OQ #13: How does platform handle M&A? *(audit scope)*

---

## Sprint 4: Launch Prep + Convergence (April 22 - May 11)

### Session Work
| Task | Est. | Notes |
|------|------|-------|
| **Task 2-11: Launch Strategy Decision** | 1-2 sessions | Deferred until here (~2 weeks from end). Choose: beta with friendly users, read-only research mode, or full launch with confidence indicators. |
| **Task 2-2: Leverage Pillar Composition** | Deferred | Waiting on full matching rebuild. If rebuild happens by now, zero proximity/size sub-weights and redistribute. Otherwise stays deferred. |
| **Phase 5 execution begins** | Per roadmap | Start with highest-value state/local data sources identified in Sprint 3 roadmap. |

### Parallel Tracks (Continuing)
- **Task 8-1** SEC EDGAR + Mergent full load (ongoing per roadmap)
- **Task 8-2** CBA pipeline scaling (ongoing, separate project)
- **Mergent Intellect** pull finishing (~1.72M target)
- **Phase 5** state/local contracts collection ramping up

### Wrap-Up Reviews
| Item | Purpose |
|------|---------|
| **Research Agent Roadmap status check** | With Task 4-9 complete and accuracy known, update `RESEARCH_AGENT_ROADMAP.md` with next priorities. |
| **Score change report** | Run full MV rebuild with `--with-report` to baseline everything before any launch. |
| **Document reconciliation** | Final weekly run of Task 2-6 checks. All docs should be consistent. |

### Open Questions (Sprint 4)
- OQ #1-4 (Scoring): Legacy formula switch, pillar weights, Leverage rename, feedback loops *(inform Task 2-11 launch decision)*
- OQ #29-36 (Strategic): Organizer interviews, use cases, weight decisions, Indeed/Glassdoor, H-1B *(inform launch strategy)*
- OQ #16: Compute budget for batch research *(must answer before scaling research)*
- OQ #32-33: Industry Growth and Union Proximity weight changes *(D5/D12 decisions, inform launch)*

---

## Parallel Tracks Summary

These run across the full 2 months with their own roadmaps:

| Track | Start | Duration | Status |
|-------|-------|----------|--------|
| **Mergent Intellect Pull** | Already running | Ongoing | 400K of 1.72M done. Provides DUNS, EIN, hierarchy for targets. |
| **Task 8-1: SEC EDGAR + Mergent Full Load** | Sprint 2 (roadmap), Sprint 3 (execution) | 3-4 weeks | `[ROADMAP NEEDED]` — SEC XBRL parsing + Mergent bulk load are independent workstreams. |
| **Task 8-2: CBA Database** | Sprint 2 (roadmap), Sprint 3 (execution) | 3-6 months total | `[ROADMAP NEEDED]` — Nearly separate project. Contract sourcing, PDF extraction, taxonomy. |
| **Task 8-3: Union Web Scraper** | Sprint 2 (review) | TBD | Has existing roadmap (`UNION_SCRAPER_UPGRADE_ROADMAP.md`). Review for usefulness first. |
| **Phase 5: State/Local Expansion** | Sprint 3 (roadmap), Sprint 4 (execution) | Months | `[ROADMAP NEEDED]` — Contracts, PERB, state OSHA, wage theft agencies. |
| **Multi-AI Code Audit** | Sprint 3 | 1-2 weeks | Full codebase + documentation audit. |

---

## Deferred / End-of-Timeline Items

| Item | When | Condition |
|------|------|-----------|
| **Task 2-2: Leverage Pillar** | After matching rebuild | Blocked on full matching pipeline rebuild. |
| **Task 2-11: Launch Strategy** | Sprint 4 (2 weeks from end) | Intentionally deferred. |
| **Task 8-6: News Monitoring** | With deployment | Last feature to integrate. Figure out same time as deployment planning. |

---

## Roadmaps Needed (Deliverables)

These planning documents must be created before their associated work begins:

1. **Gold Standard Dossier Plan** (Sprint 1) — 20 employer selection, ground truth methodology, benchmark scoring
2. **SEC EDGAR + Mergent Full Load Roadmap** (Sprint 2) — Two workstreams: XBRL parsing + bulk ETL
3. **CBA Database Scaling Roadmap** (Sprint 2) — Contract sourcing strategy, extraction pipeline, taxonomy expansion
4. **Phase 5: State & Local Data Expansion Roadmap** (Sprint 3) — Contracts collection, PERB feasibility, state OSHA, wage theft, ps_* integration

---

## Open Questions Index

All 36 open questions from the master roadmap, matched to the task/sprint where they should be answered:

### Answered by Specific Tasks
| OQ | Question | Answered By |
|----|----------|-------------|
| 7 | How accurate is ACS-based workforce estimation? | Task 3-13 (Sprint 1) |
| 14 | Research agent accuracy against 20 known employers? | Task 4-9 (Sprint 2-3) |
| 15 | Should research target mid-tier employers? | Task 4-9 design (Sprint 2) |
| 17a | Should new dossier sections affect grading formula? | Task 4-9 / R3-1 (Sprint 1-2) |
| 17-19 | Union intermediate bodies, public sector IDs, Explorer UX | Task 7-7 (Sprint 2-3) |
| 3 (union) | Duplicate unions in database? | Task 7-7 dedup audit (Sprint 2) |
| 20-24 | PERB formats, FLRA, Census of Govts, FOIA | Phase 5 roadmap (Sprint 3) |

### Answered by Multi-AI Audit (Sprint 3)
| OQ | Question |
|----|----------|
| 5 | Coverage breakdown by 2-digit NAICS |
| 6 | Coverage breakdown by state |
| 10 | Actual FP rate for aggressive matches |
| 11 | Is Yale-New Haven #1 legitimate? |
| 12 | Can employers appear in both scorecards? |
| 13 | How does platform handle M&A? |
| 25 | Deployment/staging environment? |
| 26 | Who has server access? |
| 27 | Data refresh cadence? |
| 28 | Has backup restore been tested? |

### Inform Launch Decision (Sprint 4)
| OQ | Question |
|----|----------|
| 1 | Switch to legacy variable-denominator formula? |
| 2 | Rename Leverage pillar? |
| 4 | Feedback loop between scores and user behavior? |
| 16 | Compute budget for batch research? |
| 29 | Does "research briefing tool" match organizer needs? |
| 30 | Third use case beyond profiles and flags? |
| 31 | How do organizers currently do research? |
| 32 | Industry Growth weight increase to 3x? (D5) |
| 33 | Union Proximity weight decrease? (D12) |
| 34-36 | Indeed MCP, Glassdoor/Indeed reviews, H-1B signals |

### Answered During Investigation/Decision Tasks
| OQ | Question | When |
|----|----------|------|
| 8 | Does CBP add meaningful info? | Sprint 1 (3-13 work) |
| 9 | ABS diversity metrics use case? | Sprint 1 decision |
| 17b | Email extraction worth building? | Sprint 1 (8-4 decision) |
| 17c | State/local procurement DBs available? | Phase 5 roadmap (Sprint 3) |
| 17d | Private company assets source? | Task 8-1 roadmap (Sprint 2) |
| R3 Q1 | Email extraction worth effort? | Sprint 1 (8-4 decision) |
| R3 Q2 | Private company financial sources? | Task 8-1 (Sprint 2) |
| R3 Q3 | Occupation-level growth data source? | Task 3-13 / 8-5 (Sprint 1) |
| R3 Q5 | New sections affect grading? | Task 4-9 (Sprint 2) |

---

## Weekly Rhythm

Once Task 2-5 is done and Task 2-6 is active:

- **Every session:** Work on the current sprint's session tasks
- **Weekly:** Run doc reconciliation check (`check_doc_consistency.py`)
- **Background:** Mergent Intellect pull continues; parallel track roadmaps execute independently
- **End of each sprint:** Review progress, adjust next sprint if needed
