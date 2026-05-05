#!/usr/bin/env bash
set -euo pipefail

export PGPASSWORD="${REPL_PASSWORD:-}"

PRIMARY_HOST="${PRIMARY_HOST:-postgres-primary}"
PRIMARY_PORT="${PRIMARY_PORT:-5432}"
REPL_USER="${REPL_USER:-replicator}"
SLOT_NAME="${SLOT_NAME:-region_b_slot}"

if [[ -z "${REPL_PASSWORD:-}" ]]; then
  echo "REPL_PASSWORD must be set" >&2
  exit 1
fi

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  echo "Replica: initializing from primary via pg_basebackup..."
  if [[ -n "$(ls -A "${PGDATA}" 2>/dev/null || true)" ]]; then
    echo "Replica: PGDATA is not empty but not initialized." >&2
    echo "Replica: please recreate volumes (docker compose down -v) and retry." >&2
    exit 1
  fi

  until pg_isready -h "${PRIMARY_HOST}" -p "${PRIMARY_PORT}" -U "${REPL_USER}" >/dev/null 2>&1; do
    echo "Replica: waiting for primary to accept replication connections..."
    sleep 1
  done

  pg_basebackup \
    -h "${PRIMARY_HOST}" \
    -p "${PRIMARY_PORT}" \
    -U "${REPL_USER}" \
    -D "${PGDATA}" \
    -Fp -Xs -P -R \
    -C -S "${SLOT_NAME}"

  echo "Replica: base backup complete."
fi

exec docker-entrypoint.sh postgres -c hot_standby=on -c listen_addresses='*'

