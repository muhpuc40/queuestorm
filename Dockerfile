# QueueStorm Investigator — lightweight, no GPU, no baked secrets.
# Final image is well under the 500MB recommended size.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY app ./app
COPY sample_output.json ./sample_output.json

# Run as a non-root user.
RUN useradd -m appuser
USER appuser

EXPOSE 8000

# Bind to 0.0.0.0 so the judge harness can reach it. Honour $PORT if overridden.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
