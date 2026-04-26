FROM python:3.11-slim

WORKDIR /app

COPY services/orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/orchestrator /app
COPY services/memory /app/services/memory
COPY services/analyst /app/services/analyst
COPY services/router /app/services/router
COPY packages /app/packages

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
