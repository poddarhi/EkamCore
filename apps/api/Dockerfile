# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir poetry==2.3.2

COPY pyproject.toml poetry.lock* ./

RUN poetry export -f requirements.txt --without-hashes -o requirements.txt && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local

COPY api/ ./api/
COPY alembic/ ./alembic/ 2>/dev/null || true
COPY alembic.ini ./alembic.ini 2>/dev/null || true

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8420

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8420"]
