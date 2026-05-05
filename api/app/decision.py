from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from app.db import (
    healthcheck,
    is_in_recovery,
    replica_caught_up,
    replica_lag_seconds,
    replica_wal_lag_bytes,
)

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass
class DecisionMemory:
    # Tracks when we started observing primary unreachable (to enforce "N seconds" stability)
    primary_unreachable_since: float | None = None
    last_primary_reachable_ts: float | None = None


def _now() -> float:
    return time.time()


def _risk(can_failover: bool, checks: dict[str, bool], metrics: dict[str, Any]) -> RiskLevel:
    if can_failover:
        return "LOW"

    # High-risk conditions: promoting would likely lose data or create ambiguity.
    if not checks.get("no_split_brain", True):
        return "HIGH"
    if not checks.get("wal_fresh", True):
        return "HIGH"
    if not checks.get("replication_lag_ok", True):
        return "HIGH"

    # Medium if we're blocked but conditions aren't catastrophic (e.g. failure not stable yet).
    if not checks.get("failure_stable", True):
        return "MEDIUM"
    if not checks.get("replica_healthy", True):
        return "HIGH"

    return "MEDIUM"


def evaluate_decision(
    *,
    active_region: str,
    primary_conn,
    replica_conn,
    memory: DecisionMemory,
    failure_stable_seconds: float,
    wal_lag_bytes_threshold: int,
) -> dict[str, Any]:
    """
    Decision model for whether we should fail over from region-a -> region-b.
    """
    now = _now()

    primary_reachable = healthcheck(primary_conn)
    replica_healthy = healthcheck(replica_conn)

    primary_in_recovery = is_in_recovery(primary_conn)
    replica_in_recovery = is_in_recovery(replica_conn)

    # Split brain guard:
    # - if both DBs are reachable and both claim "primary", we must block automation.
    no_split_brain = not (primary_reachable and replica_healthy and (not primary_in_recovery) and (not replica_in_recovery))

    # Replica lag: prefer WAL LSN lag (bytes) because it stays correct when idle.
    wal_lag_bytes = replica_wal_lag_bytes(replica_conn)
    caught_up = replica_caught_up(replica_conn)
    replication_lag_ok = (wal_lag_bytes is not None) and (wal_lag_bytes <= wal_lag_bytes_threshold)
    wal_fresh = bool(caught_up) and replication_lag_ok

    # Keep the old seconds metric for UI observability only (not gating).
    lag_seconds = replica_lag_seconds(replica_conn) if replica_in_recovery else 0.0
    last_replay_delay = lag_seconds

    # Failure stability tracking.
    if primary_reachable:
        memory.primary_unreachable_since = None
        memory.last_primary_reachable_ts = now
        failure_duration = 0.0
        failure_stable = False
    else:
        if memory.primary_unreachable_since is None:
            memory.primary_unreachable_since = now
        failure_duration = now - memory.primary_unreachable_since
        failure_stable = failure_duration >= failure_stable_seconds

    checks = {
        "primary_reachable": primary_reachable,
        "replica_healthy": replica_healthy,
        "replication_lag_ok": replication_lag_ok,
        "wal_fresh": wal_fresh,
        "no_split_brain": no_split_brain,
        "failure_stable": failure_stable,
    }

    # Allowed only when:
    # - we are currently active on region-a (otherwise it's not a "failover" decision)
    # - primary is NOT reachable and that failure is stable
    # - replica is healthy
    # - replica is a standby (promotion target) OR primary is unreachable (still allow if replica already promoted)
    # - lag ok and wal fresh
    # - no split brain
    can_failover = (
        active_region == "region-a"
        and (not primary_reachable)
        and failure_stable
        and replica_healthy
        and replication_lag_ok
        and wal_fresh
        and no_split_brain
    )

    metrics = {
        "replication_lag_seconds": lag_seconds,
        "last_replay_delay": last_replay_delay,
        "wal_lag_bytes": wal_lag_bytes,
        "caught_up": caught_up,
        "failure_duration": failure_duration,
        "failure_stable_seconds": failure_stable_seconds,
        "wal_lag_bytes_threshold": wal_lag_bytes_threshold,
    }

    risk_level: RiskLevel = _risk(can_failover, checks, metrics)

    return {
        "can_failover": can_failover,
        "risk_level": risk_level,
        "checks": checks,
        "metrics": metrics,
    }

