# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (see compose.yaml) so the shared library at
# ./shared is available. Build via: docker compose build order-service
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install the shared contracts library (editable).
COPY shared /shared
RUN pip install --no-cache-dir -e /shared

COPY order-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY order-service/ .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
