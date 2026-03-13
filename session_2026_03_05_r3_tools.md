# Session 2026-03-05: R3 Research Tools (R3-2, R3-3, R3-4, R3-8)

## Tools Implemented

### R3-2: search_corporate_structure
- Sources: crosswalk (25K), GLEIF ownership (499K links), CorpWatch hierarchy (3.5M relationships), SEC (517K)
- Returns: parent company, subsidiaries, unionized siblings, SEC info, public/private status
- CorpWatch relationship direction: source_cw_id = parent, target_cw_id = child
- top_parent_id on corpwatch_companies points to ultimate parent

### R3-3: search_employer_locations
- Sources: osha_establishments (1M), sam_entities, osha_f7_matches
- Deduplicates by city-state-zip, groups by state
- Walmart test: 40 locations across 20 states
- sam_entities has NO `business_types` column (removed from query)

### R3-4: search_leadership
- DB path: crosswalk -> SEC for public companies
- Web path: Gemini 2.5 Flash + Google Search grounding
- Returns: ceo, executives, board_members
- Gracefully returns empty when GOOGLE_API_KEY not set

### R3-8: search_state_enforcement
- DB path: nyc_debarment_list (210 rows, column: `prosecuting_agency` not `agency`)
- Web path: Gemini + Google Search for state-level violations and contracts
- Fixed: `_safe_dict` converts dates to ISO strings, so debarment date comparison uses string comparison

## Data Discoveries
- `corpwatch_relationships.relation_type` is NULL for all 3.5M rows (not useful for filtering)
- `sam_entities` has `entity_structure` but NOT `business_types`
- `nyc_debarment_list` columns: `prosecuting_agency` (not `agency`), no `reason` column
- SOS filings table does NOT exist (sos_filings) -- tool uses Gemini web search instead
- SEC proxy executives table does NOT exist -- leadership uses Gemini web search
- Research tool registry: now 36 tools total (was 32 before this session's additions)

## Bugs Fixed During Implementation
- CorpWatch parent/child query had swapped direction (source=parent, target=child, not reverse)
- `sam_entities.business_types` column doesn't exist -- removed from SELECT
- `nyc_debarment_list` uses `prosecuting_agency` not `agency`
- Date comparison in state_enforcement: `_safe_dict` converts dates to ISO strings, must compare string-to-string

## Codex Parallel Work
- Wrote task spec at `Start each AI/CODEX_TASKS_2026_03_05.md`
- Codex tasks: R3-6 (new dossier sections), 6-3 (comparison view), 6-6 (outcome feedback), 4-8 (tool effectiveness)
- Codex already modified `agent.py` _DOSSIER_SECTIONS (added corporate_structure, locations, leadership)
- Need to verify merge when Codex finishes (both edited agent.py)
