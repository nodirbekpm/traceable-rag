FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependencies first: this layer is rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim

# Named volumes inherit this ownership on first mount.
RUN useradd --create-home --uid 1000 anchor \
    && mkdir -p /data/raw /models \
    && chown anchor:anchor /data/raw /models
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/models

USER anchor
EXPOSE 8000
CMD ["uvicorn", "anchor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
