"""Shared ETL logging utility. Writes run metadata to data_refresh_log."""

from db_config import get_connection


def log_etl_run(source_name, table_name, row_count, status, script_path,
                error_message=None, duration_seconds=None):
    """Log an ETL run to data_refresh_log (separate connection, autocommit)."""
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO data_refresh_log
          (source_name, table_name, row_count, status, script_path, error_message, duration_seconds)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (source_name, table_name, row_count, status, script_path, error_message, duration_seconds))
    cur.close()
    conn.close()
