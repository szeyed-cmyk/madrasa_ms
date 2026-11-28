# Madrasa Pro 1.0.8 - container image. Build from the archive root:  docker build -t madrasa-pro .
# Base: latest Python 3.12 patch (3.12.16-slim), pinned by multi-arch index digest. Rebuild regularly.
FROM python:3.12.16-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_PATH=/app/data/madrasa.db

WORKDIR /app

# Pinned, hash-checked dependencies first (better layer caching).
COPY ["Madrasa Admin Project/requirements.lock", "/app/requirements.lock"]
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

# Only the application folder goes into /app (main.py, app/, templates/, static/ incl. the prebuilt
# static/app.css and static/vendor/alpine.min.js, sample/). .dockerignore keeps data/*, *.db,
# .secret_key, .env and caches out. There is no landing page: "/" is the application home.
COPY ["Madrasa Admin Project/", "/app/"]

# SQLite database, backups and the generated secret key live in /app/data (the app also creates the
# folder itself). Mount a volume/disk there (docker-compose.yml and render.yaml do).
RUN mkdir -p /app/data && rm -f /app/data/.secret_key /app/data/*.db

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1

# main.py reads HOST and PORT from the environment.
CMD ["python", "main.py"]
