#!/usr/bin/env bash
set -euo pipefail

echo "== Bring up stack =="
./scripts/up.sh

echo
echo "== Initial status =="
./scripts/status.sh

echo
echo "== Write on active (region-a) =="
curl -sS -X POST "http://localhost:8080/write" \
  -H "content-type: application/json" \
  -d '{"key":"hello","value":"from-region-a"}' | jq .

echo
echo "== Read from active (region-a) =="
curl -sS "http://localhost:8080/read?key=hello" | jq .

echo
echo "== Failover (stop region-a, switch to region-b) =="
./scripts/failover-to-region-b.sh

echo
echo "== Read from region-b (may be null if lagging) =="
curl -sS "http://localhost:8080/read?key=hello" | jq .

echo
echo "== Status after failover =="
./scripts/status.sh

