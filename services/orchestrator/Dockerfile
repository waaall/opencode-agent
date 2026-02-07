FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/orchestrator/pyproject.toml /app/pyproject.toml
COPY services/orchestrator/README.md /app/README.md
COPY services/orchestrator/app /app/app
COPY services/orchestrator/migrations /app/migrations

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

