#!/usr/bin/env bash
# Secret and image-content gate. Runs on the runner BEFORE docker build so a
# leaked key fails fast, and again after the build for image contents.
#
# Usage: scan-secrets.sh [image]
set -euo pipefail

OUT="${OUT_DIR:-docker-verification}"
mkdir -p "$OUT"
IMAGE="${1:-}"
FAILURES=0

echo "== 1. tracked files that must never exist =="
for pattern in '.env' '.env.production' '*.p8' '*.pem' '*.key' 'token_key*' '*.db'; do
  matches=$(git ls-files -- "$pattern" 2>/dev/null | grep -v '\.env\.example' || true)
  if [ -n "$matches" ]; then
    echo "::error::tracked file matching $pattern: $matches"
    FAILURES=$((FAILURES+1))
  fi
done

echo "== 2. high-signal secret patterns in tracked, non-fixture files =="
# Only report file:line, never the value itself.
scan_patterns=(
  'BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY'
  'AKIA[0-9A-Z]{16}'
  'gh[pousr]_[A-Za-z0-9]{30,}'
  'railway_[A-Za-z0-9]{20,}'
  'change-me-in-production'
)
for pattern in "${scan_patterns[@]}"; do
  hits=$(git grep -nE "$pattern" -- \
      ':!*.md' ':!docs/*' ':!reports/*' ':!tests/fixtures/*' ':!*lock*' 2>/dev/null || true)
  if [ -n "$hits" ]; then
    case "$pattern" in
      'change-me-in-production')
        # allowed as the documented default, forbidden in production configs only
        filtered=$(echo "$hits" | grep -v 'config.py' || true)
        if [ -n "$filtered" ]; then
          echo "::error::placeholder secret outside config defaults:"
          echo "$filtered"
          FAILURES=$((FAILURES+1))
        fi
        ;;
      *)
        echo "::error::possible secret (pattern: $pattern):"
        echo "$hits" | head -5
        FAILURES=$((FAILURES+1))
        ;;
    esac
  fi
done

echo "== 3. .env must be ignored =="
if ! git check-ignore -q .env 2>/dev/null; then
  echo "::error::.env is not git-ignored"
  FAILURES=$((FAILURES+1))
else
  echo ".env ignored: ok"
fi

echo "== 4. frontend bundle must not carry secrets =="
if [ -d frontend/dist ]; then
  if grep -rIlE '(SESSION_SECRET|TOKEN_ENCRYPTION_KEY|CLIENT_SECRET)' frontend/dist >/dev/null 2>&1; then
    echo "::error::secret-looking identifier found in frontend/dist"
    FAILURES=$((FAILURES+1))
  fi
fi

echo "== 5. image contents =="
if [ -n "$IMAGE" ]; then
  docker run --rm --entrypoint sh "$IMAGE" -c '
    set -e
    fail=0
    for p in /app/.env /app/.git /app/backend/.env /app/frontend/.map; do
      if [ -e "$p" ]; then echo "unexpected path in image: $p"; fail=1; fi
    done
    if [ -d /app/.git ]; then echo "git history inside image"; fail=1; fi
    if find /app/frontend/dist -name "*.map" | grep -q .; then echo "source maps in image"; fail=1; fi
    if grep -rIl "change-me-in-production" /app/app 2>/dev/null | grep -v config.py | grep -q .; then
      echo "placeholder secret outside config defaults"; fail=1
    fi
    if grep -rIlE "BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY" /app 2>/dev/null | grep -q .; then
      echo "private key inside image"; fail=1
    fi
    id -u | sed "s/^/image_uid: /"
    exit $fail
  ' | tee "$OUT/image-security.txt"
  if [ "${PIPESTATUS[0]}" != "0" ]; then
    FAILURES=$((FAILURES+1))
  fi
fi

if [ "$FAILURES" -gt 0 ]; then
  echo "SECRET SCAN FAILED ($FAILURES problem groups)"
  exit 1
fi
echo "SECRET SCAN OK"
