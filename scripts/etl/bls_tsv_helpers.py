"""
Shared helpers for loading BLS tab-delimited data files (SOII, JOLTS, NCS).

Functions:
  parse_bls_lookup(filepath) -- read lookup file, return (headers, rows)
  load_lookup_table(conn, filepath, table_name, create_sql) -- TRUNCATE + load
  stream_bls_data(filepath) -- generator yielding parsed data rows
  load_data_file(conn, filepath, table_name, insert_sql, batch_size) -- batch load
"""
from __future__ import annotations

from datetime import datetime
from typing import Generator


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def parse_bls_lookup(filepath: str) -> tuple[list[str], list[list[str]]]:
    """Read a tab-delimited BLS lookup file.

    Returns (headers, rows) where each row is a list of stripped strings.
    Converts T/F selectable columns to Python bool strings ('true'/'false').
    """
    headers = []
    rows = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\r\n")
            parts = [p.strip() for p in line.split("\t")]
            if i == 0:
                headers = [h.lower() for h in parts]
                continue
            # Convert T/F selectable to bool
            sel_idx = None
            for j, h in enumerate(headers):
                if h == "selectable":
                    sel_idx = j
                    break
            if sel_idx is not None and sel_idx < len(parts):
                v = parts[sel_idx].upper()
                parts[sel_idx] = "true" if v == "T" else "false"
            rows.append(parts)
    return headers, rows


def load_lookup_table(conn, filepath: str, table_name: str, create_sql: str) -> int:
    """Create (IF NOT EXISTS) + TRUNCATE + bulk-load a BLS lookup table.

    Returns number of rows loaded.
    """
    from psycopg2.extras import execute_values

    headers, rows = parse_bls_lookup(filepath)
    if not rows:
        print(f"  [{ts()}] WARNING: no rows in {filepath}")
        return 0

    with conn.cursor() as cur:
        cur.execute(create_sql)
        cur.execute(f"TRUNCATE {table_name}")
        cols = ", ".join(headers[: len(rows[0])])
        placeholders = ", ".join(["%s"] * len(rows[0]))
        sql = f"INSERT INTO {table_name} ({cols}) VALUES %s ON CONFLICT DO NOTHING"
        # Trim rows to header width
        trimmed = [r[: len(headers)] for r in rows]
        execute_values(cur, sql, trimmed, page_size=1000)
    conn.commit()
    print(f"  [{ts()}] {table_name}: {len(rows):,} rows")
    return len(rows)


def stream_bls_data(
    filepath: str,
) -> Generator[tuple[str, int, str, float | None, str], None, None]:
    """Generator yielding (series_id, year, period, value, footnotes) from a BLS data file.

    Strips whitespace, skips header, converts value to float (None if empty/unparseable).
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # skip header
            line = line.rstrip("\r\n")
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            series_id = parts[0].strip()
            if not series_id:
                continue
            try:
                year = int(parts[1].strip())
            except (ValueError, IndexError):
                continue
            period = parts[2].strip()
            val_str = parts[3].strip()
            try:
                value = float(val_str) if val_str else None
            except ValueError:
                value = None
            footnotes = parts[4].strip() if len(parts) > 4 else ""
            yield (series_id, year, period, value, footnotes)


def load_data_file(
    conn,
    filepath: str,
    table_name: str,
    insert_sql: str,
    batch_size: int = 50000,
) -> int:
    """TRUNCATE + batch execute_values load from a BLS data file.

    insert_sql should be like:
      INSERT INTO table (series_id, year, period, value, footnote_codes) VALUES %s
        ON CONFLICT DO NOTHING

    Returns total rows loaded. Prints progress every 500K rows.
    """
    from psycopg2.extras import execute_values

    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {table_name}")
    conn.commit()

    total = 0
    batch = []
    with conn.cursor() as cur:
        for row in stream_bls_data(filepath):
            batch.append(row)
            if len(batch) >= batch_size:
                execute_values(cur, insert_sql, batch, page_size=5000)
                conn.commit()
                total += len(batch)
                batch = []
                if total % 500_000 == 0:
                    print(f"  [{ts()}] {table_name}: {total:,} rows loaded...")
        if batch:
            execute_values(cur, insert_sql, batch, page_size=5000)
            conn.commit()
            total += len(batch)

    print(f"  [{ts()}] {table_name}: {total:,} rows total")
    return total
