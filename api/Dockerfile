# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir uv==0.4.*

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Non-root user for security
RUN addgroup --system concierge && adduser --system --ingroup concierge concierge

# Copy only the installed packages from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application code (no torch, no notebooks, no tests)
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY main.py ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER concierge

EXPOSE 8000

# Run Alembic migration then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
