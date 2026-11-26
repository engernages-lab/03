#!/usr/bin/env bash
# Remove ONLY the resources this run created (prefixed with the run id).
# Never prunes globally: the runner may host other jobs' containers/volumes.
#
# Usage: cleanup-test-resources.sh <run-id> [volume-name]
set -uo pipefail

RUN_ID="${1:?run id}"
VOLUME="${2:-}"
PREFIX="pocketscore-c21-${RUN_ID}"

echo "== containers matching ${PREFIX}-* =="
ids=$(docker ps -aq --filter "name=${PREFIX}-" || true)
if [ -n "$ids" ]; then
  # shellcheck disable=SC2086
  docker rm -f $ids >/dev/null || true
  echo "removed containers: $(echo "$ids" | tr '\n' ' ')"
else
  echo "none"
fi

if [ -n "$VOLUME" ]; then
  echo "== volume ${VOLUME} =="
  if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    docker volume rm "$VOLUME" >/dev/null || echo "volume busy, left in place"
    echo "removed volume ${VOLUME}"
  else
    echo "volume absent"
  fi
fi

echo "== remaining pocketscore resources (should be unrelated ones only) =="
docker ps -a --filter "name=pocketscore" --format '{{.Names}}' || true
docker volume ls --filter "name=pocketscore" --format '{{.Name}}' || true
