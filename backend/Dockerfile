# PocketScore AI - backend API image (Railway / Docker)
# Build from the repository root:
#   docker build -f backend/Dockerfile -t pocketscore-api .
#
# The frontend is built INSIDE the image. Previously the Dockerfile copied a
# pre-built frontend/dist, which only existed on a developer machine or in CI:
# a plain `railway up` (or any clean clone) has no dist and the build died on
# COPY. Building it here keeps the image self-contained.

# ---- stage 1: build the SPA -------------------------------------------------
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS frontend

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
FROM python:3.11-slim@sha256:7032841967d07aa3353905945dc186901c89b6b319c61425f4439f677a4a8a34

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POCKETSCORE_ENVIRONMENT=production \
    POCKETSCORE_HOST=0.0.0.0 \
    POCKETSCORE_STORAGE_DIR=/data/storage \
    POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db \
    POCKETSCORE_MODEL_PRELOAD=true \
    POCKETSCORE_FRONTEND_DIST=/app/frontend/dist

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

# ---- non-root runtime user (V1.1-C.2.3.4.3) --------------------------------
# The application runs as UID/GID 10001. Nothing in the image is group- or
# world-writable: /app stays root-owned and read-only for the app user, and only
# the data mount is writable.
RUN groupadd --system --gid 10001 pocketscore \
    && useradd --system --uid 10001 --gid pocketscore \
       --home-dir /app --shell /usr/sbin/nologin pocketscore

# Data lives on a volume so redeploys never touch user projects. The mount point
# must exist before the platform attaches the volume.
#
# Permissions: 0775 on /data with group pocketscore, NOT 0777. The container runs
# as gid 10001, so it can create /data/storage and /data/backups on a fresh
# volume. An existing Railway volume whose directories are owned by another
# uid/gid is NOT chowned automatically — recursive chown on every boot is exactly
# the pattern this phase forbids. See docs/operations for the one-off migration
# options and the isolated-volume evidence.
#
# NOTE: no `VOLUME ["/data"]` instruction here on purpose. Railway validates the
# Dockerfile and rejects it ("docker VOLUME is not supported, use Railway
# Volumes"), because the platform attaches volumes itself. Locally and in CI the
# volume is attached explicitly with `-v <name>:/data`, so nothing depends on the
# instruction.
RUN mkdir -p /data/storage /data/backups \
    && chown -R 10001:10001 /data \
    && chmod 0775 /data /data/storage /data/backups

# A writable tmp for the streaming upload path; mounted tmpfs in hardened runs.
# NUMBA_CACHE_DIR and HOME point here too: librosa/numba compile JIT kernels on
# first use and cache them under $HOME. As uid 10001 with a root-owned /app that
# write fails inside the inference thread, which surfaces as a reset connection
# instead of a clean error (run 46151659085).
RUN mkdir -p /app/tmp/numba /app/tmp/mpl \
    && chown -R 10001:10001 /app/tmp \
    && chmod 0700 /app/tmp

ENV TMPDIR=/app/tmp \
    HOME=/app/tmp \
    NUMBA_CACHE_DIR=/app/tmp/numba \
    MPLCONFIGDIR=/app/tmp/mpl \
    POCKETSCORE_BACKUP_DIR=/data/backups

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request,sys; port=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status == 200 else 1)"

# Railway injects PORT; local runs fall back to 8000. `exec` keeps PID 1 as
# uvicorn so SIGTERM triggers the graceful shutdown path.
#
# Proxy trust: uvicorn may only rewrite the client address from X-Forwarded-For
# when the peer is a trusted proxy. `POCKETSCORE_TRUSTED_PROXY_IPS` defaults to
# loopback; deploying behind a platform edge that forwards from a private range
# means setting it explicitly (e.g. 10.0.0.0/8). `*` is never the default, because
# that would let any client forge an IP and bypass API rate limiting.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --timeout-graceful-shutdown 25 --proxy-headers --forwarded-allow-ips=\"${POCKETSCORE_TRUSTED_PROXY_IPS:-127.0.0.1}\""]
