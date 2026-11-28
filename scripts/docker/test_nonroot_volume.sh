#!/usr/bin/env bash
# Historical-volume compatibility for a non-root container (V1.1-C.2.3.4.3).
#
# The real Staging volume already holds data written while the image ran as root.
# This script simulates that on an isolated volume and reports the boundary
# honestly instead of hiding it.
#
# Usage:  test_nonroot_volume.sh <mode-a|mode-b|mode-c|all> [image]
#
#   mode-a  volume already owned by 10001:10001  -> must be fully usable
#   mode-b  volume owned by root (the realistic legacy case) -> read must work,
#           write is *measured* and reported, never silently fixed
#   mode-c  one-off, scope-limited ownership migration on an isolated volume,
#           with hashes before/after to prove no data changed
#
# Exit 78 means Docker is unavailable (NOT VERIFIED), so a missing daemon can
# never look like a pass.
set -euo pipefail

MODE="${1:-all}"
IMAGE="${2:-pocketscore-ai:c2343-test}"
STAMP="$(date +%Y%m%d%H%M%S)-$$"
VOL_A="pocketscore-volchk-owned-${STAMP}"
VOL_B="pocketscore-volchk-root-${STAMP}"

log() { printf '[volchk:%s] %s\n' "$MODE" "$*"; }

command -v docker >/dev/null 2>&1 || { log "docker not available -> NOT VERIFIED"; exit 78; }
docker info >/dev/null 2>&1 || { log "docker daemon not reachable -> NOT VERIFIED"; exit 78; }

cleanup() {
  for vol in "$VOL_A" "$VOL_B"; do
    if docker volume inspect "$vol" >/dev/null 2>&1; then
      docker volume rm "$vol" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT

seed_owned_volume() {
  docker volume create "$VOL_A" >/dev/null
  # seeding must be root: the runtime image drops to uid 10001
  docker run --rm --user 0:0 -v "$VOL_A:/data" --entrypoint sh "$IMAGE" -c '
    mkdir -p /data/storage /data/backups
    printf "legacy-audio" > /data/storage/legacy.wav
    printf "legacy-backup" > /data/backups/legacy.bak
    chown -R 10001:10001 /data
  '
}

run_mode_a() {
  log "== mode A: volume pre-owned by 10001:10001 =="
  seed_owned_volume
  docker run --rm -v "$VOL_A:/data" --entrypoint python "$IMAGE" -c '
import os, pathlib
assert os.getuid() == 10001, f"expected uid 10001, got {os.getuid()}"
for path in ("/data/storage/legacy.wav", "/data/backups/legacy.bak"):
    assert pathlib.Path(path).is_file(), f"legacy file missing: {path}"
assert pathlib.Path("/data/storage/legacy.wav").read_text() == "legacy-audio"
pathlib.Path("/data/storage/new.wav").write_bytes(b"new")
assert pathlib.Path("/data/storage/new.wav").read_text() == "new"
pathlib.Path("/data/storage/new.wav").unlink()
print("mode A ok: legacy read + new write + delete as uid", os.getuid())
'
  log "mode A PASSED"
}

seed_root_volume() {
  docker volume create "$VOL_B" >/dev/null
  docker run --rm --user 0:0 -v "$VOL_B:/data" --entrypoint sh "$IMAGE" -c '
    mkdir -p /data/storage /data/backups
    printf "legacy-audio" > /data/storage/legacy.wav
    printf "legacy-backup" > /data/backups/legacy.bak
    chown -R 0:0 /data
    chmod 0755 /data /data/storage /data/backups
    chmod 0644 /data/storage/legacy.wav /data/backups/legacy.bak
  '
}

run_mode_b() {
  log "== mode B: volume owned by root (legacy) =="
  seed_root_volume
  # This container is allowed to fail: the point is to *measure* the boundary.
  set +e
  output=$(docker run --rm -v "$VOL_B:/data" --entrypoint python "$IMAGE" -c '
import os, pathlib
readable = pathlib.Path("/data/storage/legacy.wav").read_text() == "legacy-audio"
try:
    pathlib.Path("/data/storage/new.wav").write_bytes(b"new")
    writable = True
except OSError as exc:
    writable = False
    errno_path = f"{exc.errno}:{exc.filename}"
print(f"uid={os.getuid()} readable={readable} writable={writable}")
' 2>&1)
  rc=$?
  set -e
  printf '%s\n' "$output"
  log "mode B exit=${rc} (a permission failure on write is expected and is the finding, not a test bug)"
  case "$output" in
    *"readable=True"*) log "legacy data is readable by uid 10001" ;;
    *) log "WARNING: legacy data was not readable; record this as a compatibility failure" ;;
  esac
  case "$output" in
    *"writable=True"*) log "legacy volume is also writable (unexpected for root-owned 0755)" ;;
    *) log "legacy volume is NOT writable by uid 10001 -> one-off migration required before deploy" ;;
  esac
}

run_mode_c() {
  log "== mode C: scope-limited one-off migration (isolated volume only) =="
  seed_root_volume
  before=$(docker run --rm --user 0:0 -v "$VOL_B:/data" --entrypoint sh "$IMAGE" -c '
    sha256sum /data/storage/legacy.wav /data/backups/legacy.bak | sort
  ')
  log "hashes before migration:"
  printf '%s\n' "$before"

  docker run --rm --user 0:0 -v "$VOL_B:/data" --entrypoint sh "$IMAGE" -c '
    chown 10001:10001 /data
    chown -R 10001:10001 /data/storage /data/backups
  '

  after=$(docker run --rm --user 0:0 -v "$VOL_B:/data" --entrypoint sh "$IMAGE" -c '
    sha256sum /data/storage/legacy.wav /data/backups/legacy.bak | sort
  ')
  log "hashes after migration:"
  printf '%s\n' "$after"
  [ "$before" = "$after" ] || { log "FAIL: data changed during migration"; exit 1; }
  log "data hashes unchanged by the migration"

  docker run --rm -v "$VOL_B:/data" --entrypoint python "$IMAGE" -c '
import os, sqlite3, pathlib
assert os.getuid() == 10001, os.getuid()
assert pathlib.Path("/data/storage/legacy.wav").read_text() == "legacy-audio"
pathlib.Path("/data/storage/new.wav").write_bytes(b"new")
db = sqlite3.connect("/data/probe.db")
db.execute("PRAGMA journal_mode=WAL")
db.execute("CREATE TABLE t (v TEXT)")
db.execute("INSERT INTO t VALUES (\"ok\")")
db.commit()
wal = pathlib.Path("/data/probe.db-wal")
assert wal.exists(), "WAL file missing while the connection is open"
rows = db.execute("SELECT v FROM t").fetchall()
db.close()
assert rows == [("ok",)], rows
print("mode C ok: legacy readable, writes + WAL work as uid", os.getuid())
'
  log "mode C PASSED"
}

case "$MODE" in
  mode-a|a) run_mode_a ;;
  mode-b|b) run_mode_b ;;
  mode-c|c) run_mode_c ;;
  all)
    run_mode_a
    run_mode_b
    run_mode_c
    ;;
  *)
    log "unknown mode: $MODE (use mode-a, mode-b, mode-c or all)"
    exit 2
    ;;
esac

log "done"
