#!/bin/bash
set -e

echo "Checking for database at $DB_HOST:5432..."

# Wait for Postgres to be ready
until timeout 1 bash -c "cat < /dev/null > /dev/tcp/$DB_HOST/5432" 2>/dev/null; do
  echo "PostgreSQL is not ready yet - waiting 2 seconds..."
  sleep 2
done

echo "Database is UP!"

# Run your DB initialization script
echo "Running init_db.py..."
python init_db.py

# Start the application
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:5000 --workers 2 flask_app.app:app