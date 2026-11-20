# syntax=docker/dockerfile:1.7
# Production image for the MediCore AI API. Build context: project root.
#   docker build -f backend/Dockerfile -t medicore-api .
# Requires the offline pipeline outputs to exist: models/ (risk model, segmentation, RAG index)
# and data/processed/eda_report.json.

# ---------------------------------------------------------------- builder: wheels + embedding model
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r /tmp/requirements.txt
# Bake the embedding model into the image so production never downloads it at runtime
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH HF_HOME=/opt/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    MODELS_DIR=/app/models DATA_DIR=/app/data APP_ENV=production LOG_FORMAT=json \
    WEB_CONCURRENCY=2 PORT=8000
# tesseract: OCR for scanned reports; libgomp: XGBoost/FAISS; curl: healthcheck
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgomp1 curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 appuser
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf
WORKDIR /app
COPY --chown=appuser src ./src
COPY --chown=appuser models ./models
COPY --chown=appuser data/processed/eda_report.json ./data/processed/eda_report.json
COPY --chown=appuser backend ./backend
USER appuser
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1
# Migrations run in a separate one-shot step (see docker-compose.yml) so multiple replicas never race.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*' --no-server-header --timeout-keep-alive 30"]
