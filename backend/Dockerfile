FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies for pymssql
RUN apt-get update && \
    apt-get install -y --no-install-recommends bash gcc g++ freetds-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
