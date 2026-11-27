# PocketScore AI - backend API image (Railway / Docker)
# Build from the repository root:
#   docker build -f backend/Dockerfile -t pocketscore-api .
#
# The frontend is built INSIDE the image. Previously the Dockerfile copied a
# pre-built frontend/dist, which only existed on a developer machine or in CI:
# a plain `railway up` (or any clean clone) has no dist and the build died on
# COPY. Building it here keeps the image self-contained.

# ---- stage 1: build the SPA -------------------------------------------------
FROM node:20-slim AS frontend

WORKDIR /web

# Lockfile-only install first so dependency layers cache independently of source.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./

# The backend serves the bundle at the origin root (/assets, /index.html), while
# GitHub Pages serves it under /03/. Default to "/" so the containerised SPA can
# actually load its own assets; pass /03/ only when building for Pages.
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build && test -f dist/index.html

# ---- stage 2: runtime -------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POCKETSCORE_ENVIRONMENT=production \
    POCKETSCORE_HOST=0.0.0.0 \
    POCKETSCORE_STORAGE_DIR=/data/storage \
    POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db \
    POCKETSCORE_MODEL_PRELOAD=true

WORKDIR /app

# ffmpeg is shipped by imageio-ffmpeg (no system ffmpeg needed); soundfile and
# librosa do need libsndfile at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-model.txt ./requirements-model.txt
# The model package is installed WITHOUT its declared deps: on Linux + Python
# 3.11 basic-pitch asks for tensorflow (~600 MB) although this project runs the
# bundled nmp.onnx through onnxruntime. Its non-TF closure is in requirements.txt.
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install --no-deps -r requirements-model.txt \
    && python -c "import basic_pitch, onnxruntime; print('basic_pitch + onnxruntime OK')" \
    && python -c "import importlib.util as u; assert u.find_spec('tensorflow') is None, 'TensorFlow leaked into the image'"

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

# One service serves both the API and the SPA.
COPY --from=frontend /web/dist ./frontend/dist

# Data lives on a volume so redeploys never touch user projects. The mount point
# must exist and be writable before the platform attaches the volume.
#
# NOTE: no `VOLUME ["/data"]` instruction here on purpose. Railway validates the
# Dockerfile and rejects it ("docker VOLUME is not supported, use Railway
# Volumes"), because the platform attaches volumes itself. Locally and in CI the
# volume is attached explicitly with `-v <name>:/data`, so nothing depends on the
# instruction.
RUN mkdir -p /data/storage && chmod 0777 /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request,sys; port=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status == 200 else 1)"

# Railway injects PORT; local runs fall back to 8000. `exec` keeps PID 1 as
# uvicorn so SIGTERM triggers the graceful shutdown path.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --timeout-graceful-shutdown 25 --proxy-headers --forwarded-allow-ips='*'"]
