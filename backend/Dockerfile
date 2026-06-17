# Container image for the Orchestration Agent API (WBS F-11 pattern).
# Builds ONLY the lightweight orchestrator server -- no heavy ML deps.
FROM python:3.12-slim

WORKDIR /app

# Install slim deps first (better layer caching)
COPY requirements-orchestrator.txt .
RUN pip install --no-cache-dir -r requirements-orchestrator.txt

# Copy the backend app code
COPY . .

# Azure Container Apps / App Service inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Health check hits the orchestrator's health endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/orchestrator/health')" || exit 1

CMD ["sh", "-c", "uvicorn orchestrator_server:app --host 0.0.0.0 --port ${PORT}"]
