#!/bin/bash
set -e

echo "==> Waiting for database to be ready..."

# Create the 'contra' database if it doesn't exist
python -c "
import pymssql, os
from urllib.parse import urlparse, unquote

url = os.environ.get('DATABASE_URL', '')
parsed = urlparse(url)
host = parsed.hostname or 'localhost'
port = parsed.port or 1433
user = unquote(parsed.username or 'sa')
password = unquote(parsed.password or '')
db_name = (parsed.path or '/contra').lstrip('/')

conn = pymssql.connect(server=host, port=port, user=user, password=password)
conn.autocommit(True)
cursor = conn.cursor()
cursor.execute('SELECT name FROM sys.databases WHERE name = %s', (db_name,))
if not cursor.fetchone():
    print(f'==> Creating database {db_name}...')
    cursor.execute(f'CREATE DATABASE [{db_name}]')
    print(f'==> Database {db_name} created.')
else:
    print(f'==> Database {db_name} already exists.')
conn.close()
"

echo "==> Running Alembic migrations..."
cd /app && alembic upgrade head

echo "==> Starting Contra backend..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
