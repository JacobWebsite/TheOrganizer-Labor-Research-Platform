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


@router.get("/api/system/data-freshness")
def system_data_freshness():
    """Return data source freshness with stale (>90 day) flag."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.data_freshness') AS rel")
            has_data_freshness = cur.fetchone()["rel"] is not None

            if has_data_freshness:
                cur.execute("""
                    SELECT
                        source_name,
                        latest_record_date,
                        table_name,
                        row_count,
                        last_refreshed
                    FROM data_freshness
                    ORDER BY source_name
                """)
                rows = cur.fetchall()
            else:
                cur.execute("""
                    SELECT
                        source_name,
                        date_range_end AS latest_record_date,
                        source_name AS table_name,
                        record_count AS row_count,
                        last_updated AS last_refreshed
                    FROM data_source_freshness
                    ORDER BY source_name
                """)
                rows = cur.fetchall()

    now = datetime.now(timezone.utc)
    sources = []
    for row in rows:
        last_refreshed = row.get("last_refreshed")
        stale = False
        if last_refreshed is not None:
            ref_dt = (
                last_refreshed
                if getattr(last_refreshed, "tzinfo", None) is not None
                else last_refreshed.replace(tzinfo=timezone.utc)
            )
            stale = (now - ref_dt).days > 90

        sources.append(
            {
                "source_name": row.get("source_name"),
                "latest_record_date": (
                    row.get("latest_record_date").isoformat()
                    if row.get("latest_record_date") is not None
                    else None
                ),
                "table_name": row.get("table_name"),
                "row_count": row.get("row_count"),
                "last_refreshed": (
                    last_refreshed.isoformat()
                    if last_refreshed is not None
                    else None
                ),
                "stale": stale,
            }
        )

    return {
        "sources": sources,
        "source_count": len(sources),
        "stale_count": sum(1 for s in sources if s["stale"]),
        "uses_fallback_table": not has_data_freshness,
    }
