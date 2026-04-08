#!/bin/bash
set -e

# 1. Applying db migrations
echo "--- [PROCESO] Aplicando migraciones (Alembic) ---"
python -m flask db upgrade

# 2. Run initialization (file is in the current directory now)
echo "Running database initialization..."
python init_db.py

# 2. Start Web Server
# We remove --chdir because we are already in the correct folder (/app)
echo "Starting Web Server..."
exec gunicorn --bind 0.0.0.0:10000 "app:create_app()"