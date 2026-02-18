from datetime import datetime, timezone

from fastapi import APIRouter

from ..database import get_db

router = APIRouter()


@router.get("/api/health")
def system_health_check():
    """Basic API health check with DB pool connectivity."""
    db_ok = False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                db_ok = cur.fetchone() is not None
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "db": db_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/stats")
def system_stats():
    """Read-only platform stats summary."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM f7_employers_deduped")
            total_employers = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) AS total FROM mv_organizing_scorecard")
            total_scorecard_rows = cur.fetchone()["total"]

            cur.execute("""
                SELECT source_system, COUNT(*) AS match_count
                FROM unified_match_log
                WHERE status = 'active'
                GROUP BY source_system
                ORDER BY source_system
            """)
            matches_by_source = cur.fetchall()

            cur.execute("""
                SELECT started_at
                FROM match_runs
                ORDER BY started_at DESC NULLS LAST
                LIMIT 1
            """)
            last_run = cur.fetchone()

    return {
        "total_employers": total_employers,
        "total_scorecard_rows": total_scorecard_rows,
        "match_counts_by_source": matches_by_source,
        "last_match_run_timestamp": (
            last_run["started_at"].isoformat()
            if last_run and last_run.get("started_at")
            else None
        ),
    }

