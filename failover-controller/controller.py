from __future__ import annotations

import os
import subprocess
import time
from typing import Any

import requests


API = os.environ.get("API_BASE", "http://api:8080")
CHECK_INTERVAL_SECONDS = float(os.environ.get("CHECK_INTERVAL_SECONDS", "2"))


def sh(args: list[str]) -> str:
    cp = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return cp.stdout.decode("utf-8", errors="replace").strip()


def api_get(path: str) -> dict[str, Any]:
    r = requests.get(f"{API}{path}", timeout=1.5)
    r.raise_for_status()
    return r.json()


def api_switch(region: str) -> None:
    r = requests.post(f"{API}/admin/switch", params={"region": region}, timeout=2)
    r.raise_for_status()


def promote_replica() -> None:
    # Run promotion inside the replica container as postgres user.
    sh(
        [
            "docker",
            "exec",
            "-u",
            "postgres",
            "postgres-replica",
            "pg_ctl",
            "-D",
            "/var/lib/postgresql/data",
            "promote",
        ]
    )


def main() -> None:
    last_action_ts = 0.0

    while True:
        try:
            decision = api_get("/decision")
            can_failover = bool(decision.get("can_failover"))

            # Additional throttle to avoid repeated promotions/switches.
            if can_failover and (time.time() - last_action_ts) > 10:
                print("[controller] decision=can_failover, promoting replica and switching traffic...")
                promote_replica()
                api_switch("region-b")
                last_action_ts = time.time()
                print("[controller] failover complete, active_region=region-b")

        except Exception as e:
            # If API is temporarily unavailable, just keep trying.
            print(f"[controller] loop error: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

