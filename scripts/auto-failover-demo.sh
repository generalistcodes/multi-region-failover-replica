#!/usr/bin/env bash
set -euo pipefail

echo "== Bring up stack (includes router + controller) =="
docker compose up -d --build

echo
echo "== Write via router (active region-a) =="
curl -sS -X POST "http://localhost:8090/write" \
  -H "content-type: application/json" \
  -d '{"key":"auto","value":"before-failover"}' | jq .

echo
echo "== Stop region-a primary =="
docker compose stop postgres-primary

echo
echo "== Wait for controller to fail over (watch logs) =="
echo "Tip: in another terminal run: docker compose logs -f failover-controller"
sleep 8

echo
echo "== Status via router (should be active_region=region-b) =="
curl -sS "http://localhost:8090/status" | jq .

echo
echo "== Write via router after auto-failover =="
curl -sS -X POST "http://localhost:8090/write" \
  -H "content-type: application/json" \
  -d '{"key":"auto","value":"after-failover"}' | jq .

echo
echo "== Read via router =="
curl -sS "http://localhost:8090/read?key=auto" | jq .

