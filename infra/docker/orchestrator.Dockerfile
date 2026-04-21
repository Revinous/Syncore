FROM python:3.11-slim

WORKDIR /app

COPY services/orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/orchestrator /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

