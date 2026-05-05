from __future__ import annotations

import logging
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from psycopg_pool import ConnectionPool

from app.db import (
    connect,
    ensure_schema,
    healthcheck,
    is_in_recovery,
    list_kv,
    make_pool,
    primary_replication_status,
    read_kv,
    replica_caught_up,
    replica_lag_seconds,
    replica_wal_lag_bytes,
    write_kv,
)
from app.settings import settings
from app.state import read_active_region, write_active_region
from app.decision import DecisionMemory, evaluate_decision


def _configure_logging() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


_configure_logging()
log = structlog.get_logger()


app = FastAPI(title="Local Multi-Region Failover Simulator", version="1.0.0")

decision_memory = DecisionMemory()
_pools: dict[str, ConnectionPool] = {}


class WriteRequest(BaseModel):
    key: str
    value: str


def _dsns() -> dict[str, str]:
    dsns: dict[str, str] = {"region-a": settings.region_a_dsn, "region-b": settings.region_b_dsn}
    if settings.region_c_dsn:
        dsns["region-c"] = settings.region_c_dsn
    if settings.region_d_dsn:
        dsns["region-d"] = settings.region_d_dsn
    if settings.region_e_dsn:
        dsns["region-e"] = settings.region_e_dsn
    enabled = {r.strip().lower() for r in (settings.enabled_regions or "").split(",") if r.strip()}
    return {k: v for k, v in dsns.items() if k in enabled}


def _active_region() -> str:
    allowed = tuple(_dsns().keys())
    return read_active_region(settings.active_region_file, settings.default_active_region, allowed).value


def _conn_for_region(region: str):
    pool = _pools.get(region)
    if pool is None:
        # Fallback (should not happen after startup).
        return connect(_dsns()[region])
    return pool.connection()


@app.on_event("startup")
def _startup() -> None:
    # Create connection pools for all enabled regions.
    for region, dsn in _dsns().items():
        _pools[region] = make_pool(dsn)

    # Ensure schema exists on primary (replica will get it via streaming)
    with _conn_for_region("region-a") as c:
        ensure_schema(c)
    log.info("startup_complete", active_region=_active_region())


@app.on_event("shutdown")
def _shutdown() -> None:
    for p in _pools.values():
        try:
            p.close()
        except Exception:
            pass


@app.get("/status")
def status() -> dict[str, Any]:
    active = _active_region()
    out: dict[str, Any] = {"active_region": active, "regions": {}}

    # Health + lag
    for region in _dsns().keys():
        try:
            with _conn_for_region(region) as c:
                ok = healthcheck(c)
                in_recovery = is_in_recovery(c)
                role = "standby" if in_recovery else "primary"
                lag = replica_lag_seconds(c) if in_recovery else 0.0
                out["regions"][region] = {
                    "db_healthy": ok,
                    "role": role,
                    "in_recovery": in_recovery,
                    "replica_lag_seconds": lag,
                }
        except Exception as e:
            out["regions"][region] = {"db_healthy": False, "error": str(e)}

    # Primary view of replication
    try:
        with _conn_for_region("region-a") as c:
            out["replication"] = primary_replication_status(c)
    except Exception as e:
        out["replication_error"] = str(e)

    return out


@app.get("/dashboard")
def dashboard(limit: int = 20) -> dict[str, Any]:
    """
    Collapsed dashboard endpoint for the UI.

    Returns status + latest rows per enabled region in one request to minimize round-trips.
    """
    limit = max(1, min(200, limit))
    s = status()
    rows_by_region: dict[str, Any] = {}
    for region in _dsns().keys():
        try:
            with _conn_for_region(region) as c:
                rows_by_region[region] = list_kv(c, limit=limit)
        except Exception as e:
            rows_by_region[region] = {"error": str(e)}
    return {"status": s, "rows": rows_by_region, "limit": limit}


@app.get("/decision")
def decision() -> dict[str, Any]:
    """
    Failover decision endpoint: explains why failover is allowed/blocked.
    """
    active = _active_region()
    try:
        with _conn_for_region("region-a") as primary, _conn_for_region("region-b") as replica:
            return evaluate_decision(
                active_region=active,
                primary_conn=primary,
                replica_conn=replica,
                memory=decision_memory,
                failure_stable_seconds=settings.decision_failure_stable_seconds,
                wal_lag_bytes_threshold=settings.decision_wal_lag_bytes_threshold,
            )
    except Exception as e:
        # If we can't even evaluate, be conservative.
        return {
            "can_failover": False,
            "risk_level": "HIGH",
            "checks": {"evaluation_ok": False},
            "metrics": {"error": str(e)},
        }


@app.post("/write")
def write(req: WriteRequest) -> dict[str, Any]:
    active = _active_region()

    if active == "region-a":
        target_region = "region-a"
    else:
        # Writes to replica only make sense after promotion in a real system.
        # For this local simulator, we allow it, but we warn in logs.
        target_region = "region-b"

    # If writing to region-a, enforce standby WAL lag budget (bytes).
    if target_region == "region-a" and settings.max_replica_wal_lag_bytes > 0:
        try:
            with _conn_for_region("region-b") as replica:
                bytes_lag = replica_wal_lag_bytes(replica)
                caught_up = replica_caught_up(replica)
                if caught_up is False:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "replica_not_caught_up",
                            "caught_up": caught_up,
                        },
                    )
                if bytes_lag is not None and bytes_lag > settings.max_replica_wal_lag_bytes:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "replica_too_far_behind",
                            "replica_wal_lag_bytes": bytes_lag,
                            "max_replica_wal_lag_bytes": settings.max_replica_wal_lag_bytes,
                        },
                    )
        except HTTPException:
            raise
        except Exception as e:
            # If replica is down, this is a design choice: we still allow primary writes.
            log.warning("replica_lag_check_failed", error=str(e))

    with _conn_for_region(target_region) as c:
        row = write_kv(c, req.key, req.value)

    log.info("write", region=target_region, active_region=active, key=req.key)
    return {"region": target_region, "active_region": active, "row": row}


@app.get("/read")
def read(key: str) -> dict[str, Any]:
    active = _active_region()
    with _conn_for_region(active) as c:
        row = read_kv(c, key)

    log.info("read", region=active, active_region=active, key=key, found=bool(row))
    return {"region": active, "active_region": active, "row": row}


@app.post("/admin/switch")
def switch(region: str) -> dict[str, Any]:
    if region not in _dsns():
        raise HTTPException(status_code=400, detail=f"unknown region {region!r}")
    allowed = tuple(_dsns().keys())
    new_active = write_active_region(settings.active_region_file, region, allowed).value
    log.warning("active_region_switched", active_region=new_active)
    return {"active_region": new_active}


@app.get("/admin/kv")
def admin_kv(region: str, limit: int = 100) -> dict[str, Any]:
    """
    Debug endpoint for the UI: read KV rows from a specific region.
    """
    if region not in _dsns():
        raise HTTPException(status_code=400, detail=f"unknown region {region!r}")
    limit = max(1, min(500, limit))

    with _conn_for_region(region) as c:
        rows = list_kv(c, limit=limit)
    return {"region": region, "rows": rows}


@app.get("/admin/read")
def admin_read(region: str, key: str) -> dict[str, Any]:
    """
    Debug endpoint for the UI: read a key from a specific region.
    """
    if region not in _dsns():
        raise HTTPException(status_code=400, detail=f"unknown region {region!r}")
    with _conn_for_region(region) as c:
        row = read_kv(c, key)
    return {"region": region, "row": row}

