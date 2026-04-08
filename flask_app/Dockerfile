FROM python:3.11-slim
WORKDIR /app
# We must now specify the subfolder
COPY flask_app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy the files from the folder
COPY flask_app/ .
COPY models.py .
COPY migrations/ migrations/
ENV PYTHONPATH="/app"
ENV FLASK_APP="flask_app/app.py:create_app()"
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]