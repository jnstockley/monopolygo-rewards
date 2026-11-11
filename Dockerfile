FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.15.2-slim-bookworm AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.15.2-slim-bookworm AS runtime
ARG VERSION=0.1.0
LABEL org.opencontainers.image.title="monopolygo-rewards" \
      org.opencontainers.image.description="Single-account free daily rewards worker" \
      org.opencontainers.image.version="${VERSION}"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    DATA_DIR=/app/data ARTIFACT_DIR=/app/artifacts HEADLESS=true
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && /app/.venv/bin/python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 rewards \
    && useradd --uid 10001 --gid rewards --create-home rewards \
    && mkdir -p /app/data /app/artifacts /app/logs \
    && chown -R rewards:rewards /app/data /app/artifacts /app/logs \
    && chmod -R a+rX /opt/playwright
USER rewards
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD ["monopolygo-rewards", "healthcheck"]
ENTRYPOINT ["monopolygo-rewards"]
