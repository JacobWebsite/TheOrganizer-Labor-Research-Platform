"""
Advisory lock utility for pipeline scripts.

Prevents concurrent execution of scoring/matching pipeline steps that would
corrupt materialized views (DROP+CREATE is not atomic across scripts).

Usage:
    from scripts.scoring._pipeline_lock import pipeline_lock

    conn = get_connection()
    with pipeline_lock(conn, 'unified_scorecard'):
        # DROP + CREATE MV logic here
        ...
"""
import contextlib

# Stable lock IDs — never reuse or renumber.
LOCK_IDS = {
    'employer_data_sources': 800001,
    'unified_scorecard': 800002,
    'target_data_sources': 800003,
    'target_scorecard': 800004,
    'search_mv': 800005,
    'gower_similarity': 800006,
    'scorecard_mv': 800007,
    'employer_groups': 800008,
    'nlrb_patterns': 800009,
    'wage_outliers': 800010,
}


@contextlib.contextmanager
def pipeline_lock(conn, name):
    """Acquire a PostgreSQL advisory lock. Fails fast if another script holds it."""
    lock_id = LOCK_IDS[name]
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
    acquired = cur.fetchone()[0]
    if not acquired:
        raise RuntimeError(
            f"Pipeline lock '{name}' (id={lock_id}) is held by another process. "
            f"Cannot run concurrently."
        )
    try:
        yield
    finally:
        try:
            # If the transaction is in a failed state, rollback first so we can
            # execute the unlock. Advisory locks are session-level and survive rollback.
            if conn.closed == 0:
                conn.rollback()
                cur.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
        except Exception:
            pass  # Best-effort unlock; lock is released when connection closes anyway
