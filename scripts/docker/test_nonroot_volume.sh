#!/usr/bin/env bash
# Historical-volume compatibility for a non-root container (V1.1-C.2.3.4.3).
#
# The real Staging volume already contains data written while the container ran
# as root. This script simulates that: it seeds an isolated volume as root with
# legacy ownership, then starts the final image as uid 10001 and checks whether
# the application can still read and write.
#
# Three modes are exercised so the result is actionable rather than binary:
#   A) volume owned by 10001:10001            -> must work
#   B) volume owned by root:root, files 0644  -> app can read, cannot write
#   C) same as B after a ONE-OFF chown of the volume root only (no -R on /data
#      contents, no per-boot recursive chown) -> must work
#
# Exit 78 means Docker is unavailable (NOT VERIFIED).
set -euo pipefail

IMAGE="${1:-pocketscore-ai:c2343-test}"
VOL_A="pocketscore-volchk-owned-$(date +%Y%m%d%H%M%S)-$$"
VOL_B="pocketscore-volchk-root-$(date +%Y%m%d%H%M%S)-$$"
CONTAINER="pocketscore-volchk-$$"

log() { printf '[volchk] %s\n' "$*"; }

command -v docker >/dev/null 2>&1 || { log "docker not available -> NOT VERIFIED"; exit 78; }
docker info >/dev/null 2>&1 || { log "docker daemon not reachable -> NOT VERIFIED"; exit 78; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  for vol in "$VOL_A" "$VOL_B"; do
    docker volume inspect "$vol" >/dev/null 2>&1 && docker volume rm "$vol" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

docker volume create "$VOL_A" >/dev/null
docker volume create "$VOL_B" >/dev/null

# ---------------------------------------------------------------- A: owned
log "== A. volume pre-owned by 10001:10001 =="
docker run --rm -v "$VOL_A:/data" --entrypoint sh "$IMAGE" -c '
  mkdir -p /data/storage /data/backups
  printf "legacy-audio" > /data/storage/legacy.wav
  printf "legacy-backup" > /data/backups/legacy.bak
  chown -R 10001:10001 /data
'
docker run --rm -v "$VOL_A:/data" --entrypoint python "$IMAGE" -c '
import pathlib, sys
assert 0 != __import__("os").getuid()
for p in ("/data/storage/legacy.wav", "/data/backups/legacy.bak"):
    assert pathlib.Path(p).is_file(), p
pathlib.Path("/data/storage/new.wav").write_bytes(b"new")
print("mode A ok: read legacy + wrote new")
'

# ------------------------------------------------------- B: root-owned
log "== B. volume owned by root (the realistic pre-existing case) =="
docker run --rm -v "$VOL_B:/data" --entrypoint sh "$IMAGE" -c '
  mkdir -p /data/storage /data/backups
  printf "legacy-audio" > /data/storage/legacy.wav
  chmod 0644 /data/storage/legacy.wav
  chown -R 0:0 /data
  chmod 0755 /data /data/storage /data/backups
'
set +e
out=$(docker run --rm -v "$VOL_B:/data" --entrypoint python "$IMAGE" -c '
import pathlib, os
readable = pathlib.Path("/data/storage/legacy.wav").read_text() == "legacy-audio"
try:
    pathlib.Path("/data/storage/new.wav").write_bytes(b"new")
    writable = True
except OSError as exc:
    writable = False
print(f"uid={os.getuid()} readable={readable} writable={writable}")
' 2>&1)
rc=$?
set -e
log "$out"
[ "$rc" = "0" ] || log "expected a permission failure on write"

# ------------------------------------------------- C: one-off migration
log "== C. one-off ownership migration (volume root + app dirs only) =="
docker run --rm -v "$VOL_B:/data" --entrypoint sh "$IMAGE" -c '
  chown 10001:10001 /data
  chown -R 10001:10001 /data/storage /data/backups
  find /data -maxdepth 1 -type f -exec chown 10001:10001 {} \;
'
docker run --rm -v "$VOL_B:/data" --entrypoint python "$IMAGE" -c '
import pathlib, os, sqlite3
assert os.getuid() == 10001
assert pathlib.Path("/data/storage/legacy.wav").read_text() == "legacy-audio"
pathlib.Path("/data/storage/new.wav").write_bytes(b"new")
db = sqlite3.connect("/data/probe.db")
db.execute("PRAGMA journal_mode=WAL")
db.execute("CREATE TABLE t (v TEXT)")
db.execute("INSERT INTO t VALUES (\"ok\")")
db.commit(); db.close()
assert pathlib.Path("/data/probe.db-wal").exists()
print("mode C ok: legacy readable, new writes and WAL work")
'

log "ALL HISTORICAL-VOLUME MODES EXERCISED"
log "NOTE: this proves the container side only. The Railway volume still has to"
log "      be migrated once, in a dedicated window, before deploying."
