## Local multi-region failover simulator (Docker)

This repo runs a **two-region Postgres** setup on one laptop:

<img width="1428" height="1038" alt="image" src="https://github.com/user-attachments/assets/a150a0f5-c326-4e84-87e2-bf4e76bc76c1" />

- **Download**: on GitHub, use the green **Code** button → **Download ZIP**, or download directly via `https://github.com/generalistcodes/failover-safe/archive/refs/heads/main.zip`

- **Region A**: `postgres-primary` (primary)
- **Region B**: `postgres-replica` (streaming replica, promotable on failover)
- **API**: FastAPI service that routes **writes/reads** to the currently active region and exposes **replication/health** status
- **Router (LB simulation)**: optional single entrypoint on `localhost:8090`
- **UI (Next.js)**: optional dashboard on `localhost:3000` showing both regions side-by-side
- **Failover controller**: optional loop that auto-promotes Region B and switches traffic

### What this simulates

- **Streaming replication** (WAL shipping) from Region A → Region B
- **Failover** by:
  - stopping Region A
  - promoting Region B to primary
  - switching the API’s active region
- **Replication lag visibility** via `/status`
- **Optional automatic failover** when Region A becomes unhealthy

### Architecture docs

- **ADR**: `docs/adr/0001-local-multi-region-failover-sim.md`
- **PlantUML diagrams**:
  - `docs/diagrams/architecture.puml`
  - `docs/diagrams/failover-sequence.puml`
  - `docs/diagrams/failover-decision.puml`
  - `docs/diagrams/failover-state.puml`

### Prereqs

- Docker + Docker Compose plugin
- `curl`
- `jq` (used by scripts for pretty JSON)

### Quick start

Make scripts executable:

```bash
chmod +x scripts/*.sh postgres/replica/bootstrap/*.sh postgres/primary/init/*.sh
```

Bring everything up:

```bash
./scripts/up.sh
```

Check status:

```bash
./scripts/status.sh
```

### Router (load balancer simulation)

If you prefer to hit a single stable endpoint, use the router:

- Router: `http://localhost:8090`
- It forwards `/write`, `/read`, `/status`, and `/admin/switch` to the API

Example:

```bash
curl -sS "http://localhost:8090/status" | jq .
curl -sS -X POST "http://localhost:8090/write" \
  -H "content-type: application/json" \
  -d '{"key":"hello","value":"via-router"}' | jq .
```

### UI dashboard (Next.js)

Bring it up and open the dashboard:

```bash
docker compose up -d --build ui
```

- UI: `http://localhost:3000`
- It shows **Region A vs Region B** side-by-side and polls every ~1s.
- To demo **replication** (A → B), make sure the **active region is `region-a`** and Region B is still a standby (i.e., before any promotion/failover).

### API endpoints

- **POST `/write`**: write a key/value to the active region

```bash
curl -sS -X POST "http://localhost:8080/write" \
  -H "content-type: application/json" \
  -d '{"key":"hello","value":"world"}' | jq .
```

- **GET `/read?key=...`**: read from the active region

```bash
curl -sS "http://localhost:8080/read?key=hello" | jq .
```

- **POST `/admin/switch?region=region-a|region-b`**: switch which region the API uses

```bash
curl -sS -X POST "http://localhost:8080/admin/switch?region=region-b" | jq .
```

- **GET `/status`**: observability endpoint (active region, DB health, replication status/lag)

```bash
curl -sS "http://localhost:8080/status" | jq .
```

### Failover simulation (Region A → Region B)

This does three things:

1. stops `postgres-primary` (region-a)
2. promotes `postgres-replica` (region-b) to accept writes
3. switches API routing to `region-b`

```bash
./scripts/failover-to-region-b.sh
```

After failover, reads and writes should continue via Region B:

```bash
curl -sS -X POST "http://localhost:8080/write" \
  -H "content-type: application/json" \
  -d '{"key":"after","value":"failover"}' | jq .
curl -sS "http://localhost:8080/read?key=after" | jq .
```

### Automatic failover (bonus)

The `failover-controller` container periodically calls `/status`. If:

- active region is `region-a`
- Region A DB is unhealthy for a few checks
- Region B DB is healthy

it will:

1. run `pg_ctl promote` inside `postgres-replica`
2. switch the API active region to `region-b`

To try it:

```bash
docker compose up -d --build
docker compose stop postgres-primary
docker compose logs -f failover-controller
```

### “Failback” note (getting Region A back)

Once Region B is promoted, the original Region A has diverged and **can’t safely rejoin** without re-seeding.
For this lab, `./scripts/failback-to-region-a.sh` simply resets everything to a clean state:

```bash
./scripts/failback-to-region-a.sh
```

### DB replication setup (what’s happening)

#### Primary (Region A)

`postgres-primary` is started with:

- `wal_level=replica`
- `max_wal_senders=10`
- `max_replication_slots=10`
- `hot_standby=on`

On first init it also:

- creates a **replication user** (`REPL_USER`, `REPL_PASSWORD`)
- appends `pg_hba.conf` rules to allow replication connections on the docker network

#### Replica (Region B)

On first start, `postgres-replica`:

- waits for primary to be ready
- runs `pg_basebackup -R ...` to clone the primary and write `primary_conninfo`
- creates a replication slot (`region_b_slot`)
- starts in hot-standby mode

### Consistency + replication lag

- `/status` reports:
  - `pg_stat_replication` from Region A (primary view)
  - `pg_last_xact_replay_timestamp()` on Region B (replica view), turned into **approx lag seconds**
- The API’s `POST /write` (when active is Region A) can **optionally fail** with HTTP 409 if the replica is too far behind (env `MAX_REPLICA_LAG_SECONDS`, set `<= 0` to disable).

### Ports

- API: `http://localhost:8080`
- Router: `http://localhost:8090`
- Infra inspector: `http://localhost:7070/infra`
- Region A Postgres: `localhost:54321`
- Region B Postgres: `localhost:54322`
- Region C Postgres: `localhost:54323`
- Region D Postgres: `localhost:54324`
- Region E Postgres: `localhost:54325`

### Tear down

```bash
docker compose down
```

To delete volumes (fresh cluster):

```bash
docker compose down -v
```

