FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIPAS2TAK_OUTPUT_DIR=/data/output \
    LIPAS2TAK_CACHE_DIR=/data/cache

WORKDIR /app
COPY pyproject.toml README.md ./
COPY lipas2tak ./lipas2tak
RUN pip install --no-cache-dir .

COPY config ./config
COPY icons ./icons

RUN useradd --system --uid 10001 lipas && mkdir -p /data && chown lipas /data
USER lipas
VOLUME ["/data"]

# Oletus: ajo heti ja sitten 7 päivän välein. Kertaluonteinen ajo:
#   docker run --rm -v ./data:/data IMAGE run
ENTRYPOINT ["lipas2tak", "--config", "/app/config/config.yaml", "--types", "/app/config/types.yaml"]
CMD ["schedule", "--every-days", "7"]
