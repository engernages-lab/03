#!/usr/bin/env bash
# V1.1-C.2.2.2 Phase 4/5: real cloud HTTP regression against Railway staging.
# Every probe writes evidence under reports/V1.1-C.2.2.2/artifacts/.
# The token is read from the environment and never written to any file.
set -uo pipefail

U="${PSC_STAGING_URL:?set PSC_STAGING_URL}"
T="${POCKETSCORE_ACCESS_GATE_TOKEN:?set POCKETSCORE_ACCESS_GATE_TOKEN}"
ORIGIN="https://engernages-lab.github.io"
A="reports/V1.1-C.2.2.2/artifacts"
mkdir -p "$A"
U="${U%/}"

pass=0
fail=0
check() {
  if [ "$2" = "$3" ]; then
    echo "PASS  $1 ($3)"
    pass=$((pass + 1))
  else
    echo "FAIL  $1 (expected $2, got $3)"
    fail=$((fail + 1))
  fi
}

echo "== 1. homepage =="
# The access gate covers everything except /health and /ready, so the SPA root is
# 401 for anonymous visitors by design. Record BOTH states instead of pretending
# the page is public.
anon=$(curl -s -o "$A/homepage-anonymous.json" -w '%{http_code}' "$U/")
echo "anonymous GET / -> $anon"
check "GET / anonymous is gated" 401 "$anon"

curl -s -D "$A/homepage-response-headers.txt" -o "$A/homepage.html" \
  -H "Authorization: Bearer $T" \
  -w '{"status":%{http_code},"type":"%{content_type}","bytes":%{size_download},"time":%{time_total}}' \
  "$U/" > "$A/homepage-meta.json"
cat "$A/homepage-meta.json"
echo
home_code=$(grep -o '"status":[0-9]*' "$A/homepage-meta.json" | cut -d: -f2)
check "GET / with token" 200 "$home_code"

if grep -qi '<!doctype html>' "$A/homepage.html"; then
  echo "PASS  / returns real HTML"
  pass=$((pass + 1))
else
  echo "FAIL  / is not HTML"
  fail=$((fail + 1))
fi

if grep -qi 'application/json' "$A/homepage-response-headers.txt"; then
  echo "FAIL  / served JSON"
  fail=$((fail + 1))
else
  echo "PASS  / is not JSON"
  pass=$((pass + 1))
fi

echo "== 2. assets extracted from the served HTML =="
js=$(grep -o '/assets/[^"]*\.js' "$A/homepage.html" | head -1)
css=$(grep -o '/assets/[^"]*\.css' "$A/homepage.html" | head -1)
echo "js=$js css=$css"

{
  echo "{"
  for pair in "js:$js" "css:$css"; do
    kind=${pair%%:*}
    path=${pair#*:}
    [ -z "$path" ] && continue
    anon_code=$(curl -s -o /dev/null -w '%{http_code}' "$U$path")
    auth_code=$(curl -s -o "/tmp/$kind.body" -w '%{http_code}' -H "Authorization: Bearer $T" "$U$path")
    ctype=$(curl -s -o /dev/null -w '%{content_type}' -H "Authorization: Bearer $T" "$U$path")
    bytes=$(curl -s -o /dev/null -w '%{size_download}' -H "Authorization: Bearer $T" "$U$path")
    echo "  \"$kind\": {\"path\": \"$path\", \"anonymous\": $anon_code, \"authenticated\": $auth_code, \"content_type\": \"$ctype\", \"bytes\": $bytes},"
  done
  echo "  \"checked_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""
  echo "}"
} > "$A/frontend-assets-check.json"
cat "$A/frontend-assets-check.json"

auth_js=$(python -c "import json;print(json.load(open('$A/frontend-assets-check.json'))['js']['authenticated'])" 2>/dev/null || echo "?")
check "asset with token" 200 "$auth_js"

if grep -q '/03/assets' "$A/homepage.html"; then
  echo "FAIL  Pages base path /03/ leaked into the image"
  fail=$((fail + 1))
else
  echo "PASS  no /03/ base path"
  pass=$((pass + 1))
fi

echo "== 3. SPA client routes (direct access == what a refresh does) =="
: > "$A/spa-routes.txt"
for route in /dashboard /scores /transcription /settings; do
  code=$(curl -s -o /tmp/route.html -w '%{http_code}' -H "Authorization: Bearer $T" "$U$route")
  ishtml=$(grep -qi '<!doctype html>' /tmp/route.html && echo yes || echo no)
  echo "$route status=$code html=$ishtml" | tee -a "$A/spa-routes.txt"
  check "route $route" 200 "$code"
  check "route $route html" yes "$ishtml"
done

echo "== 4. access gate =="
code_anon=$(curl -s -o "$A/gate-anon.json" -w '%{http_code}' "$U/api/v1/documents")
code_wrong=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer wrong-token" "$U/api/v1/documents")
code_valid=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $T" "$U/api/v1/documents")
code_docs=$(curl -s -o /dev/null -w '%{http_code}' "$U/docs")
code_openapi=$(curl -s -o /dev/null -w '%{http_code}' "$U/openapi.json")
check "api anonymous" 401 "$code_anon"
check "api wrong token" 401 "$code_wrong"
check "api valid token" 200 "$code_valid"
check "docs anonymous" 401 "$code_docs"
check "openapi anonymous" 401 "$code_openapi"

if grep -q 'ACCESS_GATE_REQUIRED' "$A/gate-anon.json"; then
  echo "PASS  error envelope"
  pass=$((pass + 1))
else
  echo "FAIL  wrong envelope"
  fail=$((fail + 1))
fi

if grep -qF "$T" "$A/gate-anon.json" 2>/dev/null; then
  echo "FAIL  token echoed in response"
  fail=$((fail + 1))
else
  echo "PASS  token not echoed"
  pass=$((pass + 1))
fi

echo "== 5. health / ready =="
curl -s -D /tmp/hh.txt -o "$A/health-response.json" -w 'health_status=%{http_code} health_time=%{time_total}\n' "$U/health"
curl -s -D /tmp/rh.txt -o "$A/ready-response.json" -w 'ready_status=%{http_code} ready_time=%{time_total}\n' "$U/ready"

ready_rc=0
python - "$A/ready-response.json" <<'PY' || ready_rc=$?
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
checks = data.get("checks", {})
required = ["database", "storage", "ffmpeg", "librosa", "midi", "model", "inference", "access_gate"]
missing = [key for key in required if key not in checks]
gate = checks.get("access_gate", {})
print("ready:", data.get("ready"), "| missing checks:", missing or "none")
print("database:", checks.get("database"))
print(
    "access_gate:",
    {key: gate.get(key) for key in ("mode", "enabled", "token_configured", "basic_configured")},
)
print(
    "model:",
    checks.get("model", {}).get("status"),
    "| inference capacity:",
    checks.get("inference", {}).get("capacity"),
)
if missing or not data.get("ready"):
    sys.exit(1)
if gate.get("enabled") is not True or gate.get("mode") != "token":
    sys.exit(2)
PY
check "ready contract" 0 "$ready_rc"

echo "== 6. CORS =="
curl -s -o /dev/null -D /tmp/cors.txt -X OPTIONS "$U/api/v1/documents" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
allowed=$(grep -i '^access-control-allow-origin' /tmp/cors.txt | tr -d '\r' | awk '{print $2}')
foreign=$(curl -s -o /dev/null -w '%{http_code}' -X OPTIONS "$U/api/v1/documents" \
  -H "Origin: https://evil.example" -H "Access-Control-Request-Method: GET")
echo "allowed_origin=$allowed foreign_preflight=$foreign"
check "cors allowed origin" "$ORIGIN" "$allowed"
check "cors foreign rejected" 400 "$foreign"
cp /tmp/cors.txt "$A/cors-preflight-headers.txt"

{
  echo "{"
  echo "  \"homepage_anonymous\": $anon,"
  echo "  \"homepage_authenticated\": $home_code,"
  echo "  \"assets_authenticated\": ${auth_js:-0},"
  echo "  \"api_anonymous\": $code_anon,"
  echo "  \"api_wrong_token\": $code_wrong,"
  echo "  \"api_valid_token\": $code_valid,"
  echo "  \"docs_anonymous\": $code_docs,"
  echo "  \"openapi_anonymous\": $code_openapi,"
  echo "  \"cors_allowed\": \"$allowed\","
  echo "  \"cors_foreign\": $foreign,"
  echo "  \"passed\": $pass,"
  echo "  \"failed\": $fail"
  echo "}"
} > "$A/access-gate-check.json"

echo
echo "RESULT passed=$pass failed=$fail"
[ "$fail" -eq 0 ] || exit 1
