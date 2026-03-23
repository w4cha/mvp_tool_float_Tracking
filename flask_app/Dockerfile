FROM python:3.11-slim

RUN apt-get update && apt-get install -y libpq-dev gcc tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# This looks for requirements.txt INSIDE the flask_app folder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# This copies EVERYTHING from flask_app into /app (including init_db.py)
COPY . .

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]