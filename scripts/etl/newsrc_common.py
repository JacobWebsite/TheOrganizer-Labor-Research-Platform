"""
Shared helpers for loading newly downloaded bulk data sources.
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = PROJECT_ROOT / "New Data sources 2_27"


def sanitize_column_names(raw_cols: Sequence[str]) -> List[str]:
    """
    Sanitize source headers into stable Postgres-safe snake_case names.
    """
    out: List[str] = []
    seen = set()
    for i, raw in enumerate(raw_cols):
        col = (raw or "").strip()
        if col.startswith("#"):
            col = col[1:]
        col = col.lower()
        col = re.sub(r"[^a-z0-9]+", "_", col)
        col = col.strip("_")
        if not col:
            col = f"col_{i+1}"
        if col[0].isdigit():
            col = f"c_{col}"

        base = col
        j = 2
        while col in seen:
            col = f"{base}_{j}"
            j += 1
        seen.add(col)
        out.append(col)
    return out


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_table_for_header(conn, table_name: str, header: Sequence[str], truncate: bool = False) -> List[str]:
    """
    Create table for a source header if missing, with all columns as TEXT.
    Optionally truncate existing rows.
    """
    cols = sanitize_column_names(header)
    table_ident = quote_ident(table_name)
    col_sql = ",\n    ".join(f"{quote_ident(c)} TEXT" for c in cols)

    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_ident} (
        {col_sql},
        _source_file TEXT,
        _loaded_at TIMESTAMP DEFAULT NOW()
    );
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
        if truncate:
            cur.execute(f"TRUNCATE TABLE {table_ident}")
    conn.commit()
    return cols


class HeaderInjectStream:
    """
    File-like wrapper that prepends a synthetic CSV header line to a body stream.
    Used when source files have no header or need normalized header text.
    """

    def __init__(self, header_line: str, body_stream):
        self._head = io.StringIO(header_line)
        self._body = body_stream

    def read(self, size: int = -1):
        chunk = self._head.read(size)
        if size == -1:
            return chunk + self._body.read()
        if len(chunk) == size:
            return chunk
        return chunk + self._body.read(size - len(chunk))


def copy_stream_to_table(
    conn,
    table_name: str,
    columns: Sequence[str],
    stream,
    delimiter: str = ",",
):
    """
    COPY CSV stream into table, then set source metadata in one pass by loading
    into a temp table first.
    """
    table_ident = quote_ident(table_name)
    cols_sql = ", ".join(quote_ident(c) for c in columns)

    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE _tmp_newsrc_load (LIKE {table_ident} INCLUDING DEFAULTS) ON COMMIT DROP")
        cur.copy_expert(
            f"COPY _tmp_newsrc_load ({cols_sql}) FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER '{delimiter}')",
            stream,
        )
        cur.execute(f"INSERT INTO {table_ident} ({cols_sql}) SELECT {cols_sql} FROM _tmp_newsrc_load")
    conn.commit()


def iter_zip_csv_entries(zip_path: Path) -> Iterator[Tuple[str, io.TextIOBase]]:
    """
    Yield (entry_name, text_stream) for each CSV file in a zip.
    Caller is responsible for consuming stream immediately.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                with zf.open(name, "r") as raw:
                    yield name, io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")


def open_gzip_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="")
