"""
Generate a comprehensive project metrics report.

Queries live DB for table/MV row counts, master_employers breakdown,
script counts per directory, and test count. Outputs to docs/PROJECT_METRICS.md.

Usage:
    py scripts/maintenance/generate_project_metrics.py
"""

import os
import sys
import subprocess
import glob
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from psycopg2.extras import RealDictCursor
from db_config import get_connection

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'docs', 'PROJECT_METRICS.md')


def get_db_metrics(cur):
    """Query database for key metrics."""
    metrics = {}

    # Database size
    cur.execute('SELECT pg_size_pretty(pg_database_size(current_database())) AS size')
    metrics['db_size'] = cur.fetchone()['size']

    # Object counts
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE c.relkind = 'r') AS tables,
            COUNT(*) FILTER (WHERE c.relkind = 'v') AS views,
            COUNT(*) FILTER (WHERE c.relkind = 'm') AS materialized_views
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
    """)
    row = cur.fetchone()
    metrics['tables'] = row['tables']
    metrics['views'] = row['views']
    metrics['materialized_views'] = row['materialized_views']

    # Index count and size
    cur.execute("""
        SELECT COUNT(*) AS cnt,
               pg_size_pretty(SUM(pg_relation_size(c.oid))) AS total_size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'i'
    """)
    idx = cur.fetchone()
    metrics['indexes'] = idx['cnt']
    metrics['index_size'] = idx['total_size']

    return metrics


def get_mv_counts(cur):
    """Get row counts for all materialized views."""
    cur.execute("""
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'm'
        ORDER BY c.relname
    """)
    mv_names = [r['relname'] for r in cur.fetchall()]

    mv_counts = {}
    for mv in mv_names:
        cur.execute(f'SELECT COUNT(*) AS cnt FROM {mv}')
        mv_counts[mv] = cur.fetchone()['cnt']

    return mv_counts


def get_top_tables(cur, limit=30):
    """Get top tables by estimated row count."""
    cur.execute("""
        SELECT c.relname AS table_name,
               c.reltuples::bigint AS est_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'm')
          AND c.reltuples > 0
        ORDER BY c.reltuples DESC
        LIMIT %s
    """, (limit,))
    return [(r['table_name'], r['est_rows']) for r in cur.fetchall()]


def get_uml_breakdown(cur):
    """Get unified_match_log breakdown by source and status."""
    cur.execute("""
        SELECT source_system,
               COUNT(*) FILTER (WHERE status = 'active') AS active,
               COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
               COUNT(*) FILTER (WHERE status = 'superseded') AS superseded,
               COUNT(*) AS total
        FROM unified_match_log
        GROUP BY source_system
        ORDER BY active DESC
    """)
    return cur.fetchall()


def get_master_employers(cur):
    """Get master_employers breakdown by source_origin."""
    try:
        cur.execute("""
            SELECT source_origin, COUNT(*) AS cnt
            FROM master_employers
            GROUP BY source_origin
            ORDER BY cnt DESC
        """)
        return cur.fetchall()
    except Exception:
        return None


def get_master_source_ids(cur):
    """Get master_employer_source_ids breakdown."""
    try:
        cur.execute("""
            SELECT source_system, COUNT(*) AS cnt
            FROM master_employer_source_ids
            GROUP BY source_system
            ORDER BY cnt DESC
        """)
        return cur.fetchall()
    except Exception:
        return None


def get_script_counts():
    """Count scripts per directory."""
    dirs = [
        'scripts/etl', 'scripts/matching', 'scripts/scoring',
        'scripts/ml', 'scripts/maintenance', 'scripts/scraper',
        'scripts/analysis', 'scripts/setup', 'scripts/performance'
    ]
    counts = {}
    for d in dirs:
        full_path = os.path.join(PROJECT_ROOT, d)
        py_files = glob.glob(os.path.join(full_path, '*.py'))
        counts[d] = len(py_files)

    # Sub-directories
    for sub in ['scripts/matching/adapters', 'scripts/matching/matchers']:
        full_path = os.path.join(PROJECT_ROOT, sub)
        py_files = glob.glob(os.path.join(full_path, '*.py'))
        counts[sub] = len(py_files)

    return counts


def get_test_count():
    """Run pytest --collect-only to count tests."""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests/', '--collect-only', '-q'],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=60
        )
        # Look for "X tests collected" or "X test(s) collected" in output
        for line in result.stdout.splitlines():
            if 'selected' in line or 'collected' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit():
                        return int(part)
        # Fallback: count lines that look like test items
        count = 0
        for line in result.stdout.splitlines():
            if '::test_' in line or '::Test' in line:
                count += 1
        return count if count > 0 else None
    except Exception:
        return None


def generate_markdown():
    """Generate the full metrics markdown."""
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        db_metrics = get_db_metrics(cur)
        mv_counts = get_mv_counts(cur)
        top_tables = get_top_tables(cur)
        uml_breakdown = get_uml_breakdown(cur)
        master_employers = get_master_employers(cur)
        master_source_ids = get_master_source_ids(cur)
        script_counts = get_script_counts()
        test_count = get_test_count()

        lines = []
        lines.append('# Project Metrics -- Labor Relations Research Platform')
        lines.append(f'\n**Auto-generated:** {timestamp}')
        lines.append(f'**Script:** `py scripts/maintenance/generate_project_metrics.py`')
        lines.append('')
        lines.append('---')
        lines.append('')

        # Section 1: Database Overview
        lines.append('## Database Overview')
        lines.append('')
        lines.append(f'| Metric | Value |')
        lines.append(f'|--------|-------|')
        lines.append(f'| Database size | {db_metrics["db_size"]} |')
        lines.append(f'| Tables | {db_metrics["tables"]} |')
        lines.append(f'| Views | {db_metrics["views"]} |')
        lines.append(f'| Materialized views | {db_metrics["materialized_views"]} |')
        lines.append(f'| Indexes | {db_metrics["indexes"]} ({db_metrics["index_size"]}) |')
        lines.append('')

        # Section 2: Materialized Views
        lines.append('## Materialized Views')
        lines.append('')
        lines.append('| View | Rows |')
        lines.append('|------|------|')
        for name, count in sorted(mv_counts.items(), key=lambda x: -x[1]):
            lines.append(f'| `{name}` | {count:,} |')
        lines.append('')

        # Section 3: Top Tables
        lines.append('## Top 30 Tables by Row Count (estimated)')
        lines.append('')
        lines.append('| Table | Est. Rows |')
        lines.append('|-------|-----------|')
        for name, est in top_tables:
            lines.append(f'| `{name}` | {est:,} |')
        lines.append('')

        # Section 4: Unified Match Log
        lines.append('## Unified Match Log Breakdown')
        lines.append('')
        uml_total = sum(r['total'] for r in uml_breakdown)
        lines.append(f'**Total UML rows:** {uml_total:,}')
        lines.append('')
        lines.append('| Source | Active | Rejected | Superseded | Total |')
        lines.append('|--------|--------|----------|------------|-------|')
        for r in uml_breakdown:
            lines.append(f'| {r["source_system"]} | {r["active"]:,} | {r["rejected"]:,} | {r["superseded"]:,} | {r["total"]:,} |')
        lines.append('')

        # Section 5: Master Employers
        if master_employers:
            lines.append('## Master Employers')
            lines.append('')
            total = sum(r['cnt'] for r in master_employers)
            lines.append(f'**Total master_employers:** {total:,}')
            lines.append('')
            lines.append('| Source Origin | Count |')
            lines.append('|-------------|-------|')
            for r in master_employers:
                lines.append(f'| {r["source_origin"]} | {r["cnt"]:,} |')
            lines.append('')

        if master_source_ids:
            total_ids = sum(r['cnt'] for r in master_source_ids)
            lines.append(f'**Total master_employer_source_ids:** {total_ids:,}')
            lines.append('')
            lines.append('| Source System | Count |')
            lines.append('|-------------|-------|')
            for r in master_source_ids:
                lines.append(f'| {r["source_system"]} | {r["cnt"]:,} |')
            lines.append('')

        # Section 6: Script Counts
        lines.append('## Script Inventory')
        lines.append('')
        lines.append('| Directory | Count |')
        lines.append('|-----------|-------|')
        total_scripts = 0
        total_pipeline = 0
        for d, c in sorted(script_counts.items()):
            lines.append(f'| `{d}` | {c} |')
            total_scripts += c
            if 'analysis' not in d and 'adapters' not in d and 'matchers' not in d:
                total_pipeline += c
        lines.append(f'| **Total** | **{total_scripts}** |')
        lines.append('')

        # Section 7: Tests
        if test_count:
            lines.append('## Tests')
            lines.append('')
            lines.append(f'**Total tests collected:** {test_count}')
            lines.append('')

        # Section 8: MV Freshness
        lines.append('## MV Freshness')
        lines.append('')
        lines.append('Approximate last rebuild time based on `pg_stat_user_tables.last_analyze`.')
        lines.append('')
        lines.append('| Materialized View | Last Analyze |')
        lines.append('|-------------------|-------------|')
        cur.execute("""
            SELECT s.relname, s.last_analyze
            FROM pg_stat_user_tables s
            JOIN pg_class c ON c.relname = s.relname
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'm'
            ORDER BY s.relname
        """)
        for row in cur.fetchall():
            mv_name = row['relname']
            last_analyze = row['last_analyze']
            ts = str(last_analyze) if last_analyze else '(never)'
            lines.append(f'| `{mv_name}` | {ts} |')
        lines.append('')

        # Section 9: Score Factor Coverage
        lines.append('## Score Factor Coverage')
        lines.append('')
        lines.append('Percentage of employers with each scoring factor in mv_unified_scorecard.')
        lines.append('')

        factor_cols = [
            'score_osha', 'score_nlrb', 'score_whd', 'score_contracts',
            'score_union_proximity', 'score_financial', 'score_industry_growth',
            'score_size', 'score_similarity',
        ]
        try:
            cur.execute('SELECT COUNT(*) AS cnt FROM mv_unified_scorecard')
            total_employers = cur.fetchone()['cnt']
            lines.append(f'**Total employers:** {total_employers:,}')
            lines.append('')
            lines.append('| Factor | Count | Pct |')
            lines.append('|--------|-------|-----|')
            for fc in factor_cols:
                cur.execute(f'SELECT COUNT(*) AS cnt FROM mv_unified_scorecard WHERE {fc} IS NOT NULL')
                cnt = cur.fetchone()['cnt']
                pct = (100.0 * cnt / total_employers) if total_employers else 0
                lines.append(f'| `{fc}` | {cnt:,} | {pct:.1f}% |')
            lines.append('')
        except Exception:
            lines.append('*(mv_unified_scorecard not available)*')
            lines.append('')

        # Section 10: Score Distribution
        lines.append('## Score Distribution')
        lines.append('')
        try:
            cur.execute("""
                SELECT
                    ROUND(MIN(weighted_score)::numeric, 2) AS mn,
                    ROUND(AVG(weighted_score)::numeric, 2) AS avg,
                    ROUND(MAX(weighted_score)::numeric, 2) AS mx
                FROM mv_unified_scorecard
                WHERE weighted_score IS NOT NULL
            """)
            dist = cur.fetchone()
            lines.append(f'| Metric | Value |')
            lines.append(f'|--------|-------|')
            lines.append(f'| Min weighted_score | {dist["mn"]} |')
            lines.append(f'| Avg weighted_score | {dist["avg"]} |')
            lines.append(f'| Max weighted_score | {dist["mx"]} |')
            lines.append('')

            lines.append('**Tier Distribution:**')
            lines.append('')
            lines.append('| Tier | Count | Pct |')
            lines.append('|------|-------|-----|')
            cur.execute("""
                SELECT score_tier, COUNT(*) AS cnt
                FROM mv_unified_scorecard
                GROUP BY score_tier
                ORDER BY CASE score_tier
                    WHEN 'Priority' THEN 1
                    WHEN 'Strong' THEN 2
                    WHEN 'Promising' THEN 3
                    WHEN 'Moderate' THEN 4
                    WHEN 'Low' THEN 5
                    ELSE 6
                END
            """)
            tier_total = total_employers if total_employers else 1
            for row in cur.fetchall():
                pct = (100.0 * row['cnt'] / tier_total)
                lines.append(f'| {row["score_tier"]} | {row["cnt"]:,} | {pct:.1f}% |')
            lines.append('')
        except Exception:
            lines.append('*(mv_unified_scorecard not available)*')
            lines.append('')

        # Section 11: Data Freshness
        lines.append('## Data Freshness')
        lines.append('')
        lines.append('Latest dates per data source.')
        lines.append('')
        lines.append('| Source | Latest Date |')
        lines.append('|--------|------------|')

        freshness_queries = [
            ('OSHA (inspections)', "SELECT MAX(last_inspection_date) AS d FROM osha_establishments"),
            ('WHD (findings)', "SELECT MAX(findings_end_date) AS d FROM whd_cases"),
            ('NLRB (elections)', "SELECT MAX(election_date) AS d FROM nlrb_elections"),
            ('NLRB (cases)', "SELECT MAX(latest_date) AS d FROM nlrb_cases"),
            ('SAM (registrations)', "SELECT MAX(registration_date) AS d FROM sam_entities"),
            ('Form 990', "SELECT MAX(tax_period) AS d FROM irs_990_data"),
        ]
        for label, query in freshness_queries:
            try:
                cur.execute(query)
                val = cur.fetchone()['d']
                lines.append(f'| {label} | {val} |')
            except Exception:
                conn.rollback()
                lines.append(f'| {label} | (table not found) |')
        lines.append('')

        return '\n'.join(lines)

    finally:
        cur.close()
        conn.close()


def main():
    md = generate_markdown()
    print(md)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'\nWritten to {OUTPUT_PATH}')

    # Also write to PLATFORM_STATUS.md
    status_path = os.path.join(PROJECT_ROOT, 'docs', 'PLATFORM_STATUS.md')
    with open(status_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'Written to {status_path}')


if __name__ == '__main__':
    main()
