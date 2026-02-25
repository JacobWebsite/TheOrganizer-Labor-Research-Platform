# I15 - Missing Source ID Linkages Root Cause

Generated: 2026-02-24 19:05:07

## UML Active Counts by Source

| Source System | Active Count |
| --- | --- |
| osha | 48,882 |
| crosswalk | 19,293 |
| sam | 14,522 |
| 990 | 13,254 |
| nlrb | 13,030 |
| whd | 10,991 |
| corpwatch | 3,275 |
| sec | 2,760 |
| gleif | 1,810 |
| mergent | 1,045 |
| bmf | 8 |

## Per-Source Analysis

### osha_f7_matches (source_system='osha')

| Metric | Count | Pct |
| --- | --- | --- |
| Total legacy records | 98,891 | 100% |
| Linked (active UML) | 43,998 | 44.5% |
| Orphaned (no active UML) | 54,893 | 55.5% |

**Orphan categorization:**

| Category | Count |
| --- | --- |
| Has superseded UML entry | 54,893 |
| Has rejected UML entry | 0 |
| No UML entry at all | 0 |

### whd_f7_matches (source_system='whd')

| Metric | Count | Pct |
| --- | --- | --- |
| Total legacy records | 19,462 | 100% |
| Linked (active UML) | 10,991 | 56.5% |
| Orphaned (no active UML) | 8,471 | 43.5% |

**Orphan categorization:**

| Category | Count |
| --- | --- |
| Has superseded UML entry | 8,471 |
| Has rejected UML entry | 0 |
| No UML entry at all | 0 |

### national_990_f7_matches (source_system='990')

| Metric | Count | Pct |
| --- | --- | --- |
| Total legacy records | 20,005 | 100% |
| Linked (active UML) | 13,215 | 66.1% |
| Orphaned (no active UML) | 6,790 | 33.9% |

**Orphan categorization:**

| Category | Count |
| --- | --- |
| Has superseded UML entry | 6,790 |
| Has rejected UML entry | 0 |
| No UML entry at all | 0 |

### sam_f7_matches (source_system='sam')

**ERROR:** column lt.sam_id does not exist
LINE 7:                   AND uml.source_id = lt.sam_id::text
                                              ^


Table may not exist or has schema issues.

### sec_f7_matches (source_system='sec')

**ERROR:** current transaction is aborted, commands ignored until end of transaction block


Table may not exist or has schema issues.

## Sample Orphaned Records

### osha_f7_matches orphan samples

**Superseded UML entries:**

| source_id | target_id |
| --- | --- |
| 66f1e78d5b488379ec92411b4cb7cbe5 | a88c1db153884dee |
| 66f35266dabfaf4d59b990c6ff372f4d | a017d38af2759a67 |
| 6706c660205d5290f4f3d50b126e917d | b9935fa4aa4f6191 |
| 6709d178efed8f95970cbe7207033d11 | 0c9581cd903d9f48 |
| 670e53646b6ff46a96fcd0bef111c7a5 | 1f3dedd04ff06a5e |

### whd_f7_matches orphan samples

**Superseded UML entries:**

| source_id | target_id |
| --- | --- |
| 1532634 | 07a828fff2228aa1 |
| 1412917 | 3d8d8672a7ad8dac |
| 1839687 | 5b57f99c0953a7c5 |
| 1667082 | 4b8ab844e22e128c |
| 1778036 | d42006f7b4f82382 |

### national_990_f7_matches orphan samples

**Superseded UML entries:**

| source_id | target_id |
| --- | --- |
| 100002 | f3e11b3525a6073e |
| 100079 | 66cd0e2ddf5ff582 |
| 100087 | f6fda2da9f68c021 |
| 100261 | 1660f0c1d12b49a6 |
| 100308 | fedaf55ba5a03cdc |

## Summary

| Table | Source | Total | Linked | Orphaned | Orphan % |
| --- | --- | --- | --- | --- | --- |
| osha_f7_matches | osha | 98,891 | 43,998 | 54,893 | 55.5% |
| whd_f7_matches | whd | 19,462 | 10,991 | 8,471 | 43.5% |
| national_990_f7_matches | 990 | 20,005 | 13,215 | 6,790 | 33.9% |

## Root Cause Analysis

Orphaned legacy match records fall into three categories:

1. **Superseded matches** -- The deterministic matcher re-ran with `--rematch-all`, creating new UML entries and marking old ones as superseded. The legacy table was not updated to reflect the new source_id/target_id pair.
2. **Rejected matches** -- Quality audits (e.g., trigram floor rejection) marked UML entries as rejected, but the corresponding legacy table row was not deleted.
3. **Pre-UML matches** -- Legacy tables were populated before the unified_match_log existed. These matches were never backfilled into UML.

## Recommendations

1. **Backfill missing UML entries** -- For 'no UML entry' orphans, create active UML rows from legacy tables using `rebuild_legacy_tables.py`.
2. **Clean superseded orphans** -- Delete legacy rows whose UML entry is superseded (the new match takes precedence).
3. **Clean rejected orphans** -- Delete legacy rows whose UML entry is rejected (quality floor failure).
4. **Add FK constraints** -- Consider adding foreign key relationships between legacy tables and UML to prevent future drift.
5. **Deprecate legacy tables** -- Long-term, stop writing to legacy match tables and use UML as the single source of truth.
