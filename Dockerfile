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

# Build-time only; nothing at runtime calls it.
COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /usr/local/bin/uv

# Dependencies first: application code changes far more often than the
# dependency set, and this keeps the expensive layer cached across rebuilds.
#
# From uv.lock, hash-checked, rather than resolved at build time. Resolving
# here meant the image got whatever the transitive packages were that day —
# not what CI had tested — and a rebuild months apart could differ silently.
COPY pyproject.toml uv.lock README.md ./
RUN uv export --locked --no-emit-project -o /tmp/requirements.txt \
 && uv pip install --system --require-hashes -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
RUN uv pip install --system --no-deps .

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
# One worker, and the reason is the rate limiter rather than performance.
#
# The limiter counts in memory, so four workers meant four independent
# counters and an effective limit of four times whatever the setting said.
# A bound that still holds but whose number is wrong is worse than a smaller
# bound that is right: the next person to tune it is tuning a fiction.
#
# The throughput given up was never needed. The load here is a handful of
# teachers uploading a stack of papers after class, and every request is a
# short database write — not the shape that wants four processes.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085", "--workers", "1"]
