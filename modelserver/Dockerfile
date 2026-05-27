FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY artifacts/ ./artifacts/

EXPOSE 8001

CMD ["uv", "run", "--frozen", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
