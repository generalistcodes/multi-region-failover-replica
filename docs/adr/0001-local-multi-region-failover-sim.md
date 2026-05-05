## ADR 0001: Local multi-region failover simulator (Docker)

- **Status**: Accepted
- **Date**: 2026-05-05

### Context

We want a runnable local lab that mimics a multi-region architecture on a single laptop:

- Region A (primary)
- Region B (replica / failover)
- Manual and automatic failover
- Visible replication lag and request routing
- A UI to compare state between regions

Constraints:

- Must be easy to run with Docker Compose.
- Must be understandable: the goal is operational intuition (roles, health, lag, divergence).
- Avoid “magic”: failover should be explicit and observable.

### Decision

We model the system as:

- **Postgres streaming replication**:
  - `postgres-primary` (Region A) is the initial primary.
  - `postgres-replica` (Region B) is initialized via `pg_basebackup -R` and stays in recovery (hot-standby).
- **API router (FastAPI)**:
  - `POST /write` writes to the currently active region.
  - `GET /read` reads from the active region.
  - `GET /status` reports DB health, **role** (primary/standby), and lag.
  - `POST /admin/switch` flips the active region used by the API.
  - Debug endpoints allow reading/listing data from a specific region (`/admin/*`) to drive the UI.
- **Router service (LB simulation)**:
  - A small forwarding service providing a single stable endpoint to the API.
- **Failover controller**:
  - Polls `/status`.
  - If Region A is unhealthy for N checks and Region B is healthy, it:
    - runs `pg_ctl promote` in Region B
    - calls `/admin/switch?region=region-b`
- **Next.js UI**:
  - Displays Region A and Region B KV state side-by-side with polling.

### Rationale

- **Streaming replication** is the simplest “real” primary/standby model available locally.
- **Promotion** (`pg_ctl promote`) reflects how real failover works: standby becomes writable.
- **Role visibility** via `pg_is_in_recovery()` prevents confusion:
  - standby: `pg_is_in_recovery() = true`
  - primary: `pg_is_in_recovery() = false`
- A **separate controller** matches real-world patterns (e.g., Patroni-like behavior) without embedding orchestration logic into the API.
- The **UI** makes lag and convergence (or divergence) immediately visible.

### Consequences

- **After failover/promotion**, Region B is no longer a replica; replication stops and the regions can **diverge**.
  - This is expected and intentional for the lab.
  - Returning to “A primary → B standby” requires **re-seeding** (for this lab: reset volumes).
- Automatic failover is “best effort”:
  - It reacts to observed health from the API.
  - It does not attempt quorum / fencing; this is a local learning tool, not production HA.

### Operational notes

- **To demo replication convergence**: keep Region A as primary and Region B as standby (do not promote B).
- **To demo failover**:
  - stop Region A container
  - allow controller to promote B and switch the API active region
- **To reset back to streaming replication**:
  - `docker compose down -v && docker compose up -d --build`

### Diagrams

- Component + sequence diagrams are in:
  - `docs/diagrams/architecture.puml`
  - `docs/diagrams/failover-sequence.puml`
  - `docs/diagrams/failover-decision.puml`
  - `docs/diagrams/failover-state.puml`

