#!/usr/bin/env bash
# Linux SIGTERM gate (the thing Windows could not test in C.2).
# Starts its own container, waits for ready, then `docker stop` and inspects the
# exit code plus the shutdown logs.
#
# Usage: verify-graceful-shutdown.sh <image> <volume> <run-id> <port>
set -euo pipefail

IMAGE="${1:?image}"
VOLUME="${2:?volume}"
RUN_ID="${3:?run id}"
PORT="${4:?port}"
OUT="${OUT_DIR:-docker-verification}"
NAME="pocketscore-c21-${RUN_ID}-shutdown"
BASE="http://127.0.0.1:${PORT}"
mkdir -p "$OUT"

docker run -d --name "$NAME" \
  -p "127.0.0.1:${PORT}:${PORT}" \
  -e "PORT=${PORT}" \
  -e POCKETSCORE_ENVIRONMENT=staging \
  -e POCKETSCORE_LOG_JSON=true \
  -e "POCKETSCORE_SESSION_SECRET=${TEST_SESSION_SECRET}" \
  -e "POCKETSCORE_TOKEN_ENCRYPTION_KEY=${TEST_TOKEN_KEY}" \
  -e POCKETSCORE_CORS_ORIGINS=http://127.0.0.1:${PORT} \
  -e POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false \
  -e "POCKETSCORE_ACCESS_GATE_TOKEN=${TEST_ACCESS_TOKEN}" \
  -e POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db \
  -e POCKETSCORE_STORAGE_DIR=/data/storage \
  -e POCKETSCORE_MODEL_PRELOAD=true \
  -v "${VOLUME}:/data" \
  "$IMAGE" >/dev/null

bash scripts/docker/wait-ready.sh "$BASE" "$NAME" 240

echo "== docker stop (30s budget) =="
STOP_STARTED=$(date +%s)
set +e
docker stop --time 30 "$NAME" >/dev/null
STOP_RC=$?
set -e
STOP_SECONDS=$(( $(date +%s) - STOP_STARTED ))

EXIT_CODE=$(docker inspect "$NAME" --format '{{.State.ExitCode}}')
OOM_KILLED=$(docker inspect "$NAME" --format '{{.State.OOMKilled}}')
docker logs "$NAME" > "$OUT/container-logs.txt" 2>&1 || true

{
  echo "container: $NAME"
  echo "docker_stop_rc: $STOP_RC"
  echo "stop_seconds: $STOP_SECONDS"
  echo "container_exit_code: $EXIT_CODE"
  echo "oom_killed: $OOM_KILLED"
  echo "--- last 40 log lines ---"
  tail -40 "$OUT/container-logs.txt"
} | tee "$OUT/graceful-shutdown.txt"

# A PID-1 uvicorn logs its shutdown path; absence means SIGTERM did not reach it.
if ! grep -qiE "shutting down|finished server process|application shutdown complete|Shutdown complete" "$OUT/container-logs.txt"; then
  echo "::error::no graceful shutdown markers in container logs (SIGTERM likely not handled)"
  exit 1
fi
if grep -qiE "Traceback \(most recent call last\)" "$OUT/container-logs.txt"; then
  echo "::error::traceback during shutdown"
  exit 1
fi
if [ "$EXIT_CODE" != "0" ] && [ "$EXIT_CODE" != "143" ]; then
  echo "::error::unexpected container exit code $EXIT_CODE"
  exit 1
fi
if [ "$OOM_KILLED" = "true" ]; then
  echo "::error::container was OOM-killed"
  exit 1
fi

echo "GRACEFUL SHUTDOWN OK: stop returned in ${STOP_SECONDS}s, exit=$EXIT_CODE"
docker rm "$NAME" >/dev/null || true
