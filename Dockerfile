FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Pillow needs these at runtime for JPEG/PNG/WebP; the -dev headers are not
# required because we install wheels rather than building from source.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g libwebp7 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependencies first: application code changes far more often than the
# dependency set, and this keeps the expensive layer cached across rebuilds.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-deps .

# Runs unprivileged. The data volume is chowned in the entrypoint because its
# ownership is decided by the host mount, not by this image.
RUN useradd --system --create-home --uid 10001 cram
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8085/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085", "--workers", "4"]
