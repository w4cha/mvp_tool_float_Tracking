#!/bin/bash
set -e

# Initialize the database schema (tables, etc.)
echo "Running database initialization..."
python flask_app/init_db.py

# Start the Flask app with Gunicorn
# --bind 0.0.0.0:$PORT tells Gunicorn to use Render's dynamic port
# --chdir flask_app enters your app folder before running
echo "Starting Web Server..."
exec gunicorn --bind 0.0.0.0:10000--chdir ./flask_app app:app