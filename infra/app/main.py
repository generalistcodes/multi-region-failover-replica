from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import docker
from fastapi import FastAPI


app = FastAPI(title="Local infra inspector", version="1.0.0")

_TTL_SECONDS = float(os.getenv("INFRA_CACHE_TTL_SECONDS", "2.0"))
_MAX_WORKERS = int(os.getenv("INFRA_MAX_WORKERS", "8"))

_lock = threading.Lock()
_cache: dict[str, Any] = {"snapshot": None, "ts": 0.0}


def _docker() -> docker.DockerClient:
    return docker.DockerClient(base_url="unix://var/run/docker.sock")


def _region_containers() -> dict[str, str]:
    # Region naming convention in this lab
    return {
        "region-a": "postgres-primary",
        "region-b": "postgres-replica",
        "region-c": "postgres-replica-c",
        "region-d": "postgres-replica-d",
        "region-e": "postgres-replica-e",
    }


def _ip_for_network(container_attrs: dict[str, Any], network_name: str) -> str | None:
    networks = (container_attrs.get("NetworkSettings") or {}).get("Networks") or {}
    net = networks.get(network_name) or {}
    ip = net.get("IPAddress")
    return ip or None


def _stats_snapshot(c) -> dict[str, Any]:
    s = c.stats(stream=False)
    mem_usage = (s.get("memory_stats") or {}).get("usage")
    mem_limit = (s.get("memory_stats") or {}).get("limit")

    cpu_total = ((s.get("cpu_stats") or {}).get("cpu_usage") or {}).get("total_usage")
    cpu_prev_total = ((s.get("precpu_stats") or {}).get("cpu_usage") or {}).get("total_usage")
    sys_total = (s.get("cpu_stats") or {}).get("system_cpu_usage")
    sys_prev_total = (s.get("precpu_stats") or {}).get("system_cpu_usage")
    online_cpus = (s.get("cpu_stats") or {}).get("online_cpus") or 0

    cpu_percent = None
    try:
        cpu_delta = float(cpu_total - cpu_prev_total)
        sys_delta = float(sys_total - sys_prev_total)
        if sys_delta > 0 and online_cpus > 0:
            cpu_percent = (cpu_delta / sys_delta) * online_cpus * 100.0
    except Exception:
        cpu_percent = None

    return {
        "cpu_percent": cpu_percent,
        "mem_usage_bytes": mem_usage,
        "mem_limit_bytes": mem_limit,
    }


def _region_snapshot(dc: docker.DockerClient, region: str, container_name: str) -> tuple[str, dict[str, Any]]:
    try:
        c = dc.containers.get(container_name)
        attrs = c.attrs
        mounts = attrs.get("Mounts") or []
        ports = (attrs.get("NetworkSettings") or {}).get("Ports") or {}

        return (
            region,
            {
                "region": region,
                "compose": {"service": container_name, "container": container_name},
                "network": {
                    "network": "failover-multi-az_regions",
                    "ip": _ip_for_network(attrs, "failover-multi-az_regions") or _ip_for_network(attrs, "regions"),
                },
                "ports": ports,
                "mounts": [
                    {
                        "type": m.get("Type"),
                        "name": m.get("Name"),
                        "source": m.get("Source"),
                        "destination": m.get("Destination"),
                    }
                    for m in mounts
                ],
                "resources": _stats_snapshot(c),
            },
        )
    except Exception as e:
        return (region, {"region": region, "error": str(e)})


def _compute_snapshot() -> dict[str, Any]:
    dc = _docker()
    out: dict[str, Any] = {"regions": {}}

    items = list(_region_containers().items())
    # Docker stats can be slow; parallelize to avoid N*latency.
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, max(1, len(items)))) as ex:
        futures = [ex.submit(_region_snapshot, dc, region, container_name) for region, container_name in items]
        for f in as_completed(futures):
            region, payload = f.result()
            out["regions"][region] = payload
    return out


@app.get("/infra")
def infra() -> dict[str, Any]:
    now = time.time()
    with _lock:
        snap = _cache.get("snapshot")
        ts = float(_cache.get("ts") or 0.0)
        if snap is not None and (now - ts) <= _TTL_SECONDS:
            return snap

    snap = _compute_snapshot()
    with _lock:
        _cache["snapshot"] = snap
        _cache["ts"] = now
    return snap

