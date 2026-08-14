FROM python:3.13-slim

ARG PROJECT_VERSION=dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROJECT_VERSION=$PROJECT_VERSION \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

# Install dependencies (cached) before copying the source.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY assets/ ./assets/
COPY fixtures/ ./fixtures/
COPY manage.py ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Collect + hash + compress static assets into /app/staticfiles (served by WhiteNoise).
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
