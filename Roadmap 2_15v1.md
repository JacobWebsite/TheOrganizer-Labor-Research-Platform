# Roadmap 2_15v1

Date: 2026-02-15
Owner: Labor Research Platform

## 1) What this roadmap is based on

This plan is synthesized from the most recent Round 2 audits first, then older strategy docs and case studies.

Highest weight (most recent):
- docs/AUDIT_REPORT_ROUND2_CODEX.md (2026-02-14)
- docs/AUDIT_REPORT_ROUND2_CLAUDE.md (2026-02-14)
- audit comparison 2_015/three_audit_comparison_r2.md (2026-02-15)
- improving matching implementation_2_15.md (2026-02-15)
- docs/HISTORICAL_EMPLOYER_ANALYSIS.md (2026-02-15)

Secondary weight (older but still valuable):
- ROADMAP.md
- docs/LABOR_PLATFORM_ROADMAP_v12.md
- docs/EXTENDED_ROADMAP.md
- docs/MERGENT_SCORECARD_PIPELINE.md
- docs/AFSCME_NY_CASE_STUDY.md
- docs/TEAMSTERS_COMPARISON_REPORT.md
- docs/NY_DENSITY_MAP_METHODOLOGY.md
- Every Method for Classifying Busine.txt
- compass_artifact_wf-2776d45b-4978-4bbb-96b4-f597ce8c18cc_text_markdown.md
- afscme scrape/afscme_scraper_claude_code_prompt_v2_maxplan.md

## 2) Strategic goals for this version

1. Make the platform reliable enough for real organizer workflows (security, crashes, data trust).
2. Redesign the frontend to be meaningfully slimmer and easier to use.
3. Standardize matching so coverage and explainability both improve.
4. Preserve prior high-value ideas (comparables, enrichment sources, historical analysis) without bloating scope.

## 3) Resolved disagreements and decisions

### A) OSHA match rate: 47.3% vs 25.37%
- Conflict: Different denominators (current employers vs all employers including historical).
- Decision: Report both by default in docs and UI.
- Recommendation: Use current-employer rate for organizer workflow KPIs; use all-employer rate for data-quality audits.

### B) WHD: fixed vs still broken
- Conflict: F7->WHD improved strongly; Mergent->WHD remains weak.
- Decision: Mark status as IMPROVED, not FIXED.
- Recommendation: Prioritize F7 pathway for organizer UX; track Mergent pathway as secondary enrichment debt.

### C) 990 matching: fixed vs still broken
- Conflict: Dedicated 990 match table works; Mergent `matched_990_id` is sparse.
- Decision: Treat 990 pipeline as working in primary pathway.
- Recommendation: Deprecate or clearly label vestigial Mergent 990 column to avoid repeated misreads.

### D) Scoring unified vs dual
- Conflict: Backend unified; frontend still has dual-score remnants.
- Decision: Backend architecture is correct, frontend cleanup is still required.
- Recommendation: Elevate this to near-term frontend work because score inconsistency in UI erodes trust quickly.

### E) NLRB orphan rate interpretation
- Conflict: Some records are structurally unmatched by design (participants table broader than elections).
- Decision: Treat as both structural and product debt.
- Recommendation: Build a canonical NLRB bridge view and document exactly what is joinable vs not joinable.

### F) GLEIF "fixed" vs "still too large"
- Conflict: Public-facing slice improved, raw schema still heavy.
- Decision: Both are true.
- Recommendation: Keep only organizer-relevant derived GLEIF assets in primary environment; archive raw bulk schema outside hot path.

## 4) Where I disagree with prior docs

1. I disagree with treating frontend dual-score remnants as "low priority".
Reason: This is a trust and interpretation issue in the interface where organizers make decisions.
Recommendation: Move to Phase 2 (not backlog).

2. I disagree with keeping docs/README as a late cleanup task.
Reason: Current docs are materially wrong on startup, paths, and capability framing.
Recommendation: Fix docs in Phase 0 while stability fixes are being shipped.

3. I disagree with broad data-source expansion before matching standardization.
Reason: Adding sources before policy, confidence bands, and review queue will scale ambiguity.
Recommendation: Complete matching policy and provenance first, then expand integrations.

## 5) Product direction for a less bloated frontend

Design target: faster to understand, fewer surfaces, no contradictory scoring, and less file-level sprawl.

### New UX shape (streamlined)
- Keep 4 primary screens only:
  1. Territory Overview
  2. Employer Profile
  3. Union Profile
  4. Matching Review Queue (internal/admin)
- Move deep tools (`api_map.html`, `test_api.html`) to explicit "Developer Tools" area outside organizer flow.
- One canonical score component and one score explanation component shared across list/detail pages.

### Technical simplification
- Break `modals.js` into feature modules (`modal_employer.js`, `modal_union.js`, `modal_exports.js`, etc.).
- Replace inline HTML handlers with delegated listeners in JS.
- Adopt ES module boundaries for shared state and API clients.
- Enforce a single runtime config source for API base URL and environment flags.

### UX guardrails
- Remove duplicate or legacy score labels/scales.
- Show data freshness and match confidence in-context, not hidden.
- Prioritize default views to organizer questions: "where should we focus next" and "why this target".

### Frontend success criteria
- 30%+ reduction in organizer click path for top tasks (find top targets, open profile, export).
- 0 dual-score references in UI code or text.
- 0 hardcoded localhost URLs in user-facing assets.
- <= 1,200 lines per frontend file (soft cap).

## 6) Execution roadmap (6-week plan)

## Phase 0 (Week 1): Stability and trust blockers

Priority: Critical

- Fix density endpoint crashes.
- Enforce auth in non-dev mode (`LABOR_JWT_SECRET` required).
- Resolve 29 script connection bugs and set shared connection usage policy.
- Update docs/README startup and architecture references (`files/` not `frontend/`, current API pathing).
- Publish one metrics glossary clarifying denominator choices for match-rate reporting.

Exit criteria:
- Organizer-critical API smoke tests pass.
- Auth guardrail tested.
- Docs no longer contradict runtime entrypoints.

## Phase 1 (Week 1-2): Matching policy and evidence standardization

Priority: High

Use improving matching implementation_2_15.md as base:
- Standard match result schema across deterministic and probabilistic tiers.
- Confidence bands (`HIGH/MEDIUM/LOW`) and scenario-specific thresholds.
- Persist matched, rejected, and review-required outputs with evidence payload.
- Add run IDs and reproducibility fields for every match run.

Exit criteria:
- Every match row has method, tier, confidence band, evidence.
- Weekly QA report includes unresolved trend and false-positive sample rate.

## Phase 2 (Week 2-4): Frontend streamlining redesign

Priority: High

- Implement 4-screen IA and remove organizer-facing clutter.
- Split modal subsystem and eliminate inline event handlers.
- Remove all dual-score remnants and legacy scoring labels.
- Add confidence/freshness UI surfaces in list and profile views.
- Move developer utilities out of organizer path.

Exit criteria:
- Organizer usability test: top target to export flow in <= 5 minutes.
- No duplicate score scales in UI or API responses.
- Modular frontend structure documented and linted.

## Phase 3 (Week 4-5): Data integrity and historical employer strategy

Priority: Medium-High

- Investigate and resolve union file-number orphan backlog.
- Build NLRB canonical bridge view and joinability documentation.
- Execute historical-employer decision:
  - Merge confirmed duplicates from aggressive same-state matches.
  - Archive non-active historical rows with provenance preserved.
  - Keep optional reactivation path for trend-analysis workloads.

Exit criteria:
- Orphan counts reduced and tracked.
- Historical rows no longer create denominator confusion in core dashboards.

## Phase 4 (Week 5-6): Targeted enrichment and advanced scoring

Priority: Medium

- Continue Mergent/990/OSHA/WHD integration only through canonical match contracts.
- Add comparables layer (Gower-based similarity) to employer profile and score explanation.
- Pilot propensity-style organizing opportunity score as an experimental metric (not primary yet).
- Integrate AFSCME web-scrape workflow into reviewed ingest path.

Exit criteria:
- Comparables visible with transparent evidence fields.
- New enrichment does not bypass confidence policy.

## 7) Integration priorities kept from older roadmap docs

Retained in adjusted order:
1. H/K first (employer enrichment and OSHA reliability).
2. I/J second (990 and SEC/EDGAR) after match policy hardening.
3. L/M third (political and contract intelligence).
4. N/O last (news and predictive layer).

Why adjusted:
- Older sequence is directionally right, but now gated by match explainability and frontend clarity.

## 8) Governance and reporting cadence

Weekly:
- API smoke status (especially density, scorecard, detail endpoints).
- Match quality dashboard by scenario and confidence band.
- Frontend streamlining burn-down (file size, event handler migration, IA migration).
- Documentation drift check (generated facts vs markdown claims).

Every two weeks:
- Re-rank backlog by organizer value delivered, not just engineering convenience.

## 9) Immediate next 10 tasks

1. Patch density router crash points and add regression tests.
2. Enforce auth requirement outside dev profile.
3. Fix 29 script DB connection bugs.
4. Correct docs/README startup and architecture references.
5. Implement match result schema + confidence policy tables.
6. Add review queue tables and API scaffold.
7. Remove dual-score UI logic and labels.
8. Split `modals.js` into feature modules.
9. Replace inline handlers with delegated JS listeners.
10. Publish metrics glossary with denominator standards.

## 10) Definition of success for Roadmap 2_15v1

- Platform is secure-by-default for any non-local deployment.
- Organizer-critical routes are stable and tested.
- Frontend is measurably simpler and no longer internally contradictory.
- Matching is reproducible, explainable, and confidence-scored.
- Expansion work (Mergent/990/SEC/etc.) proceeds through a controlled data contract.
