from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import psycopg
import psycopg.rows
from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class DbInfo:
    region: str
    dsn: str


def connect(dsn: str) -> psycopg.Connection:
    # Backwards-compatible connector (still used in some call sites).
    # autocommit keeps demo simple for single-row writes.
    return psycopg.connect(dsn, autocommit=True, row_factory=psycopg.rows.dict_row)


def make_pool(dsn: str) -> ConnectionPool:
    # Small pool: the UI polls frequently; reuse connections to reduce churn.
    return ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=6,
        kwargs={"autocommit": True, "row_factory": psycopg.rows.dict_row},
    )


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kv (
          k TEXT PRIMARY KEY,
          v TEXT NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def write_kv(conn: psycopg.Connection, key: str, value: str) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO kv(k, v) VALUES (%s, %s)
        ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, updated_at = now()
        RETURNING k, v, updated_at
        """,
        (key, value),
    ).fetchone()
    return dict(row)


def read_kv(conn: psycopg.Connection, key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT k, v, updated_at FROM kv WHERE k = %s", (key,)).fetchone()
    return dict(row) if row else None


def list_kv(conn: psycopg.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT k, v, updated_at
        FROM kv
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def healthcheck(conn: psycopg.Connection) -> bool:
    try:
        conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False


def is_in_recovery(conn: psycopg.Connection) -> bool:
    return bool(conn.execute("SELECT pg_is_in_recovery() AS v").fetchone()["v"])


def primary_replication_status(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """
    Runs on primary. Shows streaming replication status (if any).
    """
    rows = conn.execute(
        """
        SELECT
          application_name,
          client_addr::text AS client_addr,
          state,
          sync_state,
          write_lag::text AS write_lag,
          flush_lag::text AS flush_lag,
          replay_lag::text AS replay_lag
        FROM pg_stat_replication
        ORDER BY application_name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def replica_lag_seconds(conn: psycopg.Connection) -> float | None:
    """
    Runs on replica. Returns seconds behind primary, if computable.
    """
    # If not in recovery, it's a promoted primary.
    in_recovery = conn.execute("SELECT pg_is_in_recovery() AS v").fetchone()["v"]
    if not in_recovery:
        return 0.0

    # Approximate lag: now - last replayed transaction timestamp.
    ts = conn.execute("SELECT pg_last_xact_replay_timestamp() AS ts").fetchone()["ts"]
    if ts is None:
        return None
    return max(0.0, time.time() - ts.timestamp())


def replica_wal_lag_bytes(conn: psycopg.Connection) -> int | None:
    """
    Runs on a standby. Returns WAL lag in bytes (receive_lsn - replay_lsn).

    This stays near-zero when caught up, even when the system is idle (unlike
    pg_last_xact_replay_timestamp-based "seconds since last replay").
    """
    in_recovery = conn.execute("SELECT pg_is_in_recovery() AS v").fetchone()["v"]
    if not in_recovery:
        return 0

    row = conn.execute(
        """
        SELECT
          pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())::bigint AS bytes_lag
        """
    ).fetchone()
    return int(row["bytes_lag"]) if row and row["bytes_lag"] is not None else None


def replica_caught_up(conn: psycopg.Connection) -> bool | None:
    """
    True when standby has replayed everything it received.
    """
    in_recovery = conn.execute("SELECT pg_is_in_recovery() AS v").fetchone()["v"]
    if not in_recovery:
        return True
    row = conn.execute(
        """
        SELECT (pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn()) AS caught_up
        """
    ).fetchone()
    return bool(row["caught_up"]) if row and row["caught_up"] is not None else None

