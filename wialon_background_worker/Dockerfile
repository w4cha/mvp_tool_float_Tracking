FROM python:3.11-slim
WORKDIR /app
COPY wialon_background_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wialon_background_worker/ .
COPY models.py .
ENV PYTHONPATH="/app"
CMD ["python", "-u", "wialon.py"]