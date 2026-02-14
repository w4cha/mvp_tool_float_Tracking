# Use a single base image for both processes
FROM python:3.11-slim

# Install system dependencies (merged from both your previous Dockerfiles)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ensure you have a requirements.txt in the root that includes:
# flask, sqlalchemy, psycopg2-binary, gunicorn, and any worker deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Make sure your entrypoint script is executable
RUN chmod +x ./flask_app/entrypoint.sh