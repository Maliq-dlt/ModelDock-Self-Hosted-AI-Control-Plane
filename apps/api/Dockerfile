FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

COPY apps/api ./
COPY scripts/seed_demo.py scripts/retention.py scripts/evaluation_worker.py ./scripts/
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
