# API Syncron : image légère, utilisateur non root, migrations au démarrage.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY deploy/requirements-server.txt /app/requirements-server.txt
RUN pip install -r /app/requirements-server.txt

COPY src/syncron_core /app/src/syncron_core
COPY src/syncron_server /app/src/syncron_server

RUN useradd --create-home --uid 10001 syncron && mkdir -p /data/media && chown -R syncron /data
USER syncron

ENV SYNCRON_MEDIA_DIR=/data/media
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"
CMD ["python", "-m", "syncron_server"]
