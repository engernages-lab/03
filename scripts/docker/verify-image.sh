#!/usr/bin/env bash
# Inspect the built image: dependencies, model backend, ffmpeg, frontend bundle.
# A docker build exit 0 does not prove the image can actually transcribe, and a
# heredoc piped into `docker run` without -i would silently assert nothing, so
# both are handled explicitly here.
set -euo pipefail

IMAGE="${1:?usage: verify-image.sh <image>}"
OUT="${OUT_DIR:-docker-verification}"
mkdir -p "$OUT"

echo "== image =="
docker image inspect "$IMAGE" --format '{{.Id}} {{.Size}} {{.Created}}' | tee "$OUT/image-info.txt"
docker image ls "$IMAGE" --format 'image={{.Repository}}:{{.Tag}} size={{.Size}}'

echo "== layer sizes (top 12) =="
docker history "$IMAGE" --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' 2>/dev/null \
  | sort -h -r | head -12 | tee -a "$OUT/image-info.txt" || true

# NOTE: -i is mandatory: without it python receives an empty stdin and every
# assertion below would pass vacuously.
echo "== python + dependency probe =="
docker run --rm -i --entrypoint python "$IMAGE" - <<'PY' | tee "$OUT/build-info.json"
import importlib.metadata as md
import importlib.util
import json
import sys


def version(name):
    try:
        return md.version(name)
    except Exception:
        return None


report = {
    "python": sys.version.split()[0],
    "platform": sys.platform,
    "onnxruntime": version("onnxruntime"),
    "basic_pitch": version("basic-pitch"),
    "numpy": version("numpy"),
    "librosa": version("librosa"),
    "soundfile": version("soundfile"),
    "imageio_ffmpeg": version("imageio-ffmpeg"),
    "fastapi": version("fastapi"),
    "uvicorn": version("uvicorn"),
    "tensorflow_present": importlib.util.find_spec("tensorflow") is not None,
}
print(json.dumps(report, indent=2))
PY

if ! grep -q '"python"' "$OUT/build-info.json"; then
  echo "::error::dependency probe produced no output - stdin was not delivered to the container"
  exit 1
fi

echo "== hard assertions =="
docker run --rm -i --entrypoint python "$IMAGE" - <<'PY'
import importlib.util
import pathlib
import shutil
import sys

failures = []

if sys.version_info < (3, 10):
    failures.append(f"python too old: {sys.version}")

if importlib.util.find_spec("onnxruntime") is None:
    failures.append("onnxruntime missing")
if importlib.util.find_spec("basic_pitch") is None:
    failures.append("basic_pitch missing")
if importlib.util.find_spec("tensorflow") is not None:
    failures.append("tensorflow leaked into the image (image bloat, wrong backend)")

import basic_pitch

onnx = pathlib.Path(basic_pitch.__file__).parent / "saved_models" / "icassp_2022" / "nmp.onnx"
if not onnx.is_file():
    failures.append(f"model file missing: {onnx}")

import imageio_ffmpeg

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
if not ffmpeg or not pathlib.Path(ffmpeg).exists():
    failures.append("ffmpeg binary missing")

if shutil.which("python") is None:
    failures.append("python not on PATH")

dist = pathlib.Path("/app/frontend/dist")
if not (dist / "index.html").is_file():
    failures.append(f"frontend bundle missing at {dist}")

for module in ("app.main", "app.services.audio.model_manager", "app.services.audio.inference_limiter"):
    try:
        __import__(module)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"import {module} failed: {type(exc).__name__}: {exc}")

if failures:
    print("IMAGE VERIFY FAILED")
    for item in failures:
        print(" -", item)
    raise SystemExit(1)

print("IMAGE ASSERTIONS OK: python", sys.version.split()[0], "| model", onnx.name, "| ffmpeg", pathlib.Path(ffmpeg).name)
PY

echo "== dependency consistency =="
# basic-pitch 0.4.0 declares tensorflow for Linux+py3.11. This project runs the
# ONNX graph on purpose, so that single declared edge is expected to be missing.
# Every other inconsistency is a real failure.
set +e
docker run --rm --entrypoint python "$IMAGE" -m pip check > "$OUT/dependency-audit-raw.txt" 2>&1
PIP_RC=$?
set -e
cat "$OUT/dependency-audit-raw.txt"

if [ "$PIP_RC" -ne 0 ]; then
  # keep only the intentionally unsatisfied edge
  other=$(grep -viE 'basic-pitch.*(tensorflow|tensorflow-macos|tflite-runtime|coremltools)' \
            "$OUT/dependency-audit-raw.txt" | grep -vE '^\s*$' || true)
  if [ -n "$other" ]; then
    echo "::error::unexpected dependency inconsistency:"
    echo "$other"
    exit 1
  fi
  echo "dependency check: only the intentional basic-pitch/tensorflow edge is unsatisfied (ONNX backend by design)"
else
  echo "dependency check: pip check clean"
fi

{
  echo "pip check rc=${PIP_RC}"
  echo "--- intentional exception: basic-pitch declares tensorflow on linux/py3.11; this image runs nmp.onnx via onnxruntime ---"
  cat "$OUT/dependency-audit-raw.txt"
} > "$OUT/dependency-audit.txt"

echo "verify-image: OK"
