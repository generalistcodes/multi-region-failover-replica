#!/usr/bin/env bash
set -euo pipefail

echo "Stopping region-a (postgres-primary)..."
docker compose stop postgres-primary

echo "Promoting region-b (postgres-replica) to primary..."
docker compose exec -T -u postgres postgres-replica pg_ctl -D /var/lib/postgresql/data promote

echo "Switching API active region to region-b..."
curl -sS -X POST "http://localhost:8080/admin/switch?region=region-b" | jq .

echo "Done."

