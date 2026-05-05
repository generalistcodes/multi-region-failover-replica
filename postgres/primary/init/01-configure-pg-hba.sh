#!/usr/bin/env bash
set -euo pipefail

# Allow the replica to connect for streaming replication.
cat >> "${PGDATA}/pg_hba.conf" <<'EOF'

# Local multi-region simulation (docker network)
host replication all 0.0.0.0/0 scram-sha-256
host all all 0.0.0.0/0 scram-sha-256
EOF

