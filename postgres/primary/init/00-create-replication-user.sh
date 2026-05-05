#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${REPL_USER:-}" || -z "${REPL_PASSWORD:-}" ]]; then
  echo "REPL_USER/REPL_PASSWORD must be set for replication user creation" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${REPL_USER}') THEN
    CREATE ROLE ${REPL_USER} WITH REPLICATION LOGIN PASSWORD '${REPL_PASSWORD}';
  END IF;
END
\$\$;
SQL

