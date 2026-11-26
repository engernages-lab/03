#!/usr/bin/env bash
# Deployment gate: the staging API must be unreachable without credentials.
#
# Run this BEFORE any deployment is announced, and again right after:
#   scripts/deploy/verify-access-gate.sh https://<host> [token]
#
# Failure modes it catches:
#   * gate accidentally disabled (every request succeeds) -> FAIL, this is the
#     whole point: an unauthenticated staging API must never be reachable
#   * gate enabled but the health probes are blocked -> deployment would look
#     unhealthy to the platform
#   * token configured but not honoured (typo, empty var, wrong mode)
set -euo pipefail

BASE="${1:?usage: verify-access-gate.sh <base-url> [token]}"
TOKEN="${2:-${POCKETSCORE_ACCESS_GATE_TOKEN:-}}"
OUT="${OUT_DIR:-docker-verification}"
mkdir -p "$OUT"
BASE="${BASE%/}"

echo "== 1. probes must be reachable without credentials =="
health_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/health" || echo 000)
ready_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/ready" || echo 000)
echo "/health -> $health_code ; /ready -> $ready_code"
if [ "$health_code" != "200" ]; then
  echo "::error::/health must return 200 without credentials (got $health_code)"
  exit 1
fi

echo "== 2. business endpoints must reject anonymous requests =="
anon_code=$(curl -s -o "$OUT/gate-anon.json" -w '%{http_code}' --max-time 10 "$BASE/api/v1/documents" || echo 000)
echo "GET /api/v1/documents (no credentials) -> $anon_code"
if [ "$anon_code" != "401" ]; then
  echo "::error::access gate is NOT enforcing: expected 401, got $anon_code"
  echo "         an unauthenticated staging API must not be reachable - deployment gate FAILED"
  exit 1
fi
grep -q 'ACCESS_GATE_REQUIRED' "$OUT/gate-anon.json" || {
  echo "::error::401 body is not the project error envelope"
  cat "$OUT/gate-anon.json"
  exit 1
}

echo "== 3. uploads must reject anonymous requests too =="
upload_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
  -F "file=@tests/fixtures/melody.wav" "$BASE/api/v1/audio/upload" || echo 000)
echo "POST /api/v1/audio/upload (no credentials) -> $upload_code"
if [ "$upload_code" != "401" ]; then
  echo "::error::upload endpoint is not behind the gate (got $upload_code)"
  exit 1
fi

if [ -z "$TOKEN" ]; then
  echo "== 4. credential check skipped (no token supplied) =="
  echo "GATE ENFORCED (anonymous access blocked). Pass a token to also verify the allow path."
  exit 0
fi

echo "== 4. a valid credential must be accepted =="
auth_code=$(curl -s -o /tmp/gate-auth.json -w '%{http_code}' --max-time 10 \
  -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/documents" || echo 000)
echo "GET /api/v1/documents (bearer) -> $auth_code"
if [ "$auth_code" != "200" ]; then
  echo "::error::valid credential was rejected (got $auth_code)"
  head -c 400 /tmp/gate-auth.json || true
  exit 1
fi

echo "== 5. a wrong credential must still be rejected =="
bad_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
  -H "Authorization: Bearer wrong-token" "$BASE/api/v1/documents" || echo 000)
if [ "$bad_code" != "401" ]; then
  echo "::error::wrong credential was accepted (got $bad_code)"
  exit 1
fi

{
  echo "base: $BASE"
  echo "health_without_credentials: $health_code"
  echo "ready_without_credentials: $ready_code"
  echo "documents_anonymous: $anon_code"
  echo "upload_anonymous: $upload_code"
  echo "documents_with_token: $auth_code"
  echo "documents_with_wrong_token: $bad_code"
  echo "verdict: gate enforced"
} | tee "$OUT/access-gate.txt"

echo "ACCESS GATE OK: anonymous blocked, credential accepted, wrong credential rejected"
