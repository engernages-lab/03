#!/usr/bin/env bash
# Poll /health then /ready with a hard timeout. On failure, dump container logs.
# Usage: wait-ready.sh <base-url> <container-name> [timeout-seconds]
set -euo pipefail

BASE="${1:?usage: wait-ready.sh <base-url> <container> [timeout]}"
CONTAINER="${2:?container name required}"
TIMEOUT="${3:-180}"
OUT="${OUT_DIR:-docker-verification}"
mkdir -p "$OUT"

deadline=$(( $(date +%s) + TIMEOUT ))
health_seconds=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --max-time 5 "$BASE/health" -o "$OUT/health-check.json"; then
    health_seconds=$(( TIMEOUT - (deadline - $(date +%s)) ))
    break
  fi
  sleep 2
done

if [ -z "$health_seconds" ]; then
  echo "::error::/health did not return 200 within ${TIMEOUT}s"
  docker logs "$CONTAINER" 2>&1 | tail -80 || true
  exit 1
fi
echo "/health ok after ~${health_seconds}s"

# readiness must report ready:true (model loaded AND warm-up done)
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --max-time 10 "$BASE/ready" -o "$OUT/ready-check.json"; then
    ready=$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1])).get("ready")).lower())' "$OUT/ready-check.json")
    if [ "$ready" = "true" ]; then
      python3 - "$OUT/ready-check.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1]))
checks = data.get("checks", {})
model = checks.get("model", {})
print("ready:", data.get("ready"))
print("model:", model.get("status"), "load=", model.get("load_seconds"), "warmup=", model.get("warmup_seconds"))
print("storage:", checks.get("storage"))
print("inference:", checks.get("inference"))
assert model.get("status") == "ready", model
assert checks.get("storage", {}).get("ok") is True, checks.get("storage")
assert checks.get("inference", {}).get("capacity", 0) >= 1, checks.get("inference")
PY
      echo "wait-ready: OK"
      exit 0
    fi
  fi
  sleep 2
done

echo "::error::/ready did not report ready:true within ${TIMEOUT}s"
curl -sS "$BASE/ready" | head -40 || true
docker logs "$CONTAINER" 2>&1 | tail -80 || true
exit 1
