# PocketScore AI - backend API image (Railway / Docker)
# Build from the repository root:
#   docker build -f backend/Dockerfile -t pocketscore-api .
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
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

# Optional: bake the built frontend into the image so one service can serve both.
COPY frontend/dist ./frontend/dist

# Data lives on a volume so redeploys never touch user projects.
RUN mkdir -p /data/storage && chmod 0777 /data

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request,sys; port=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status == 200 else 1)"

# Railway injects PORT; local runs fall back to 8000. `exec` keeps PID 1 as
# uvicorn so SIGTERM triggers the graceful shutdown path.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --timeout-graceful-shutdown 25 --proxy-headers --forwarded-allow-ips='*'"]
