# Session: CBA Heading-First Classification + Fragment Fix (2026-03-19)

## Changes Made

### Rule Engine Overhaul (`scripts/cba/rule_engine.py`)
- Added `HeadingExclusion` dataclass and `heading_exclusions` field on `CategoryRules`
- New `_heading_excluded()` function: checks chunk title AND parent article title against exclusion patterns
- Heading affinity penalty replaces flat +0.10 boost: >= 0.5 -> +0.05, >= 0.3 -> 0.0, 0.0 -> -0.15
- Fragment merging in `_split_paragraphs()`: lowercase/conjunction starts merge into previous paragraph
- `_should_merge()` helper with ARTICLE/Section prefix detection to avoid merging headings
- Minimum paragraph length raised from 15 to 80 chars

### Parent Title Propagation (`scripts/cba/models.py`, `04_tag_category.py`)
- Added `parent_title: str | None = None` to `ArticleChunk`
- `get_chunks_and_spans()` builds article title lookup from structure_json, propagates to level-2+ chunks

### Config Updates (all 14 `config/cba_rules/*.json`)
- 5 categories with active heading exclusions: scheduling, wages, healthcare, management_rights, leave
- 9 categories with empty `heading_exclusions: []`

### New Script: `scripts/cba/reprocess_all.py`
- Batch reprocessor: deletes old provisions, re-runs rule engine, inserts new ones
- Supports `--dry-run` and `--cba-id N`
- Prints before/after comparison table

### Frontend: CBAReview.jsx
- "other" always appears at top of provision class dropdown
- Auto-selects "other" class when "other" category picked
- Amber notes field appears when "other" selected, required before save

### Tests: 12 new tests
- `TestHeadingExclusion`: 7 tests (grievance blocked, parent_title blocked, hours allowed, discipline blocked, helper, empty exclusions, parse all)
- `TestHeadingAffinityPenalty`: 2 tests (unrelated section penalty, hours section boost)
- `TestFragmentMerging`: 5 tests (lowercase, conjunction, uppercase, heading, section prefix)
- All 201 CBA tests pass (69 rule engine + 132 others)

## Key Findings
- Reprocess results: 874 -> 842 provisions (-32, -3.7%) across 24 contracts
- CBA 29 gained +9 (fragment merging recovered short provisions)
- CBA 35 and 39 each dropped -8 (most cross-category FPs eliminated)
- Possible `cba_reviews` CHECK constraint mismatch: allows `recategorize/delete/split/approve` but frontend sends `correct/reject`

## Roadmap Updates
- CBA Tool status updated: heading-first classification implemented, 842 provisions, ready for next review round
