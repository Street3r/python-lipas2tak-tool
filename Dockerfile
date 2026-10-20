FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIPAS2TAK_OUTPUT_DIR=/data/output \
    LIPAS2TAK_CACHE_DIR=/data/cache

# git + ssh for the publisher (lipas2tak publish)
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY lipas2tak ./lipas2tak
RUN pip install --no-cache-dir .

COPY config ./config
COPY icons ./icons

RUN useradd --system --uid 10001 lipas && mkdir -p /data && chown lipas /data
USER lipas
VOLUME ["/data"]

# Default: weekly on Monday 04:00 Finnish time (runs at start only if a scheduled
# run was missed). One-off run:
#   docker run --rm -v ./data:/data IMAGE run
ENTRYPOINT ["lipas2tak", "--config", "/app/config/config.yaml", "--types", "/app/config/types.yaml"]
CMD ["schedule", "--at", "mon 04:00"]
