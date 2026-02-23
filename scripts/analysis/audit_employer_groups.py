import argparse
import os
import sys
from collections import defaultdict

from psycopg2.extras import RealDictCursor

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover
    fuzz = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


def token_sort_ratio_01(a: str, b: str) -> float:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return 0.0
    if fuzz is not None:
        return float(fuzz.token_sort_ratio(a, b)) / 100.0
    # fallback
    sa = " ".join(sorted(a.lower().split()))
    sb = " ".join(sorted(b.lower().split()))
    return 1.0 if sa == sb else 0.0


def main():
    parser = argparse.ArgumentParser(description="Audit employer canonical grouping quality")
    parser.add_argument(
        "--output",
        default="docs/investigations/I8_employer_grouping_quality.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) AS c FROM employer_canonical_groups")
        total_groups = cur.fetchone()["c"]

        cur.execute(
            """
            SELECT
              SUM(CASE WHEN member_count = 1 THEN 1 ELSE 0 END) AS size_1,
              SUM(CASE WHEN member_count BETWEEN 2 AND 5 THEN 1 ELSE 0 END) AS size_2_5,
              SUM(CASE WHEN member_count BETWEEN 6 AND 10 THEN 1 ELSE 0 END) AS size_6_10,
              SUM(CASE WHEN member_count BETWEEN 11 AND 50 THEN 1 ELSE 0 END) AS size_11_50,
              SUM(CASE WHEN member_count > 50 THEN 1 ELSE 0 END) AS size_50_plus
            FROM employer_canonical_groups
            """
        )
        dist = cur.fetchone()

        cur.execute(
            """
            SELECT group_id, canonical_name, member_count
            FROM employer_canonical_groups
            ORDER BY member_count DESC, group_id
            LIMIT 20
            """
        )
        top20 = cur.fetchall()

        cur.execute(
            """
            WITH g AS (
                SELECT canonical_group_id AS group_id,
                       COUNT(DISTINCT SUBSTRING(naics FROM 1 FOR 2)) AS naics2_count
                FROM f7_employers_deduped
                WHERE canonical_group_id IS NOT NULL
                  AND naics IS NOT NULL
                  AND LENGTH(naics) >= 2
                GROUP BY canonical_group_id
                HAVING COUNT(DISTINCT SUBSTRING(naics FROM 1 FOR 2)) > 1
            )
            SELECT g.group_id, ecg.canonical_name, ecg.member_count, g.naics2_count
            FROM g
            JOIN employer_canonical_groups ecg ON ecg.group_id = g.group_id
            ORDER BY g.naics2_count DESC, ecg.member_count DESC
            LIMIT 10
            """
        )
        mixed_naics_groups = cur.fetchall()

        mixed_naics_members = {}
        for g in mixed_naics_groups:
            cur.execute(
                """
                SELECT employer_id, employer_name, naics
                FROM f7_employers_deduped
                WHERE canonical_group_id = %s
                ORDER BY employer_name
                LIMIT 50
                """,
                (g["group_id"],),
            )
            mixed_naics_members[g["group_id"]] = cur.fetchall()

        cur.execute(
            """
            SELECT g.group_id,
                   g.canonical_name,
                   f.employer_name,
                   f.name_standard
            FROM employer_canonical_groups g
            JOIN f7_employers_deduped f ON f.canonical_group_id = g.group_id
            ORDER BY g.group_id
            """
        )
        name_rows = cur.fetchall()

        by_group = defaultdict(list)
        canonical_name = {}
        for r in name_rows:
            gid = r["group_id"]
            canonical_name[gid] = r["canonical_name"]
            by_group[gid].append(r)

        weak_name_groups = []
        for gid, members in by_group.items():
            can = canonical_name.get(gid) or ""
            best = 0.0
            best_name = ""
            for m in members:
                nm = m.get("name_standard") or m.get("employer_name") or ""
                score = token_sort_ratio_01(can, nm)
                if score > best:
                    best = score
                    best_name = nm
            if best < 0.80:
                weak_name_groups.append((gid, can, best, best_name, len(members)))

        weak_name_groups.sort(key=lambda x: (x[2], -x[4]))

        cur.execute("SELECT COUNT(*) AS c FROM employer_canonical_groups WHERE member_count = 1")
        single_member_groups = cur.fetchone()["c"]

        cur.execute(
            """
            SELECT group_id, canonical_name, member_count, states
            FROM employer_canonical_groups
            WHERE CARDINALITY(states) >= 3
            ORDER BY CARDINALITY(states) DESC, member_count DESC
            """
        )
        cross_state_groups = cur.fetchall()

        cur.execute(
            """
            SELECT g.group_id,
                   g.canonical_name,
                   COUNT(uml.id) AS active_match_count
            FROM employer_canonical_groups g
            JOIN f7_employers_deduped f ON f.canonical_group_id = g.group_id
            LEFT JOIN unified_match_log uml
              ON uml.target_id = f.employer_id
             AND uml.status = 'active'
            GROUP BY g.group_id, g.canonical_name
            ORDER BY active_match_count DESC
            LIMIT 20
            """
        )
        top_impact_groups = cur.fetchall()

        lines = []
        lines.append("# I8 Employer Grouping Quality Audit")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Total canonical groups: **{total_groups:,}**")
        lines.append(f"- Single-member groups: **{single_member_groups:,}**")
        lines.append(f"- Groups spanning 3+ states: **{len(cross_state_groups):,}**")
        lines.append(f"- Groups with mixed 2-digit NAICS (sampled): **{len(mixed_naics_groups):,}**")
        lines.append(f"- Groups where canonical_name best token-sort match < 0.80: **{len(weak_name_groups):,}**")
        lines.append("")

        lines.append("## Group Size Distribution")
        lines.append("| Bucket | Groups |")
        lines.append("|---|---:|")
        lines.append(f"| 1 | {dist['size_1'] or 0:,} |")
        lines.append(f"| 2-5 | {dist['size_2_5'] or 0:,} |")
        lines.append(f"| 6-10 | {dist['size_6_10'] or 0:,} |")
        lines.append(f"| 11-50 | {dist['size_11_50'] or 0:,} |")
        lines.append(f"| 50+ | {dist['size_50_plus'] or 0:,} |")

        lines.append("")
        lines.append("## Top 20 Largest Groups")
        lines.append("| group_id | canonical_name | members |")
        lines.append("|---:|---|---:|")
        for r in top20:
            lines.append(f"| {r['group_id']} | {r['canonical_name']} | {r['member_count']:,} |")

        lines.append("")
        lines.append("## Mixed-NAICS Groups (2-digit conflicts)")
        for g in mixed_naics_groups:
            lines.append(
                f"### Group {g['group_id']} - {g['canonical_name']} (members={g['member_count']}, naics2_variants={g['naics2_count']})"
            )
            for m in mixed_naics_members[g["group_id"]]:
                lines.append(f"- `{m['employer_id']}` {m['employer_name']} | naics={m.get('naics')}")

        lines.append("")
        lines.append("## Canonical Name Mismatch Flags (best token_sort_ratio < 0.80)")
        lines.append("| group_id | canonical_name | best_member_name | best_score | member_count |")
        lines.append("|---:|---|---|---:|---:|")
        for gid, can, best, best_name, member_ct in weak_name_groups[:50]:
            lines.append(f"| {gid} | {can} | {best_name} | {best:.2f} | {member_ct:,} |")

        lines.append("")
        lines.append("## Cross-State Groups (3+ states)")
        lines.append("| group_id | canonical_name | member_count | state_count | states |")
        lines.append("|---:|---|---:|---:|---|")
        for r in cross_state_groups[:100]:
            st = r.get("states") or []
            lines.append(f"| {r['group_id']} | {r['canonical_name']} | {r['member_count']:,} | {len(st)} | {', '.join(st)} |")

        lines.append("")
        lines.append("## Most Impactful Groups by Active External Matches")
        lines.append("| group_id | canonical_name | active_matches |")
        lines.append("|---:|---|---:|")
        for r in top_impact_groups:
            lines.append(f"| {r['group_id']} | {r['canonical_name']} | {r['active_match_count']:,} |")

        lines.append("")
        lines.append("## Recommendations")
        lines.append("- Review mixed-NAICS groups first; prioritize splitting where industries are clearly incompatible.")
        lines.append("- Enforce canonical-name/member-name floor to catch poor representatives.")
        lines.append("- Re-evaluate single-member groups to determine whether grouping overhead is justified.")
        lines.append("- Keep high-impact groups clean first because they influence the most downstream scoring matches.")

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"Wrote {args.output}")
        print(f"Total groups: {total_groups:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
