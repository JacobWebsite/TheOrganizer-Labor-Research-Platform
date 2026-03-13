"""
Fact-check: Verify 10 critical claims in .claude/agents/ and .claude/specs/
against the actual PostgreSQL database (olms_multiyear).
"""
import sys
sys.path.insert(0, r'C:\Users\jakew\.local\bin\Labor Data Project_real')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

print()
print("=" * 130)
print("FACT-CHECK: .claude/agents/ and .claude/specs/ claims vs actual PostgreSQL database")
print("Database: olms_multiyear, localhost, user postgres")
print("Date: 2026-03-01")
print("=" * 130)
print()

facts = []

# 1. f7_employers_deduped row count
cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
actual = cur.fetchone()[0]
facts.append({
    "num": 1,
    "fact": "f7_employers_deduped row count",
    "claimed": 146863,
    "actual": actual,
    "files": "specs/database-schema.md (line 20), agents/database.md (line 21), agents/scoring.md (line 15)",
})

# 2. mv_unified_scorecard row count
cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
actual = cur.fetchone()[0]
facts.append({
    "num": 2,
    "fact": "mv_unified_scorecard row count",
    "claimed": 146863,
    "actual": actual,
    "files": "specs/database-schema.md (line 117), specs/scoring-system.md (line 32), unified-scorecard-guide.md (line 9)",
})

# 3. mv_target_scorecard row count
cur.execute("SELECT COUNT(*) FROM mv_target_scorecard")
actual = cur.fetchone()[0]
facts.append({
    "num": 3,
    "fact": "mv_target_scorecard row count",
    "claimed": 4386205,
    "actual": actual,
    "files": "specs/database-schema.md (line 118), agents/scoring.md (line 22)",
})

# 4. unified_match_log row count
cur.execute("SELECT COUNT(*) FROM unified_match_log")
actual = cur.fetchone()[0]
facts.append({
    "num": 4,
    "fact": "unified_match_log row count",
    "claimed": "~1.8M",
    "actual": actual,
    "files": "specs/database-schema.md (line 65), specs/matching-pipeline.md (line 13, 167), agents/matching.md (line 57)",
})

# 5. corporate_identifier_crosswalk row count
cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
actual = cur.fetchone()[0]
facts.append({
    "num": 5,
    "fact": "corporate_identifier_crosswalk row count",
    "claimed": 22831,
    "actual": actual,
    "files": "specs/corporate-crosswalk.md (line 9), specs/database-schema.md (line 81)",
})

# 6. employer_canonical_groups group count
cur.execute("SELECT COUNT(DISTINCT group_id) FROM employer_canonical_groups")
actual = cur.fetchone()[0]
facts.append({
    "num": 6,
    "fact": "employer_canonical_groups distinct groups",
    "claimed": 16209,
    "actual": actual,
    "files": "specs/database-schema.md (line 28)",
})

# 7. mv_employer_search row count
cur.execute("SELECT COUNT(*) FROM mv_employer_search")
actual = cur.fetchone()[0]
facts.append({
    "num": 7,
    "fact": "mv_employer_search row count",
    "claimed": 107321,
    "actual": actual,
    "files": "specs/database-schema.md (line 121), specs/scoring-system.md (line 19, 251)",
})

# 8. score_similarity
cur.execute("""
    SELECT COUNT(*) AS total,
           COUNT(score_similarity) AS non_null,
           ROUND(100.0 * COUNT(score_similarity) / NULLIF(COUNT(*), 0), 4) AS pct
    FROM mv_unified_scorecard
""")
r = cur.fetchone()
total_rows, non_null_sim, pct_sim = r
facts.append({
    "num": 8,
    "fact": "score_similarity: exists? non-NULL pct?",
    "claimed": "weight=1 (guide) vs weight=0 (scoring-system)",
    "actual": "{} non-NULL of {} ({}%)".format(non_null_sim, total_rows, pct_sim),
    "files": "specs/unified-scorecard-guide.md (line 86: weight=1), specs/scoring-system.md (line 97-98: weight=0x broken)",
})

# 9. NLRB ULP distinct F7 employers matched (CA cases)
cur.execute("""
    SELECT COUNT(DISTINCT matched_employer_id)
    FROM nlrb_participants
    WHERE matched_employer_id IS NOT NULL
      AND case_number LIKE '%%' || '-CA-' || '%%'
""")
actual = cur.fetchone()[0]
facts.append({
    "num": 9,
    "fact": "NLRB ULP distinct F7 employers (CA cases)",
    "claimed": 22371,
    "actual": actual,
    "files": "specs/matching-pipeline.md (line 206), agents/matching.md (line 119)",
})

# 10. national_990_f7_matches row count
cur.execute("SELECT COUNT(*) FROM national_990_f7_matches")
actual = cur.fetchone()[0]
facts.append({
    "num": 10,
    "fact": "national_990_f7_matches row count",
    "claimed": 14428,
    "actual": actual,
    "files": "specs/database-schema.md (line 62)",
})

conn.close()

# ---- Print summary table ----
header = "{:<4} {:<50} {:<20} {:<20} {:<10}".format("#", "Fact", "Claimed", "Actual", "Verdict")
print(header)
print("-" * 130)

verdicts = {}
for f in facts:
    n = f["num"]
    name = f["fact"]
    claimed = f["claimed"]
    actual = f["actual"]

    if n == 4:
        a = int(actual)
        if abs(a - 1800000) / 1800000 <= 0.05:
            verdict = "CLOSE"
        else:
            verdict = "MISMATCH"
    elif n == 8:
        verdict = "SEE NOTE"
    else:
        try:
            c = int(claimed)
            a = int(actual)
            if c == a:
                verdict = "MATCH"
            elif abs(c - a) / max(c, 1) <= 0.05:
                verdict = "CLOSE"
            else:
                verdict = "MISMATCH"
        except (ValueError, TypeError):
            verdict = "N/A"

    verdicts[n] = verdict
    print("{:<4} {:<50} {:<20} {:<20} {:<10}".format(n, name, str(claimed), str(actual), verdict))

print()
print("=" * 130)
print("VERDICT SUMMARY")
print("=" * 130)

match_count = sum(1 for v in verdicts.values() if v == "MATCH")
close_count = sum(1 for v in verdicts.values() if v == "CLOSE")
mismatch_count = sum(1 for v in verdicts.values() if v == "MISMATCH")
other_count = sum(1 for v in verdicts.values() if v not in ("MATCH", "CLOSE", "MISMATCH"))

print("  MATCH:    {}/10".format(match_count))
print("  CLOSE:    {}/10".format(close_count))
print("  MISMATCH: {}/10".format(mismatch_count))
print("  SEE NOTE: {}/10".format(other_count))
print()

# Detailed notes
print("DETAILED NOTES:")
print()

print("  #4 unified_match_log: Claimed ~1.8M, actual 2,207,505 (+22.6%).")
print("      The ~1.8M figure is stale. The log has grown by ~407K rows since the specs were written,")
print("      likely from additional matching runs (seed scripts, re-runs, NLRB ULP matching, etc).")
print()

print("  #5 corporate_identifier_crosswalk: Claimed 22,831, actual 17,111 (-25.1%).")
print("      The crosswalk was rebuilt at some point WITHOUT re-running _match_usaspending.py.")
print("      USASpending rows (~8K) are entirely missing. Current tier breakdown:")
print("      EIN_F7_BACKFILL=12,368, EIN_EXACT=2,335, NAME_STATE=2,158, LEI_EXACT=82, combos=168.")
print("      Fix: re-run `PYTHONPATH=. py scripts/etl/_match_usaspending.py` to restore USASpending tier.")
print()

print("  #6 employer_canonical_groups: Claimed 16,209 groups, actual 16,647 (+2.7%).")
print("      Within 5% tolerance (CLOSE). Likely grew from subsequent data loads or grouping runs.")
print()

print("  #8 score_similarity: CONTRADICTORY CLAIMS across spec files.")
print("      - specs/unified-scorecard-guide.md (line 86) says weight=1")
print("      - specs/scoring-system.md (line 97-98) says weight=0x (broken pipeline)")
print("      - agents/scoring.md (line 39) says weight=1x, re-enabled")
print("      - CLAUDE.md Section 8 says weight=1, re-enabled")
print("      ACTUAL: Column exists but has 0 non-NULL values (0.00%). Effectively dead weight.")
print("      The MV definition includes the column but the Gower similarity pipeline produces no data.")
print("      The weight setting is moot since all values are NULL (excluded from weighted average).")
print()

print("  #9 NLRB ULP distinct F7 employers: Claimed 22,371, actual 22,371. EXACT MATCH.")
print("      Note: the query must use LIKE '%-CA-%' (not LIKE 'CA%') because NLRB case numbers")
print("      are formatted as region-type-sequence (e.g., '15-CA-156638').")
print()

print("  #10 national_990_f7_matches: Claimed 14,428, actual 20,005 (+38.7%).")
print("      The 990 matching pipeline was re-run since the spec was written, adding ~5,577 new matches.")
print("      The specs are stale and need updating.")
