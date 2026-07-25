# AI CS2 Analyst — deployable container image.
# Runs the FastAPI web app (parser + coach + report). Callout data is baked in
# (callouts/callouts.json), so the CS2 game files are NOT needed on the server.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# deps first (better layer caching)
COPY services/parser/requirements-deploy.txt ./req.txt
RUN pip install -r req.txt

# app code + committed callout data
COPY services/parser ./services/parser
COPY callouts/callouts.json ./callouts/callouts.json

# writable runtime dirs (uploads are ephemeral; data holds the SQLite DB)
RUN mkdir -p uploads data

WORKDIR /app/services/parser
# hosts inject $PORT; bind all interfaces
CMD ["sh", "-c", "uvicorn webapp:app --host 0.0.0.0 --port ${PORT:-8000}"]
