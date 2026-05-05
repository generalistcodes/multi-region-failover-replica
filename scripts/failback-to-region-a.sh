#!/usr/bin/env bash
set -euo pipefail

echo "After promoting region-b, the original region-a cannot safely rejoin without re-sync."
echo "Resetting the lab back to a clean state (recreate volumes)..."

docker compose down -v
./scripts/up.sh

echo "Switching API active region to region-a..."
curl -sS -X POST "http://localhost:8080/admin/switch?region=region-a" | jq .

echo "Done (fresh cluster)."

