# PocketScore AI - backend API image
# Build from the repository root:
#   docker build -f backend/Dockerfile -t pocketscore-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POCKETSCORE_ENVIRONMENT=production \
    POCKETSCORE_HOST=0.0.0.0 \
    POCKETSCORE_PORT=8000 \
    POCKETSCORE_STORAGE_DIR=/data/storage \
    POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db

WORKDIR /app

# ffmpeg is shipped by imageio-ffmpeg, but soundfile/librosa benefit from libsndfile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

# Optional: bake the built frontend into the image so a single service can serve both.
COPY frontend/dist ./frontend/dist

RUN mkdir -p /data/storage
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
