#!/usr/bin/env bash
set -euo pipefail

docker compose up -d --build

echo
echo "API:  http://localhost:8080"
echo "DB A: postgres://app:app_password@localhost:54321/app"
echo "DB B: postgres://app:app_password@localhost:54322/app"

