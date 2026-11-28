FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-deploy.txt \
    && useradd --system --uid 10001 --no-create-home appuser
COPY app.py db.py ./
COPY services ./services
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts
USER 10001:10001
EXPOSE 8000
# One worker preserves the local-only in-memory limiter's meaning.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--access-logfile", "-", "app:create_app()"]
