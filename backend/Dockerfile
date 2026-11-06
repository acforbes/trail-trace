# --- Build Stage ---
FROM python:3.11-slim AS builder

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Final Runtime Stage ---
FROM python:3.11-slim AS runner

WORKDIR /code

# Force stdin, stdout, and stderr to be totally unbuffered for Cloud Run logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy installed dependencies from builder stage
COPY --from=builder /root/.local /root/.local
COPY ./app /code/app

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/code

EXPOSE 8080

#CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
# Use exec form to bind to Cloud Run's dynamic port
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
#Production Alternative: Gunicorn with Uvicorn Workers
#CMD ["sh", "-c", "exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 --timeout 0 -k uvicorn.workers.UvicornWorker main:app"]
