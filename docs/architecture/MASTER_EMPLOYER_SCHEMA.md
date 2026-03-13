# Master Employer Schema Design

Date: 2026-02-21  
Scope: Task 2 (`scripts/etl/create_master_employers.sql`)  
Related upstream task: Task 1 (`scripts/etl/load_bmf_bulk.py`)

## Purpose

`master_employers` is the canonical employer universe used to expand beyond the current F-7-only scope. It supports non-union target discovery by integrating records from F-7, SAM, Mergent, BMF, OSHA, NLRB, and SEC.

The schema is designed to:
- Keep a stable internal key for all downstream joins.
- Preserve full source traceability.
- Support auditable merges and dedup decisions.
- Be seeded incrementally by wave without breaking earlier waves.

## Tables

1. `master_employers`
- One row per canonical employer entity.
- Stores best-known attributes (name, location, NAICS, employee count).
- Includes strategic booleans (`is_union`, `is_public`, `is_federal_contractor`, `is_nonprofit`).
- Tracks provenance with `source_origin`.

2. `master_employer_source_ids`
- Crosswalk from `master_id` to source-specific IDs (`f7`, `sam`, `mergent`, `bmf`, `osha`, `nlrb`, `sec`, etc.).
- Stores match confidence and match time for auditability.

3. `master_employer_merge_log`
- Immutable-style audit table for winner/loser merges.
- Captures reason and actor (`system` or user).

## Decision 1: Primary Key Strategy

Choice: `BIGSERIAL` synthetic key (`master_id`).

Rationale:
- Works cleanly across mixed source ID types (TEXT hashes, integers, EINs, UEIs, CIKs).
- Smaller/faster indexes and joins than UUID for this workload.
- Avoids dependence on source keys that can conflict or be recycled.
- Avoids hash-based PK collisions and unstable recomputation risk.

Why not UUID:
- Useful for distributed writes, but not needed for this single-DB architecture.
- Larger index/storage overhead with no near-term benefit.

Why not hash PK:
- Hashing canonical names/locations is brittle and not merge-friendly.
- Canonical values can improve over time; PK should not depend on mutable attributes.

## Decision 2: EIN Handling

Choice: `ein` is nullable and non-unique in `master_employers`.

Rationale:
- EIN is a strong identity key but not one-to-one with real-world employers.
- Parent/subsidiary structures can share EINs.
- Some EIN values can appear in legacy/reused contexts.

Implementation pattern:
- Keep `ein` as an attribute and index it for lookup speed.
- Preserve source-level identity in `master_employer_source_ids`.
- Dedup logic uses EIN as high-confidence evidence, not as a unique constraint.

## Decision 3: Name Resolution Priority

When source names disagree, select:
1. F-7 (`display_name`) when a confirmed F-7 entity exists.
2. SEC/Mergent legal-name style values when public-company linkage exists.
3. SAM legal/business names.
4. BMF organization names.
5. OSHA/NLRB names (often establishment-level or petition text variants).

Rules:
- `display_name`: best original-case name for UI.
- `canonical_name`: normalized matching form for dedup/search.
- Never discard source variants; keep all variants via source crosswalk context and future alias tables.

## Decision 4: Employee Count Reconciliation

Proposed priority for `employee_count`:
1. F-7 `latest_unit_size` for unionized entities (known unit size context).
2. Mergent/SEC-style company-level counts.
3. SAM counts (useful but may be stale/self-reported).
4. OSHA establishment counts (location-level; use cautiously).
5. Model estimates (future) tagged as estimated.

Rules:
- Track source in `employee_count_source`.
- Do not average incompatible levels (enterprise vs establishment).
- If multiple valid counts exist at same priority, select the most recent (when available) or highest-confidence source record.

## Decision 5: Seeding Order

Recommended order:
1. F-7 (Wave 0)
2. SAM
3. Mergent
4. BMF
5. OSHA
6. NLRB

Why:
- F-7 is already deduped and anchors existing product behavior.
- SAM + Mergent add stronger structured identifiers (UEI/DUNS/EIN) before high-noise sources.
- BMF adds very broad nonprofit coverage keyed by EIN (depends on Task 1 full load).
- OSHA and NLRB are high-volume, lower-identifier sources and should match against a richer existing graph first.

## Decision 6: Dedup Strategy by Wave

Each wave follows "match-first, insert-second":
1. High-confidence ID matches (EIN, DUNS, UEI, CIK).
2. Deterministic normalized name + geography.
3. Existing `unified_match_log` evidence where available.
4. Controlled fuzzy fallback with confidence threshold.
5. If no acceptable match, create new `master_employers` row and record source ID.

For all merges:
- Record event in `master_employer_merge_log`.
- Keep loser source IDs by re-pointing them to winner `master_id`.
- Do not delete provenance.

## Decision 7: Visibility Rules for Target Discovery

Default visibility threshold for "target" pages:
- Employer must have at least 2 scoring factors with data.

Reason:
- Reduces low-signal noise from large source-only imports.
- Aligns with redesign spec guidance for meaningful target surfacing.
- Keeps search broad while keeping target recommendations actionable.

## Indexing and Performance Notes

Required indexes implemented:
- `master_employers(ein)`
- `master_employers(state)`
- `master_employers(naics)`
- `master_employers` GIN trigram on `canonical_name`
- `master_employers(source_origin)`

Operational indexes added:
- `master_employer_source_ids(source_system, source_id)`
- `master_employer_source_ids(master_id)`
- merge-log winner/loser indexes

These support fast wave upserts, crosswalk joins, and investigative workflows.

## Wave 0 Seed Behavior

`create_master_employers.sql` includes a Wave 0 seed:
- Inserts from `f7_employers_deduped` into `master_employers`.
- Sets `is_union = TRUE`, `source_origin = 'f7'`.
- Carries `naics`, `city`, `state`, `zip`, and `latest_unit_size`.
- Inserts F-7 source IDs (`employer_id`) into `master_employer_source_ids` with confidence `1.0`.

Seed is idempotent with `NOT EXISTS` guards.

## Dependency Link to Task 1 (BMF Bulk Load)

Task 1 adds and populates BMF fields needed for Wave 4:
- `ein`
- `name_normalized`
- `is_labor_org`
- `group_exemption_number`

This enables BMF wave behavior:
- Match BMF to existing masters via EIN first.
- Flag likely labor organizations for exclusion/review in organizing target workflows.
- Preserve group-exemption structures for parent/subordinate nonprofit relationships.

## Out of Scope for This Task

- Running this SQL in the database.
- Building SAM/Mergent/BMF/OSHA/NLRB seeding scripts.
- Automatic merge execution logic.
- API changes for master-based search.

