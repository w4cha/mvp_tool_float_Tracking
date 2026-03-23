FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install local requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from flask_app/ into the container /app
COPY . .

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

# Start the app
ENTRYPOINT ["./entrypoint.sh"]