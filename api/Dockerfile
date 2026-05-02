FROM python:3.11-slim

WORKDIR /app

# curl: used by the compose healthcheck.
# docker.io: provides the docker CLI for the POST /ingest convenience endpoint.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
