FROM python:3.11-slim

WORKDIR /app
COPY services/retrieval-api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/retrieval-api/app /app/app
COPY data/knowledge /app/data/knowledge
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

