FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set Chile Timezone
ENV TZ=America/Santiago
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Copy and install local requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from the worker folder into /app
COPY . .

# Run unbuffered so logs appear in real-time
CMD ["python", "-u", "wialon.py"]