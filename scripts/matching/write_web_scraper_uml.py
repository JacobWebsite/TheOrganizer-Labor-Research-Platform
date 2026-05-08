"""
Write scraper-extracted employer claims to unified_match_log.

Scope: `source_system='web_scraper'` UML rows. Each row represents a claim
that a specific union website mentioned a specific employer (e.g., an article
saying "Amazon workers join Teamsters"). The target is an f7_employers_deduped
row resolved via normalization + trigram matching.

This is Phase 4.2 from `~/.claude/plans/let-s-do-all-those-deep-kazoo.md`.

Phase 4.1 (directory-level union-to-OLMS UML) was reviewed and SKIPPED: UML
is strictly f7-targeted (2.8M rows, target_system='f7' exclusively), and
writing union-to-OLMS rows with a new target_system would pollute downstream
consumers. Instead the union detail endpoint (`/api/unions/{f_num}`) surfaces
`web_profile` directly from `web_union_profiles`. See the plan document for
the decision rationale.

This script writes rows only when `web_union_employers` is populated by a
Phase 3 rule-engine extraction run. At present (Phase 2 complete), that table
exists but is empty — a dry run will report 0 rows, which is the expected
state until extraction runs.

Usage:
    py -u scripts/matching/write_web_scraper_uml.py --dry-run
    py -u scripts/matching/write_web_scraper_uml.py --run-id 2026-04-21
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import psycopg2.extras as extras

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


SOURCE_SYSTEM = 'web_scraper'
TARGET_SYSTEM = 'f7'
MATCH_METHOD = 'WEB_SCRAPER_TRIGRAM'  # distinguishes the method; canonical in METHOD_LABELS
MATCH_TIER = 'deterministic'  # canonical UML value (alt: 'probabilistic')
DEFAULT_RUN_ID = f'web_scraper_{dt.date.today().isoformat()}'


def _confidence_band(score: float) -> str:
    """Match the platform convention used by splink_config.py."""
    if score >= 0.85:
        return 'HIGH'
    if score >= 0.70:
        return 'MEDIUM'
    return 'LOW'


def _candidate_count(conn, extraction_method: str | None) -> int:
    cur = conn.cursor()
    where = []
    params: list = []
    if extraction_method:
        where.append("extraction_method = %s")
        params.append(extraction_method)
    sql = "SELECT COUNT(*) FROM web_union_employers"
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    cur.execute(sql, params)
    return cur.fetchone()[0]


def fetch_candidate_rows(
    conn,
    extraction_method: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Return joinable (scraper_claim -> f7_employer) candidates for UML.

    Joins web_union_employers (scraper output, Phase 3) against
    f7_employers_deduped.name_standard with a trigram similarity filter.

    Supports LIMIT/OFFSET for batched processing (the trigram subqueries are
    per-row, so running all ~10K claims in one shot can stall).
    """
    cur = conn.cursor(cursor_factory=extras.RealDictCursor)

    # Is web_union_employers populated?
    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.tables
        WHERE table_name = 'web_union_employers'
    """)
    if cur.fetchone()['n'] == 0:
        print('[INFO] web_union_employers table does not exist yet. '
              'Run Phase 3 extraction first.')
        return []

    # Two LATERAL joins run the trigram lookup ONCE each per claim.
    # `m_state` is state-filtered (high precision); `m_xs` is cross-state
    # (broader fallback). build_uml_rows() prefers m_state when available.
    # Performance relies on gin_trgm_ops index `idx_f7_name_std_trgm` on
    # f7_employers_deduped.name_standard (added 2026-04-24).
    where = [
        "COALESCE(c.employer_name_clean, c.employer_name) IS NOT NULL",
        "length(COALESCE(c.employer_name_clean, c.employer_name)) >= 3",
    ]
    params: list = []
    if extraction_method:
        where.append("c.extraction_method = %s")
        params.append(extraction_method)

    sql = f"""
        SELECT
            c.id                          AS claim_id,
            c.web_profile_id,
            c.employer_name,
            c.employer_name_clean,
            c.confidence_score            AS rule_confidence,
            c.extraction_method           AS rule_id,
            c.source_element              AS rule_source,
            c.source_url,
            p.parent_union,
            p.state                       AS claim_state,
            p.f_num                       AS union_f_num,
            m_state.best_f7_id            AS state_best_f7_id,
            m_state.best_similarity       AS state_best_similarity,
            m_state.candidate_count       AS state_candidate_count,
            m_xs.best_f7_id               AS xs_best_f7_id,
            m_xs.best_similarity          AS xs_best_similarity,
            m_xs.candidate_count          AS xs_candidate_count
        FROM web_union_employers c
        JOIN web_union_profiles p ON p.id = c.web_profile_id
        LEFT JOIN LATERAL (
            -- State-filtered match: only f7 rows in the same state as the union local.
            -- Only evaluated when p.state is populated.
            SELECT f7.employer_id AS best_f7_id,
                   similarity(f7.name_standard,
                              COALESCE(c.employer_name_clean, c.employer_name)::text) AS best_similarity,
                   COUNT(*) OVER () AS candidate_count
            FROM f7_employers_deduped f7
            WHERE p.state IS NOT NULL
              AND f7.state = p.state
              AND f7.name_standard %% COALESCE(c.employer_name_clean, c.employer_name)::text
            ORDER BY similarity(f7.name_standard,
                                COALESCE(c.employer_name_clean, c.employer_name)::text) DESC
            LIMIT 1
        ) m_state ON TRUE
        LEFT JOIN LATERAL (
            -- Cross-state fallback: used when no state match (or state is NULL).
            SELECT f7.employer_id AS best_f7_id,
                   similarity(f7.name_standard,
                              COALESCE(c.employer_name_clean, c.employer_name)::text) AS best_similarity,
                   COUNT(*) OVER () AS candidate_count
            FROM f7_employers_deduped f7
            WHERE f7.name_standard %% COALESCE(c.employer_name_clean, c.employer_name)::text
            ORDER BY similarity(f7.name_standard,
                                COALESCE(c.employer_name_clean, c.employer_name)::text) DESC
            LIMIT 1
        ) m_xs ON TRUE
        WHERE {' AND '.join(where)}
        ORDER BY c.id
    """
    if limit is not None:
        sql += f' LIMIT {int(limit)} OFFSET {int(offset)}'
    cur.execute(sql, params)
    return cur.fetchall()


def build_uml_rows(candidates: list[dict], run_id: str) -> list[tuple]:
    """Convert candidate rows into UML tuples, filtering ambiguous cases.

    For each claim, prefer the state-matched f7 candidate when present.
    State-matched rows get a higher score (0.90 cap) than cross-state
    (0.80 cap), reflecting the location corroboration.
    """
    rows: list[tuple] = []
    skipped_ambiguous = 0
    skipped_low_sim = 0
    skipped_no_match = 0
    for c in candidates:
        # Pick match source: state-filtered preferred, else cross-state
        state_cnt = int(c.get('state_candidate_count') or 0)
        xs_cnt = int(c.get('xs_candidate_count') or 0)
        state_f7 = c.get('state_best_f7_id')
        xs_f7 = c.get('xs_best_f7_id')

        if state_f7 is not None and state_cnt > 0:
            match_source = 'state'
            best_f7 = state_f7
            best_cnt = state_cnt
            best_sim = float(c.get('state_best_similarity') or 0)
            score_cap = 0.90
        elif xs_f7 is not None and xs_cnt > 0:
            match_source = 'cross_state'
            best_f7 = xs_f7
            best_cnt = xs_cnt
            best_sim = float(c.get('xs_best_similarity') or 0)
            score_cap = 0.80
        else:
            skipped_no_match += 1
            continue

        if best_cnt > 5:
            skipped_ambiguous += 1
            continue
        if best_sim < 0.70:
            skipped_low_sim += 1
            continue

        score = min(best_sim, score_cap)
        band = _confidence_band(score)
        # Canonical UML status values: active|superseded|rejected|orphaned|inactive.
        # 'active' for single-candidate, 'rejected' for ambiguous 2-5.
        status = 'active' if best_cnt == 1 else 'rejected'
        evidence = {
            'rule_id': c['rule_id'],
            'rule_confidence': float(c['rule_confidence']) if c['rule_confidence'] is not None else None,
            'rule_source': c['rule_source'],
            'parent_union': c['parent_union'],
            'claim_state': c.get('claim_state'),
            'union_f_num': c['union_f_num'],
            'source_url': c['source_url'],
            'candidate_name': c['employer_name'],
            'trigram_similarity': best_sim,
            'trigram_candidate_count': best_cnt,
            'match_source': match_source,
            'review_reason': None if best_cnt == 1 else 'ambiguous_multi_candidate',
        }
        rows.append((
            run_id,
            SOURCE_SYSTEM,
            str(c['claim_id']),
            TARGET_SYSTEM,
            str(best_f7),
            MATCH_METHOD,
            MATCH_TIER,
            band,
            score,
            json.dumps(evidence),
            status,
        ))
    print(f'[BUILD] {len(rows)} UML rows prepared '
          f'(skipped: ambiguous={skipped_ambiguous}, low_sim={skipped_low_sim}, '
          f'no_match={skipped_no_match})')
    return rows


def write_rows(conn, rows: list[tuple]) -> int:
    if not rows:
        return 0
    cur = conn.cursor()
    extras.execute_values(
        cur,
        """INSERT INTO unified_match_log
               (run_id, source_system, source_id, target_system, target_id,
                match_method, match_tier, confidence_band, confidence_score,
                evidence, status)
           VALUES %s
           ON CONFLICT (run_id, source_system, source_id, target_id) DO NOTHING""",
        rows,
    )
    written = cur.rowcount
    conn.commit()
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true',
                    help='Plan the write without committing')
    ap.add_argument('--run-id', default=DEFAULT_RUN_ID,
                    help=f'UML run_id (default: {DEFAULT_RUN_ID})')
    ap.add_argument('--extraction-method',
                    help='Restrict to one extraction_method (e.g. rule_engine_v1)')
    ap.add_argument('--batch-size', type=int, default=500,
                    help='Rows per SELECT batch (default 500)')
    ap.add_argument('--max-rows', type=int,
                    help='Stop after processing N candidate rows (debug)')
    args = ap.parse_args()

    conn = get_connection()

    # Diagnostic breakdown
    cur = conn.cursor()
    cur.execute(
        """SELECT extraction_method, COUNT(*) FROM web_union_employers
           GROUP BY extraction_method ORDER BY 2 DESC"""
    )
    print('[INFO] web_union_employers by extraction_method:')
    for row in cur.fetchall():
        print(f'  {row[0]!r:25s} {row[1]}')

    total = _candidate_count(conn, args.extraction_method)
    if total == 0:
        print('[EXIT] no candidates to process')
        conn.close()
        return 0
    if args.max_rows:
        total = min(total, args.max_rows)

    print(f'[STEP 1] Processing {total} candidates in batches of {args.batch_size}'
          f'{f" (extraction_method={args.extraction_method})" if args.extraction_method else ""}')

    all_rows: list[tuple] = []
    processed = 0
    offset = 0
    while processed < total:
        batch_limit = min(args.batch_size, total - processed)
        cands = fetch_candidate_rows(
            conn,
            extraction_method=args.extraction_method,
            limit=batch_limit,
            offset=offset,
        )
        if not cands:
            break
        rows = build_uml_rows(cands, args.run_id)
        all_rows.extend(rows)
        processed += len(cands)
        offset += len(cands)
        print(f'  [{processed}/{total}] cumulative UML rows: {len(all_rows)}')

    if args.dry_run:
        print('[DRY RUN] sample UML rows:')
        for r in all_rows[:5]:
            print(' ',
                  {'source_id': r[2], 'target_id': r[4],
                   'band': r[7], 'score': r[8],
                   'status': r[10]})
        print(f'[DRY RUN] total rows that would be written: {len(all_rows)}')
        conn.close()
        return 0

    print(f'[STEP 2] Writing {len(all_rows)} rows to unified_match_log...')
    n_written = write_rows(conn, all_rows)
    print(f'[OK] inserted {n_written} new UML rows '
          f'(already-present ones skipped via ON CONFLICT)')
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
