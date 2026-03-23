FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies for pymssql
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ freetds-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
