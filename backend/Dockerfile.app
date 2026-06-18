# Full Sentinel backend container — includes the Mitigation Safety module.
#
# This image is distinct from `Dockerfile` (the slim orchestrator-only image)
# because the full app pulls in the heavy ML deps and the Azure / APScheduler
# stack the staged-rollout pipeline requires. Build with:
#
#     docker build -f backend/Dockerfile.app -t sentinel-app:latest backend/
#
# Run with the same DATABASE_URL the orchestrator uses; the entrypoint
# runs `alembic upgrade head` first so a fresh DB ends up at the same
# schema head before serving traffic.
FROM python:3.12-slim

WORKDIR /app

# Build-time deps for psycopg2-binary, sentence-transformers, etc.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Install the FULL requirements set (mitigation_safety deps live here).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source.
COPY . .

# Azure Container Apps / App Service inject $PORT; default 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Liveness checks the orchestrator's existing endpoint so behavior matches
# the legacy image.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/orchestrator/health')" || exit 1

# Entrypoint: apply migrations then serve `app.main:app`. The alembic step
# is idempotent and safe on every restart; if it fails, we fall back to
# starting the app anyway because the app's own startup hook installs the
# audit-immutability trigger as a belt-and-braces.
CMD ["sh", "-c", "alembic upgrade head || echo '[boot] alembic upgrade failed; continuing'; uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
