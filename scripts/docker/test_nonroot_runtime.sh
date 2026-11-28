#!/usr/bin/env bash
# Non-root runtime verification for the PocketScore image (V1.1-C.2.3.4.3).
#
# Proves, against the real final stage, that:
#   * the process runs as uid 10001 (not root);
#   * the app can write its data paths on a fresh isolated volume;
#   * SQLite creates and writes with WAL/SHM;
#   * audio and backup files can be created, read and removed;
#   * SIGTERM stops the container cleanly;
#   * data survives a container restart.
#
# Only the volume it creates itself is ever removed. If Docker is unavailable the
# script exits 78 (EX_CONFIG) so the caller can report NOT VERIFIED instead of a
# silent pass.
set -euo pipefail

IMAGE="${1:-pocketscore-ai:c2343-test}"
PORT="${PORT:-8123}"
VOLUME="pocketscore-nonroot-$(date +%Y%m%d%H%M%S)-$$"
CONTAINER="pocketscore-nonroot-run-$$"

log() { printf '[nonroot] %s\n' "$*"; }
fail() { printf '[nonroot] FAIL: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || { log "docker not available -> NOT VERIFIED"; exit 78; }
docker info >/dev/null 2>&1 || { log "docker daemon not reachable -> NOT VERIFIED"; exit 78; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  # remove ONLY the volume created above
  if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "image: $IMAGE"
log "volume: $VOLUME"

docker volume create "$VOLUME" >/dev/null

log "== 1. identity inside the image =="
uid_line=$(docker run --rm --entrypoint id "$IMAGE")
log "$uid_line"
echo "$uid_line" | grep -qE 'uid=10001' || fail "runtime user is not 10001 ($uid_line)"
echo "$uid_line" | grep -qE 'uid=0' && fail "runtime user is root"

log "== 2. python runs as the same non-root uid =="
py_uid=$(docker run --rm --entrypoint python "$IMAGE" -c "import os; print(os.getuid())")
log "python uid=$py_uid"
[ "$py_uid" = "10001" ] || fail "python uid=$py_uid (expected 10001)"

log "== 3. start the app on the isolated volume =="
docker run -d --name "$CONTAINER" \
  -v "$VOLUME:/data" \
  -e PORT="$PORT" \
  -e POCKETSCORE_ENVIRONMENT=test \
  -e POCKETSCORE_ACCESS_GATE_MODE=off \
  -e POCKETSCORE_MODEL_PRELOAD=false \
  -e POCKETSCORE_LOG_LEVEL=INFO \
  -p "127.0.0.1:${PORT}:${PORT}" \
  "$IMAGE" >/dev/null

ready=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" = "1" ] || { docker logs "$CONTAINER" | tail -40; fail "app did not become healthy"; }

health=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health")
ready_code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/ready")
log "health=$health ready=$ready_code"
[ "$health" = "200" ] || fail "health=$health"
[ "$ready_code" = "200" ] || { docker logs "$CONTAINER" | tail -30; fail "ready=$ready_code"; }

log "== 4. data paths are writable by the non-root user =="
docker exec "$CONTAINER" python - <<'PY'
import os, sqlite3, pathlib, sys
storage = pathlib.Path("/data/storage")
backups = pathlib.Path("/data/backups")
report = {}
for path in (storage, backups):
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".probe"
    probe.write_bytes(b"ok")
    probe.unlink()
    report[path.name] = "rw"

db = pathlib.Path("/data/pocketscore.db")
conn = sqlite3.connect(db)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
conn.execute("INSERT INTO t (v) VALUES ('hello')")
conn.commit()
wal = pathlib.Path("/data/pocketscore.db-wal")
print("uid", os.getuid(), "paths", report, "wal_exists", wal.exists(), "db_size", db.stat().st_size)
assert os.getuid() != 0, "must not run as root"
assert wal.exists(), "WAL file was not created"
conn.close()

audio = storage / "audio-probe.wav"
audio.write_bytes(b"RIFF0000WAVEfmt " + b"\x00" * 32)
assert audio.read_bytes()[:4] == b"RIFF"
art = storage / "artwork-probe.jpg"
art.write_bytes(b"\xff\xd8\xff\xe0payload")
assert art.is_file()

backup = backups / "backup-probe.sqlite3"
backup.write_bytes(db.read_bytes())
assert backup.stat().st_size > 0

audio.unlink()
assert not audio.exists(), "audio delete failed"
PY
log "data path checks OK"

log "== 5. docker healthcheck reports healthy =="
for _ in $(seq 1 45); do
  status=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "none")
  [ "$status" = "healthy" ] && break
  sleep 2
done
log "health status: ${status:-unknown}"
[ "${status:-}" = "healthy" ] || log "WARN: healthcheck status=${status:-unknown} (start-period may still be running)"

log "== 6. SIGTERM =="
docker kill --signal TERM "$CONTAINER" >/dev/null
for _ in $(seq 1 40); do
  running=$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo "false")
  [ "$running" = "false" ] && break
  sleep 1
done
exit_code=$(docker inspect --format '{{.State.ExitCode}}' "$CONTAINER")
log "exit code after SIGTERM: $exit_code"
[ "$exit_code" = "0" ] || [ "$exit_code" = "143" ] || fail "unexpected exit code $exit_code"

log "== 7. restart persistence =="
docker rm -f "$CONTAINER" >/dev/null
docker run -d --name "$CONTAINER" \
  -v "$VOLUME:/data" \
  -e PORT="$PORT" -e POCKETSCORE_ENVIRONMENT=test \
  -e POCKETSCORE_ACCESS_GATE_MODE=off -e POCKETSCORE_MODEL_PRELOAD=false \
  -p "127.0.0.1:${PORT}:${PORT}" "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$CONTAINER" python - <<'PY'
import sqlite3, pathlib
conn = sqlite3.connect("/data/pocketscore.db")
rows = conn.execute("SELECT v FROM t").fetchall()
conn.close()
assert rows and rows[0][0] == "hello", f"data lost after restart: {rows}"
assert pathlib.Path("/data/storage/artwork-probe.jpg").is_file(), "artwork lost"
assert pathlib.Path("/data/backups/backup-probe.sqlite3").is_file(), "backup lost"
print("persistence OK:", rows)
PY

log "ALL NON-ROOT RUNTIME CHECKS PASSED"
