#!/usr/bin/env bash
set -euo pipefail

curl -sS "http://localhost:8080/status" | jq .

