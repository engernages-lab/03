#!/usr/bin/env bash
# Secret and image-content gate. Runs on the runner BEFORE docker build so a
# leaked key fails fast, and again after the build for image contents.
#
# Design note: a placeholder such as `change-me-in-production` is *documented*
# in .env.example / docker-compose.yml / the settings validator, so those files
# are allowed to mention it. What must not happen is a real credential in a
# tracked file, or the placeholder reaching a production config.
#
# Usage: scan-secrets.sh [image]
set -euo pipefail

OUT="${OUT_DIR:-docker-verification}"
mkdir -p "$OUT"
IMAGE="${1:-}"
FAILURES=0

# Paths that legitimately document the placeholder default.
# NOTE: matching is against "path:line:content" from `git grep`, so the patterns
# are path-anchored rather than anchored at the start of the line.
PLACEHOLDER_ALLOWLIST='(^|/)(\.env\.example|docker-compose\.yml|config\.py):|(^|/)tests/|(^|/)scan-secrets\.sh:'

echo "== 1. tracked files that must never exist =="
for pattern in '.env' '.env.production' '*.p8' '*.pem' '*.key' 'token_key*' '*.db'; do
  matches=$(git ls-files -- "$pattern" 2>/dev/null | grep -v '\.env\.example$' || true)
  if [ -n "$matches" ]; then
    echo "::error::tracked file matching $pattern: $matches"
    FAILURES=$((FAILURES+1))
  fi
done

echo "== 2. real credential shapes in tracked files =="
# Only report file:line, never the value itself.
for pattern in \
  'BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY' \
  'AKIA[0-9A-Z]{16}' \
  'gh[pousr]_[A-Za-z0-9]{30,}' \
  'railway_[A-Za-z0-9]{20,}'
do
  hits=$(git grep -nE "$pattern" -- \
      ':!*.md' ':!docs/*' ':!reports/*' ':!tests/fixtures/*' ':!*lock*' 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo "::error::possible credential (pattern: $pattern):"
    echo "$hits" | head -5
    FAILURES=$((FAILURES+1))
  fi
done

echo "== 3. placeholder secret outside its documented homes =="
placeholder_hits=$(git grep -n "change-me-in-production" -- \
    ':!*.md' ':!docs/*' ':!reports/*' ':!tests/fixtures/*' ':!*lock*' 2>/dev/null || true)
if [ -n "$placeholder_hits" ]; then
  offenders=$(echo "$placeholder_hits" | grep -vE "$PLACEHOLDER_ALLOWLIST" || true)
  if [ -n "$offenders" ]; then
    echo "::error::placeholder secret used outside a documented default:"
    echo "$offenders" | head -5
    FAILURES=$((FAILURES+1))
  else
    echo "placeholder only appears in documented defaults: ok"
  fi
fi

echo "== 4. .env must be ignored =="
if git check-ignore -q .env 2>/dev/null; then
  echo ".env ignored: ok"
else
  echo "::error::.env is not git-ignored"
  FAILURES=$((FAILURES+1))
fi

echo "== 5. frontend bundle must not carry secrets =="
if [ -d frontend/dist ]; then
  if grep -rIlE '(SESSION_SECRET|TOKEN_ENCRYPTION_KEY|CLIENT_SECRET)\s*[:=]' frontend/dist >/dev/null 2>&1; then
    echo "::error::secret-looking assignment found in frontend/dist"
    FAILURES=$((FAILURES+1))
  else
    echo "frontend bundle clean: ok"
  fi
fi

echo "== 6. image contents =="
if [ -n "$IMAGE" ]; then
  set +e
  docker run --rm --entrypoint sh "$IMAGE" -c '
    fail=0
    for p in /app/.env /app/backend/.env /app/.env.production; do
      if [ -e "$p" ]; then echo "unexpected env file in image: $p"; fail=1; fi
    done
    if [ -d /app/.git ]; then echo "git history inside image"; fail=1; fi
    if find /app/frontend/dist -name "*.map" 2>/dev/null | grep -q .; then echo "source maps in image"; fail=1; fi
    if grep -rIl "change-me-in-production" /app/app 2>/dev/null | grep -v "core/config.py" | grep -q .; then
      echo "placeholder secret outside the settings validator"; fail=1
    fi
    if grep -rIlE "BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY" /app 2>/dev/null | grep -q .; then
      echo "private key inside image"; fail=1
    fi
    echo "image_uid: $(id -u)"
    exit $fail
  ' | tee "$OUT/image-security.txt"
  rc=${PIPESTATUS[0]}
  set -e
  if [ "$rc" != "0" ]; then
    echo "::error::image security checks failed"
    FAILURES=$((FAILURES+1))
  fi
else
  echo "(no image argument: image checks skipped)"
fi

if [ "$FAILURES" -gt 0 ]; then
  echo "SECRET SCAN FAILED ($FAILURES problem group(s))"
  exit 1
fi
echo "SECRET SCAN OK"
