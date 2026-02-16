#!/usr/bin/env python3
"""
Profile matching pipeline and related database query performance.
"""
import re
import time
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from scripts.matching.deterministic_matcher import DeterministicMatcher


def parse_execution_ms(explain_lines: List[str]) -> float:
    for line in explain_lines:
        m = re.search(r"Execution Time: ([0-9.]+) ms", line)
        if m:
            return float(m.group(1))
    return -1.0


def explain_query(cur, name: str, query: str) -> Dict:
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {query}")
    plan_rows = [row[0] for row in cur.fetchall()]
    return {
        "name": name,
        "query": query,
        "execution_ms": parse_execution_ms(plan_rows),
        "plan": plan_rows,
    }


def profile_database_queries(conn) -> List[Dict]:
    queries = [
        ("Employer lookup", "SELECT * FROM f7_employers_deduped WHERE employer_id = 'F000001'"),
        ("Match log query", "SELECT * FROM unified_match_log WHERE source_system = 'osha' LIMIT 1000"),
        ("Top occupations view", "SELECT * FROM v_industry_top_occupations LIMIT 1000"),
    ]

    results = []
    with conn.cursor() as cur:
        for name, query in queries:
            try:
                results.append(explain_query(cur, name, query))
            except Exception as exc:
                results.append(
                    {
                        "name": name,
                        "query": query,
                        "execution_ms": -1.0,
                        "plan": [f"ERROR: {exc}"],
                    }
                )
                conn.rollback()
    return results


def load_sample_osha_records(conn, limit: int) -> List[Dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                o.establishment_id::text AS id,
                o.estab_name AS name,
                o.site_state AS state,
                o.site_city AS city,
                o.site_zip AS zip,
                o.naics_code AS naics,
                NULL::text AS ein,
                o.site_address AS address
            FROM osha_establishments o
            LEFT JOIN osha_f7_matches m ON o.establishment_id = m.establishment_id
            WHERE m.establishment_id IS NULL
              AND o.estab_name IS NOT NULL
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "state": r[2],
            "city": r[3],
            "zip": r[4],
            "naics": r[5],
            "ein": r[6],
            "address": r[7],
        }
        for r in rows
    ]


def profile_exact_matching(conn, limit: int = 5000) -> Dict:
    records = load_sample_osha_records(conn, limit)
    run_id = f"profile-exact-{int(time.time())}"
    matcher = DeterministicMatcher(conn, run_id, "osha", dry_run=True, skip_fuzzy=True)

    start = time.perf_counter()
    matches = matcher.match_batch(records)
    elapsed = time.perf_counter() - start

    return {
        "records": len(records),
        "matches": len(matches),
        "seconds": round(elapsed, 3),
        "records_per_sec": round(len(records) / elapsed, 2) if elapsed > 0 else 0.0,
    }


def profile_fuzzy_matching(conn, limit: int = 1500) -> Dict:
    records = load_sample_osha_records(conn, limit)
    run_id = f"profile-fuzzy-{int(time.time())}"
    matcher = DeterministicMatcher(conn, run_id, "osha", dry_run=True, skip_fuzzy=False)

    start = time.perf_counter()
    matches = matcher.match_batch(records)
    elapsed = time.perf_counter() - start

    return {
        "records": len(records),
        "matches": len(matches),
        "seconds": round(elapsed, 3),
        "records_per_sec": round(len(records) / elapsed, 2) if elapsed > 0 else 0.0,
    }


def suggest_indexes(query_profiles: List[Dict]) -> List[str]:
    suggestions = []
    for prof in query_profiles:
        plan_text = "\n".join(prof["plan"])
        if "Seq Scan on unified_match_log" in plan_text:
            suggestions.append(
                "Add/verify index on unified_match_log(source_system, status, created_at) for frequent filtered scans."
            )
        if "Seq Scan on f7_employers_deduped" in plan_text and "employer_id" in prof["query"]:
            suggestions.append("Add/verify index or PK on f7_employers_deduped(employer_id).")
        if "Seq Scan on bls_industry_occupation_matrix" in plan_text:
            suggestions.append(
                "Add composite index on bls_industry_occupation_matrix(industry_code, percent_of_industry DESC)."
            )
    return sorted(set(suggestions))


def write_report(path: Path, exact: Dict, fuzzy: Dict, query_profiles: List[Dict], suggestions: List[str]) -> None:
    lines = []
    lines.append("# Performance Profile")
    lines.append("")
    lines.append("## Matching Throughput")
    lines.append("")
    lines.append(f"- Exact pass sample: {exact['records']} records, {exact['matches']} matches, {exact['seconds']}s ({exact['records_per_sec']} rec/s)")
    lines.append(f"- Fuzzy pass sample: {fuzzy['records']} records, {fuzzy['matches']} matches, {fuzzy['seconds']}s ({fuzzy['records_per_sec']} rec/s)")
    lines.append("")
    lines.append("## Query Timings")
    lines.append("")
    for q in query_profiles:
        lines.append(f"- {q['name']}: {q['execution_ms']} ms")
    lines.append("")
    lines.append("## Bottlenecks")
    lines.append("")
    worst = sorted([q for q in query_profiles if q["execution_ms"] >= 0], key=lambda x: x["execution_ms"], reverse=True)
    if worst:
        lines.append(f"- Slowest profiled query: {worst[0]['name']} ({worst[0]['execution_ms']} ms)")
    if fuzzy["seconds"] > exact["seconds"]:
        lines.append("- Fuzzy tier costs more than exact tiers; batch size and trigram selectivity are primary levers.")
    else:
        lines.append("- Exact tier dominates sample runtime; index warm-up and cache locality likely main factors.")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    if suggestions:
        for s in suggestions:
            lines.append(f"- {s}")
    else:
        lines.append("- No urgent missing-index signal from sampled plans.")
    lines.append("- Keep deterministic batch sizes between 1,000 and 5,000 records for stable throughput.")
    lines.append("- For fuzzy tiers, test trigram thresholds 0.45-0.55 to trade recall for speed.")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("Matching Pipeline Performance Profile")
    print("=" * 60)

    conn = get_connection()
    try:
        print("Profiling exact matching...")
        exact = profile_exact_matching(conn)
        print(f"  Exact: {exact}")

        print("Profiling fuzzy matching...")
        fuzzy = profile_fuzzy_matching(conn)
        print(f"  Fuzzy: {fuzzy}")

        print("Profiling database queries...")
        query_profiles = profile_database_queries(conn)
        for q in query_profiles:
            print(f"  {q['name']}: {q['execution_ms']} ms")

        suggestions = suggest_indexes(query_profiles)
        report_path = Path(__file__).resolve().parent.parent.parent / "docs" / "PERFORMANCE_PROFILE.md"
        write_report(report_path, exact, fuzzy, query_profiles, suggestions)
        print(f"\nReport written: {report_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
