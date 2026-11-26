#!/usr/bin/env bash
# Volume persistence gate: write through container #1, delete it, read through a
# brand new container on the same volume. A restart of the same process is NOT
# equivalent, so the first container is removed (not just stopped).
#
# Usage: verify-persistence.sh <image> <volume> <run-id> <port>
set -euo pipefail

IMAGE="${1:?image}"
VOLUME="${2:?volume}"
RUN_ID="${3:?run id}"
PORT="${4:?port}"
OUT="${OUT_DIR:-docker-verification}"
PREFIX="pocketscore-c21-${RUN_ID}"
C1="${PREFIX}-c1"
C2="${PREFIX}-c2"
BASE="http://127.0.0.1:${PORT}"
mkdir -p "$OUT"

run_container() {
  local name="$1"
  docker run -d --name "$name" \
    -p "127.0.0.1:${PORT}:${PORT}" \
    -e "PORT=${PORT}" \
    -e POCKETSCORE_ENVIRONMENT=staging \
    -e POCKETSCORE_DEBUG=false \
    -e POCKETSCORE_LOG_JSON=true \
    -e POCKETSCORE_SESSION_SECRET="${TEST_SESSION_SECRET}" \
    -e POCKETSCORE_TOKEN_ENCRYPTION_KEY="${TEST_TOKEN_KEY}" \
    -e POCKETSCORE_CORS_ORIGINS=http://127.0.0.1:${PORT} \
    -e POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false \
    -e POCKETSCORE_ACCESS_GATE_TOKEN="" \
    -e POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db \
    -e POCKETSCORE_STORAGE_DIR=/data/storage \
    -e POCKETSCORE_MODEL_PRELOAD=true \
    -e POCKETSCORE_MAX_UPLOAD_MB=50 \
    -e POCKETSCORE_MAX_CONCURRENT_INFERENCES=1 \
    -v "${VOLUME}:/data" \
    "$IMAGE" >/dev/null
}

echo "== container #1 (write) =="
run_container "$C1"
bash scripts/docker/wait-ready.sh "$BASE" "$C1" 240
python3 scripts/docker/verify-transcription.py --base-url "$BASE" \
  --token "$TEST_ACCESS_TOKEN" \
  --audio tests/fixtures/melody.wav --out "$OUT/transcription-result.json"

DOCUMENT_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["document_id"])' "$OUT/transcription-result.json")
ASSET_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["asset_id"])' "$OUT/transcription-result.json")
echo "document=$DOCUMENT_ID asset=$ASSET_ID"

curl -fsS -H "Authorization: Bearer $TEST_ACCESS_TOKEN" "$BASE/api/v1/documents/$DOCUMENT_ID" -o "$OUT/before-restart-document.json"
curl -fsS -H "Authorization: Bearer $TEST_ACCESS_TOKEN" "$BASE/api/v1/audio/assets/$ASSET_ID" -o "$OUT/before-restart-asset.json"
BEFORE=$(python3 -c '
import json, sys, hashlib
doc = json.load(open(sys.argv[1]))
asset = json.load(open(sys.argv[2]))
payload = {"events": len(doc.get("events") or []), "title": doc.get("title"), "checksum": asset.get("checksum_sha256"), "size": asset.get("size_bytes")}
print(hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
' "$OUT/before-restart-document.json" "$OUT/before-restart-asset.json")
echo "state digest before restart: $BEFORE"

echo "== delete container #1 (volume kept) =="
docker stop --time 30 "$C1" >/dev/null
docker rm "$C1" >/dev/null

echo "== container #2 (read, same volume) =="
run_container "$C2"
bash scripts/docker/wait-ready.sh "$BASE" "$C2" 240

DOC_STATUS=$(curl -s -H "Authorization: Bearer $TEST_ACCESS_TOKEN" -o "$OUT/after-restart-document.json" -w '%{http_code}' "$BASE/api/v1/documents/$DOCUMENT_ID")
ASSET_STATUS=$(curl -s -H "Authorization: Bearer $TEST_ACCESS_TOKEN" -o "$OUT/after-restart-asset.json" -w '%{http_code}' "$BASE/api/v1/audio/assets/$ASSET_ID")
ASSETS_TOTAL=$(curl -fsS -H "Authorization: Bearer $TEST_ACCESS_TOKEN" "$BASE/api/v1/audio/assets?limit=5" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("total"))')

AFTER=$(python3 -c '
import json, sys, hashlib
doc = json.load(open(sys.argv[1]))
asset = json.load(open(sys.argv[2]))
payload = {"events": len(doc.get("events") or []), "title": doc.get("title"), "checksum": asset.get("checksum_sha256"), "size": asset.get("size_bytes")}
print(hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
' "$OUT/after-restart-document.json" "$OUT/after-restart-asset.json")

python3 - "$OUT/persistence-result.json" <<PY
import json
result = {
    "container_before": "$C1",
    "container_after": "$C2",
    "volume": "$VOLUME",
    "document_id": "$DOCUMENT_ID",
    "asset_id": "$ASSET_ID",
    "document_http_after": int("$DOC_STATUS"),
    "asset_http_after": int("$ASSET_STATUS"),
    "assets_total_after": int("$ASSETS_TOTAL" or 0),
    "state_digest_before": "$BEFORE",
    "state_digest_after": "$AFTER",
    "identical": "$BEFORE" == "$AFTER",
}
json.dump(result, open("$OUT/persistence-result.json", "w"), indent=2)
print(json.dumps(result, indent=2))
PY

python3 - "$OUT/persistence-result.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1]))
problems = []
if data["document_http_after"] != 200:
    problems.append(f"document unreadable after restart: {data['document_http_after']}")
if data["asset_http_after"] != 200:
    problems.append(f"asset unreadable after restart: {data['asset_http_after']}")
if data["assets_total_after"] < 1:
    problems.append("no audio assets after restart")
if not data["identical"]:
    problems.append("document/asset state changed across the container rebuild")
if problems:
    print("PERSISTENCE VERIFY FAILED")
    for item in problems:
        print(" -", item)
    raise SystemExit(1)
print("PERSISTENCE VERIFY OK: same document, asset and events after rebuilding the container")
PY

echo "== cleanup container #2 =="
docker stop --time 30 "$C2" >/dev/null || true
docker rm "$C2" >/dev/null || true
