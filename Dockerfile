FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV FLASK_ENV=production
ENV TZ=America/Santiago

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# We run the init script (inside flask_app) then start supervisor
CMD python -m flask_app.init_db && supervisord -c supervisord.conf