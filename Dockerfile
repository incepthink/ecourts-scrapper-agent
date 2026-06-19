# Python 3.12 — ddddocr/onnxruntime have no 3.13+ wheels yet.
FROM python:3.12-slim

# System libs needed by opencv/onnxruntime (pulled in by ddddocr).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Default command runs the API; the worker service overrides it (see render.yaml):
#   web:    uvicorn api:app --host 0.0.0.0 --port $PORT
#   worker: rq worker -u $REDIS_URL scrapes
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
