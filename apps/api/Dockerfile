# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir poetry==2.3.2 poetry-plugin-export==1.10.0

COPY pyproject.toml poetry.lock* ./

RUN poetry export -f requirements.txt --without-hashes -o requirements.txt

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY api/ ./api/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8420

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8420"]
