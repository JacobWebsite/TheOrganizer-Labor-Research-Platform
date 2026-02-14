"""
Database connection pool singleton.
"""
from contextlib import contextmanager

import psycopg2  # noqa: F401 -- needed by pool
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from .config import DB_CONFIG

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            cursor_factory=RealDictCursor,
            **DB_CONFIG,
        )
    return _pool


@contextmanager
def get_db():
    """Yield a connection from the pool; auto-commit on success, rollback on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def release_db(conn):
    try:
        _get_pool().putconn(conn)
    except Exception:
        pass


def get_raw_connection():
    """Get a raw psycopg2 connection (not from pool, no RealDictCursor).
    Caller must close it. Useful for operations needing autocommit mode."""
    import psycopg2
    return psycopg2.connect(**DB_CONFIG)
