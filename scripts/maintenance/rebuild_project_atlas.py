#!/usr/bin/env python
"""Rebuild the Project Atlas dashboard.

Reads the authoritative roadmap at
  C:\\Users\\jakew\\LaborDataTerminal\\LaborDataTerminal_real\\MERGED_ROADMAP_2026_04_07.md
plus PROJECT_STATE.md and MEMORY.md for current-status evidence, then
merges with the existing history state and writes:
  - project_atlas_state.json  (append-only task ledger, never deletes)
  - project_atlas.html        (self-contained interactive dashboard)

Run manually:
    py scripts/maintenance/rebuild_project_atlas.py

Called automatically from the `/wrapup` skill (Part E).
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

# --- Paths -------------------------------------------------------------------

VAULT = Path(r"C:\Users\jakew\LaborDataTerminal\LaborDataTerminal_real")
ROADMAP_MD = VAULT / "MERGED_ROADMAP_2026_04_07.md"
PROJECT_STATE_MD = Path(
    r"C:\Users\jakew\.local\bin\Labor Data Project_real\Start each AI\PROJECT_STATE.md"
)
MEMORY_MD = Path(
    r"C:\Users\jakew\.claude\projects\C--Users-jakew-LaborDataTerminal-LaborDataTerminal-real\memory\MEMORY.md"
)
ATLAS_HTML = VAULT / "project_atlas.html"
ATLAS_JSON = VAULT / "project_atlas_state.json"

# --- Tier / status metadata --------------------------------------------------

TIER_ORDER = ["P0", "P1", "P2", "T1", "T2", "T3", "D"]
TIER_LABELS = {
    "P0": "P0 - Fix What's Broken",
    "P1": "P1 - Trust & Polish",
    "P2": "P2 - Doc & Context Debt",
    "T1": "Tier 1 - Must Happen Before Launch",
    "T2": "Tier 2 - Can Wait",
    "T3": "Tier 3 - Horizon",
    "D":  "Open Decisions",
}
STATUS_ORDER = ["done", "partial", "open", "deferred", "blocked", "archived", "unknown"]

# Manual status overrides observed from recent session summaries
# (evidence beyond what the roadmap table literally shows).
# Keys are task IDs as they appear in the roadmap (#1-#89 for numbered rows).
# P0/P1/P2 tables lack a status column so every numbered row needs an override.
STATUS_OVERRIDES: dict[str, tuple[str, str]] = {
    # --- P0: all 27 fixed (P0 Bug Sweep done, see session_2026_04_08 + 2026_04_14) ---
    "#1":  ("done", "2026-04-08"),
    "#2":  ("done", "2026-04-08"),
    "#3":  ("done", "2026-04-08"),
    "#4":  ("done", "2026-04-08"),
    "#5":  ("done", "2026-04-08"),
    "#6":  ("done", "2026-04-08"),
    "#7":  ("done", "2026-04-08"),
    "#8":  ("done", "2026-04-08"),
    "#9":  ("done", "2026-04-08"),
    "#10": ("done", "2026-04-08"),
    "#11": ("done", "2026-04-08"),
    "#12": ("done", "2026-04-08"),
    "#13": ("done", "2026-04-08"),
    "#14": ("done", "2026-04-08"),
    "#15": ("done", "2026-04-08"),
    "#16": ("done", "2026-04-08"),
    "#17": ("done", "2026-04-08"),
    "#18": ("done", "2026-04-08"),
    "#19": ("done", "2026-04-08"),
    "#20": ("done", "2026-04-08"),
    "#21": ("done", "2026-04-08"),
    "#22": ("done", "2026-04-08"),
    "#23": ("done", "2026-04-08"),
    "#24": ("done", "2026-04-08"),
    "#25": ("done", "2026-04-24"),  # VACUUM FULL actually ran 2026-04-24 (cba_embeddings, cba_provisions, corporate_identifier_crosswalk)
    "#26": ("done", "2026-04-08"),
    "#27": ("done", "2026-04-08"),
    # --- P1: 20 done + #48 partial (17/21 as of 2026-04-14 + #44/#46/#47 on 2026-04-16 + #32/33/34 verified/extended on 2026-04-24) ---
    "#18": ("done", "2026-04-30"),  # PHONETIC_STATE deactivation closes the R7-PARTIAL piece (NAME_AGGRESSIVE was 4/8); 7,671 superseded across 8 sources
    "#28": ("done", "2026-04-14"),
    "#29": ("done", "2026-04-10"),
    "#30": ("done", "2026-04-10"),
    "#31": ("done", "2026-04-10"),
    "#32": ("done", "2026-04-24"),  # Freshness API already used record dates; verified 2026-04-24
    "#33": ("done", "2026-04-24"),  # 12 new date_query entries added to data_source_catalog 2026-04-24 (see session_2026_04_24_p0_vacuum_p1_freshness)
    "#34": ("done", "2026-04-24"),  # SAM + USAspending date_query verified present 2026-04-24
    "#35": ("done", "2026-04-11"),
    "#36": ("done", "2026-04-11"),
    "#37": ("done", "2026-04-11"),
    "#38": ("done", "2026-04-14"),
    "#39": ("done", "2026-04-14"),
    "#40": ("done", "2026-04-14"),
    "#41": ("done", "2026-04-14"),
    "#42": ("done", "2026-04-14"),
    "#43": ("done", "2026-04-30"),  # NLRB search dedup -- modified rebuild_search_mv.py DISTINCT ON to drop election_date; 86,153 -> 55,531 NLRB rows (-36%)
    "#44": ("done", "2026-04-16"),
    "#45": ("done", "2026-04-14"),
    "#46": ("done", "2026-04-16"),
    "#47": ("done", "2026-04-16"),
    "#48": ("partial", "2026-04-16"),
    # --- P2: doc & AI context debt, per session_2026_04_15_p2_doc_sweep ---
    # 2A: CLAUDE.md & Core Docs
    "#49": ("done", "2026-04-07"),
    "#50": ("done", "2026-04-07"),
    "#51": ("done", "2026-04-07"),
    "#52": ("done", "2026-04-07"),
    "#53": ("done", "2026-04-07"),
    "#54": ("done", "2026-04-15"),
    # 2B: Agent & Spec Files
    "#55": ("open", ""),
    "#56": ("done", "2026-04-07"),
    "#57": ("done", "2026-04-07"),
    "#58": ("open", ""),
    "#59": ("done", "2026-04-07"),
    "#60": ("done", "2026-04-07"),
    "#61": ("done", "2026-04-07"),
    "#62": ("done", "2026-04-07"),
    "#63": ("done", "2026-04-15"),
    "#64": ("done", "2026-04-15"),
    "#65": ("done", "2026-04-15"),
    # 2C: Vault Notes
    "#66": ("done", "2026-04-07"),
    "#67": ("done", "2026-04-07"),
    "#68": ("done", "2026-04-07"),
    "#69": ("done", "2026-04-07"),
    "#70": ("done", "2026-04-07"),
    "#71": ("done", "2026-04-07"),
    "#72": ("done", "2026-04-07"),
    "#73": ("done", "2026-04-07"),
    "#74": ("open", ""),
    "#75": ("done", "2026-04-07"),
    "#76": ("done", "2026-04-07"),
    "#77": ("done", "2026-04-07"),
    "#78": ("done", "2026-04-07"),
    "#79": ("done", "2026-04-07"),
    "#80": ("done", "2026-04-07"),
    "#81": ("done", "2026-04-07"),
    "#82": ("done", "2026-04-23"),  # DOCUMENT_INDEX.md rebuilt in wrapup session
    "#83": ("partial", ""),
    "#84": ("done", "2026-04-15"),
    "#85": ("partial", ""),
    "#86": ("done", "2026-04-23"),  # Agent and Skill Infrastructure note refreshed (dossier-writer agent + union-website-cms-fingerprints spec)
    "#87": ("open", ""),
    "#88": ("done", "2026-04-15"),
    "#89": ("open", ""),
}

# Manually encoded Tier 1/2/3 tasks not reliably parsable from tables lacking an ID column.
# These get stable synthetic IDs and authoritative status from recent session summaries.
SYNTHETIC_TASKS: list[dict] = [
    # --- Tier 1A. Matching quality ---
    {"id": "T1-match-mergent-full-load", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Mergent full load", "description": "Jacob pulls remaining ~1.2M employers manually (529K of ~1.7M loaded as of 2026-04-12)",
     "status": "partial", "effort": "ongoing", "source": "Jacob"},
    {"id": "T1-match-etl-generalize", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Mergent ETL generalization (P4-5)", "description": "Generalize loader to handle all states",
     "status": "open", "effort": "6-8h", "source": "roadmap"},
    {"id": "T1-match-rerun-post-mergent", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Matching re-run post-Mergent", "description": "Re-run pipeline with full Mergent data",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-04-05"},
    {"id": "T1-match-quality-audit", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Matching quality audit", "description": "Systematic review of match confidence, triage weak matches. Audit found 47% FP at 0.70-0.85",
     "status": "open", "effort": "audit", "source": "roadmap"},
    {"id": "T1-match-gower-similarity", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Gower Similarity (P1-2)", "description": "15.5M rows, 80.4% coverage (Apr 1). Needs distance-based retune — covered by #36.",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-04-01"},
    {"id": "T1-match-evidence-naics-headcount", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Store NAICS/employee_count in match evidence", "description": "Enable cross-source consistency checks",
     "status": "open", "effort": "new", "source": "Claude FA6"},
    {"id": "T1-match-gleif-nlrb-v2", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Integrate GLEIF and NLRB into V2 pipeline", "description": "Still using legacy scripts",
     "status": "open", "effort": "new", "source": "Claude FA6"},
    {"id": "T1-match-conflict-audit-view", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Conflict-audit view for multi-source employers", "description": "78.4% disagree on headcount across 3+ sources",
     "status": "open", "effort": "new", "source": "Codex FA6"},
    {"id": "T1-match-conflict-field-rules", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Field-level conflict rules", "description": "Replace priority/string-length conflict handling with recency",
     "status": "open", "effort": "new", "source": "Codex FA6"},
    {"id": "T1-match-orphan-rate", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Recompute F7 orphan rate each run", "description": "Currently 64.7% unmatched (95,070 of 146,863)",
     "status": "open", "effort": "new", "source": "Codex FA6"},
    {"id": "T1-match-sourceless-masters", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Investigate 7,711 source-less master rows", "description": "Masters with zero source links",
     "status": "open", "effort": "new", "source": "Codex FA6"},
    {"id": "T1-match-target-source-count", "tier": "T1", "section": "1A. Matching Quality",
     "title": "Fix target-side source-count (has_990/has_sec/has_gleif)", "description": "mv_target_data_sources returns 0 for these",
     "status": "open", "effort": "new", "source": "Codex FA6"},
    {"id": "T1-match-llm-validation", "tier": "T1", "section": "1A. Matching Quality",
     "title": "LLM match validation for 0.70-0.85 band", "description": "Haiku batch v2 shipped 2026-04-16; rule engine H1-H16 + 63,592 merges applied 2026-04-21. 400,967 hierarchy rows loaded.",
     "status": "partial", "effort": "in progress", "source": "Claude FA6", "closure_date": "2026-04-21"},

    # --- Tier 1B. Research Agent Value ---
    {"id": "T1-research-linkedin", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "LinkedIn scraping quality", "description": "Reliable and expansive LinkedIn data",
     "status": "partial", "effort": "~90%", "source": "roadmap"},
    {"id": "T1-research-search-tuning", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Brave search tuning", "description": "Queries more targeted",
     "status": "partial", "effort": "partial", "source": "roadmap"},
    {"id": "T1-research-accuracy-benchmark", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Research accuracy benchmark (P3-1)", "description": "20 known employers, manually verify every fact. 20 gold dossiers shipped 2026-04-21.",
     "status": "partial", "effort": "in progress", "source": "roadmap", "closure_date": "2026-04-21"},
    {"id": "T1-research-batch-100", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Batch research pipeline (100 employers)", "description": "Run 100 employers through research agent",
     "status": "open", "effort": "new", "source": "roadmap"},
    {"id": "T1-research-gold-standard", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Gold standard demo (20 flagship dossiers)", "description": "20 dossiers delivered 2026-04-21: 118,912 words, 1,764 citations, $0 out-of-pocket via Claude Code subagents.",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-04-21"},
    {"id": "T1-research-identity-gate", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Identity-consistency gate", "description": "Flag when enrichment tools disagree on company identity",
     "status": "open", "effort": "new", "source": "Codex FA10"},
    {"id": "T1-research-action-id-trace", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Require action_id traceability for facts", "description": "Run 188 has 0 of 63 fact rows with direct action_id",
     "status": "open", "effort": "new", "source": "Codex FA10"},
    {"id": "T1-research-fix-autograder", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Fix auto-grader", "description": "Weight Assessment section higher, add identity mismatch blocking",
     "status": "open", "effort": "new", "source": "Both FA10"},
    {"id": "T1-research-reaudit-enrich", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Re-audit search_company_enrich", "description": "Highest-risk tool: matched Pew Research Center instead of King David Nursing",
     "status": "open", "effort": "new", "source": "Codex FA10"},
    {"id": "T1-research-locations-sql", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Fix search_employer_locations SQL error", "description": "Column m.osha_establishment_id does not exist",
     "status": "open", "effort": "new", "source": "Codex FA10"},
    {"id": "T1-research-backfill-facts", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Backfill research_facts for older runs", "description": "Pre-March 23 runs have real data only in JSON blob, not relational table",
     "status": "open", "effort": "new", "source": "Claude FA10"},
    {"id": "T1-research-disable-dead-tools", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Remove/disable dead tools", "description": "search_abs_demographics (0%), compare_employer_wages (0%), search_web (errors), perform_search, perform_web_search",
     "status": "open", "effort": "new", "source": "Both FA10"},
    {"id": "T1-research-separate-placeholders", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Separate system placeholders from factual claims", "description": "In storage and UI",
     "status": "open", "effort": "new", "source": "Codex FA10"},
    {"id": "T1-research-assessment-auth", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Reduce assessment section authority", "description": "Campaign strengths/challenges are AI synthesis, not source-traced",
     "status": "open", "effort": "new", "source": "Codex FA10"},
    {"id": "T1-research-clean-orphaned-runs", "tier": "T1", "section": "1B. Research Agent Value",
     "title": "Clean up 2 orphaned running runs", "description": "Stuck since February; cleaned 2026-04-14",
     "status": "done", "effort": "done", "source": "Claude FA10", "closure_date": "2026-04-14"},

    # --- Tier 1C. Union Explorer & Union Data ---
    {"id": "T1-union-explorer-ux", "tier": "T1", "section": "1C. Union Explorer & Union Data",
     "title": "Union Explorer UX cleanup (P6-3)", "description": "Major fix Mar 24. Residual: affiliate noise in detail pages.",
     "status": "partial", "effort": "mostly done", "source": "roadmap", "closure_date": "2026-03-24"},
    {"id": "T1-union-public-sector", "tier": "T1", "section": "1C. Union Explorer & Union Data",
     "title": "Public sector integration (P7-1)", "description": "7,987 public sector employers not connected to scoring/search",
     "status": "open", "effort": "1-2 weeks", "source": "roadmap"},
    {"id": "T1-union-dedup-gap-audit", "tier": "T1", "section": "1C. Union Explorer & Union Data",
     "title": "Union dedup & gap audit", "description": "26,693 entries, 6,053 flagged inactive. Web scraper expansion 2026-04-19/21 added 1,379 rows.",
     "status": "partial", "effort": "in progress", "source": "roadmap", "closure_date": "2026-04-21"},
    {"id": "T1-union-min-data-threshold", "tier": "T1", "section": "1C. Union Explorer & Union Data",
     "title": "Min-data threshold default (P6-4)", "description": "Hide <3 factor employers from default search",
     "status": "partial", "effort": "2-4h", "source": "roadmap"},

    # --- Tier 1D. Scoring & Signals ---
    {"id": "T1-score-leverage-weights", "tier": "T1", "section": "1D. Scoring & Signals",
     "title": "Leverage pillar weights (P1-1)", "description": "Redistribute weight from proximity to contracts/financial/similarity. D12 closed 2026-04-03.",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-04-03"},
    {"id": "T1-score-d5-industry-growth", "tier": "T1", "section": "1D. Scoring & Signals",
     "title": "D5: Industry Growth 3x?", "description": "Currently 10/100 in Leverage. Both audits say defer until after score trust fixes.",
     "status": "deferred", "effort": "defer", "source": "Decision D5"},
    {"id": "T1-score-d12-proximity", "tier": "T1", "section": "1D. Scoring & Signals",
     "title": "D12: Reduce Union Proximity weight", "description": "Reduced 25->10, freed 15 redistributed to contracts/financial/similarity.",
     "status": "done", "effort": "done", "source": "Decision D12", "closure_date": "2026-04-03"},
    {"id": "T1-score-d13-stability", "tier": "T1", "section": "1D. Scoring & Signals",
     "title": "D13: Stability pillar fate", "description": "Demoted to flags, score_stability always NULL.",
     "status": "done", "effort": "done", "source": "Decision D13", "closure_date": "2026-04-03"},
    {"id": "T1-score-dup-employer-reps", "tier": "T1", "section": "1D. Scoring & Signals",
     "title": "Investigate duplicate employer representations", "description": "Mixed similarity outcomes for same brand (Packaging Corp of America)",
     "status": "open", "effort": "new", "source": "Codex FA5"},
    {"id": "T1-score-hierarchy-loss", "tier": "T1", "section": "1D. Scoring & Signals",
     "title": "Investigate corporate_hierarchy data loss (869K->153K)", "description": "716K CorpWatch foreign-parent links missing. Addressed 2026-04-21: rule_derived_hierarchy +400,967 rows.",
     "status": "partial", "effort": "in progress", "source": "Claude FA4", "closure_date": "2026-04-21"},

    # --- Tier 1E. Age Demographics ---
    {"id": "T1-age-demographics-model", "tier": "T1", "section": "1E. Age Demographics",
     "title": "Age demographics model (P3-3)", "description": "Extend IPF framework to age brackets",
     "status": "open", "effort": "1-2 weeks", "source": "roadmap"},
    {"id": "T1-age-targeting-signal", "tier": "T1", "section": "1E. Age Demographics",
     "title": "Age-adjusted targeting signal", "description": "Combine age + Hispanic/race into amenability indicator",
     "status": "open", "effort": "post-model", "source": "roadmap"},

    # --- Tier 1F. State & Local Contracts ---
    {"id": "T1-contracts-strategy", "tier": "T1", "section": "1F. State & Local Contracts",
     "title": "State/local contract strategy", "description": "DECIDED 2026-04-10: 3-state beta NY/VA/OH, target ~June 5",
     "status": "done", "effort": "research", "source": "roadmap",
     "closure_date": "2026-04-10", "closure_note": "D8 decision; Gemini Deep Research scouting report delivered 2026-04-11"},
    {"id": "T1-contracts-pilot-3-states", "tier": "T1", "section": "1F. State & Local Contracts",
     "title": "Pilot 2-3 states (NY/VA/OH per D8)",
     "description": "DONE 2026-04-22. 11 staging tables loaded (6.34M rows / 346K vendors), unified view + MV built, 4,790 deterministic name+state matches against f7_employers (3,096 in beta states), corporate_identifier_crosswalk +3 cols + 3,842 new contractor flags, score_contracts coverage 9,310 -> 13,147 (+41%). 3 codex findings deferred (vendor masters polluting source_count, sub-vendor undercount in NYC contracts loader, NY ABO silent partial load).",
     "status": "done", "effort": "launch blocker", "source": "roadmap",
     "closure_date": "2026-04-22", "closure_note": "5 parallel ETL agents shipped 11 loaders; integration via new state_local_contracts_f7_matches + crosswalk extension + score_contracts CASE update"},
    {"id": "T1-contracts-masters-match", "tier": "T1", "section": "1F. State & Local Contracts",
     "title": "Match state/local contracts vs master_employers (5.5M)",
     "description": "DONE 2026-04-23. match_state_local_contracts_to_masters.py applies rule engine H1-H16 post-filter on 66,779 exact name+state candidate pairs; 46,814 distinct masters matched (10x f7), 30,218 Tier A + 16,587 Tier C (spot-checked 500/500 by Jacob, promoted to tier_A_human_reviewed) + 9 Tier B. mv_target_data_sources gained is_state_local_contractor + state_local_source_count cols (43,463 contractors). mv_target_scorecard signal_contracts coverage 778,223 fed-only -> 803,059 (+24,836). 30,692 matches in beta states (18,497 Tier A).",
     "status": "done", "effort": "done", "source": "session_2026_04_23", "closure_date": "2026-04-23"},

    # --- Tier 1G. Infrastructure & Credibility ---
    {"id": "T1-infra-offsite-backup", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Off-site backup (P0-3)", "description": "Local only; cloud descoped 2026-04-03",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-04-03"},
    {"id": "T1-infra-claudemd-counts", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Update CLAUDE.md counts (P2-3)", "description": "Stale file counts, row counts, test counts",
     "status": "done", "effort": "done", "source": "roadmap"},
    {"id": "T1-infra-doc-contradictions", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Fix documentation contradictions (P2-4)", "description": "README references, scoring factor counts, etc.",
     "status": "partial", "effort": "partial", "source": "roadmap"},
    {"id": "T1-infra-project-metrics", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Run generate_project_metrics.py (P2-5)", "description": "Re-ran 2026-04-23. DB now 42 GB, 297 tables, 12 MVs, 644 indexes. docs/PROJECT_METRICS.md + docs/PLATFORM_STATUS.md refreshed.",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-04-23"},
    {"id": "T1-infra-d8-launch", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "D8: Launch approach", "description": "DECIDED 2026-04-10: 3-state beta NY/VA/OH, target ~June 5",
     "status": "done", "effort": "decided", "source": "Decision D8", "closure_date": "2026-04-10"},
    {"id": "T1-infra-zombie-mvs", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Drop/fix 6 zombie MVs", "description": "mv_jolts_industry_rates, mv_ncs_benefits_access, mv_oes_area_wages, mv_qcew_state_industry_wages, mv_soii_industry_rates, mv_whd_employer_agg. 5 dropped 2026-04-14; 4 turned out to be real, restored 2026-04-16.",
     "status": "partial", "effort": "partial", "source": "Both FA12", "closure_date": "2026-04-16"},
    {"id": "T1-infra-unused-indexes", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Audit and drop 170 unused indexes", "description": "All have idx_scan = 0. Top 20 dropped 2026-04-14 (3GB reclaim).",
     "status": "partial", "effort": "partial", "source": "Both FA12", "closure_date": "2026-04-14"},
    {"id": "T1-infra-mv-refresh-log", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Add MV refresh log/metadata table", "description": "MV freshness not auditable today",
     "status": "open", "effort": "new", "source": "Codex FA12"},
    {"id": "T1-infra-organizing-scorecard", "tier": "T1", "section": "1G. Infrastructure & Credibility",
     "title": "Decide fate of organizing scorecard", "description": "Legacy API with size-as-signal, broken summary endpoints",
     "status": "open", "effort": "new", "source": "Codex FA3/FA8"},

    # --- Tier 2A. SEC Financial Integration ---
    {"id": "T2-sec-api-endpoint", "tier": "T2", "section": "2A. SEC Financial Integration",
     "title": "API endpoint for financials (P4-1)", "description": "GET /employers/{id}/financials",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-03-29"},
    {"id": "T2-sec-research-agent", "tier": "T2", "section": "2A. SEC Financial Integration",
     "title": "Research agent SEC integration (P4-2)", "description": "Latest revenue/income in dossiers",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-03-29"},
    {"id": "T2-sec-frontend-financial", "tier": "T2", "section": "2A. SEC Financial Integration",
     "title": "Frontend financial display (P4-3)", "description": "Sparkline trends, formatted numbers",
     "status": "done", "effort": "done", "source": "roadmap", "closure_date": "2026-03-29"},
    {"id": "T2-sec-10k-employee-count", "tier": "T2", "section": "2A. SEC Financial Integration",
     "title": "Employee count extraction from 10-K (P4-4)", "description": "LLM parsing of 10-K prose. 6,794 candidates remaining, ~$140 API cost.",
     "status": "open", "effort": "~$140", "source": "roadmap"},
    {"id": "T2-sec-ceo-pay-ratio", "tier": "T2", "section": "2A. SEC Financial Integration",
     "title": "CEO pay ratio & exec comp (P4-6)", "description": "20-30h of work. Deprioritized.",
     "status": "deferred", "effort": "20-30h", "source": "roadmap"},
    {"id": "T2-sec-v12-demographics-api", "tier": "T2", "section": "2A. SEC Financial Integration",
     "title": "Wire V12 demographics into API", "description": "API now serves method=v12_qwi with qwi_level/diversity_tier. Wired 2026-04-14.",
     "status": "done", "effort": "done", "source": "Both FA8", "closure_date": "2026-04-14"},

    # --- Tier 2B. Additional Data Sources ---
    {"id": "T2-ds-state-perb", "tier": "T2", "section": "2B. Additional Data Sources",
     "title": "State PERB pilot (P7-2) NY + CA", "description": "Public Employment Relations Board data",
     "status": "open", "effort": "2 weeks/state", "source": "roadmap"},
    {"id": "T2-ds-state-osha", "tier": "T2", "section": "2B. Additional Data Sources",
     "title": "State OSHA plan data (P7-3)", "description": "22 states run own OSHA programs",
     "status": "open", "effort": "2-4 weeks/state", "source": "roadmap"},
    {"id": "T2-ds-state-wage-theft", "tier": "T2", "section": "2B. Additional Data Sources",
     "title": "State wage theft agencies (P7-4)", "description": "State wage enforcement beyond federal WHD",
     "status": "open", "effort": "2-4 weeks/state", "source": "roadmap"},
    {"id": "T2-ds-wage-outlier-expansion", "tier": "T2", "section": "2B. Additional Data Sources",
     "title": "Wage outlier expansion (D14)", "description": "CLOSED - superseded by D16 (wage outlier removed entirely)",
     "status": "done", "effort": "closed", "source": "Decision D14", "closure_date": "2026-04-11"},

    # --- Tier 2C. Scrapers & Collection ---
    {"id": "T2-scrape-union-web-expansion", "tier": "T2", "section": "2C. Scrapers & Collection",
     "title": "Union web scraper expansion (P8-2)", "description": "SEIU/APWU/CWA/IBEW/USW + Teamsters shipped 2026-04-17/19/21. web_union_profiles 625->2,189.",
     "status": "partial", "effort": "largely done", "source": "roadmap", "closure_date": "2026-04-21"},
    {"id": "T2-scrape-employer-batch", "tier": "T2", "section": "2C. Scrapers & Collection",
     "title": "Employer website batch scraper (P8-3)", "description": "Systematic crawling of employer websites",
     "status": "open", "effort": "new", "source": "roadmap"},
    {"id": "T2-scrape-archive-low-value", "tier": "T2", "section": "2C. Scrapers & Collection",
     "title": "Archive low-value data (P8-6)", "description": "Evaluate BMF, CorpWatch, Mergent for archive",
     "status": "open", "effort": "2-4h", "source": "roadmap"},
    {"id": "T2-scrape-cba-pdf-extract", "tier": "T2", "section": "2C. Scrapers & Collection",
     "title": "Extract 145 contract PDF links into CBA pipeline", "description": "Scraper's most valuable output - nearly doubles CBA corpus",
     "status": "open", "effort": "new", "source": "Both FA11"},

    # --- Tier 2D. Codebase Cleanup ---
    {"id": "T2-cleanup-dead-root-py", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Archive 27 dead root Python scripts", "description": "Only db_config.py and import_mergent.py are active",
     "status": "done", "effort": "done", "source": "Claude FA3", "closure_date": "2026-04-14"},
    {"id": "T2-cleanup-old-prompts-audits", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Archive 6 old prompt files + 2 audit reports", "description": "V7/V8/V9/V10 prompts, Round 5 audit",
     "status": "done", "effort": "done", "source": "Claude FA3", "closure_date": "2026-04-14"},
    {"id": "T2-cleanup-audit-dirs", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Move audit directories to archive", "description": "audits 2_22/ and audits 2_25_2_26/",
     "status": "done", "effort": "done", "source": "Claude FA3", "closure_date": "2026-04-14"},
    {"id": "T2-cleanup-splink-scripts", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Archive 4 dead Splink scripts", "description": "Superseded by V2 engine",
     "status": "done", "effort": "done", "source": "Claude FA3", "closure_date": "2026-04-14"},
    {"id": "T2-cleanup-unified-scorecard-frontend", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Delete dead frontend components", "description": "UnifiedScorecardPage + Table",
     "status": "done", "effort": "done", "source": "Both FA3", "closure_date": "2026-04-14"},
    {"id": "T2-cleanup-open-frontend-bat", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Remove/fix open-frontend.bat", "description": "Points to missing URL",
     "status": "open", "effort": "2 min", "source": "Codex FA3"},
    {"id": "T2-cleanup-dead-api-routers", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Remove 8 dead API routers", "description": "density, projections, museums, sectors, vr, public_sector, trends, standalone osha",
     "status": "open", "effort": "15 min", "source": "Claude FA3"},
    {"id": "T2-cleanup-files-dir", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Clean files/ directory", "description": "Dead JS/CSS/HTML legacy assets",
     "status": "open", "effort": "10 min", "source": "Both FA3"},
    {"id": "T2-cleanup-pillar-stability", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Remove perpetually-null pillar_stability from API", "description": "Always NULL, adds noise to responses",
     "status": "open", "effort": "5 min", "source": "Both FA2"},
    {"id": "T2-cleanup-prompts-to-vault", "tier": "T2", "section": "2D. Codebase Cleanup",
     "title": "Archive prompt files to vault Prompts/", "description": "Scattered in codebase root",
     "status": "open", "effort": "30 min", "source": "Claude FA3"},

    # --- Tier 3A. CBA Tool ---
    {"id": "T3-cba-5000-scaling", "tier": "T3", "section": "3A. CBA Tool",
     "title": "CBA scaling toward 5,000 contracts (P8-1)", "description": "Infrastructure complete, 174 loaded. RunPod OCR aborted 2026-04-17; retry ~$77 on 4x 4090 with explicit per-GPU tmux launches.",
     "status": "partial", "effort": "scaling", "source": "roadmap"},

    # --- Tier 3B. Research Agent Evolution ---
    {"id": "T3-research-r4-outcomes", "tier": "T3", "section": "3B. Research Agent Evolution",
     "title": "R4: Outcome tracking & predictive feedback (P5-1)", "description": "Research-to-outcome linking",
     "status": "open", "effort": "horizon", "source": "roadmap"},
    {"id": "T3-research-r5-deep-intel", "tier": "T3", "section": "3B. Research Agent Evolution",
     "title": "R5: Deep intelligence (P5-2)", "description": "Vector search (RAG), cross-employer patterns, NLP interface",
     "status": "open", "effort": "horizon", "source": "roadmap"},

    # --- Tier 3C. Advanced Analytics & Visualization ---
    {"id": "T3-analytics-lodes-map", "tier": "T3", "section": "3C. Advanced Analytics & Visualization",
     "title": "LODES commute map", "description": "Map showing big union employers and commute patterns",
     "status": "open", "effort": "horizon", "source": "roadmap"},
    {"id": "T3-analytics-cps-microdata", "tier": "T3", "section": "3C. Advanced Analytics & Visualization",
     "title": "CPS microdata (P8-4)", "description": "Custom union density by occupation x industry x geography",
     "status": "open", "effort": "horizon", "source": "roadmap"},
    {"id": "T3-analytics-news-monitoring", "tier": "T3", "section": "3C. Advanced Analytics & Visualization",
     "title": "News monitoring pipeline (P8-5)", "description": "Auto-flag employers with strikes, campaigns, safety incidents",
     "status": "open", "effort": "horizon", "source": "roadmap"},

    # --- Decisions (D1-D16) ---
    {"id": "D1",  "tier": "D", "section": "Decisions",
     "title": "No enforcement gate for any tier (D1/D7)",
     "description": "No minimum enforcement signal to reach any scoring tier.",
     "status": "done", "effort": "closed", "source": "Decision log"},
    {"id": "D3",  "tier": "D", "section": "Decisions",
     "title": "Size weight zeroed (D3)",
     "description": "Size is a filter dimension, not a scoring signal.",
     "status": "done", "effort": "done", "source": "Decision log"},
    {"id": "D5",  "tier": "D", "section": "Decisions",
     "title": "Industry Growth weight 3x? (D5)",
     "description": "Currently 10/100 in Leverage. Both audits say defer until after score trust fixes.",
     "status": "deferred", "effort": "defer", "source": "Decision log"},
    {"id": "D6",  "tier": "D", "section": "Decisions",
     "title": "Kill propensity model (D6)",
     "description": "Removed propensity model layer.",
     "status": "done", "effort": "done", "source": "Decision log"},
    {"id": "D8",  "tier": "D", "section": "Decisions",
     "title": "Launch approach (D8)",
     "description": "DECIDED 2026-04-10: 3-state beta NY/VA/OH with state/local contracts, 20-100 gold dossiers, full Mergent. Target ~June 5.",
     "status": "done", "effort": "decided", "source": "Decision log", "closure_date": "2026-04-10"},
    {"id": "D11", "tier": "D", "section": "Decisions",
     "title": "Scoring framework overhaul (D11)",
     "description": "Anger/Stability/Leverage. Superseded by D13 (stability demoted).",
     "status": "done", "effort": "closed", "source": "Decision log"},
    {"id": "D12", "tier": "D", "section": "Decisions",
     "title": "Union Proximity weight (D12)",
     "description": "Reduced 25->10, freed 15 redistributed to contracts/financial/similarity.",
     "status": "done", "effort": "done", "source": "Decision log", "closure_date": "2026-04-03"},
    {"id": "D13", "tier": "D", "section": "Decisions",
     "title": "Stability pillar fate (D13)",
     "description": "Demoted to flags (Option B). score_stability always NULL.",
     "status": "done", "effort": "done", "source": "Decision log", "closure_date": "2026-04-03"},
    {"id": "D14", "tier": "D", "section": "Decisions",
     "title": "Expand wage outliers? (D14)",
     "description": "CLOSED - superseded by D16. Wage outlier scoring removed entirely.",
     "status": "done", "effort": "closed", "source": "Decision log", "closure_date": "2026-04-11"},
    {"id": "D15", "tier": "D", "section": "Decisions",
     "title": "Form 5500 benefits integration (D15)",
     "description": "REMOVED. Benefits are a proxy for worker count, not a direct signal.",
     "status": "done", "effort": "closed", "source": "Decision log"},
    {"id": "D16", "tier": "D", "section": "Decisions",
     "title": "Shelf wage outlier (D16)",
     "description": "Removed entirely. OES upgraded to MSA-first lookup.",
     "status": "done", "effort": "done", "source": "Decision log", "closure_date": "2026-04-11"},

    # --- R7 Audit (2026-04-26) ---
    # The R7 roadmap (MERGED_ROADMAP_2026_04_25.md) uses R7-1..R7-19 + REG-1..REG-7 IDs that
    # the table parser doesn't pick up (they're not in the #N or D# pattern). Encoded here.
    # 21 items closed in the 2026-04-27 session — see
    # memory/session_2026_04_27_r7_audit_tracks_a_through_h.md.
    {"id": "R7-2", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Demographics NULL vintage on every response",
     "description": "Added acs_year/qcew_year/methodology fields to all 4 response paths in api/routers/demographics.py.",
     "status": "done", "effort": "30m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-3", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Demographics raw numeric Hispanic labels",
     "description": "Replaced 2-code HISPANIC_LABELS with full IPUMS HISPAN encoding (0=Not Hispanic, 1=Mexican, 2=Puerto Rican, 3=Cuban, 4=Other).",
     "status": "done", "effort": "15m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-5", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Empty unified-search returns 146,863 rows",
     "description": "Added required-filter guard at api/routers/employers.py:357. Metro check moved ahead so ?metro= alone still 422s.",
     "status": "done", "effort": "5m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-6", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Family-rollup routes absent from running :8001",
     "description": "Restarted uvicorn; Windows zombie-socket pattern recurred -- moved Vite proxy to next port. Shipped via M-1 hygiene check too.",
     "status": "done", "effort": "15m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-7", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Search ranks wrong canonical entities",
     "description": "Tiebreak ORDER BY rewritten (canonical_group_id + consolidated_workers priority) + new config/employer_aliases.json with 5-entry seed for collision exclusions (Cleveland Clinic vs Cleveland-Cliffs, NYC HHC vs NYU). Verified Cleveland Clinic Foundation now in top 5. Limitation: flat-MASTER cases (Walmart/Amazon) still need 4-8hr alias-name-expansion lift -- documented as deferred follow-up.",
     "status": "partial", "effort": "30m + deferred", "source": "R7 audit", "closure_date": "2026-04-28"},
    {"id": "R7-8", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Government Contracts JSX hard-codes federal short-circuit",
     "description": "GovernmentContractsCard.jsx now renders federal + state/local sections independently using existing dataSources fields.",
     "status": "done", "effort": "2h", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-9", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "State/local API endpoint missing",
     "description": "New /api/employers/master/{master_id}/state-local-contracts at master.py. Tier A+B default; ?include_review_tier=true.",
     "status": "done", "effort": "0.5d", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-10", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "WHD card shape mismatch (Kroger $0)",
     "description": "WhdCard.jsx 6 field renames to match API (whd_violation_count, whd_backwages, whd_penalties, etc.).",
     "status": "done", "effort": "30m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-11", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "WHD cases empty (case-sensitivity)",
     "description": "Lowercase + strip name_norm in whd.py:200 before WHERE = whd_cases.name_normalized. Verified Kroger Manufacturing 0 -> 1 case.",
     "status": "done", "effort": "30m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-12", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "NLRB Wins/Losses/ULP all '--'",
     "description": "NlrbSection.jsx 5 field renames + derive result from union_won boolean.",
     "status": "done", "effort": "45m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-13", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Comparables non_union vs nonunion mismatch",
     "description": "ComparablesCard.jsx 'nonunion' -> 'non_union' to match DB CHECK constraint at compute_gower_similarity.py:357.",
     "status": "done", "effort": "5m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-14", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Master /comparables 404 on MASTER- prefix",
     "description": "Strip MASTER- prefix at employers.py:1604 before int() cast. Mirrors line 459 pattern.",
     "status": "done", "effort": "5m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-15", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Master /data-sources 404",
     "description": "F7 path unchanged; master path synthesizes from mv_target_scorecard + state_local_contracts_master_matches. Masters not in target scorecard 404 with clearer message.",
     "status": "done", "effort": "30m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-16", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Identity grafting in search_company_enrich",
     "description": "Composite fuzzy guard (rapidfuzz partial<80 AND token_sort<65 AND token_set<75 -> reject) before accepting CompanyEnrich response. Domain lookups skip guard.",
     "status": "done", "effort": "1-2h", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-17", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Anger pillar NULL propagation",
     "description": "Added enh_score_nlrb to score_anger gate AND formula numerator+denominator (weight 3). Post-rebuild: rows w/ score_nlrb non-NULL but score_anger NULL = 2,526 -> 0.",
     "status": "done", "effort": "1-2h", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-18", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Cap weighted_score on thin-data perfect-10s",
     "description": "Cap at 7.0 when factors_available<3 AND direct_factors_available=0. Post-rebuild: 14,363 thin-data rows correctly capped; thin-data perfect-10s = 0 (was thousands).",
     "status": "done", "effort": "30m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-19", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "NLRB freshness query alias bug (UI says 2021, actual 2026)",
     "description": "Fixed UNION ALL aliasing at data_source_catalog.py:87 + re-ran create_data_freshness.py --refresh. Now shows 2026-01-21.",
     "status": "done", "effort": "5m+scrub", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "R7-1", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Demographics impossible total_workers (145M for NY hospitals)",
     "description": "Closed 2026-04-28: two ETL bugs in newsrc_curate_all.py::build_acs() -- (1) GROUP BY collapsed across 9 IPUMS sample-years inflating totals 9x; (2) sentinel filter mismatch leaked not-in-LF people. Fixed at curate step with WHERE sample='202303' AND indnaics<>'0' AND occsoc<>'0' AND classwkr<>'0'. Rebuilt cur_acs_workforce_demographics 11.5M -> 6.4M rows. Validated against BLS QCEW: NY 11.86M vs 9.71M (ratio 1.22 = expected ACS+self-employed gap). See session_2026_04_28_r7_1_demographics_etl_fix.md.",
     "status": "done", "effort": "1-2d", "source": "R7 audit", "closure_date": "2026-04-28"},
    {"id": "R7-4", "tier": "T0-R7", "section": "P0 R7-NEW Beta Blockers",
     "title": "Frontend demographics card hardcodes ACS 2022",
     "description": "Closed 2026-04-28: backend half had to be duplicated -- workforce-profile reads from profile.py (separate from R7-2's demographics.py). Added ACS_PUMS_VINTAGE/LODES_VINTAGE constants in profile.py mirroring c54da60. Threaded vintage_year into _get_acs_demographics(), _get_lodes_demographics(), and /workplace-demographics endpoint. JSX WorkforceDemographicsCard.jsx:361,366 + getMethodDescription() now read data.acs?.vintage_year / data.lodes?.vintage_year. Codex crosscheck found 2 follow-up issues, both fixed (getMethodDescription hardcoded 2022; vite proxy mismatch reverted to canonical :8001). 21/21 tests pass. See session_2026_04_28_r7_4_demographics_frontend.md.",
     "status": "done", "effort": "45m", "source": "R7 audit", "closure_date": "2026-04-28"},
    {"id": "REG-1", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "Profile 503->404 fix regressed to 500",
     "description": "Column employer_id doesn't exist on mv_employer_search. Fixed at profile.py:168 (canonical_id::text).",
     "status": "done", "effort": "5m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "REG-2", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "Backup automation failing",
     "description": "Closed 2026-05-03. Two root causes: (1) tasks used bare `py` with no PATH at task-run time -> 0x80070002 ERROR_FILE_NOT_FOUND; (2) setup_backup_task.ps1 had `-RunLevel Highest` which silently failed re-registration from non-admin sessions. Both fixed in PM commit 84db90a: dropped -RunLevel Highest from PS1 and re-registered with full python launcher path via `cmd.exe /c <full-path-py.exe> <script> >> log 2>&1`. Manual smoke produced 5.1 GB dump in 13 min; daily 3 AM armed. See session_2026_05_03_omnibus_day.md.",
     "status": "done", "effort": "1h", "source": "R7 audit", "closure_date": "2026-05-03"},
    {"id": "REG-3", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "PostgreSQL listen_addresses still '*'",
     "description": "Claimed fixed 2026-04-08 but postgresql.conf line 60 unchanged. Needs Jacob coord to bounce postgres.",
     "status": "open", "effort": "10m", "source": "R7 audit"},
    {"id": "REG-4", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "F7 orphan rate regressed",
     "description": "PARTIAL 2026-05-03. Deep-dive identified 16,659 recoverable Splink-superseded F7s (4 NAICS-2 sectors hold 58% -- construction/food/healthcare/transport). OSHA + WHD rematches via run_deterministic.py --unmatched-only wrote 19,922 new HIGH/MEDIUM matches; orphan rate moved 68.1% -> 65.7% (-2.36pp; below R7 baseline 67.4%, ~1pp above R6 baseline 64.7%). 990 + SAM rematches deferred (diminishing returns -- WHD only added 0.4pp vs OSHA's 2.0pp; another ~0.25pp expected from 990+SAM). TRUNCATED_NAME_STATE replacement (city-anchored variant) still needed before that method can be deactivated. See Open Problems/F7 Orphan Rate Regression.md.",
     "status": "partial", "effort": "overnight", "source": "R7 audit"},
    {"id": "REG-5", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "P0 docs sweep 11 of 14 incomplete",
     "description": "7 NOT-DONE + 4 PARTIAL; only 3 genuinely done.",
     "status": "open", "effort": "2-4h", "source": "R7 audit"},
    {"id": "REG-6", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "SEC Exhibit 21 scraper POC-only",
     "description": "Closed 2026-05-03 (also 24Q-17). Production run executed: load_sec_exhibit21.py --all --commit on 7,819 SEC filers in ~2:50 hr; 77,205 subsidiaries written, 1,637 distinct parents, 0 failures across the whole run (Ventas top with 2,814 subs; HCA 2,407; Comcast 1,496; Thermo Fisher 1,266; Tenet 1,201; Warner Bros Discovery 1,011). corporate_ultimate_parents source='SEC_EXHIBIT_21' grew 6 -> 77,205. See session_2026_05_03_omnibus_day.md.",
     "status": "done", "effort": "1-2d", "source": "R7 audit", "closure_date": "2026-05-03"},
    {"id": "REG-7", "tier": "T0-R7", "section": "R7 Regressions",
     "title": "NLRB nightly cron not installed",
     "description": "Built but elections still 5 years stale. Needs admin install + scrubber rerun.",
     "status": "open", "effort": "30m", "source": "R7 audit"},
    {"id": "P0-2-FA6.2", "tier": "T0-R7", "section": "P0 Original Issues",
     "title": "Admin endpoint 503 -> 403",
     "description": "require_admin in api/dependencies.py now returns 403 (Forbidden) not 503 (Service Unavailable) when DISABLE_AUTH=true and ALLOW_INSECURE_ADMIN=false.",
     "status": "done", "effort": "2m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "FA9.6", "tier": "T0-R7", "section": "P0 Quick Wins",
     "title": "ANALYZE 8 stalest tables",
     "description": "Ran ANALYZE on 8 state_contracts_* tables (last analyzed 2026-04-22). ~37s total.",
     "status": "done", "effort": "5m", "source": "R7 audit", "closure_date": "2026-04-27"},
    {"id": "M-1", "tier": "T0-R7", "section": "Process Debt (R7-Meta)",
     "title": "Add openapi-grep deploy hygiene check to release flow",
     "description": "Step 4 added to vault .claude/skills/ship/SKILL.md (2026-04-27). Standalone gate `scripts/maintenance/check_critical_routes.py` + `config/critical_routes.txt` (13 routes) + `RELEASE_CHECKLIST.md` shipped 2026-04-30 -- diffs /openapi.json against manifest, exits non-zero if any critical route missing.",
     "status": "done", "effort": "20m", "source": "R7 audit", "closure_date": "2026-04-30"},
    {"id": "M-2", "tier": "T0-R7", "section": "Process Debt (R7-Meta)",
     "title": "Add API output sanity check (plausibility bounds)",
     "description": "`api/services/demographics_bounds.py` + 16 unit tests + wired into 4 demographics endpoints (3 in demographics.py + workforce-profile in profile.py). R7-1 reproduction (145M NY hospitals) caught; total_workers vs state-workforce ceiling (BLS CPS * 1.30) + pct-sum tolerance enforced.",
     "status": "done", "effort": "60m", "source": "R7 audit", "closure_date": "2026-04-30"},
    {"id": "M-3", "tier": "T0-R7", "section": "Process Debt (R7-Meta)",
     "title": "Add P0-claim verification cycle",
     "description": "11 of 14 P0 docs falsely claimed DONE. Each sprint close: re-read each 'DONE' doc and verify.",
     "status": "open", "effort": "ongoing", "source": "R7 audit"},
    {"id": "M-4", "tier": "T0-R7", "section": "Process Debt (R7-Meta)",
     "title": "Add frontend-API contract test",
     "description": "Vitest passes on stale fixtures (caught WHD/NLRB/Comparables/Govt Contracts). Generate fixtures from openapi.json or contract-test with snapshot diffs.",
     "status": "open", "effort": "new", "source": "R7 audit"},
    {"id": "M-5", "tier": "T0-R7", "section": "Process Debt (R7-Meta)",
     "title": "Add regression sweep to audits",
     "description": "Each audit: explicitly re-test prior 'DONE' list. R7 added; make standard.",
     "status": "open", "effort": "ongoing", "source": "R7 audit"},
]

# Manual dependency overrides (beyond what's parsed from #N references)
DEPENDENCY_OVERRIDES: dict[str, list[str]] = {
    # P0 chain
    "#3": ["#1", "#2"],
    "#4": ["#1", "#2", "#3"],
    "#5": ["#1", "#2", "#3", "#4"],
    # P1 tier rule hinges on thin-data + similarity
    "#38": ["#35", "#36", "#37"],
    # Launch blockers
    "T1-contracts-pilot-3-states": ["T1-infra-d8-launch"],
    # Gower retune depends on thin-data framing
    "T1-match-gower-similarity": [],
    # Sync target-side source-count depends on seeding
    "T1-match-target-source-count": ["T1-match-evidence-naics-headcount"],
}

# -----------------------------------------------------------------------------
# Parsing

SUBSECTION_RE = re.compile(r"^###\s+(.+?)\s*$")

_PIPE_PLACEHOLDER = "\x00"

def _split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    # Swap markdown-escaped \| for a placeholder so a cell containing a pipe does
    # not break the column count. Restored after split.
    inner = inner.replace(r"\|", _PIPE_PLACEHOLDER)
    return [c.strip().replace(_PIPE_PLACEHOLDER, "|") for c in inner.split("|")]

def _tier_from_heading(line: str) -> str | None:
    m = re.match(r"^##\s+(PRIORITY\s+(\d+)|TIER\s+(\d+)|OPEN DECISIONS)", line, re.I)
    if not m:
        return None
    up = line.upper()
    if "PRIORITY" in up:
        return f"P{m.group(2)}"
    if "TIER" in up:
        return f"T{m.group(3)}"
    if "OPEN DECISIONS" in up:
        return "D"
    return None

def _clean_md(s: str) -> str:
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip()

def _classify_status(text: str) -> str:
    u = text.upper()
    if "DEPRIORITIZED" in u or "DEFER" in u:
        # only if no explicit DONE nearby
        if "DONE" not in u and "CLOSED" not in u:
            return "deferred"
    if "DONE" in u:
        if "PARTIALLY DONE" in u or "MOSTLY DONE" in u:
            return "partial"
        if "NOT DONE" in u:
            return "open"
        return "done"
    if "CLOSED" in u:
        return "done"
    if "IN PROGRESS" in u:
        return "partial"
    if "PARTIAL" in u:
        return "partial"
    if "OPEN" in u:
        return "open"
    if "NEW (" in u:
        return "open"
    return "unknown"

def parse_roadmap() -> list[dict]:
    text = ROADMAP_MD.read_text(encoding="utf-8")
    lines = text.splitlines()

    tier: str | None = None
    section: str | None = None
    headers: list[str] | None = None
    tasks: list[dict] = []

    for line in lines:
        if line.startswith("## "):
            tier = _tier_from_heading(line)
            section = None
            headers = None
            continue
        m = SUBSECTION_RE.match(line)
        if m:
            section = m.group(1).strip()
            headers = None
            continue
        if tier is None:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            headers = None
            continue
        cells = _split_row(line)
        if all(re.match(r"^[-:\s]*$", c) for c in cells):
            continue
        if headers is None:
            headers = [c.lower() for c in cells]
            continue
        if len(cells) != len(headers):
            headers = None
            continue
        row = dict(zip(headers, cells))
        task = _row_to_task(row, tier, section)
        if task:
            tasks.append(task)

    return tasks

def _row_to_task(row: dict, tier: str, section: str | None) -> dict | None:
    title_raw = row.get("task", "") or row.get("question", "") or ""
    if not title_raw or title_raw.lower() in ("task", "question", "#"):
        return None

    id_col = (row.get("#", "") or row.get("id", "")).strip()
    if id_col.isdigit():
        tid = f"#{id_col}"
    elif re.match(r"^D\d+$", id_col):
        tid = id_col
    else:
        return None  # Unnumbered rows come from SYNTHETIC_TASKS instead

    title = _clean_md(title_raw)
    what = _clean_md(row.get("what", "") or row.get("recommendation", ""))
    status_hint = _clean_md(row.get("status (apr 7)", "") or row.get("status", ""))
    effort = row.get("effort", "").strip()
    source = row.get("source", "").strip()

    deps_text = f"{what} {status_hint}"
    parsed_deps = sorted({f"#{m}" for m in re.findall(r"#(\d+)", deps_text) if f"#{m}" != tid})

    combined = f"{title_raw} {status_hint} {what}".strip()
    status = _classify_status(combined)

    return {
        "id": tid,
        "tier": tier,
        "section": section or "",
        "title": title,
        "description": what,
        "status_hint": status_hint,
        "effort": effort,
        "source": source,
        "status": status,
        "dependencies": parsed_deps,
    }

# -----------------------------------------------------------------------------
# Merging

def _today() -> str:
    return date.today().isoformat()

def _atomic_write_text(path: Path, content: str) -> None:
    """Write text via sibling `.tmp` file + rename so a crash mid-write cannot
    leave behind a truncated target. Path.replace() is atomic on POSIX and on
    Windows (Python docs §os.replace).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

def apply_overrides(tasks: list[dict]) -> None:
    for t in tasks:
        tid = t["id"]
        if tid in STATUS_OVERRIDES:
            status, closure_date = STATUS_OVERRIDES[tid]
            t["status"] = status
            if closure_date:
                t["closure_date"] = closure_date
        deps = set(t.get("dependencies", []))
        if tid in DEPENDENCY_OVERRIDES:
            deps.update(DEPENDENCY_OVERRIDES[tid])
        t["dependencies"] = sorted(deps)

def merge_with_history(current: list[dict], prev_state: dict) -> dict:
    today = _today()
    prev_tasks = {t["id"]: t for t in prev_state.get("tasks", [])}
    merged: dict[str, dict] = {}

    for t in current:
        tid = t["id"]
        prev = prev_tasks.get(tid, {})
        history = list(prev.get("history", []))
        prev_status = prev.get("status")
        if prev_status is None:
            history.append({"date": today, "status": t["status"], "note": "seen for first time"})
        elif prev_status != t["status"]:
            history.append({
                "date": today,
                "status": t["status"],
                "note": f"status changed from {prev_status}",
            })
        merged[tid] = {
            **prev,
            **t,
            "first_seen": prev.get("first_seen", today),
            "last_seen": today,
            "history": history,
            "archived": False,
        }

    # Tasks that disappeared -> archive but keep
    current_ids = {t["id"] for t in current}
    for tid, prev in prev_tasks.items():
        if tid in current_ids:
            continue
        history = list(prev.get("history", []))
        if not prev.get("archived"):
            history.append({"date": today, "status": "archived", "note": "no longer in roadmap source"})
        merged[tid] = {
            **prev,
            "archived": True,
            "archived_date": prev.get("archived_date", today),
            "history": history,
        }

    return {
        "generated": today,
        "tasks": sorted(merged.values(), key=_sort_key),
    }

def _sort_key(t: dict) -> tuple:
    tier = t.get("tier", "Z")
    tier_rank = TIER_ORDER.index(tier) if tier in TIER_ORDER else 99
    tid = t.get("id", "")
    # Numeric #N sort within P0/P1/P2
    m = re.match(r"^#(\d+)$", tid)
    if m:
        return (tier_rank, 0, int(m.group(1)))
    return (tier_rank, 1, tid)

# -----------------------------------------------------------------------------
# HTML rendering

def render_html(state: dict) -> str:
    # Escape `</` inside the embedded JSON so a string containing `</script>`
    # cannot close the surrounding <script> tag. U+2028/U+2029 are also
    # JSON-valid but break JS source, so escape those too.
    data_json = (
        json.dumps(state, ensure_ascii=False, indent=2)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    # Summary stats
    tasks = state["tasks"]
    total = len(tasks)
    by_status: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for t in tasks:
        if t.get("archived"):
            by_status["archived"] = by_status.get("archived", 0) + 1
            continue
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        by_tier[t["tier"]] = by_tier.get(t["tier"], 0) + 1

    stats_html = " ".join(
        f'<span class="stat stat-{s}"><b>{by_status.get(s, 0)}</b> {s}</span>'
        for s in STATUS_ORDER if by_status.get(s, 0)
    )

    return HTML_TEMPLATE.replace("__DATA__", data_json)\
                        .replace("__GENERATED__", html.escape(state["generated"]))\
                        .replace("__TOTAL__", str(total))\
                        .replace("__STATS__", stats_html)

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Project Atlas - Labor Data Terminal</title>
<style>
  :root {
    --bg: #f4f1ea;
    --bg-sidebar: #ebe7dd;
    --bg-card: #fdfbf5;
    --ink: #1e1b14;
    --ink-soft: #595341;
    --rule: #c9bfa7;
    --accent: #7a4e2a;
    --done: #4a7c3b;
    --partial: #b37510;
    --open: #6e6b63;
    --deferred: #7a6b8c;
    --blocked: #a73a2a;
    --archived: #9a9488;
    --unknown: #7a7668;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: ui-serif, Georgia, Cambria, "Times New Roman", Times, serif;
    background: var(--bg);
    color: var(--ink);
    font-size: 14px;
    line-height: 1.4;
  }
  header {
    padding: 14px 20px 10px;
    border-bottom: 2px solid var(--rule);
    background: var(--bg-sidebar);
    position: sticky; top: 0; z-index: 5;
  }
  header h1 {
    font-size: 22px;
    margin: 0 0 4px;
    font-weight: 700;
    letter-spacing: 0.01em;
  }
  .subtitle { font-size: 12px; color: var(--ink-soft); margin-bottom: 8px; }
  .controls {
    display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
  }
  .controls input[type=text], .controls select {
    font: inherit;
    padding: 5px 8px;
    border: 1px solid var(--rule);
    background: var(--bg-card);
    color: var(--ink);
    border-radius: 3px;
  }
  .controls input[type=text] { min-width: 220px; }
  .stats { margin-left: auto; font-size: 12px; color: var(--ink-soft); }
  .stat { margin-left: 10px; padding: 2px 8px; border: 1px solid var(--rule); border-radius: 10px; background: var(--bg-card); }
  .stat b { color: var(--ink); font-weight: 700; }

  main { display: flex; min-height: calc(100vh - 90px); }
  aside.tree {
    width: 280px; flex-shrink: 0;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--rule);
    overflow-y: auto;
    padding: 10px 8px;
    font-size: 13px;
  }
  .tier-group { margin-bottom: 8px; }
  .tier-title {
    font-weight: 700;
    padding: 4px 6px;
    cursor: pointer;
    display: flex; justify-content: space-between; align-items: center;
    border-radius: 2px;
  }
  .tier-title:hover { background: #dfd9c6; }
  .tier-title .count { font-size: 11px; color: var(--ink-soft); font-weight: 400; }
  .section-list { margin-left: 12px; border-left: 1px solid var(--rule); padding-left: 8px; }
  .section-item {
    padding: 2px 6px; cursor: pointer; border-radius: 2px;
    display: flex; justify-content: space-between; align-items: center;
    color: var(--ink-soft);
  }
  .section-item:hover, .section-item.active { background: #dfd9c6; color: var(--ink); }
  .section-item .count { font-size: 11px; }
  .tier-collapsed .section-list { display: none; }

  section.cards {
    flex: 1;
    padding: 14px 20px;
    overflow-y: auto;
  }
  .cards-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
  .cards-header h2 { margin: 0; font-size: 18px; }
  .cards-header .count { color: var(--ink-soft); font-size: 12px; }

  .card {
    background: var(--bg-card);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--unknown);
    padding: 10px 14px;
    margin-bottom: 8px;
    border-radius: 3px;
    cursor: pointer;
    position: relative;
  }
  .card:hover { box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-color: var(--accent); }
  .card.status-done      { border-left-color: var(--done); }
  .card.status-partial   { border-left-color: var(--partial); }
  .card.status-open      { border-left-color: var(--open); }
  .card.status-deferred  { border-left-color: var(--deferred); }
  .card.status-blocked   { border-left-color: var(--blocked); }
  .card.archived         { border-left-color: var(--archived); background: #f0ece1; opacity: 0.75; }
  .card.archived .title  { text-decoration: line-through; }

  .card-row { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
  .tid {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    padding: 1px 6px;
    background: var(--bg-sidebar);
    border-radius: 3px;
    color: var(--ink-soft);
  }
  .title { font-weight: 600; flex: 1; min-width: 200px; }
  .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--unknown); display: inline-block; margin-right: 6px;
  }
  .dot.done { background: var(--done); }
  .dot.partial { background: var(--partial); }
  .dot.open { background: var(--open); }
  .dot.deferred { background: var(--deferred); }
  .dot.blocked { background: var(--blocked); }
  .dot.archived { background: var(--archived); }

  .meta { font-size: 12px; color: var(--ink-soft); margin-top: 4px; }
  .meta b { color: var(--ink); font-weight: 600; }
  .desc { margin-top: 4px; color: var(--ink-soft); font-size: 13px; }
  .deps { margin-top: 4px; font-size: 11px; }
  .deps a { color: var(--accent); text-decoration: none; margin-right: 4px; padding: 1px 4px; background: var(--bg-sidebar); border-radius: 2px; }
  .deps a:hover { background: #dfd9c6; }

  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(30,27,20,0.5);
    display: none; align-items: center; justify-content: center; z-index: 100;
  }
  .modal-backdrop.open { display: flex; }
  .modal {
    background: var(--bg-card);
    width: 720px; max-width: 90vw; max-height: 85vh;
    overflow-y: auto;
    padding: 20px 24px;
    border-radius: 4px;
    border: 1px solid var(--rule);
  }
  .modal h3 { margin: 0 0 4px; }
  .modal .meta { font-size: 13px; margin-bottom: 10px; }
  .modal h4 { margin: 16px 0 4px; font-size: 14px; border-bottom: 1px solid var(--rule); padding-bottom: 2px; }
  .modal .history { font-size: 12px; color: var(--ink-soft); }
  .modal .history div { padding: 2px 0; }
  .modal svg { display: block; margin: 8px 0; }
  .close-btn { float: right; cursor: pointer; background: none; border: 1px solid var(--rule); padding: 2px 10px; border-radius: 3px; font: inherit; }

  .no-results { padding: 30px; text-align: center; color: var(--ink-soft); }
  footer { padding: 8px 20px; border-top: 1px solid var(--rule); font-size: 11px; color: var(--ink-soft); background: var(--bg-sidebar); }
</style>
</head>
<body>
<header>
  <h1>Project Atlas - Labor Data Terminal</h1>
  <div class="subtitle">Roadmap · task dependencies · status history. Generated __GENERATED__.</div>
  <div class="controls">
    <input type="text" id="search" placeholder="Search tasks... (#1, mergent, gower)" autocomplete="off">
    <select id="filter-status">
      <option value="">All statuses</option>
      <option value="done">Done</option>
      <option value="partial">Partial</option>
      <option value="open">Open</option>
      <option value="deferred">Deferred</option>
      <option value="blocked">Blocked</option>
      <option value="archived">Archived</option>
      <option value="unknown">Unknown</option>
    </select>
    <label style="font-size:12px"><input type="checkbox" id="show-archived"> show archived</label>
    <span class="stats"><b>__TOTAL__</b> tasks · __STATS__</span>
  </div>
</header>
<main>
  <aside class="tree" id="tree"></aside>
  <section class="cards">
    <div class="cards-header">
      <h2 id="cards-title">All tasks</h2>
      <span class="count" id="cards-count"></span>
    </div>
    <div id="cards-list"></div>
  </section>
</main>
<footer>
  project_atlas.html · regenerated by scripts/maintenance/rebuild_project_atlas.py (wired into /wrapup). History preserved in project_atlas_state.json - delete nothing.
</footer>

<div class="modal-backdrop" id="modal-backdrop">
  <div class="modal" id="modal">
    <button class="close-btn" onclick="closeModal()">close</button>
    <div id="modal-body"></div>
  </div>
</div>

<script>
const STATE = __DATA__;
const TIER_LABELS = {
  "P0": "P0 - Fix What's Broken",
  "P1": "P1 - Trust & Polish",
  "P2": "P2 - Doc & Context Debt",
  "T1": "Tier 1 - Must Happen Before Launch",
  "T2": "Tier 2 - Can Wait",
  "T3": "Tier 3 - Horizon",
  "D":  "Open Decisions"
};
const TIER_ORDER = ["P0","P1","P2","T1","T2","T3","D"];

let activeTier = null;
let activeSection = null;

function buildTree() {
  const tree = document.getElementById("tree");
  const byTier = {};
  for (const t of STATE.tasks) {
    if (t.archived && !document.getElementById("show-archived").checked) continue;
    (byTier[t.tier] ||= {}).__count = (byTier[t.tier]?.__count || 0) + 1;
    const sec = t.section || "(no section)";
    byTier[t.tier][sec] = (byTier[t.tier][sec] || 0) + 1;
  }
  tree.innerHTML = "";
  for (const tier of TIER_ORDER) {
    const group = byTier[tier];
    if (!group) continue;
    const el = document.createElement("div");
    el.className = "tier-group";
    const title = document.createElement("div");
    title.className = "tier-title";
    title.innerHTML = `<span>${TIER_LABELS[tier] || tier}</span><span class="count">${group.__count}</span>`;
    title.onclick = () => { activeTier = activeTier === tier ? null : tier; activeSection = null; render(); };
    el.appendChild(title);
    const list = document.createElement("div");
    list.className = "section-list";
    for (const sec of Object.keys(group).filter(k => k !== "__count").sort()) {
      const item = document.createElement("div");
      item.className = "section-item" + (activeTier === tier && activeSection === sec ? " active" : "");
      item.innerHTML = `<span>${sec}</span><span class="count">${group[sec]}</span>`;
      item.onclick = (e) => { e.stopPropagation(); activeTier = tier; activeSection = sec; render(); };
      list.appendChild(item);
    }
    el.appendChild(list);
    tree.appendChild(el);
  }
}

function renderCards() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const filterStatus = document.getElementById("filter-status").value;
  const showArchived = document.getElementById("show-archived").checked;
  const list = document.getElementById("cards-list");
  const title = document.getElementById("cards-title");
  const count = document.getElementById("cards-count");

  if (activeTier && activeSection)
    title.textContent = `${TIER_LABELS[activeTier]} · ${activeSection}`;
  else if (activeTier)
    title.textContent = TIER_LABELS[activeTier];
  else
    title.textContent = "All tasks";

  const shown = STATE.tasks.filter(t => {
    if (t.archived && !showArchived) return false;
    if (activeTier && t.tier !== activeTier) return false;
    if (activeSection && t.section !== activeSection) return false;
    if (filterStatus) {
      if (filterStatus === "archived") { if (!t.archived) return false; }
      else if (t.status !== filterStatus) return false;
    }
    if (q) {
      const hay = (t.id + " " + t.title + " " + t.description + " " + (t.section||"")).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  count.textContent = `${shown.length} tasks`;
  if (!shown.length) {
    list.innerHTML = `<div class="no-results">No tasks match these filters.</div>`;
    return;
  }
  list.innerHTML = shown.map(renderCard).join("");
  for (const card of list.querySelectorAll(".card"))
    card.onclick = () => openModal(card.dataset.id);
}

function renderCard(t) {
  const statusCls = t.archived ? "archived" : `status-${t.status}`;
  const depLinks = (t.dependencies || []).map(d =>
    `<a href="#" data-goto="${escapeAttr(d)}">${escapeHtml(d)}</a>`
  ).join("");
  const dateBit = t.closure_date ? ` · closed ${t.closure_date}` : "";
  return `<div class="card ${statusCls} ${t.archived?'archived':''}" data-id="${escapeAttr(t.id)}">
    <div class="card-row">
      <span class="dot ${t.archived?'archived':t.status}"></span>
      <span class="tid">${escapeHtml(t.id)}</span>
      <span class="title">${escapeHtml(t.title)}</span>
      <span class="meta">${escapeHtml(t.status.toUpperCase())}${dateBit}</span>
    </div>
    ${t.description ? `<div class="desc">${escapeHtml(t.description).slice(0,260)}${t.description.length>260?'...':''}</div>` : ''}
    <div class="meta">
      <b>${escapeHtml(t.tier)}</b>
      ${t.section ? ` · ${escapeHtml(t.section)}` : ''}
      ${t.effort ? ` · ${escapeHtml(t.effort)}` : ''}
      ${t.source ? ` · source ${escapeHtml(t.source)}` : ''}
    </div>
    ${depLinks ? `<div class="deps">deps: ${depLinks}</div>` : ''}
  </div>`;
}

function openModal(id) {
  const t = STATE.tasks.find(x => x.id === id);
  if (!t) return;
  const body = document.getElementById("modal-body");
  const deps = (t.dependencies||[]).map(d =>
    `<a href="#" onclick="openModal('${escapeAttr(d)}'); return false;">${escapeHtml(d)}</a>`).join(", ") || "<i>none</i>";

  const dependents = STATE.tasks.filter(x => (x.dependencies||[]).includes(t.id))
    .map(x => `<a href="#" onclick="openModal('${escapeAttr(x.id)}'); return false;">${escapeHtml(x.id)}</a>`)
    .join(", ") || "<i>none</i>";

  const history = (t.history||[]).slice().reverse().map(h =>
    `<div><b>${escapeHtml(h.date)}</b> &middot; ${escapeHtml(h.status)} &middot; ${escapeHtml(h.note||"")}</div>`
  ).join("") || "<i>no recorded changes</i>";

  body.innerHTML = `
    <h3>${escapeHtml(t.title)}</h3>
    <div class="meta">
      <span class="tid">${escapeHtml(t.id)}</span>
      <span class="dot ${t.archived?'archived':t.status}" style="margin-left:8px"></span>
      <b>${escapeHtml(t.status.toUpperCase())}</b>
      ${t.closure_date ? ` &middot; closed ${escapeHtml(t.closure_date)}` : ''}
      ${t.archived ? ` &middot; <b>ARCHIVED</b> ${t.archived_date||''}` : ''}
    </div>
    <div class="meta">
      <b>${escapeHtml(t.tier)}</b>
      ${t.section ? ` &middot; ${escapeHtml(t.section)}` : ''}
      ${t.effort ? ` &middot; ${escapeHtml(t.effort)}` : ''}
      ${t.source ? ` &middot; source ${escapeHtml(t.source)}` : ''}
    </div>
    <h4>Description</h4>
    <div>${escapeHtml(t.description||"(no description)")}</div>
    ${t.status_hint ? `<h4>Status hint (from roadmap source)</h4><div>${escapeHtml(t.status_hint)}</div>` : ''}
    <h4>Depends on</h4>
    <div>${deps}</div>
    <h4>Blocks (dependents)</h4>
    <div>${dependents}</div>
    <h4>History</h4>
    <div class="history">${history}</div>
    <h4>First seen / last seen</h4>
    <div class="meta">first ${escapeHtml(t.first_seen||"?")} &middot; last ${escapeHtml(t.last_seen||"?")}</div>
  `;
  document.getElementById("modal-backdrop").classList.add("open");
}

function closeModal() {
  document.getElementById("modal-backdrop").classList.remove("open");
}

document.getElementById("modal-backdrop").onclick = (e) => {
  if (e.target.id === "modal-backdrop") closeModal();
};
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

function render() {
  buildTree();
  renderCards();
}

document.getElementById("search").oninput = renderCards;
document.getElementById("filter-status").onchange = renderCards;
document.getElementById("show-archived").onchange = render;

render();
</script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Main

def main() -> None:
    if not ROADMAP_MD.exists():
        raise SystemExit(f"Roadmap not found: {ROADMAP_MD}")

    parsed = parse_roadmap()
    combined = parsed + [dict(t) for t in SYNTHETIC_TASKS]
    apply_overrides(combined)

    # Load prior state if present
    prev_state = {}
    if ATLAS_JSON.exists():
        try:
            prev_state = json.loads(ATLAS_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Warning: {ATLAS_JSON} unparsable; starting fresh history")

    state = merge_with_history(combined, prev_state)

    # Atomic writes: write to a sibling `.tmp` then rename. Prevents a partial
    # write from producing an unparsable JSON file on the next run (which would
    # trigger the `JSONDecodeError` branch and lose all prior history).
    _atomic_write_text(ATLAS_JSON, json.dumps(state, ensure_ascii=False, indent=2))
    _atomic_write_text(ATLAS_HTML, render_html(state))

    total = len(state["tasks"])
    by = {}
    for t in state["tasks"]:
        key = "archived" if t.get("archived") else t.get("status", "unknown")
        by[key] = by.get(key, 0) + 1
    breakdown = " · ".join(f"{k}={v}" for k, v in sorted(by.items()))
    print(f"project_atlas: {total} tasks ({breakdown})")
    print(f"  HTML: {ATLAS_HTML}")
    print(f"  JSON: {ATLAS_JSON}")

if __name__ == "__main__":
    main()
